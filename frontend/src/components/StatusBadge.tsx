import { Icon } from './Icon'
import type { StatusMeta, Tone } from '../lib/status'

export function StatusBadge({
  meta,
  size = 'default',
  suffix,
  title,
}: {
  meta: StatusMeta
  size?: 'small' | 'default'
  suffix?: string
  title?: string
}) {
  return (
    <span
      className={`status-badge tone-${meta.tone} ${size === 'small' ? 'is-small' : ''}`}
      title={title}
      aria-label={`${meta.label}${suffix ? `，${suffix}` : ''}`}
    >
      <Icon name={meta.icon} size={14} />
      <span>{meta.label}</span>
      {suffix ? <span className="status-badge__suffix">{suffix}</span> : null}
    </span>
  )
}

export function ToneDot({ tone }: { tone: Tone }) {
  return <span className={`tone-dot tone-${tone}`} aria-hidden="true" />
}
