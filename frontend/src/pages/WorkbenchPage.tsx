import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ApiError,
  api,
  downloadBlob,
  filenameFromDisposition,
  notifyAuthExpired,
  type DiagnosisCreateResponse,
  type DiagnosisSnapshot,
  type DiagnosisSummary,
  type FeatureValues,
  type Mapping,
  type UploadPrecheck,
} from '../api/client'
import { useApp } from '../store/AppContext'
import { isTerminalStatus, useDiagnosisStream, stepsFromSnapshot } from '../hooks/useDiagnosisStream'
import { useBatchStream } from '../hooks/useBatchStream'
import { useCountdown } from '../hooks/useCountdown'
import { batchSegments, confidenceText, diagnosisMeta, formatClock, formatDuration, formatDateTime } from '../lib/status'
import { FEATURE_DEFS, FEATURE_KEYS, valuesFromInput } from '../lib/features'
import { BatchPanel } from '../components/BatchPanel'
import { ChatPanel } from '../components/ChatPanel'
import { ConfidenceBadge } from '../components/ConfidenceBadge'
import { ConnectionBanner } from '../components/ConnectionBanner'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { CsvPanel } from '../components/CsvPanel'
import { EmptyState } from '../components/EmptyState'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { FormPanel } from '../components/FormPanel'
import { HistoryDrawer } from '../components/HistoryDrawer'
import { Icon } from '../components/Icon'
import { InterruptPanel } from '../components/InterruptPanel'
import { NlPanel } from '../components/NlPanel'
import { ReportPanel } from '../components/ReportPanel'
import { StatusBadge } from '../components/StatusBadge'
import { StatusBar } from '../components/StatusBar'
import { StepFlow } from '../components/StepFlow'
import { Modal } from '../components/Modal'

type TabKey = 'csv' | 'form' | 'nl' | 'chat'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'csv', label: 'CSV' },
  { key: 'form', label: '表单' },
  { key: 'nl', label: '自然语言' },
  { key: 'chat', label: '对话' },
]

const ACTIVE_DIAGNOSIS_KEY = 'edg.active-diagnosis-id'

function rememberActiveDiagnosis(id: string | null) {
  try {
    if (id) sessionStorage.setItem(ACTIVE_DIAGNOSIS_KEY, id)
    else sessionStorage.removeItem(ACTIVE_DIAGNOSIS_KEY)
  } catch {
    // 隐私模式等不可写场景仅放弃刷新恢复，不影响诊断主流程
  }
}

function recallActiveDiagnosis() {
  try {
    return sessionStorage.getItem(ACTIVE_DIAGNOSIS_KEY)
  } catch {
    return null
  }
}

