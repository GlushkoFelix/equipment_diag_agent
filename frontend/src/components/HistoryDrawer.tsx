import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type DiagnosisSummary } from '../api/client'
import { diagnosisMeta, formatDateTime, inputTypeLabel } from '../lib/status'
import { ConfirmDialog } from './ConfirmDialog'
import { ConfidenceBadge } from './ConfidenceBadge'
import { Drawer } from './Drawer'
import { EmptyState } from './EmptyState'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'

export function HistoryDrawer({
  open,
  onClose,
  onSelect,
  onDeleted,
}: {
  open: boolean
  onClose: () => void
  onSelect: (summary: DiagnosisSummary) => void
  onDeleted: (diagnosisId: string) => void
}) {
  const [items, setItems] = useState<DiagnosisSummary[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const [confidence, setConfidence] = useState('')
  const [keyword, setKeyword] = useState('')
  const [deleting, setDeleting] = useState<DiagnosisSummary | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [interruptTypes, setInterruptTypes] = useState<Record<string, 'clarification' | 'review'>>({})

  const load = useCallback(
    async (targetPage = page) => {
      setLoading(true)
      setError(null)
      try {
        const result = await api.listDiagnoses({
          page: targetPage,
          page_size: 20,
          status: status || undefined,
          confidence_level: confidence || undefined,
          keyword: keyword.trim() || undefined,
        })
        setItems(result.items)
        setPage(result.page)
        setTotalPages(result.total_pages)
        setTotal(result.total)
        const waiting = result.items.filter((item) => item.status === 'waiting_human')
        if (waiting.length) {
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
          setInterruptTypes((current) => {
            const next = { ...current }
            for (const [id, type] of resolved) {
              if (type) next[id] = type
            }
            return next
          })
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : '历史记录加载失败')
      } finally {
        setLoading(false)
      }
    },
    [page, status, confidence, keyword],
  )

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => void load(1), 300)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, status, confidence, keyword])

  useEffect(() => {
    if (open) void load(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function confirmDelete() {
    if (!deleting) return
    setDeleteBusy(true)
    try {
      await api.deleteDiagnosis(deleting.diagnosis_id)
      onDeleted(deleting.diagnosis_id)
      setDeleting(null)
      await load(page)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '删除失败，请稍后重试')
      setDeleting(null)
    } finally {
      setDeleteBusy(false)
    }
  }

  return (
    <>
      <Drawer open={open} title="历史记录" subtitle={`共 ${total} 条`} onClose={onClose}>
        <div className="history-filters">
          <label className="inline-field">
            <span>状态</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">全部</option>
              <option value="waiting_human">等待补充/确认</option>
              <option value="succeeded">完成</option>
              <option value="degraded">缺项降级</option>
              <option value="degraded_review">待人工复核</option>
              <option value="aborted">已中止</option>
              <option value="failed">失败</option>
              <option value="failed_timeout">超时失败</option>
              <option value="expired">已过期</option>
            </select>
          </label>
          <label className="inline-field">
            <span>置信度</span>
            <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
              <option value="">全部</option>
              <option value="high">高（≥0.8）</option>
              <option value="medium">中（0.5–0.8）</option>
              <option value="low">低（&lt;0.5）</option>
            </select>
          </label>
          <label className="inline-field history-filters__keyword">
            <span>关键词</span>
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="设备标识或报告标题" />
          </label>
        </div>

        <div className="history-list">
          {loading && items.length === 0
            ? [0, 1, 2].map((index) => <div key={index} className="skeleton-row" aria-hidden="true" />)
            : null}
          {error ? (
            <div className="error-card" role="alert">
              <p>{error}</p>
              <button type="button" className="btn btn-secondary" onClick={() => void load(page)}>
                重新加载
              </button>
            </div>
          ) : null}
          {!loading && !error && !items.length ? (
            <EmptyState title="暂无符合筛选条件的记录" description="调整筛选条件，或返回工作台发起一次诊断。" />
          ) : null}
          {items.map((item) => {
            const interruptType = interruptTypes[item.diagnosis_id]
            const meta =
              item.status === 'waiting_human' && !interruptType
                ? { label: '等待人工', tone: 'waiting' as const, icon: 'circle-help' }
                : diagnosisMeta({
                    status: item.status,
                    interrupt: item.status === 'waiting_human' ? { type: interruptType ?? 'clarification' } : null,
                  })
            return (
              <div key={item.diagnosis_id} className="history-item">
                <button type="button" className="history-item__main" onClick={() => onSelect(item)}>
                  <div className="history-item__row">
                    <span className="mono history-item__time">{formatDateTime(item.started_at || item.finished_at)}</span>
                    <span className="history-item__device">{item.device_id}</span>
                    <StatusBadge meta={meta} size="small" />
                  </div>
                  <div className="history-item__row history-item__row--sub">
                    <span>{item.primary_type || '未判定'}</span>
                    <ConfidenceBadge confidence={item.confidence} level={item.confidence_level} size="small" />
                    <span>{inputTypeLabel(item.input_type)}</span>
                    {item.auto_review ? <span className="inline-flag">自动复核</span> : null}
                  </div>
                </button>
                <button
                  type="button"
                  className="icon-button icon-button--tiny"
                  aria-label={`删除 ${item.device_id} 的记录`}
                  onClick={() => setDeleting(item)}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
            )
          })}
        </div>

        <div className="history-pagination">
          <button type="button" className="btn btn-text" disabled={page <= 1 || loading} onClick={() => void load(page - 1)}>
            上一页
          </button>
          <span className="mono">
            第 {page} / {Math.max(1, totalPages)} 页
          </span>
          <button type="button" className="btn btn-text" disabled={page >= totalPages || loading} onClick={() => void load(page + 1)}>
            下一页
          </button>
        </div>
        {loading && items.length > 0 ? <div className="thin-progress" aria-hidden="true" /> : null}
      </Drawer>

      <ConfirmDialog
        open={!!deleting}
        title="删除记录？"
        description="删除后不可恢复，确认删除该诊断记录？"
        confirmText="确认删除"
        cancelText="取消"
        busy={deleteBusy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </>
  )
}
