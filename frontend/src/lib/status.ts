import type { BatchRowSummary, BatchTaskSummary } from '../api/client'

export type Tone = 'info' | 'waiting' | 'success' | 'danger' | 'danger-deep' | 'neutral'

export type StatusMeta = {
  label: string
  tone: Tone
  icon: string
}

const DIAGNOSIS_META: Record<string, StatusMeta> = {
  running: { label: '运行中', tone: 'info', icon: 'loader' },
  succeeded: { label: '完成', tone: 'success', icon: 'check' },
  degraded: { label: '缺项降级', tone: 'waiting', icon: 'alert-triangle' },
  degraded_review: { label: '待人工复核', tone: 'waiting', icon: 'clipboard-list' },
  aborted: { label: '已中止', tone: 'neutral', icon: 'ban' },
  failed: { label: '失败', tone: 'danger', icon: 'x' },
  failed_timeout: { label: '超时失败', tone: 'danger-deep', icon: 'timer-off' },
  expired: { label: '已过期', tone: 'neutral', icon: 'alarm' },
}

export function diagnosisMeta(snapshot: { status: string; interrupt?: { type: string } | null } | null): StatusMeta {
  if (!snapshot) return { label: '空闲', tone: 'neutral', icon: 'dot' }
  if (snapshot.status === 'waiting_human') {
    return snapshot.interrupt?.type === 'review'
      ? { label: '等待确认', tone: 'waiting', icon: 'clipboard-check' }
      : { label: '等待补充', tone: 'waiting', icon: 'circle-help' }
  }
  return DIAGNOSIS_META[snapshot.status] ?? { label: '状态数据异常，请刷新', tone: 'neutral', icon: 'alert' }
}

export const BATCH_TASK_META: Record<string, StatusMeta> = {
  queued: { label: '排队中', tone: 'info', icon: 'clock' },
  running: { label: '运行中', tone: 'info', icon: 'loader' },
  completed: { label: '已完成', tone: 'success', icon: 'check' },
  partially_failed: { label: '部分失败', tone: 'waiting', icon: 'alert-triangle' },
  failed: { label: '任务失败', tone: 'danger', icon: 'x' },
  cancelled: { label: '已取消', tone: 'neutral', icon: 'slash' },
  timed_out: { label: '已超时', tone: 'waiting', icon: 'timer-off' },
}

export const BATCH_ROW_META: Record<string, StatusMeta> = {
  pending: { label: '待执行', tone: 'neutral', icon: 'dot' },
  running: { label: '执行中', tone: 'info', icon: 'loader' },
  succeeded: { label: '成功', tone: 'success', icon: 'check' },
  degraded: { label: '缺项降级', tone: 'waiting', icon: 'alert-triangle' },
  degraded_review: { label: '待人工复核', tone: 'waiting', icon: 'clipboard-list' },
  failed: { label: '失败', tone: 'danger', icon: 'x' },
  failed_timeout: { label: '超时失败', tone: 'danger-deep', icon: 'timer-off' },
  cancelled: { label: '已取消', tone: 'neutral', icon: 'slash' },
}

export function batchTaskMeta(status: string): StatusMeta {
  return BATCH_TASK_META[status] ?? { label: '状态数据异常，请刷新', tone: 'neutral', icon: 'alert' }
}

export function batchRowMeta(status: string): StatusMeta {
  return BATCH_ROW_META[status] ?? { label: '状态数据异常，请刷新', tone: 'neutral', icon: 'alert' }
}

export function confidenceText(confidence: number | null | undefined, level: string | null | undefined) {
  if (confidence === null || confidence === undefined) return '—'
  const label = level === 'high' ? '高' : level === 'low' ? '低' : level === 'medium' ? '中' : '—'
  return `${confidence.toFixed(2)} · ${label}`
}

export function confidenceTone(level: string | null | undefined): Tone {
  if (level === 'high') return 'success'
  if (level === 'low') return 'danger'
  return 'waiting'
}

export function inputTypeLabel(type: string) {
  const labels: Record<string, string> = {
    csv_single: 'CSV 单条',
    csv_batch: 'CSV 批量',
    form: '表单',
    nl: '自然语言',
    chat: '对话',
  }
  return labels[type] ?? type
}

export function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未记录'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatClock(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date)
}

export function formatCountdown(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds))
  const mm = String(Math.floor(safe / 60)).padStart(2, '0')
  const ss = String(safe % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export type BatchSegments = {
  completed: number
  total: number
  percent: number
  segments: { key: string; label: string; count: number; className: string }[]
}

/** UIUX §8.2: progress is derived from counts, never from the server `progress` field. */
export function batchSegments(batch: BatchTaskSummary): BatchSegments {
  const counts = batch.counts
  const total = batch.total_rows
  const completed = counts.succeeded + counts.degraded + counts.degraded_review + counts.failed + counts.failed_timeout
  const pending = counts.pending + counts.running
  return {
    completed,
    total,
    percent: total ? Math.round((completed / total) * 100) : 0,
    segments: [
      { key: 'succeeded', label: '成功', count: counts.succeeded, className: 'seg-succeeded' },
      { key: 'degraded', label: '缺项降级', count: counts.degraded, className: 'seg-degraded' },
      { key: 'degraded_review', label: '待复核', count: counts.degraded_review, className: 'seg-review' },
      { key: 'failed', label: '失败', count: counts.failed, className: 'seg-failed' },
      { key: 'failed_timeout', label: '超时失败', count: counts.failed_timeout, className: 'seg-timeout' },
      { key: 'cancelled', label: '已取消', count: counts.cancelled, className: 'seg-cancelled' },
      { key: 'pending', label: '待执行', count: pending, className: 'seg-pending' },
    ],
  }
}

export function rowNeedsReport(row: BatchRowSummary) {
  return row.status === 'succeeded' || row.status === 'degraded' || row.status === 'degraded_review'
}

export const NODE_ORDER = ['orchestrator', 'parse_input', 'retrieve', 'diagnose', 'report'] as const
export const NODE_LABEL: Record<string, string> = {
  orchestrator: '总控',
  parse_input: '数据读取',
  retrieve: '知识检索',
  diagnose: '诊断推理',
  report: '报告生成',
}
