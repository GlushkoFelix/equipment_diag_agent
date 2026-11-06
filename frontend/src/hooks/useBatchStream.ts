import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type BatchRowSummary, type BatchTaskSummary } from '../api/client'

export type BatchConnection = 'idle' | 'connecting' | 'open' | 'retrying' | 'polling' | 'closed'

const BATCH_TERMINAL = new Set(['completed', 'partially_failed', 'failed', 'cancelled', 'timed_out'])

export function useBatchStream(options: { onTerminal?: (batch: BatchTaskSummary) => void }) {
  const [batch, setBatch] = useState<BatchTaskSummary | null>(null)
  const [rows, setRows] = useState<BatchRowSummary[]>([])
  const [connection, setConnection] = useState<BatchConnection>('idle')
  const sourceRef = useRef<EventSource | null>(null)
  const idRef = useRef<string | null>(null)
  const terminalRef = useRef(false)
  const failureRef = useRef(0)
  const pollRef = useRef<number | null>(null)
  const callbacksRef = useRef(options)
  callbacksRef.current = options

  const loadRows = useCallback(async (id: string) => {
    try {
      const page = await api.getBatchRows(id, 1, 100)
      setRows(page.items)
    } catch {
      // rows can be refreshed later; stream remains authoritative for task state
    }
  }, [])

  const close = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(
    (id: string) => {
      if (pollRef.current !== null) return
      setConnection('polling')
      pollRef.current = window.setInterval(async () => {
        try {
          const next = await api.getBatch(id)
          setBatch(next)
          await loadRows(id)
          if (BATCH_TERMINAL.has(next.status)) {
            stopPolling()
            setConnection('closed')
            callbacksRef.current.onTerminal?.(next)
          }
        } catch {
          // keep polling; auth and 404 states are surfaced by the REST layer
        }
      }, 2000)
    },
    [loadRows, stopPolling],
  )

  const start = useCallback(
    (id: string) => {
      close()
      stopPolling()
      failureRef.current = 0
      terminalRef.current = false
      idRef.current = id
      setConnection('connecting')
      setRows([])
      void api.getBatch(id).then(setBatch).catch(() => undefined)
      void loadRows(id)

      const source = new EventSource(`/api/v1/batches/${id}/events`, { withCredentials: true })
      sourceRef.current = source
      source.onopen = () => {
        failureRef.current = 0
        setConnection('open')
      }
      source.onerror = () => {
        if (terminalRef.current) return
        failureRef.current += 1
        setConnection('retrying')
        if (failureRef.current >= 3) {
          close()
          startPolling(id)
        }
      }

      source.addEventListener('batch_snapshot', (event) => {
        const envelope = JSON.parse((event as MessageEvent).data) as { payload: BatchTaskSummary }
        setBatch(envelope.payload)
        void loadRows(id)
        if (BATCH_TERMINAL.has(envelope.payload.status)) {
          terminalRef.current = true
          close()
          setConnection('closed')
        }
      })
      source.addEventListener('batch_progress', (event) => {
        const envelope = JSON.parse((event as MessageEvent).data) as {
          payload: { counts: BatchTaskSummary['counts']; completed_rows: number; total_rows: number; progress: number }
        }
        setBatch((current) =>
          current
            ? {
                ...current,
                counts: envelope.payload.counts,
                completed_rows: envelope.payload.completed_rows,
                total_rows: envelope.payload.total_rows,
                progress: envelope.payload.progress,
              }
            : current,
        )
      })
      source.addEventListener('row_status', (event) => {
        const envelope = JSON.parse((event as MessageEvent).data) as { payload: BatchRowSummary }
        setRows((current) => {
          const index = current.findIndex((row) => row.row_id === envelope.payload.row_id)
          if (index < 0) return [...current, envelope.payload]
          const next = [...current]
          next[index] = envelope.payload
          return next
        })
      })
      source.addEventListener('batch_status', (event) => {
        const envelope = JSON.parse((event as MessageEvent).data) as {
          payload: { status: BatchTaskSummary['status']; counts: BatchTaskSummary['counts']; finished_at: string | null; cancel_requested: boolean; error_code: string | null }
        }
        setBatch((current) =>
          current
            ? {
                ...current,
                status: envelope.payload.status,
                counts: envelope.payload.counts,
                finished_at: envelope.payload.finished_at,
                cancel_requested: envelope.payload.cancel_requested,
                error_code: envelope.payload.error_code,
              }
            : current,
        )
        if (BATCH_TERMINAL.has(envelope.payload.status)) {
          terminalRef.current = true
          close()
          setConnection('closed')
          void loadRows(id)
          void api.getBatch(id).then((next) => {
            setBatch(next)
            callbacksRef.current.onTerminal?.(next)
          })
        }
      })
    },
    [close, loadRows, startPolling, stopPolling],
  )

  const stop = useCallback(() => {
    terminalRef.current = true
    close()
    stopPolling()
    setConnection('closed')
  }, [close, stopPolling])

  const clear = useCallback(() => {
    stop()
    idRef.current = null
    setBatch(null)
    setRows([])
    setConnection('idle')
  }, [stop])

  const refresh = useCallback(async () => {
    const id = idRef.current
    if (!id) return
    try {
      const next = await api.getBatch(id)
      setBatch(next)
      await loadRows(id)
    } catch {
      // ignore and let the user refresh manually
    }
  }, [loadRows])

  useEffect(
    () => () => {
      terminalRef.current = true
      close()
      stopPolling()
    },
    [close, stopPolling],
  )

  return { batch, setBatch, rows, setRows, connection, start, stop, clear, refresh }
}
