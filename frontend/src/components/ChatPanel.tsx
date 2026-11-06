import { useEffect, useRef, useState } from 'react'
import type { DiagnosisSnapshot, FeatureValues, Interrupt } from '../api/client'
import { ApiError, api } from '../api/client'
import { useApp } from '../store/AppContext'
import { stripNulls } from '../lib/features'
import { diagnosisMeta } from '../lib/status'
import { isTerminalStatus } from '../hooks/useDiagnosisStream'
import { InterruptPanel } from './InterruptPanel'
import { ExtractionCard, type ExtractionLike } from './ExtractionCard'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'

type ChatItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'agent'; id: string; text: string }
  | { kind: 'extraction'; id: string; messageId: string; text: string; extraction: ExtractionLike }
  | {
      kind: 'supplement'
      id: string
      messageId: string
      text: string
      extraction: ExtractionLike
      version: number
      interrupt: Interrupt | null
      confirmed: boolean
    }
  | { kind: 'process'; id: string; diagnosisId: string }
  | { kind: 'report'; id: string; diagnosisId: string; status: string }

type ChatError = { code: string; message: string; action?: 'new' | 'open' | 'none' }

const EXAMPLES = [
  '3号机 M 型，空气温度 298.1K，工艺温度 308.6K，转速 1551rpm，扭矩 42.8Nm，刀具磨损 0min',
  '4号机异响，扭矩 55，有点烫',
]

