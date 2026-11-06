import type { ReactNode } from 'react'
import { Icon } from './Icon'
import type { Tone } from '../lib/status'

export function WarningBanner({
  tone,
  title,
  children,
  action,
  live = false,
}: {
  tone: Tone
  title: string
  children?: ReactNode
  action?: ReactNode
  live?: boolean
}) {
  return (
    <div className={`warning-banner tone-${tone}`} role={live ? 'alert' : 'status'}>
      <Icon name={tone === 'danger' || tone === 'danger-deep' ? 'x' : tone === 'success' ? 'check' : tone === 'waiting' ? 'alert-triangle' : 'alert'} size={18} />
      <div className="warning-banner__body">
        <p className="warning-banner__title">{title}</p>
        {children ? <div className="warning-banner__text">{children}</div> : null}
      </div>
      {action ? <div className="warning-banner__action">{action}</div> : null}
    </div>
  )
}
