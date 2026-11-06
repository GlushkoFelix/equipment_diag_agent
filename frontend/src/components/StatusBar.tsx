import type { ReactNode } from 'react'
import type { DiagnosisSnapshot } from '../api/client'
import type { StepView } from '../hooks/useDiagnosisStream'
import { NODE_LABEL, NODE_ORDER, confidenceText, diagnosisMeta, formatClock, formatDuration } from '../lib/status'
import { CountdownChip } from './CountdownChip'
import { Icon } from './Icon'

function executedCount(steps: StepView[]) {
  const nodes = new Set(steps.filter((step) => step.phase === 'end' || step.phase === 'timeout' || step.phase === 'error').map((step) => step.node))
  return NODE_ORDER.filter((node) => nodes.has(node)).length
}

export function StatusBar({
  snapshot,
  steps,
  historyView,
  scopeLabel,
  onOpenSteps,
  onOpenInterrupt,
  onReturn,
}: {
  snapshot: DiagnosisSnapshot | null
  steps: StepView[]
  historyView?: boolean
  scopeLabel?: string
  onOpenSteps: () => void
  onOpenInterrupt: () => void
  onReturn?: () => void
}) {
  if (!snapshot) return null
  const meta = diagnosisMeta(snapshot)
  const executed = executedCount(steps)
  const current = [...steps].reverse().find((step) => step.phase === 'start')
  const missing = snapshot.interrupt?.type === 'clarification' ? snapshot.interrupt.payload.missing_fields?.length ?? 0 : 0
  const reportMissing = snapshot.report_elements_check?.missing ?? []
  const live = snapshot.status === 'failed' || snapshot.status === 'failed_timeout' ? 'assertive' : 'polite'

  let context: string = NODE_LABEL[current?.node ?? ''] || '等待服务端事件'
  if (snapshot.status === 'waiting_human') {
    context =
      snapshot.interrupt?.type === 'clarification'
        ? `缺少 ${missing} 项关键数据，补充后可继续`
        : `置信度 ${confidenceText(snapshot.confidence, snapshot.confidence_level)}，请确认结论或补充数据`
  } else if (snapshot.status === 'succeeded') {
    context = '报告已生成，可导出或复制'
  } else if (snapshot.status === 'degraded') {
    context = `报告缺少 ${reportMissing.length} 项要素，已按降级方式发布`
  } else if (snapshot.status === 'degraded_review') {
    context = '批量模式自动生成，未经人工确认'
  } else if (snapshot.status === 'aborted') {
    context = '本次诊断已放弃，未生成报告'
  } else if (snapshot.status === 'failed') {
    context = snapshot.error ? `${snapshot.error.code}：${snapshot.error.message}` : '诊断执行失败'
  } else if (snapshot.status === 'failed_timeout') {
    context = `全局 15 秒熔断，未生成报告；已完成 ${executed}/5 步`
  } else if (snapshot.status === 'expired') {
    context = '等待超时，仅可查看最后载荷并以原输入重新发起'
  }

  let right: ReactNode = null
  if (snapshot.status === 'running') {
    right = (
      <button type="button" className="text-button mono" onClick={onOpenSteps}>
        已执行 {executed}/5 步
      </button>
    )
  } else if (snapshot.status === 'waiting_human') {
    right = historyView ? (
      <span className="status-bar__meta">只读载荷</span>
    ) : (
      <button type="button" className="text-button" onClick={onOpenInterrupt}>
        <CountdownChip expiresAt={snapshot.interrupt?.expires_at} />
      </button>
    )
  } else if (snapshot.status === 'succeeded') {
    right = <span className="status-bar__meta mono">耗时 {formatDuration(snapshot.duration_ms)}</span>
  } else if (snapshot.status === 'degraded') {
    right = (
      <span className="status-bar__meta">
        <button type="button" className="text-button" onClick={onOpenSteps}>
          缺项 {reportMissing.length} 项
        </button>
        {snapshot.auto_review ? <span className="inline-flag">待人工复核（批量模式）</span> : null}
      </span>
    )
  } else if (snapshot.status === 'degraded_review') {
    right = <span className="status-bar__meta">批量模式</span>
  } else if (snapshot.status === 'aborted') {
    right = <span className="status-bar__meta">已放弃</span>
  } else if (snapshot.status === 'failed') {
    right = <span className="status-bar__meta mono">错误码 {snapshot.error?.code ?? 'UNKNOWN'}</span>
  } else if (snapshot.status === 'failed_timeout') {
    right = <span className="status-bar__meta mono">15.0s · 无报告</span>
  } else if (snapshot.status === 'expired') {
    right = <span className="status-bar__meta mono">到期 {formatClock(snapshot.interrupt?.expires_at)}</span>
  }

  return (
    <div className={`status-bar accent-${meta.tone} ${live === 'assertive' ? 'is-assertive' : ''}`} role="status" aria-live={live}>
      <span className="status-bar__accent" aria-hidden="true" />
      <div className="status-bar__left">
        <Icon name={meta.icon} size={20} className={snapshot.status === 'running' ? 'spin' : undefined} />
        <span className="status-bar__label">{meta.label}</span>
        <span className="status-bar__scope">{scopeLabel ?? (historyView ? '历史记录' : snapshot.batch ? '批量模式' : '单条诊断')}</span>
        {historyView && onReturn ? (
          <button type="button" className="text-button" onClick={onReturn}>
            返回当前诊断
          </button>
        ) : null}
      </div>
      <div className="status-bar__context" title={context}>
        {context}
      </div>
      <div className="status-bar__right">{right}</div>
    </div>
  )
}