export function ChatPanel({
  snapshot,
  busy,
  expired,
  onDiagnosisCreated,
  onOpenDiagnosis,
  onRefreshSnapshot,
  onResume,
  onRestart,
  onEvidence,
  onFocusSteps,
  onFocusReport,
}: {
  snapshot: DiagnosisSnapshot | null
  busy: boolean
  expired: boolean
  onDiagnosisCreated: (diagnosisId: string, deduplicated: boolean) => void
  onOpenDiagnosis: (diagnosisId: string) => void
  onRefreshSnapshot: () => Promise<DiagnosisSnapshot | null>
  onResume: (decision: 'confirm' | 'supplement' | 'abort', supplement?: FeatureValues, versionOverride?: number) => Promise<boolean>
  onRestart: () => void
  onEvidence: (entryId: string) => void
  onFocusSteps: () => void
  onFocusReport: () => void
}) {
  const { pushToast } = useApp()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionStatus, setSessionStatus] = useState<'draft' | 'active' | 'terminal' | 'creating'>('creating')
  const [items, setItems] = useState<ChatItem[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<ChatError | null>(null)
  const [terminalReportAdded, setTerminalReportAdded] = useState(false)
  const [boundDiagnosisId, setBoundDiagnosisId] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const lastItemRef = useRef<HTMLDivElement>(null)
  const interruptRef = useRef<HTMLDivElement>(null)
  const createdRef = useRef(false)

  const boundSnapshot = snapshot && snapshot.diagnosis_id === boundDiagnosisId ? snapshot : null
  const snapshotStatus = boundSnapshot?.status ?? null

  async function createSession() {
    setSessionStatus('creating')
    setError(null)
    try {
      const created = await api.createChatSession()
      setSessionId(created.session_id)
      setSessionStatus('draft')
      setItems([])
      setTerminalReportAdded(false)
      setBoundDiagnosisId(null)
    } catch (err) {
      setSessionStatus('creating')
      setError({
        code: err instanceof ApiError ? err.code : 'NETWORK',
        message: err instanceof ApiError ? err.message : '会话创建失败，请重试',
        action: 'none',
      })
    }
  }

  useEffect(() => {
    if (createdRef.current) return
    createdRef.current = true
    void createSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const last = items[items.length - 1]
    if (!last) return
    lastItemRef.current?.scrollIntoView({
      block: last.kind === 'extraction' || last.kind === 'supplement' ? 'start' : 'end',
      behavior: 'smooth',
    })
  }, [items.length, snapshotStatus])

  const terminal = isTerminalStatus(snapshotStatus) || sessionStatus === 'terminal'
  const waitingReview = boundSnapshot?.status === 'waiting_human' && boundSnapshot.interrupt?.type === 'review'
  const waitingClarification = boundSnapshot?.status === 'waiting_human' && boundSnapshot.interrupt?.type === 'clarification'
  const canSend = !!sessionId && !sending && !confirming && !busy && !terminal && !waitingReview

  useEffect(() => {
    if (waitingClarification || waitingReview) {
      interruptRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
    }
  }, [waitingClarification, waitingReview, boundSnapshot?.interrupt?.version])

  useEffect(() => {
    if (!terminal || !boundSnapshot || terminalReportAdded) return
    setSessionStatus('terminal')
    if (boundSnapshot.report) {
      setItems((current) => {
        if (current.some((item) => item.kind === 'report' && item.diagnosisId === boundSnapshot.diagnosis_id)) return current
        return [
          ...current,
          { kind: 'report', id: `report-${boundSnapshot.diagnosis_id}`, diagnosisId: boundSnapshot.diagnosis_id, status: boundSnapshot.status },
        ]
      })
      setTerminalReportAdded(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terminal, boundSnapshot?.diagnosis_id, boundSnapshot?.report, terminalReportAdded])

  async function handleSend() {
    if (!sessionId || !input.trim() || !canSend) return
    const text = input.trim()
    setSending(true)
    setError(null)
    setInput('')
    setItems((current) => [...current, { kind: 'user', id: `u-${Date.now()}`, text }])
    try {
      const response = await api.sendChatMessage(sessionId, text)
      if (response.diagnosis_id) {
        // active + clarification: supplement card only, state is not changed until the user confirms.
        const responseInterrupt = (response.interrupt as Interrupt | null) ?? null
        setItems((current) => [
          ...current,
          { kind: 'agent', id: `a-${Date.now()}`, text: response.agent_text },
          {
            kind: 'supplement',
            id: `s-${Date.now()}`,
            messageId: response.message_id,
            text,
            extraction: response.extraction as ExtractionLike,
            version: response.version ?? responseInterrupt?.version ?? 1,
            interrupt: responseInterrupt,
            confirmed: false,
          },
        ])
      } else {
        setItems((current) => [
          ...current,
          { kind: 'agent', id: `a-${Date.now()}`, text: response.agent_text },
          {
            kind: 'extraction',
            id: `e-${Date.now()}`,
            messageId: response.message_id,
            text,
            extraction: response.extraction as ExtractionLike,
          },
        ])
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'CHAT_DECISION_REQUIRED') {
          setError({ code: err.code, message: '当前需要确认结论，暂不接受自由文本。请在上方确认卡中处理。', action: 'none' })
          await onRefreshSnapshot()
        } else if (err.code === 'DIAGNOSIS_STATE_CONFLICT') {
          setError({ code: err.code, message: '诊断执行中，暂不接受新消息。可查看右栏步骤流。', action: 'open' })
        } else if (err.code === 'CHAT_SESSION_CLOSED') {
          setError({ code: err.code, message: '本对话已结束，请新建对话。', action: 'new' })
          setSessionStatus('terminal')
        } else {
          setError({ code: err.code, message: err.message, action: 'none' })
        }
      } else {
        setError({ code: 'NETWORK', message: '发送失败，请检查网络后重试。', action: 'none' })
      }
    } finally {
      setSending(false)
    }
  }

  async function handleExtractionConfirm(item: Extract<ChatItem, { kind: 'extraction' }>, values: FeatureValues) {
    if (!sessionId) return
    const features = stripNulls(values)
    if (!features.device_id) return
    setConfirming(true)
    setError(null)
    try {
      const response = await api.confirmChat(sessionId, {
        message_id: item.messageId,
        text: item.text,
        features,
      })
      setItems((current) => current.filter((entry) => entry.id !== item.id))
      setBoundDiagnosisId(response.diagnosis_id)
      if (response.deduplicated) {
        // OBS-01：复用只可能返回 running/waiting_human；只有终态才允许置 terminal。
        const dedupeTerminal = isTerminalStatus(response.diagnosis_status)
        setSessionStatus(dedupeTerminal ? 'terminal' : 'active')
        pushToast('已复用相同输入的诊断')
        setItems((current) => [
          ...current,
          { kind: 'agent', id: `a-${Date.now()}`, text: '已复用相同输入的诊断，按原有状态载入右栏，不重复执行。' },
          ...(dedupeTerminal
            ? []
            : [{ kind: 'process' as const, id: `p-${Date.now()}`, diagnosisId: response.diagnosis_id }]),
        ])
        onDiagnosisCreated(response.diagnosis_id, true)
      } else {
        setSessionStatus('active')
        setItems((current) => [
          ...current,
          { kind: 'agent', id: `a-${Date.now()}`, text: '已创建诊断，正在执行。诊断过程在右栏同步更新。' },
          { kind: 'process', id: `p-${Date.now()}`, diagnosisId: response.diagnosis_id },
        ])
        onDiagnosisCreated(response.diagnosis_id, false)
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'CHAT_SESSION_ALREADY_ACTIVE') {
          const diagnosisId = String((err.details as { diagnosis_id?: string } | undefined)?.diagnosis_id || snapshot?.diagnosis_id || '')
          if (diagnosisId) setBoundDiagnosisId(diagnosisId)
          setError({ code: err.code, message: '会话已绑定诊断，已为你打开已有诊断。', action: diagnosisId ? 'open' : 'none' })
          if (diagnosisId) onOpenDiagnosis(diagnosisId)
        } else if (err.code === 'CHAT_SESSION_CLOSED') {
          setError({ code: err.code, message: '本对话已结束，请新建对话。', action: 'new' })
          setSessionStatus('terminal')
        } else if (err.code === 'DEVICE_ID_INVALID' || err.code === 'VALIDATION_FAILED') {
          setError({ code: err.code, message: err.message, action: 'none' })
        } else {
          setError({ code: err.code, message: err.message, action: 'none' })
        }
      } else {
        setError({ code: 'NETWORK', message: '创建诊断失败，请检查网络后重试。', action: 'none' })
      }
    } finally {
      setConfirming(false)
    }
  }

  async function handleSupplementConfirm(item: Extract<ChatItem, { kind: 'supplement' }>, values: FeatureValues) {
    const ok = await onResume('supplement', stripNulls(values) as FeatureValues, item.version)
    if (ok) {
      setItems((current) =>
        current.map((entry) => (entry.kind === 'supplement' && entry.id === item.id ? { ...entry, confirmed: true } : entry)),
      )
      setItems((current) => [...current, { kind: 'agent', id: `a-${Date.now()}`, text: '已提交补充值，诊断继续执行。' }])
    }
  }

  const inputDisabledReason = terminal
    ? '本对话已结束，请新建对话'
    : waitingReview
      ? '当前需要确认结论，暂不接受自由文本'
      : busy
        ? '正在处理人工决策…'
        : null

  return (
    <div className="chat-panel">
      <div className="chat-stream" ref={listRef}>
        {items.length === 0 ? (
          <div className="chat-empty">
            <Icon name="message" size={22} />
            <p className="chat-empty__title">用一句话描述设备状态</p>
            <p className="chat-empty__desc">首条消息只做抽取并展示确认卡，不会直接创建诊断。</p>
            <div className="chat-empty__examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" className="example-chip" onClick={() => setInput(example)} disabled={!sessionId}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {items.map((item, index) => {
          const isLast = index === items.length - 1
          if (item.kind === 'user') {
            return (
              <div key={item.id} className="chat-row is-user">
                <div className="chat-bubble chat-bubble--user">{item.text}</div>
              </div>
            )
          }
          if (item.kind === 'agent') {
            return (
              <div key={item.id} ref={isLast ? lastItemRef : undefined} className="chat-row is-agent">
                <div className="chat-agent">
                  <span className="chat-agent__mark" aria-hidden="true">
                    <Icon name="activity" size={14} />
                  </span>
                  <div className="chat-bubble chat-bubble--agent">{item.text}</div>
                </div>
              </div>
            )
          }
          if (item.kind === 'extraction') {
            return (
              <div key={item.id} ref={isLast ? lastItemRef : undefined} className="chat-row is-agent">
                <ExtractionCard
                  extraction={item.extraction}
                  text={item.text}
                  disabled={confirming || !!terminal}
                  onConfirm={(values) => void handleExtractionConfirm(item, values)}
                />
              </div>
            )
          }
          if (item.kind === 'supplement') {
            return (
              <div key={item.id} ref={isLast ? lastItemRef : undefined} className="chat-row is-agent">
                <section className="extraction-card supplement-card" aria-label="补充卡">
                  <header className="extraction-card__head">
                    <div>
                      <h3>补充值确认</h3>
                      <p className="extraction-card__sub">自由文本抽取结果仅供确认，点击确认后才提交补充并继续诊断。</p>
                    </div>
                    <span className={`status-badge ${item.confirmed ? 'tone-success' : 'tone-waiting'}`}>
                      <Icon name={item.confirmed ? 'check' : 'clipboard-check'} size={14} />
                      {item.confirmed ? '已补充' : '待确认'}
                    </span>
                  </header>
                  <div className="supplement-values">
                    {Object.entries(item.extraction.features ?? {}).map(([key, value]) =>
                      value === null || value === undefined || value === '' ? null : (
                        <span key={key} className="supplement-values__item mono">
                          <span>{key}</span>
                          {String(value)}
                        </span>
                      ),
                    )}
                  </div>
                  {item.extraction.missing_fields?.length ? (
                    <p className="hint-text">仍有 {item.extraction.missing_fields.length} 项缺失，可继续补充。</p>
                  ) : null}
                  {!item.confirmed ? (
                    <div className="extraction-card__actions">
                      <span />
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={busy}
                        onClick={() => void handleSupplementConfirm(item, item.extraction.features)}
                      >
                        {busy ? '提交中…' : '确认补充'}
                      </button>
                    </div>
                  ) : null}
                </section>
              </div>
            )
          }
          if (item.kind === 'process') {
            return (
              <div key={item.id} ref={isLast ? lastItemRef : undefined} className="chat-row is-agent">
                <section className="process-card">
                  <div className="process-card__head">
                    <Icon name="list-checks" size={16} />
                    <span>诊断执行中</span>
                    <span className="mono">{item.diagnosisId}</span>
                  </div>
                  <p>步骤流与状态条在右栏实时更新。</p>
                  <button type="button" className="text-button" onClick={onFocusSteps}>
                    查看完整过程
                  </button>
                </section>
              </div>
            )
          }
          return (
            <div key={item.id} ref={isLast ? lastItemRef : undefined} className="chat-row is-agent">
              <section className="process-card">
                <div className="process-card__head">
                  <Icon name="file" size={16} />
                  <span>诊断报告</span>
                  {boundSnapshot ? <StatusBadge meta={diagnosisMeta(boundSnapshot)} size="small" /> : null}
                </div>
                <p>{boundSnapshot?.report_title || '报告已生成'}</p>
                <button type="button" className="text-button" onClick={onFocusReport}>
                  查看完整报告
                </button>
              </section>
            </div>
          )
        })}

        {waitingClarification && boundSnapshot ? (
          <div className="chat-row is-agent" ref={interruptRef}>
            <InterruptPanel
              inline
              snapshot={boundSnapshot}
              version={boundSnapshot.interrupt?.version ?? 1}
              busy={busy}
              expired={expired}
              onSubmit={(decision, supplement) => void onResume(decision, supplement)}
              onEvidence={onEvidence}
              onRestart={onRestart}
            />
          </div>
        ) : null}

        {waitingReview && boundSnapshot ? (
          <div className="chat-row is-agent" ref={interruptRef}>
            <InterruptPanel
              inline
              snapshot={boundSnapshot}
              version={boundSnapshot.interrupt?.version ?? 1}
              busy={busy}
              expired={expired}
              onSubmit={(decision, supplement) => void onResume(decision, supplement)}
              onEvidence={onEvidence}
              onRestart={onRestart}
            />
          </div>
        ) : null}

        {error ? (
          <div className="chat-error" role="alert">
            <Icon name="alert-triangle" size={16} />
            <div>
              <p>{error.message}</p>
              <span className="mono">{error.code}</span>
            </div>
            <div className="chat-error__actions">
              {error.action === 'new' ? (
                <button type="button" className="btn btn-secondary" onClick={() => void createSession()}>
                  新建对话
                </button>
              ) : null}
              {error.action === 'open' && snapshot ? (
                <button type="button" className="text-button" onClick={onFocusSteps}>
                  查看步骤
                </button>
              ) : null}
              <button type="button" className="icon-button icon-button--tiny" aria-label="关闭错误提示" onClick={() => setError(null)}>
                <Icon name="x" size={12} />
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="chat-composer">
        {inputDisabledReason ? <p className="chat-composer__hint">{inputDisabledReason}</p> : null}
        <div className="chat-composer__box">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void handleSend()
              }
            }}
            placeholder={sessionStatus === 'creating' ? '正在创建会话…' : '描述设备状态，Enter 发送，Shift+Enter 换行'}
            disabled={!canSend}
            rows={2}
            aria-label="对话输入"
          />
          <button type="button" className="btn btn-primary" onClick={() => void handleSend()} disabled={!canSend || !input.trim()}>
            {sending ? '发送中…' : '发送'}
          </button>
        </div>
        {terminal ? (
          <div className="chat-terminal">
            <span>本对话已结束。</span>
            <button type="button" className="text-button" onClick={() => void createSession()}>
              新建对话
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
