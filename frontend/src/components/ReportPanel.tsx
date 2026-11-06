import { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { DiagnosisSnapshot } from '../api/client'
import { confidenceText, diagnosisMeta, formatDateTime, formatDuration, inputTypeLabel } from '../lib/status'
import { ConfidenceBadge } from './ConfidenceBadge'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'
import { WarningBanner } from './WarningBanner'

function withCitationLinks(markdown: string) {
  return markdown
    .replace(/^\s*#\s+.*(?:\r?\n)+/, '')
    .replace(/\[([A-Z]{1,4}-[A-Z0-9]+(?:-\d+)?)\]/g, '[$1](#evidence-$1)')
}

export function ReportPanel({
  snapshot,
  historyView,
  onEvidence,
  onExport,
  onCopy,
  onDelete,
}: {
  snapshot: DiagnosisSnapshot
  historyView?: boolean
  onEvidence: (entryId: string) => void
  onExport: () => void
  onCopy: () => void
  onDelete: () => void
}) {
  const [showAllBanners, setShowAllBanners] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const meta = diagnosisMeta(snapshot)
  const missing = snapshot.report_elements_check?.missing ?? []
  const confidence = snapshot.confidence_level
  const lowConfidence = confidence === 'medium' || confidence === 'low'
  const banners: { tone: 'waiting' | 'success' | 'neutral' | 'info'; title: string; text: string }[] = []

  if (snapshot.status === 'degraded') {
    banners.push({
      tone: 'waiting',
      title: snapshot.auto_review ? '缺项降级 → 待人工复核（批量模式）' : '报告缺项',
      text: `报告缺少以下要素：${missing.join('、') || '—'}。系统已按降级方式发布，请结合人工判断使用。`,
    })
  }
  if (snapshot.status === 'degraded_review') {
    banners.push({
      tone: 'waiting',
      title: '待人工复核（批量模式）',
      text: '本报告由系统在批量任务中自动生成，未经人工确认。',
    })
  }
  if (lowConfidence) {
    banners.push({
      tone: 'waiting',
      title: '建议人工复核',
      text: `置信度 ${confidenceText(snapshot.confidence, snapshot.confidence_level)}，建议人工复核后再用于维修决策。`,
    })
  }
  if (snapshot.knowledge_status === 'missing') {
    banners.push({
      tone: 'neutral',
      title: '知识库未覆盖',
      text: '知识库未覆盖该故障模式，以下内容为未验证假设与通用安全建议，不构成确定性维修步骤。',
    })
  }

  const visibleBanners = showAllBanners ? banners : banners.slice(0, 2)
  const hiddenCount = banners.length - visibleBanners.length
  const markdown = useMemo(() => withCitationLinks(snapshot.report?.markdown ?? ''), [snapshot.report?.markdown])

  return (
    <article className="report-panel" aria-label="诊断报告">
      <header className="report-head">
        <div className="report-head__title-row">
          <div>
            <h1>{snapshot.report_title || `${snapshot.device_id} 诊断报告`}</h1>
            <p className="report-head__meta">
              {snapshot.device_id} · {inputTypeLabel(snapshot.input_type)} · 生成于 {formatDateTime(snapshot.report_meta?.generated_at || snapshot.finished_at)} · 耗时{' '}
              {formatDuration(snapshot.duration_ms)} · 修订 v{snapshot.diagnosis_revision} · 重试 {snapshot.retry_count} 次
            </p>
          </div>
          <div className="report-head__badges">
            <StatusBadge meta={meta} suffix={snapshot.auto_review ? '自动复核' : undefined} />
            <ConfidenceBadge confidence={snapshot.confidence} level={snapshot.confidence_level} withBar />
            {snapshot.human_decision === 'confirm' ? (
              <span className="status-badge tone-success">
                <Icon name="check" size={14} />
                已人工确认
              </span>
            ) : null}
            {snapshot.auto_review && snapshot.status !== 'degraded' ? (
              <span className="status-badge tone-waiting">待人工复核（批量模式）</span>
            ) : null}
          </div>
        </div>
        {visibleBanners.map((banner) => (
          <WarningBanner key={banner.title} tone={banner.tone} title={banner.title}>
            {banner.text}
          </WarningBanner>
        ))}
        {hiddenCount > 0 ? (
          <button type="button" className="text-button" onClick={() => setShowAllBanners(true)}>
            查看全部提示（+{hiddenCount}）
          </button>
        ) : null}
        {historyView ? (
          <dl className="history-facts">
            <div>
              <dt>输入摘要</dt>
              <dd>
                {snapshot.input_summary?.file_name
                  ? `${snapshot.input_summary.file_name} 第 ${snapshot.input_summary.row_no} 行`
                  : snapshot.input_summary?.text_excerpt || '未记录'}
              </dd>
            </div>
            <div>
              <dt>Agent 轨迹</dt>
              <dd>{snapshot.trace_steps?.length ? `${snapshot.trace_steps.length} 条事件` : '未记录'}</dd>
            </div>
            <div>
              <dt>检索命中</dt>
              <dd>{snapshot.retrieval?.hits?.length ? `${snapshot.retrieval.hits.length} 条` : '未记录'}</dd>
            </div>
            <div>
              <dt>修订 / 重试</dt>
              <dd className="mono">
                v{snapshot.diagnosis_revision} / {snapshot.retry_count}
              </dd>
            </div>
          </dl>
        ) : null}
      </header>

      <div className="report-markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          skipHtml
          components={{
            a: ({ href, children }) => {
              if (href?.startsWith('#evidence-')) {
                const entryId = href.slice('#evidence-'.length)
                return (
                  <button type="button" className="citation" onClick={() => onEvidence(entryId)}>
                    {children}
                  </button>
                )
              }
              return (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              )
            },
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>

      <footer className="report-actions">
        <button type="button" className="btn btn-primary" onClick={onExport}>
          <Icon name="download" size={16} />
          导出 Markdown
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCopy}>
          复制
        </button>
        <div className="more-menu">
          <button type="button" className="btn btn-text" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen} aria-haspopup="menu">
            更多
          </button>
          {menuOpen ? (
            <div className="more-menu__list" role="menu">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  onDelete()
                }}
              >
                <Icon name="x" size={14} />
                删除记录
              </button>
            </div>
          ) : null}
        </div>
        <span className="report-actions__note">报告内容仅用于辅助判断，导出内容与页面一致。</span>
      </footer>
    </article>
  )
}
