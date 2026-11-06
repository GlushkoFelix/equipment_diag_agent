import { useEffect, useMemo, useState } from 'react'
import { ApiError, api, notifyAuthExpired, type BatchRowDetail, type BatchRowSummary, type BatchTaskSummary } from '../api/client'
import type { BatchConnection } from '../hooks/useBatchStream'
import { batchSegments, batchTaskMeta, batchRowMeta, formatCountdown, formatDuration, rowNeedsReport } from '../lib/status'
import { useCountdown } from '../hooks/useCountdown'
import { useApp } from '../store/AppContext'
import { ConfirmDialog } from './ConfirmDialog'
import { CountdownChip } from './CountdownChip'
import { Drawer } from './Drawer'
import { Icon } from './Icon'
import { SegmentedProgress } from './SegmentedProgress'
import { StatusBadge } from './StatusBadge'

function averageRemaining(rows: BatchRowSummary[], total: number) {
  const done = rows.filter((row) => (row.duration_ms ?? 0) > 0)
  if (!done.length) return null
  const sample = done.slice(-20)
  const avg = sample.reduce((sum, row) => sum + (row.duration_ms ?? 0), 0) / sample.length
  const remaining = Math.max(0, total - done.length)
  return Math.round((avg * remaining) / 1000)
}