function FeatureSnapshotTable({ snapshot }: { snapshot: DiagnosisSnapshot }) {
  const normalized = (snapshot.features?.normalized ?? {}) as Record<string, unknown>
  const derived = (snapshot.features?.derived ?? {}) as Record<string, unknown>
  const rows = FEATURE_KEYS.filter((key) => normalized[key] !== undefined && normalized[key] !== null).map((key) => ({
    label: FEATURE_DEFS[key].label,
    unit: FEATURE_DEFS[key].unit || '',
    value: String(normalized[key]),
  }))
  ;[
    ['温差', 'K', derived.temp_diff],
    ['功率', 'W', derived.power_w],
    ['磨损×扭矩', '', derived.wear_torque],
  ].forEach(([label, unit, value]) => {
    if (value !== undefined && value !== null) rows.push({ label: String(label), unit: String(unit), value: String(value) })
  })
  if (!rows.length) return <p className="hint-text">未获得标准化特征。</p>
  return (
    <table className="mini-table feature-snapshot">
      <caption className="sr-only">已获得的标准化特征</caption>
      <thead>
        <tr>
          <th scope="col">特征</th>
          <th scope="col">数值</th>
          <th scope="col">单位</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td>{row.label}</td>
            <td className="num mono">{row.value}</td>
            <td>{row.unit || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function WorkbenchPage() {
  const { user, logout, pushToast, online } = useApp()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabKey>('csv')
  const [chatActivated, setChatActivated] = useState(false)
  const [csvMode, setCsvMode] = useState<'single' | 'batch'>('single')
  const [historySnapshot, setHistorySnapshot] = useState<DiagnosisSnapshot | null>(null)
  const [pinnedSnapshot, setPinnedSnapshot] = useState<DiagnosisSnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const [formInitial, setFormInitial] = useState<FeatureValues | null>(null)
  const [formNonce, setFormNonce] = useState(0)
  const [recent, setRecent] = useState<DiagnosisSummary[]>([])
  const [recentInterruptTypes, setRecentInterruptTypes] = useState<Record<string, 'clarification' | 'review'>>({})
  const [recentTick, setRecentTick] = useState(0)
  const [interruptOpen, setInterruptOpen] = useState(false)
  const [dismissedVersion, setDismissedVersion] = useState<number | null>(null)
  const [abortConfirm, setAbortConfirm] = useState(false)
  const [conflictOpen, setConflictOpen] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [resetConfirm, setResetConfirm] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyConfirmOpen, setHistoryConfirmOpen] = useState(false)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const [selectedEntry, setSelectedEntry] = useState<string | null>(null)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [stepsCollapsed, setStepsCollapsed] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const reportRef = useRef<HTMLDivElement>(null)
  const stepsRef = useRef<HTMLDivElement>(null)
  const userMenuRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef(false)

  const stream = useDiagnosisStream({
    onInterrupt: () => {
      setRecentTick((tick) => tick + 1)
    },
    onTerminal: () => {
      setRecentTick((tick) => tick + 1)
    },
    onDomainError: (payload) => {
      const message = String(payload.message || '诊断流返回错误事件')
      setPageError(message)
    },
  })
  const batchStream = useBatchStream({
    onTerminal: () => setRecentTick((tick) => tick + 1),
  })

  const viewSnapshot = historySnapshot ?? pinnedSnapshot ?? stream.snapshot
  const readOnlyView = !!historySnapshot || (!!pinnedSnapshot && !!pinnedSnapshot.batch)
  const viewSteps = historySnapshot || pinnedSnapshot ? stepsFromSnapshot(viewSnapshot as DiagnosisSnapshot) : stream.steps
  const scopeLabel = historySnapshot ? '历史记录' : pinnedSnapshot?.batch ? '批量行' : undefined
  const liveView = viewSnapshot === stream.snapshot
  const interruptRemaining = useCountdown(viewSnapshot?.interrupt?.expires_at)
  const interruptLocked = !!viewSnapshot && viewSnapshot.status === 'waiting_human' && interruptRemaining.seconds <= 0

  const refreshRecent = useCallback(() => setRecentTick((tick) => tick + 1), [])

  // 刷新恢复：仅恢复同一标签页内未终态的活动诊断（含 waiting_human 复核/澄清），
  // 复用 start(id) 的“补拉快照 + 建流 + onInterrupt”路径，不改变任何展示态。
  useEffect(() => {
    if (restoreRef.current) return
    restoreRef.current = true
    const id = recallActiveDiagnosis()
    if (!id) return
    api
      .getDiagnosis(id)
      .then((snapshot) => {
        if (isTerminalStatus(snapshot.status)) {
          rememberActiveDiagnosis(null)
          return
        }
        stream.start(id)
      })
      .catch(() => rememberActiveDiagnosis(null))
  }, [stream.start])

  useEffect(() => {
    let alive = true
    api
      .listDiagnoses({ page: 1, page_size: 5 })
      .then(async (result) => {
        if (!alive) return
        setRecent(result.items)
        const waiting = result.items.filter((item) => item.status === 'waiting_human')
        if (!waiting.length) return
        const resolved = await Promise.all(
          waiting.map(async (item) => {
            try {
              const snapshot = await api.getDiagnosis(item.diagnosis_id)
              return [item.diagnosis_id, snapshot.interrupt?.type] as const
            } catch {
              return [item.diagnosis_id, undefined] as const
            }
          }),
        )
        if (!alive) return
        const next: Record<string, 'clarification' | 'review'> = {}
        for (const [id, type] of resolved) {
          if (type) next[id] = type
        }
        setRecentInterruptTypes(next)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [recentTick])

  useEffect(() => {
    if (!viewSnapshot || readOnlyView) return
    if (viewSnapshot.status === 'waiting_human' && activeTab !== 'chat') {
      const version = viewSnapshot.interrupt?.version ?? viewSnapshot.version
      if (dismissedVersion !== version) setInterruptOpen(true)
    } else if (viewSnapshot.status !== 'waiting_human') {
      setInterruptOpen(false)
    }
  }, [viewSnapshot, activeTab, readOnlyView, dismissedVersion])

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) setUserMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toastError = useCallback(
    (error: unknown, fallback: string) => {
      if (error instanceof ApiError) {
        const fields = (error.details as { fields?: { label?: string; message?: string }[] } | undefined)?.fields
        const detail = fields?.length ? `（${fields.map((field) => `${field.label || ''}${field.message ? `：${field.message}` : ''}`).join('；')}）` : ''
        pushToast(`${error.message}${detail}`, 'error')
      } else {
        pushToast(fallback, 'error')
      }
    },
    [pushToast],
  )

  const applyCreateResponse = useCallback(
    async (response: DiagnosisCreateResponse) => {
      rememberActiveDiagnosis(response.diagnosis_id)
      setHistorySnapshot(null)
      setPinnedSnapshot(null)
      if (response.deduplicated) {
        stream.clear()
        const snapshot = await api.getDiagnosis(response.diagnosis_id)
        setPinnedSnapshot(snapshot)
        pushToast('已复用相同输入的诊断')
      } else {
        stream.start(response.diagnosis_id)
      }
      refreshRecent()
    },
    [pushToast, refreshRecent, stream],
  )

  async function startForm(values: FeatureValues) {
    if (stream.snapshot?.status === 'running') {
      pushToast('当前诊断运行中，请等待完成后再提交', 'error')
      return false
    }
    setBusy(true)
    setPageError(null)
    try {
      const response = await api.createDiagnosis({ input_type: 'form', ...values })
      await applyCreateResponse(response)
      return true
    } catch (error) {
      toastError(error, '诊断创建失败，请稍后重试')
      return false
    } finally {
      setBusy(false)
    }
  }

  async function startNl(values: FeatureValues, text: string) {
    if (stream.snapshot?.status === 'running') {
      pushToast('当前诊断运行中，请等待完成后再提交', 'error')
      return false
    }
    setBusy(true)
    setPageError(null)
    try {
      const payload: Record<string, unknown> = { input_type: 'nl', text, device_id: values.device_id }
      for (const key of FEATURE_KEYS) {
        if (key !== 'device_id' && values[key] !== null && values[key] !== undefined) payload[key] = values[key]
      }
      const response = await api.createDiagnosis(payload)
      await applyCreateResponse(response)
      return true
    } catch (error) {
      toastError(error, '诊断创建失败，请稍后重试')
      return false
    } finally {
      setBusy(false)
    }
  }

  async function startCsvSingle(payload: { upload: UploadPrecheck; mapping: Mapping; default_device_id: string | null; row_no: number }) {
    if (stream.snapshot?.status === 'running') {
      pushToast('当前诊断运行中，请等待完成后再提交', 'error')
      return false
    }
    setBusy(true)
    setPageError(null)
    try {
      const preview = await api.mappingPreview(payload.upload.upload_id, {
        mapping: payload.mapping,
        mode: 'single',
        row_no: payload.row_no,
        default_device_id: payload.default_device_id,
      })
      if (!preview.valid || preview.missing_required.length) {
        pushToast('字段映射不完整，请补齐后再提交', 'error')
        return false
      }
      const response = await api.createDiagnosis({
        input_type: 'csv_single',
        upload_id: payload.upload.upload_id,
        row_no: payload.row_no,
        mapping: payload.mapping,
        default_device_id: payload.default_device_id,
      })
      await applyCreateResponse(response)
      return true
    } catch (error) {
      toastError(error, 'CSV 诊断创建失败')
      return false
    } finally {
      setBusy(false)
    }
  }

  async function startCsvBatch(payload: { upload: UploadPrecheck; mapping: Mapping; default_device_id: string | null }) {
    if (stream.snapshot?.status === 'running') {
      pushToast('当前单条诊断运行中，仍可创建批量任务；批量与单条可并存', 'info')
    }
    setBusy(true)
    setPageError(null)
    try {
      const response = await api.createBatch({
        upload_id: payload.upload.upload_id,
        mapping: payload.mapping,
        default_device_id: payload.default_device_id,
      })
      batchStream.start(response.batch_task_id)
      setBatchOpen(true)
      pushToast('批量任务已创建')
      refreshRecent()
      return true
    } catch (error) {
      toastError(error, '批量任务创建失败')
      return false
    } finally {
      setBusy(false)
    }
  }

  async function openDiagnosis(snapshot: DiagnosisSnapshot, source: 'history' | 'pinned') {
    if (source === 'history') {
      setHistorySnapshot(snapshot)
      setPinnedSnapshot(null)
    } else {
      setPinnedSnapshot(snapshot)
      setHistorySnapshot(null)
    }
    setDismissedVersion(null)
  }

  async function openHistoryItem(summary: DiagnosisSummary) {
    setHistoryOpen(false)
    try {
      const snapshot = await api.getDiagnosis(summary.diagnosis_id)
      await openDiagnosis(snapshot, 'history')
    } catch (error) {
      toastError(error, '历史记录加载失败')
    }
  }

  async function openRecent(summary: DiagnosisSummary) {
    try {
      const snapshot = await api.getDiagnosis(summary.diagnosis_id)
      await openDiagnosis(snapshot, 'history')
    } catch (error) {
      toastError(error, '记录加载失败')
    }
  }

  async function openBatchReport(diagnosisId: string) {
    try {
      const snapshot = await api.getDiagnosis(diagnosisId)
      setPinnedSnapshot(snapshot)
      setHistorySnapshot(null)
      setBatchOpen(false)
    } catch (error) {
      toastError(error, '报告加载失败')
    }
  }

  function returnToLive() {
    setHistorySnapshot(null)
    setPinnedSnapshot(null)
  }

  async function refreshView() {
    if (!viewSnapshot) return
    try {
      if (liveView) {
        const next = await stream.refresh()
        if (next && next.status === 'waiting_human') setInterruptOpen(true)
      } else {
        const next = await api.getDiagnosis(viewSnapshot.diagnosis_id)
        if (historySnapshot) setHistorySnapshot(next)
        else setPinnedSnapshot(next)
      }
    } catch (error) {
      toastError(error, '刷新状态失败')
    }
  }

  async function doResume(decision: 'confirm' | 'supplement' | 'abort', supplement?: FeatureValues, versionOverride?: number) {
    if (!viewSnapshot) return false
    const id = viewSnapshot.diagnosis_id
    setBusy(true)
    setPageError(null)
    try {
      const next = await api.resume(id, {
        decision,
        version: versionOverride ?? viewSnapshot.version,
        ...(supplement ? { supplement } : {}),
      })
      if (stream.diagnosisId === id) {
        stream.setSnapshot(next)
        if (next.status !== 'waiting_human') setInterruptOpen(false)
        void stream.refresh()
      } else if (historySnapshot) {
        setHistorySnapshot(next)
      } else {
        setPinnedSnapshot(next)
      }
      if (decision === 'abort') pushToast('记录已保存为已中止')
      if (decision === 'confirm') pushToast('已确认结论，正在重新生成报告')
      refreshRecent()
      return true
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 'VERSION_CONFLICT') {
          setConflictOpen(true)
        } else if (error.code === 'DIAGNOSIS_EXPIRED') {
          await refreshView()
          pushToast('中断已过期，请以原输入重新发起', 'error')
        } else if (error.code === 'DECISION_NOT_ALLOWED' || error.code === 'DIAGNOSIS_STATE_CONFLICT' || error.code === 'INTERRUPT_NOT_ACTIVE') {
          await refreshView()
          pushToast('当前状态不允许该决策，已刷新快照', 'error')
        } else {
          toastError(error, '决策提交失败')
        }
      } else {
        toastError(error, '决策提交失败')
      }
      return false
    } finally {
      setBusy(false)
    }
  }

  function requestResume(decision: 'confirm' | 'supplement' | 'abort', supplement?: FeatureValues, versionOverride?: number) {
    if (decision === 'abort') {
      setAbortConfirm(true)
      return Promise.resolve(false)
    }
    return doResume(decision, supplement, versionOverride)
  }

  function backfillOriginal() {
    if (!viewSnapshot) return
    if (viewSnapshot.input_type === 'csv_single' || viewSnapshot.input_type === 'csv_batch') {
      setActiveTab('csv')
      pushToast('请重新选择 CSV 文件并按原映射提交')
      return
    }
    const values = valuesFromInput(viewSnapshot.features?.normalized as Record<string, unknown> | undefined)
    setFormInitial(values)
    setFormNonce((value) => value + 1)
    setActiveTab('form')
    pushToast('已回填原输入，请修改后重新提交')
  }

  async function exportReport() {
    if (!viewSnapshot?.report) return
    try {
      const response = await fetch(api.reportUrl(viewSnapshot.diagnosis_id), { credentials: 'same-origin' })
      if (response.status === 401) {
        notifyAuthExpired()
        return
      }
      if (!response.ok) throw new Error('export failed')
      const blob = await response.blob()
      const filename =
        filenameFromDisposition(response.headers.get('Content-Disposition')) ||
        `诊断报告_${viewSnapshot.device_id}_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1_$2')}.md`
      downloadBlob(blob, filename.replace(/[\\/:*?"<>|]/g, '_'))
      pushToast('报告已导出', 'success')
    } catch {
      pushToast('报告导出失败，请检查网络后重试。', 'error')
    }
  }

  async function copyReport() {
    if (!viewSnapshot?.report) return
    try {
      await navigator.clipboard.writeText(viewSnapshot.report.markdown)
      pushToast('已复制 Markdown 报告', 'success')
    } catch {
      pushToast('复制失败，请检查浏览器权限', 'error')
    }
  }

  async function deleteCurrent() {
    if (!viewSnapshot) return
    const id = viewSnapshot.diagnosis_id
    setBusy(true)
    try {
      await api.deleteDiagnosis(id)
      if (recallActiveDiagnosis() === id) rememberActiveDiagnosis(null)
      if (stream.diagnosisId === id) stream.clear()
      setHistorySnapshot(null)
      setPinnedSnapshot(null)
      setDeleteConfirm(false)
      refreshRecent()
      pushToast('记录已删除', 'success')
    } catch (error) {
      toastError(error, '删除失败')
    } finally {
      setBusy(false)
    }
  }

  function requestNewDiagnosis() {
    if (stream.snapshot?.status === 'running') {
      pushToast('当前诊断运行中，请等待完成后再新建', 'error')
      return
    }
    if (stream.snapshot?.status === 'waiting_human' && activeTab !== 'chat') {
      setResetConfirm(true)
      return
    }
    resetWorkspace()
  }

  function resetWorkspace() {
    rememberActiveDiagnosis(null)
    stream.clear()
    setHistorySnapshot(null)
    setPinnedSnapshot(null)
    setInterruptOpen(false)
    setDismissedVersion(null)
    setPageError(null)
    setFormInitial(null)
    setFormNonce((value) => value + 1)
    setResetConfirm(false)
  }

  function requestHistory() {
    if (activeTab === 'chat') {
      setHistoryConfirmOpen(true)
      return
    }
    setHistoryOpen(true)
  }

  function beginChatToHistory() {
    setHistoryConfirmOpen(false)
    setActiveTab('csv')
    setHistoryOpen(true)
  }

  const batch = batchStream.batch
  const diagnosisRunning = stream.snapshot?.status === 'running'
  const batchPercent = batch ? batchSegments(batch).percent : 0
  const batchIndicator = batch
    ? batch.status === 'running' || batch.status === 'queued'
      ? `批量 ${batchPercent}%`
      : batch.status === 'completed'
        ? '批量完成'
        : batch.status === 'partially_failed'
          ? '批量部分失败'
          : batch.status === 'cancelled'
            ? '批量已取消'
            : batch.status === 'timed_out'
              ? '批量已超时'
              : '批量失败'
    : null

  const mainContent = (() => {
    if (!viewSnapshot) {
      return (
        <div className="right-idle">
          <EmptyState
            title="等待诊断输入"
            description="从左侧选择 CSV、表单、自然语言或对话开始。首条消息与抽取阶段不会创建诊断记录。"
            secondary={
              <button type="button" className="text-button" onClick={() => setHistoryOpen(true)}>
                查看历史记录
              </button>
            }
          />
          <div className="idle-rails" aria-hidden="true">
            <div>
              <span className="mono">01</span>
              <p>输入</p>
            </div>
            <div>
              <span className="mono">02</span>
              <p>检索</p>
            </div>
            <div>
              <span className="mono">03</span>
              <p>推理</p>
            </div>
            <div>
              <span className="mono">04</span>
              <p>报告</p>
            </div>
          </div>
        </div>
      )
    }
    if (viewSnapshot.status === 'running') {
      return (
        <div className="running-stage">
          <div className="skeleton-report" aria-label="报告生成中" role="status">
            <div className="skeleton-line skeleton-line--title" />
            <div className="skeleton-line skeleton-line--meta" />
            <div className="skeleton-block" />
            <div className="skeleton-line" />
            <div className="skeleton-line skeleton-line--short" />
          </div>
          <p className="hint-text">报告生成前不提供导出或复制；运行中不提供取消。</p>
        </div>
      )
    }
    if (viewSnapshot.status === 'waiting_human') {
      return (
        <div className="pending-card">
          <StatusBadge meta={diagnosisMeta(viewSnapshot)} />
          <h2>{viewSnapshot.interrupt?.type === 'clarification' ? '需要补充数据' : '需要你确认结论'}</h2>
          <p>
            {viewSnapshot.interrupt?.type === 'clarification'
              ? `本次诊断缺少 ${viewSnapshot.interrupt.payload.missing_fields?.length ?? 0} 项关键数据，补充后可继续。`
              : `置信度 ${confidenceText(viewSnapshot.confidence, viewSnapshot.confidence_level)}，请确认结论或补充数据。`}
          </p>
          {readOnlyView ? (
            <p className="hint-text">历史记录为只读查看态，不提供补充或确认。</p>
          ) : activeTab === 'chat' ? (
            <p className="hint-text">请在左侧对话流中的内嵌卡片处理。</p>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => setInterruptOpen(true)}>
              继续处理
            </button>
          )}
        </div>
      )
    }
    if (viewSnapshot.status === 'failed') {
      return (
        <section className="terminal-card" aria-label="诊断失败">
          <header className="terminal-card__head">
            <Icon name="x" size={20} />
            <div>
              <h2>诊断失败</h2>
              <p>{viewSnapshot.error?.message || '诊断执行过程中出现节点错误，未生成报告。'}</p>
            </div>
          </header>
          <dl className="readonly-facts">
            <div>
              <dt>错误码</dt>
              <dd className="mono">{viewSnapshot.error?.code || 'UNKNOWN'}</dd>
            </div>
            <div>
              <dt>失败节点</dt>
              <dd>{viewSnapshot.error?.node || '未记录'}</dd>
            </div>
            <div>
              <dt>耗时</dt>
              <dd className="mono">{formatDuration(viewSnapshot.duration_ms)}</dd>
            </div>
            <div>
              <dt>可恢复</dt>
              <dd>{viewSnapshot.error?.recoverable ? '是，修改输入后重新提交' : '否'}</dd>
            </div>
          </dl>
          <FeatureSnapshotTable snapshot={viewSnapshot} />
          <div className="terminal-card__actions">
            {!readOnlyView ? (
              <button type="button" className="btn btn-primary" onClick={backfillOriginal}>
                修改输入并重新提交
              </button>
            ) : null}
            <span className="hint-text">不提供一键重试。</span>
          </div>
        </section>
      )
    }
    if (viewSnapshot.status === 'failed_timeout') {
      return (
        <section className="terminal-card terminal-card--timeout" aria-label="超时失败">
          <header className="terminal-card__head">
            <Icon name="timer-off" size={20} />
            <div>
              <h2>超时失败 · 未生成报告</h2>
              <p>本次诊断执行超过全局 15 秒上限，系统已熔断。</p>
            </div>
          </header>
          <dl className="readonly-facts">
            <div>
              <dt>耗时</dt>
              <dd className="mono">{formatDuration(viewSnapshot.duration_ms)}</dd>
            </div>
            <div>
              <dt>超时节点</dt>
              <dd>{viewSnapshot.error?.node || '诊断推理'}</dd>
            </div>
            <div>
              <dt>错误码</dt>
              <dd className="mono">{viewSnapshot.error?.code || 'TIMEOUT'}</dd>
            </div>
            <div>
              <dt>报告</dt>
              <dd>无报告</dd>
            </div>
          </dl>
          <FeatureSnapshotTable snapshot={viewSnapshot} />
          <p className="hint-text">已获得但未完成诊断；不渲染报告区，不提供导出、复制或重试。</p>
          <div className="terminal-card__actions">
            {!readOnlyView ? (
              <button type="button" className="btn btn-primary" onClick={backfillOriginal}>
                修改输入并重新提交
              </button>
            ) : null}
            <button type="button" className="btn btn-secondary" onClick={() => setStepsCollapsed(false)}>
              查看已完成步骤
            </button>
          </div>
        </section>
      )
    }
    if (viewSnapshot.status === 'aborted') {
      return (
        <section className="terminal-card" aria-label="已中止">
          <header className="terminal-card__head">
            <Icon name="ban" size={20} />
            <div>
              <h2>本次诊断已中止</h2>
              <p>{viewSnapshot.error?.message || '用户放弃本次诊断，未生成报告。'}</p>
            </div>
          </header>
          <dl className="readonly-facts">
            <div>
              <dt>原因</dt>
              <dd>{viewSnapshot.human_decision === 'abort' ? '人工放弃' : viewSnapshot.error?.code || '—'}</dd>
            </div>
            <div>
              <dt>耗时</dt>
              <dd className="mono">{formatDuration(viewSnapshot.duration_ms)}</dd>
            </div>
          </dl>
          <div className="terminal-card__actions">
            {!readOnlyView ? (
              <button type="button" className="btn btn-primary" onClick={resetWorkspace}>
                新建诊断
              </button>
            ) : null}
            <span className="hint-text">不生成报告。</span>
          </div>
        </section>
      )
    }
    if (viewSnapshot.status === 'expired') {
      const payload = (viewSnapshot.interrupt?.payload ?? null) as Record<string, unknown> | null
      const missing = (payload?.missing_fields ?? []) as { label: string; unit?: string | null; example?: unknown }[]
      return (
        <section className="terminal-card" aria-label="已过期">
          <header className="terminal-card__head">
            <Icon name="alarm" size={20} />
            <div>
              <h2>等待已过期</h2>
              <p>中断等待超时，仅可查看最后载荷并以原输入重新发起。</p>
            </div>
          </header>
          <dl className="readonly-facts">
            <div>
              <dt>到期时间</dt>
              <dd className="mono">{formatDateTime(viewSnapshot.interrupt?.expires_at)}</dd>
            </div>
            <div>
              <dt>中断类型</dt>
              <dd>{viewSnapshot.interrupt?.type === 'review' ? '等待确认' : '等待补充'}</dd>
            </div>
            <div>
              <dt>缺失字段</dt>
              <dd>{missing.map((field) => field.label).join('、') || '无'}</dd>
            </div>
          </dl>
          {missing.length ? (
            <table className="mini-table">
              <caption className="sr-only">过期中断的最后载荷</caption>
              <thead>
                <tr>
                  <th scope="col">字段</th>
                  <th scope="col">单位</th>
                  <th scope="col">示例</th>
                </tr>
              </thead>
              <tbody>
                {missing.map((field) => (
                  <tr key={field.label}>
                    <td>{field.label}</td>
                    <td>{field.unit || '—'}</td>
                    <td className="mono">{String(field.example ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <div className="terminal-card__actions">
            {!readOnlyView ? (
              <button type="button" className="btn btn-primary" onClick={backfillOriginal}>
                以原输入重新发起
              </button>
            ) : null}
          </div>
        </section>
      )
    }
    if (viewSnapshot.status === 'succeeded' || viewSnapshot.status === 'degraded' || viewSnapshot.status === 'degraded_review') {
      if (!viewSnapshot.report) {
        return (
          <div className="pending-card">
            <h2>报告暂不可用</h2>
            <p>服务端状态为 {viewSnapshot.status}，但报告载荷为空。请刷新状态后重试。</p>
            <button type="button" className="btn btn-secondary" onClick={() => void refreshView()}>
              刷新状态
            </button>
          </div>
        )
      }
      return (
        <div ref={reportRef}>
          <ReportPanel
            snapshot={viewSnapshot}
            historyView={readOnlyView}
            onEvidence={(entryId) => {
              setSelectedEntry(entryId)
              setEvidenceOpen(true)
            }}
            onExport={() => void exportReport()}
            onCopy={() => void copyReport()}
            onDelete={() => setDeleteConfirm(true)}
          />
        </div>
      )
    }
    return null
  })()

  const connectionNotice = (() => {
    if (!online) return <ConnectionBanner kind="offline">网络已断开，保留最后快照，恢复后自动重连。</ConnectionBanner>
    if (!liveView || !viewSnapshot) return null
    if (stream.connection === 'retrying') {
      return (
        <ConnectionBanner
          kind="retry"
          action={
            <button type="button" className="text-button" onClick={stream.reconnect}>
              重新连接
            </button>
          }
        >
          更新中断，正在重连… 最后更新 {formatClock(stream.lastUpdated)}
        </ConnectionBanner>
      )
    }
    if (stream.connection === 'polling') {
      return (
        <ConnectionBanner
          kind="poll"
          action={
            <button type="button" className="text-button" onClick={stream.reconnect}>
              重新连接
            </button>
          }
        >
          已切换为轮询更新，每 2 秒补拉快照 · 最后更新 {formatClock(stream.lastUpdated)}
        </ConnectionBanner>
      )
    }
    return null
  })()

  return (
    <div className="workbench">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <rect x="1.5" y="1.5" width="19" height="19" rx="2" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5 16.5V12h3.2v4.5M10.5 16.5V7.2h3.2v9.3M15.8 16.5V9.6" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </span>
          <div>
            <p className="topbar__title">设备故障诊断</p>
            <p className="topbar__sub mono">EDG · DIAGNOSTIC CONSOLE</p>
          </div>
          <span className={`live-dot ${online ? 'is-online' : ''}`} title={online ? '网络已连接' : '网络已断开'} />
        </div>
        <div className="topbar__actions">
          {batchIndicator ? (
            <button type="button" className="batch-indicator" onClick={() => setBatchOpen((open) => !open)}>
              <Icon name="list-checks" size={16} />
              <span className="mono">{batchIndicator}</span>
            </button>
          ) : null}
          <button type="button" className="topbar__button" onClick={requestNewDiagnosis}>
            <Icon name="file" size={16} />
            新建诊断
          </button>
          <button type="button" className="topbar__button" onClick={requestHistory}>
            <Icon name="clock" size={16} />
            历史记录
          </button>
          <div className="user-menu" ref={userMenuRef}>
            <button type="button" className="topbar__button" onClick={() => setUserMenuOpen((open) => !open)} aria-expanded={userMenuOpen}>
              <span className="user-avatar" aria-hidden="true">
                {(user?.username || 'U').slice(0, 1).toUpperCase()}
              </span>
              {user?.username}
              <Icon name="chevron-down" size={14} />
            </button>
            {userMenuOpen ? (
              <div className="user-menu__list" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setUserMenuOpen(false)
                    navigate('/eval')
                  }}
                >
                  <Icon name="activity" size={14} />
                  评测结果
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={async () => {
                    setUserMenuOpen(false)
                    await logout()
                    navigate('/login')
                  }}
                >
                  <Icon name="arrow-left" size={14} />
                  退出登录
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="viewport-warning">请在 ≥1024px 的桌面浏览器使用</div>

      <div className="workbench__body">
        <aside className="left-panel">
          <div className="left-panel__head">
            <h1>诊断输入</h1>
            <span className="left-panel__hint">选择入口后提交</span>
          </div>
          <div
            className="tabs"
            role="tablist"
            aria-label="输入入口"
            onKeyDown={(event) => {
              if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
              const index = TABS.findIndex((tab) => tab.key === activeTab)
              const next = event.key === 'ArrowRight' ? (index + 1) % TABS.length : (index - 1 + TABS.length) % TABS.length
              setActiveTab(TABS[next].key)
              if (TABS[next].key === 'chat') setChatActivated(true)
            }}
          >
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.key}
                className={activeTab === tab.key ? 'is-active' : ''}
                onClick={() => {
                  setActiveTab(tab.key)
                  if (tab.key === 'chat') setChatActivated(true)
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="tab-content">
            <div hidden={activeTab !== 'csv'}>
              <CsvPanel mode={csvMode} onModeChange={setCsvMode} busy={busy} locked={diagnosisRunning} onCreateSingle={startCsvSingle} onCreateBatch={startCsvBatch} />
            </div>
            <div hidden={activeTab !== 'form'}>
              <FormPanel key={formNonce} busy={busy} locked={diagnosisRunning} initialValues={formInitial} onSubmit={startForm} />
            </div>
            <div hidden={activeTab !== 'nl'}>
              <NlPanel busy={busy} locked={diagnosisRunning} onConfirm={startNl} onUseForm={() => setActiveTab('form')} />
            </div>
            {chatActivated ? (
              <div hidden={activeTab !== 'chat'} className="chat-host">
                <ChatPanel
                  snapshot={liveView ? stream.snapshot : pinnedSnapshot}
                  busy={busy}
                  expired={viewSnapshot?.status === 'expired'}
                  onDiagnosisCreated={(diagnosisId, deduplicated) => {
                    rememberActiveDiagnosis(diagnosisId)
                    if (deduplicated) {
                      void api.getDiagnosis(diagnosisId).then((snapshot) => {
                        stream.clear()
                        setPinnedSnapshot(snapshot)
                        setHistorySnapshot(null)
                      })
                    } else {
                      setHistorySnapshot(null)
                      setPinnedSnapshot(null)
                      stream.start(diagnosisId)
                    }
                    refreshRecent()
                  }}
                  onOpenDiagnosis={(diagnosisId) => {
                    rememberActiveDiagnosis(diagnosisId)
                    if (stream.diagnosisId === diagnosisId) {
                      void stream.refresh()
                    } else {
                      stream.start(diagnosisId)
                    }
                  }}
                  onRefreshSnapshot={async () => {
                    const id = stream.diagnosisId ?? viewSnapshot?.diagnosis_id
                    if (!id) return null
                    return stream.diagnosisId === id ? stream.refresh() : api.getDiagnosis(id)
                  }}
                  onResume={requestResume}
                  onRestart={backfillOriginal}
                  onEvidence={(entryId) => {
                    setSelectedEntry(entryId)
                    setEvidenceOpen(true)
                  }}
                  onFocusSteps={() => {
                    setStepsCollapsed(false)
                    stepsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                  }}
                  onFocusReport={() => reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                />
              </div>
            ) : null}
          </div>

          {activeTab !== 'chat' ? (
            <section className="recent" aria-label="最近记录">
              <div className="recent__head">
                <h2>最近记录</h2>
                <button type="button" className="text-button" onClick={() => setHistoryOpen(true)}>
                  查看全部
                </button>
              </div>
              {recent.length ? (
                <ul className="recent__list">
                  {recent.map((item) => {
                    const interruptType = recentInterruptTypes[item.diagnosis_id]
                    const meta =
                      item.status === 'waiting_human' && !interruptType
                        ? { label: '等待人工', tone: 'waiting' as const, icon: 'circle-help' }
                        : diagnosisMeta({
                            status: item.status,
                            interrupt: item.status === 'waiting_human' ? { type: interruptType ?? 'clarification' } : null,
                          })
                    return (
                      <li key={item.diagnosis_id}>
                        <button type="button" onClick={() => void openRecent(item)}>
                          <span className="mono recent__time">{formatDateTime(item.finished_at || item.started_at)}</span>
                          <span className="recent__device">{item.device_id}</span>
                          <span className="recent__type">{item.primary_type || '未判定'}</span>
                          <ConfidenceBadge confidence={item.confidence} level={item.confidence_level} size="small" />
                          <StatusBadge meta={meta} size="small" />
                        </button>
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="recent__empty">暂无诊断记录，开始第一次诊断。</p>
              )}
            </section>
          ) : null}
        </aside>

        <main className="right-panel">
          {pageError ? (
            <div className="page-error" role="alert">
              <span>{pageError}</span>
              <button type="button" className="text-button" onClick={() => setPageError(null)}>
                关闭
              </button>
            </div>
          ) : null}
          {viewSnapshot ? (
            <StatusBar
              snapshot={viewSnapshot}
              steps={viewSteps}
              historyView={readOnlyView}
              scopeLabel={scopeLabel}
              onOpenSteps={() => setStepsCollapsed(false)}
              onOpenInterrupt={() => setInterruptOpen(true)}
              onReturn={readOnlyView && stream.snapshot ? returnToLive : undefined}
            />
          ) : null}
          {connectionNotice}
          <div className="right-scroll">
            {viewSnapshot ? (
              <div ref={stepsRef}>
                <StepFlow
                  snapshot={viewSnapshot}
                  steps={viewSteps}
                  collapsed={stepsCollapsed}
                  onToggle={() => setStepsCollapsed((value) => !value)}
                />
              </div>
            ) : null}
            {mainContent}
          </div>

          {batchOpen && batch ? (
            <BatchPanel
              open={batchOpen}
              batch={batch}
              rows={batchStream.rows}
              connection={batchStream.connection}
              onClose={() => setBatchOpen(false)}
              onOpenReport={(diagnosisId) => void openBatchReport(diagnosisId)}
            />
          ) : null}
        </main>
      </div>

      {viewSnapshot ? (
        <InterruptPanel
          open={interruptOpen && !readOnlyView && activeTab !== 'chat'}
          snapshot={viewSnapshot}
          version={viewSnapshot.interrupt?.version ?? 1}
          busy={busy}
          expired={viewSnapshot.status === 'expired'}
          locked={interruptLocked}
          onSubmit={requestResume}
          onEvidence={(entryId) => {
            setSelectedEntry(entryId)
            setEvidenceOpen(true)
          }}
          onRestart={backfillOriginal}
          onClose={() => {
            setInterruptOpen(false)
            setDismissedVersion(viewSnapshot.interrupt?.version ?? viewSnapshot.version ?? null)
          }}
        />
      ) : null}

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onSelect={(summary) => void openHistoryItem(summary)}
        onDeleted={(diagnosisId) => {
          if (viewSnapshot?.diagnosis_id === diagnosisId) {
            setHistorySnapshot(null)
            setPinnedSnapshot(null)
            if (stream.diagnosisId === diagnosisId) stream.clear()
          }
          refreshRecent()
        }}
      />

      <EvidenceDrawer open={evidenceOpen} snapshot={viewSnapshot} selectedEntryId={selectedEntry} onClose={() => setEvidenceOpen(false)} />

      <ConfirmDialog
        open={abortConfirm}
        title="放弃本次诊断？"
        description="放弃后本次诊断将记录为「已中止」，不会生成报告。此操作不可撤销。"
        confirmText="确认放弃"
        cancelText="继续补充"
        busy={busy}
        onConfirm={async () => {
          setAbortConfirm(false)
          await doResume('abort')
        }}
        onCancel={() => setAbortConfirm(false)}
      />

      <ConfirmDialog
        open={deleteConfirm}
        title="删除记录？"
        description="删除后不可恢复，确认删除该诊断记录？"
        confirmText="确认删除"
        cancelText="取消"
        busy={busy}
        onConfirm={() => void deleteCurrent()}
        onCancel={() => setDeleteConfirm(false)}
      />

      <ConfirmDialog
        open={resetConfirm}
        title="收起当前等待中的诊断？"
        description="等待中的诊断会保留在历史记录中，可稍后继续处理。收起后可新建诊断。"
        confirmText="收起并新建"
        cancelText="继续处理"
        tone="default"
        onConfirm={resetWorkspace}
        onCancel={() => setResetConfirm(false)}
      />

      <ConfirmDialog
        open={historyConfirmOpen}
        title="切换历史将结束当前对话会话"
        description="打开历史记录会结束左侧当前对话。对话已产生的诊断记录仍保留在右栏与历史中。"
        confirmText="结束对话并查看历史"
        cancelText="继续对话"
        tone="default"
        onConfirm={beginChatToHistory}
        onCancel={() => setHistoryConfirmOpen(false)}
      />

      <Modal
        open={conflictOpen}
        title="状态已变更，请刷新"
        onClose={() => setConflictOpen(false)}
        width="var(--layout-modal-sm)"
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setConflictOpen(false)}>
              关闭
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={async () => {
                await refreshView()
                setConflictOpen(false)
              }}
            >
              刷新状态
            </button>
          </>
        }
      >
        <p className="confirm-text">诊断可能已被其他操作更新。刷新后会重新拉取中断载荷，不会重放旧决策。</p>
      </Modal>
    </div>
  )
}
