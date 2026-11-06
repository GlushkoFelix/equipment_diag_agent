import { useEffect, useRef } from 'react'
import type { DiagnosisSnapshot } from '../api/client'
import { Drawer } from './Drawer'
import { EmptyState } from './EmptyState'

type Hit = NonNullable<DiagnosisSnapshot['retrieval']>['hits'][number]

export function EvidenceDrawer({
  open,
  snapshot,
  selectedEntryId,
  onClose,
}: {
  open: boolean
  snapshot: DiagnosisSnapshot | null
  selectedEntryId: string | null
  onClose: () => void
}) {
  const hits: Hit[] = (snapshot?.retrieval?.hits ?? []).slice(0, 5)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open || !selectedEntryId) return
    const target = listRef.current?.querySelector<HTMLElement>(`[data-entry="${selectedEntryId}"]`)
    target?.scrollIntoView({ block: 'nearest' })
  }, [open, selectedEntryId])

  const selectedOffline = !!selectedEntryId && !hits.some((hit) => hit.entry_id === selectedEntryId)

  return (
    <Drawer open={open} title="检索依据" subtitle="Top-5 命中" width="var(--layout-evidence-w)" onClose={onClose}>
      <div ref={listRef} className="evidence-drawer">
        {selectedOffline ? (
          <div className="warning-banner tone-neutral" role="status">
            <div className="warning-banner__body">
              <p className="warning-banner__title">条目已下线</p>
              <div className="warning-banner__text">引用条目 {selectedEntryId} 已从当前知识库下线，历史引用仍保留。</div>
            </div>
          </div>
        ) : null}
        {hits.length ? (
          hits.map((hit, index) => (
            <article
              key={hit.entry_id}
              data-entry={hit.entry_id}
              className={`evidence-item ${selectedEntryId === hit.entry_id ? 'is-selected' : ''}`}
            >
              <header className="evidence-item__head">
                <span className="mono">{hit.entry_id}</span>
                <span className="mono">#{index + 1}</span>
              </header>
              <p className="evidence-item__title">{hit.title}</p>
              <div className="evidence-item__meta">
                <span>{hit.fault_type || '—'}</span>
                <span className="mono">分数 {hit.score?.toFixed(2)}</span>
              </div>
              <p className="evidence-item__snippet">{hit.snippet}</p>
            </article>
          ))
        ) : (
          <EmptyState title="本次诊断无检索命中" description="知识库未覆盖该故障模式时，报告中的结论为未验证假设。" />
        )}
      </div>
    </Drawer>
  )
}