export function BatchPanel({
  open,
  batch,
  rows,
  connection,
  onClose,
  onOpenReport,
}: {
  open: boolean
  batch: BatchTaskSummary | null
  rows: BatchRowSummary[]
  connection: BatchConnection
  onClose: () => void
  onOpenReport: (diagnosisId: string) => void
}) {
  const [closeConfirm, setCloseConfirm] = useState(false)
  const [cancelConfirm, setCancelConfirm] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [detail, setDetail] = useState<BatchRowDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showRows, setShowRows] = useState(true)
  const [page, setPage] = useState(1)
  const pageSize = 50
  const { expired: deadlinePassed } = useCountdown(batch?.timeout_deadline)
  const { pushToast } = useApp()

  useEffect(() => {
    setPage(1)
    setDetail(null)
    setCancelling(false)
    setActionError(null)
  }, [batch?.batch_task_id])

  useEffect(() => {
    if (batch?.status === 'cancelled' || batch?.status === 'timed_out') setCancelling(false)
  }, [batch?.status])

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize))
  const pageRows = useMemo(() => rows.slice((page - 1) * pageSize, page * pageSize), [rows, page])
  const failedRows = rows.filter((row) => row.status === 'failed' || row.status === 'failed_timeout').slice(0, 5)
  const terminal = batch ? ['completed', 'partially_failed', 'failed', 'cancelled', 'timed_out'].includes(batch.status) : false
  const canExport = rows.some((row) => ['succeeded', 'degraded', 'degraded_review', 'failed', 'failed_timeout'].includes(row.status))
  const running = batch?.status === 'queued' || batch?.status === 'running'
  const cancellingView = cancelling || (!!batch?.cancel_requested && running)
  const remainingSeconds = batch ? averageRemaining(rows, batch.total_rows) : null
  const segments = batch ? batchSegments(batch) : null

  if (!open || !batch) return null

  const meta = batchTaskMeta(batch.status)

  async function openDetail(row: BatchRowSummary) {
    if (row.status === 'running' || row.status === 'pending') return
    setDetailLoading(true)
    try {
      const result = await api.getBatchRow(batch.batch_task_id, row.row_id)
      setDetail(result)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : '行详情加载失败')
    } finally {
      setDetailLoading(false)
    }
  }

  async function cancelBatch() {
    setCancelling(true)
    setActionError(null)
    try {
      await api.cancelBatch(batch.batch_task_id)
      setCancelConfirm(false)
      pushToast('任务已取消，已完成结果已保留')
    } catch (err) {
      setCancelling(false)
      setActionError(err instanceof ApiError ? err.message : '取消请求未生效，任务可能仍在运行，请刷新后重试。')
      setCancelConfirm(false)
    }
  }

  return (
    <>
      <section className="batch-panel" aria-label="批量任务进度">
        <header className="batch-panel__head">
          <div className="batch-panel__title">
            <h2>批量任务</h2>
            <span className="mono">{batch.batch_task_id}</span>
            <StatusBadge meta={meta} suffix={cancellingView ? '取消中…' : undefined} />
          </div>
          <div className="batch-panel__head-actions">
            <span className="batch-panel__file">{batch.file_name}</span>
            <button type="button" className="icon-button" aria-label="最小化批量面板" onClick={() => (running ? setCloseConfirm(true) : onClose())}>
              <Icon name="minimize" size={16} />
            </button>
          </div>
        </header>

        {connection === 'retrying' ? (
          <div className="connection-banner" role="status">
            <Icon name="wifi-off" size={16} />
            进度更新暂时中断，正在重连；展示的是最后一次服务端快照。
          </div>
        ) : null}
        {connection === 'polling' ? (
          <div className="connection-banner connection-banner--poll" role="status">
            <Icon name="refresh" size={16} />
            已切换为轮询更新，每 2 秒补拉任务快照。
          </div>
        ) : null}
        {actionError ? (
          <div className="error-card error-card--inline" role="alert">
            <p>{actionError}</p>
            <button type="button" className="btn btn-secondary" onClick={() => setActionError(null)}>
              关闭提示
            </button>
          </div>
        ) : null}

        <div className="batch-stats">
          {[
            ['总行数', batch.total_rows],
            ['已完成', segments?.completed ?? 0],
            ['成功', batch.counts.succeeded],
            ['缺项降级', batch.counts.degraded],
            ['待复核', batch.counts.degraded_review],
            ['失败', batch.counts.failed],
            ['超时失败', batch.counts.failed_timeout],
            ['已取消', batch.counts.cancelled],
          ].map(([label, value]) => (
            <div key={String(label)} className="batch-stat">
              <span className="batch-stat__label">{label}</span>
              <span className="batch-stat__value mono">{value}</span>
            </div>
          ))}
        </div>

        <SegmentedProgress batch={batch} />

        <div className="batch-time">
          <div>
            <span className="batch-time__label">任务时限</span>
            {deadlinePassed && running ? (
              <span className="batch-time__critical">已到时限，正在停止调度…</span>
            ) : (
              <CountdownChip expiresAt={batch.timeout_deadline} prefix="剩余" />
            )}
          </div>
          <div>
            <span className="batch-time__label">预计剩余</span>
            <span className="mono">
              {cancellingView || terminal || remainingSeconds === null
                ? running && remainingSeconds === null
                  ? '估算中'
                  : '—'
                : `约 ${formatCountdown(remainingSeconds)}`}
            </span>
          </div>
          <div>
            <span className="batch-time__label">上限</span>
            <span className="mono">60:00</span>
          </div>
        </div>

        {failedRows.length ? (
          <div className="batch-failures">
            <p className="batch-failures__title">失败 / 超时行（前 5 条）</p>
            <div className="batch-failures__list">
              {failedRows.map((row) => (
                <button key={row.row_id} type="button" className="text-button" onClick={() => void openDetail(row)}>
                  第 {row.row_no} 行 · {row.device_id || '设备标识缺失'} · {row.error_code || row.status}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="batch-actions">
          <button type="button" className="btn btn-secondary" onClick={() => setShowRows((value) => !value)}>
            {showRows ? '收起结果列表' : '查看结果列表'}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!canExport}
            title={!canExport ? '暂无可导出结果' : undefined}
            onClick={async () => {
              try {
                const response = await fetch(api.batchExportUrl(batch.batch_task_id), { credentials: 'same-origin' })
                if (response.status === 401) {
                  notifyAuthExpired()
                  return
                }
                if (!response.ok) throw new Error('导出失败')
                const blob = await response.blob()
                const url = URL.createObjectURL(blob)
                const anchor = document.createElement('a')
                anchor.href = url
                anchor.download = `批量汇总_${batch.batch_task_id}.csv`
                anchor.click()
                anchor.remove()
                window.setTimeout(() => URL.revokeObjectURL(url), 1000)
              } catch {
                setActionError('汇总导出失败，请重试；已完成结果不受影响。')
              }
            }}
          >
            导出汇总 CSV
          </button>
          {running ? (
            <button type="button" className="btn btn-text btn-danger-text" disabled={cancellingView} onClick={() => setCancelConfirm(true)}>
              {cancellingView ? '取消中…' : '取消任务'}
            </button>
          ) : null}
          {terminal ? (
            <button type="button" className="btn btn-text" onClick={onClose}>
              关闭面板
            </button>
          ) : null}
          <span className="batch-actions__spacer" />
          {batch.status === 'running' && remainingSeconds !== null ? (
            <span className="hint-text">预计剩余按最近 20 行平均耗时估算</span>
          ) : null}
        </div>

        {showRows ? (
          <div className="batch-rows">
            <table className="data-table">
              <caption className="sr-only">批量任务行结果</caption>
              <thead>
                <tr>
                  <th scope="col">行号</th>
                  <th scope="col">设备标识</th>
                  <th scope="col">主类型</th>
                  <th scope="col">置信度</th>
                  <th scope="col">状态</th>
                  <th scope="col">耗时</th>
                  <th scope="col">摘要</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row) => {
                  const rowMeta = batchRowMeta(row.status)
                  return (
                    <tr key={row.row_id} className={`row-${row.status}`}>
                      <td className="mono">{row.row_no}</td>
                      <td>{row.device_id || '—'}</td>
                      <td>—</td>
                      <td className="num mono">—</td>
                      <td>
                        <span className="row-badges">
                          <StatusBadge meta={rowMeta} size="small" suffix={row.status === 'degraded_review' ? '批量模式' : undefined} />
                          {row.status === 'degraded' && row.auto_review ? (
                            <span className="status-badge tone-waiting is-small">待人工复核（批量模式）</span>
                          ) : null}
                        </span>
                      </td>
                      <td className="num mono">{formatDuration(row.duration_ms)}</td>
                      <td className="batch-rows__summary">
                        {row.status === 'failed_timeout' ? '全局超时，无报告' : row.status === 'failed' ? `${row.error_field || '—'} / ${row.error_code || '—'}` : row.report_summary || '—'}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="text-button"
                          disabled={row.status === 'pending' || row.status === 'running'}
                          onClick={() => void openDetail(row)}
                        >
                          查看详情
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="batch-rows__pagination">
              <button type="button" className="btn btn-text" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                上一页
              </button>
              <span className="mono">
                第 {page} / {totalPages} 页
              </span>
              <button type="button" className="btn btn-text" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>
                下一页
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <Drawer
        open={!!detail}
        title="行详情"
        subtitle={detail ? `第 ${detail.row.row_no} 行 · ${detail.row.device_id || '设备标识缺失'}` : ''}
        onClose={() => setDetail(null)}
      >
        {detailLoading ? <p className="hint-text">加载中…</p> : null}
        {detail ? (
          <div className="row-detail">
            <StatusBadge meta={batchRowMeta(detail.row.status)} suffix={detail.row.status === 'degraded_review' ? '批量模式' : undefined} />
            {detail.row.status === 'degraded' && detail.row.auto_review ? (
              <span className="status-badge tone-waiting">待人工复核（批量模式）</span>
            ) : null}
            <dl className="readonly-facts">
              <div>
                <dt>耗时</dt>
                <dd className="mono">{formatDuration(detail.row.duration_ms)}</dd>
              </div>
              <div>
                <dt>诊断标识</dt>
                <dd className="mono">{detail.row.diagnosis_id || '无'}</dd>
              </div>
              <div>
                <dt>错误字段 / 错误码</dt>
                <dd className="mono">
                  {detail.row.error_field || '—'} / {detail.row.error_code || '—'}
                </dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>{detail.diagnosis_status || detail.row.status}</dd>
              </div>
            </dl>
            {detail.row.status === 'failed_timeout' ? (
              <div className="warning-banner tone-danger" role="alert">
                <div className="warning-banner__body">
                  <p className="warning-banner__title">全局超时，无报告</p>
                  <div className="warning-banner__text">该行执行超过 15 秒上限，未生成报告。可查看已完成步骤，无行级重试。</div>
                </div>
              </div>
            ) : null}
            {detail.row.status === 'cancelled' ? (
              <p className="hint-text">取消原因：{detail.row.error_code === 'TASK_TIMEOUT' ? '任务到达时限' : '用户取消'}</p>
            ) : null}
            {rowNeedsReport(detail.row) && detail.report_url && detail.row.diagnosis_id ? (
              <button type="button" className="btn btn-primary" onClick={() => onOpenReport(detail.row.diagnosis_id as string)}>
                查看完整报告
              </button>
            ) : (
              <p className="hint-text">无报告</p>
            )}
            <p className="hint-text">批量行不提供确认、补充或行级重试。</p>
          </div>
        ) : null}
      </Drawer>

      <ConfirmDialog
        open={cancelConfirm}
        title="取消批量任务？"
        description="取消后不再调度新行；未开始行标记为已取消；已完成与执行中的结果会保留，此操作不可撤销。"
        confirmText="确认取消"
        cancelText="继续运行"
        busy={cancelling}
        onConfirm={() => void cancelBatch()}
        onCancel={() => setCancelConfirm(false)}
      />
      <ConfirmDialog
        open={closeConfirm}
        title="关闭批量面板？"
        description="批量任务仍在运行，关闭面板不会停止任务。可通过顶部“批量任务”指示器重新打开。"
        confirmText="关闭面板"
        cancelText="继续查看"
        tone="default"
        onConfirm={() => {
          setCloseConfirm(false)
          onClose()
        }}
        onCancel={() => setCloseConfirm(false)}
      />
    </>
  )
}
