import type { ReactNode } from 'react'

function MachineGlyph() {
  return (
    <svg className="empty-state__glyph" width="120" height="90" viewBox="0 0 120 90" fill="none" aria-hidden="true">
      <rect x="14.5" y="24.5" width="78" height="44" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M14.5 36.5H92.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="38" cy="53" r="9" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="38" cy="53" r="2.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M56 47h20M56 53h14M56 59h23" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M92.5 43h8v14h-8" stroke="currentColor" strokeWidth="1.5" />
      <path d="M20 68v8M88 68v8" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 30l-3 4 3 4M100 50l3 4-3 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function EmptyState({
  title,
  description,
  action,
  secondary,
}: {
  title: string
  description: string
  action?: ReactNode
  secondary?: ReactNode
}) {
  return (
    <div className="empty-state">
      <MachineGlyph />
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__desc">{description}</p>
      {action || secondary ? (
        <div className="empty-state__actions">
          {action}
          {secondary}
        </div>
      ) : null}
    </div>
  )
}
