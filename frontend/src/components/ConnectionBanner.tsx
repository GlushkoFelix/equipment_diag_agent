import type { ReactNode } from 'react'
import { Icon } from './Icon'

export function ConnectionBanner({
  kind,
  children,
  action,
}: {
  kind: 'retry' | 'poll' | 'offline'
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <div className={`connection-banner connection-banner--${kind}`} role="status">
      <Icon name={kind === 'offline' ? 'wifi-off' : 'refresh'} size={16} />
      <span>{children}</span>
      {action}
    </div>
  )
}
