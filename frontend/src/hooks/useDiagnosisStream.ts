import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type DiagnosisSnapshot } from '../api/client'

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'retrying' | 'polling' | 'closed'

export type StepView = {
  seq?: number | null
  node: string
  phase: string
  rule_id?: string | null
  summary?: string | null
  duration_ms?: number | null
  occurred_at?: string
}

type SseEnvelope = {
  seq: number | null
  type: string
  occurred_at: string
  revision: number | null
  payload: Record<string, unknown>
}

const TERMINAL = new Set(['succeeded', 'degraded', 'degraded_review', 'aborted', 'failed', 'failed_timeout', 'expired'])

const DIAGNOSIS_EVENTS = ['snapshot', 'step', 'status', 'interrupt', 'report', 'expired', 'error', 'heartbeat'] as const

export function isTerminalStatus(status: string | null | undefined) {
  return !!status && TERMINAL.has(status)
}

export function stepsFromSnapshot(snapshot: DiagnosisSnapshot): StepView[] {
  return (snapshot.trace_steps ?? []).map((step) => ({
    node: step.node,
    phase: step.event,
    rule_id: step.rule_id,
    summary: step.summary,
    duration_ms: step.duration_ms,
    occurred_at: step.created_at,
  }))
}

export function useDiagnosisStream(options: {
  onInterrupt?: (snapshot: DiagnosisSnapshot) => void
  onTerminal?: (snapshot: DiagnosisSnapshot) => void
  onDomainError?: (payload: Record<string, unknown>) => void
}) {
  const [diagnosisId, setDiagnosisId] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<DiagnosisSnapshot | null>(null)
  const [steps, setSteps] = useState<StepView[]>([])
  const [connection, setConnection] = useState<ConnectionState>('idle')
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [failures, setFailures] = useState(0)

  const sourceRef = useRef<EventSource | null>(null)
  const pollRef = useRef<number | null>(null)
  const pollSuccessRef = useRef(0)
  const failureRef = useRef(0)
  const lastSeqRef = useRef(-1)
  const terminalRef = useRef(false)
  const idRef = useRef<string | null>(null)
  const callbacksRef = useRef(options)

  callbacksRef.current = options

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
    pollSuccessRef.current = 0
  }, [])

  const closeSource = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
  }, [])

  const refresh = useCallback(async () => {
    const id = idRef.current
    if (!id) return null
    try {
      const next = await api.getDiagnosis(id)
      setSnapshot(next)
      setLastUpdated(new Date().toISOString())
      if (next.trace_steps?.length) setSteps(stepsFromSnapshot(next))
      if (next.status === 'waiting_human') callbacksRef.current.onInterrupt?.(next)
      return next
    } catch {
      return null
    }
  }, [])

  const stop = useCallback(() => {
    terminalRef.current = true
    closeSource()
    stopPolling()
    setConnection('closed')
    setDiagnosisId(null)
    idRef.current = null
  }, [closeSource, stopPolling])

  const startPolling = useCallback(
    (id: string) => {
      if (pollRef.current !== null) return
      setConnection('polling')
      pollRef.current = window.setInterval(async () => {
        try {
          const next = await api.getDiagnosis(id)
          pollSuccessRef.current += 1
          setSnapshot(next)
          setLastUpdated(new Date().toISOString())
          if (next.trace_steps?.length) setSteps(stepsFromSnapshot(next))
          if (isTerminalStatus(next.status)) {
            stopPolling()
            setConnection('closed')
            callbacksRef.current.onTerminal?.(next)
            return
          }
          if (pollSuccessRef.current >= 5) {
            stopPolling()
            startEventSourceRef.current?.(id)
          }
        } catch {
          // keep polling; session/auth errors are surfaced by the global fetch layer
        }
      }, 2000)
    },
    [stopPolling],
  )

  const startEventSourceRef = useRef<(id: string) => void>(() => {})

  const startEventSource = useCallback(
    (id: string) => {
      closeSource()
      setConnection('connecting')
      const source = new EventSource(`/api/v1/diagnoses/${id}/events`, { withCredentials: true })
      sourceRef.current = source

      source.onopen = () => {
        failureRef.current = 0
        setFailures(0)
        setConnection('open')
        setLastUpdated(new Date().toISOString())
      }

      source.onerror = () => {
        if (terminalRef.current) return
        failureRef.current += 1
        setFailures(failureRef.current)
        setConnection('retrying')
        if (failureRef.current >= 3) {
          closeSource()
          setConnection('polling')
          startPolling(id)
        }
      }

      const handle = (event: MessageEvent) => {
        let envelope: SseEnvelope
        try {
          envelope = JSON.parse(event.data) as SseEnvelope
        } catch {
          return
        }
        setLastUpdated(new Date().toISOString())

        if (envelope.type === 'heartbeat') return

        if (envelope.type === 'snapshot') {
          const next = envelope.payload as unknown as DiagnosisSnapshot
          if (!next?.diagnosis_id) return
          terminalRef.current = isTerminalStatus(next.status)
          lastSeqRef.current = envelope.seq ?? -1
          setSnapshot(next)
          setSteps(stepsFromSnapshot(next))
          if (next.status === 'waiting_human') callbacksRef.current.onInterrupt?.(next)
          if (terminalRef.current) {
            closeSource()
            setConnection('closed')
          }
          return
        }

        if (envelope.seq !== null && envelope.seq !== undefined) {
          if (envelope.seq <= lastSeqRef.current) return
          lastSeqRef.current = envelope.seq
        }

        if (envelope.type === 'step') {
          const payload = envelope.payload as {
            node: string
            phase: string
            rule_id?: string | null
            summary?: string | null
            duration_ms?: number | null
          }
          setSteps((current) => [
            ...current,
            {
              seq: envelope.seq,
              node: payload.node,
              phase: payload.phase,
              rule_id: payload.rule_id,
              summary: payload.summary,
              duration_ms: payload.duration_ms,
              occurred_at: envelope.occurred_at,
            },
          ])
          return
        }

        if (envelope.type === 'status') {
          const payload = envelope.payload as { to?: string }
          setSnapshot((current) =>
            current
              ? { ...current, status: (payload.to as DiagnosisSnapshot['status']) ?? current.status }
              : current,
          )
          if (payload.to && isTerminalStatus(payload.to)) {
            terminalRef.current = true
            closeSource()
            setConnection('closed')
            window.setTimeout(async () => {
              const next = await refresh()
              if (next) callbacksRef.current.onTerminal?.(next)
            }, 120)
          } else {
            void refresh()
          }
          return
        }

        if (envelope.type === 'interrupt') {
          void refresh().then((next) => {
            if (next) callbacksRef.current.onInterrupt?.(next)
          })
          return
        }

        if (envelope.type === 'report') {
          void refresh()
          return
        }

        if (envelope.type === 'expired') {
          void refresh()
          return
        }

        if (envelope.type === 'error') {
          callbacksRef.current.onDomainError?.(envelope.payload)
          void refresh()
        }
      }

      for (const type of DIAGNOSIS_EVENTS) source.addEventListener(type, handle as EventListener)
    },
    [closeSource, refresh, startPolling],
  )

  startEventSourceRef.current = startEventSource

  const start = useCallback(
    (id: string) => {
      if (idRef.current === id && sourceRef.current) return
      terminalRef.current = false
      failureRef.current = 0
      pollSuccessRef.current = 0
      lastSeqRef.current = -1
      stopPolling()
      closeSource()
      idRef.current = id
      setDiagnosisId(id)
      setSnapshot(null)
      setSteps([])
      setFailures(0)
      void refresh().then(() => startEventSource(id))
    },
    [closeSource, refresh, startEventSource, stopPolling],
  )

  const reconnect = useCallback(() => {
    stopPolling()
    const id = idRef.current
    if (!id) return
    terminalRef.current = false
    failureRef.current = 0
    setFailures(0)
    startEventSource(id)
  }, [startEventSource, stopPolling])

  const clear = useCallback(() => {
    terminalRef.current = true
    closeSource()
    stopPolling()
    idRef.current = null
    setDiagnosisId(null)
    setSnapshot(null)
    setSteps([])
    setConnection('idle')
    setFailures(0)
  }, [closeSource, stopPolling])

  useEffect(
    () => () => {
      terminalRef.current = true
      closeSource()
      stopPolling()
    },
    [closeSource, stopPolling],
  )

  return {
    diagnosisId,
    snapshot,
    setSnapshot,
    steps,
    setSteps,
    connection,
    lastUpdated,
    failures,
    start,
    stop,
    clear,
    reconnect,
    refresh,
  }
}
