import { useCountdown } from '../hooks/useCountdown'
import { formatCountdown } from '../lib/status'

export function CountdownChip({ expiresAt, prefix = '剩余' }: { expiresAt: string | null | undefined; prefix?: string }) {
  const { seconds } = useCountdown(expiresAt)
  const critical = seconds <= 300
  const zero = seconds <= 0
  return (
    <span
      className={`countdown-chip mono ${critical ? 'is-critical' : ''} ${zero ? 'is-zero' : ''}`}
      aria-label={zero ? '等待已到期，正在确认状态' : `剩余 ${formatCountdown(seconds)}`}
    >
      {zero ? '正在确认状态…' : `${prefix} ${formatCountdown(seconds)}`}
      {critical && !zero ? <span className="countdown-chip__hint">即将过期</span> : null}
    </span>
  )
}
