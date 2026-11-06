import { confidenceText, confidenceTone } from '../lib/status'

export function ConfidenceBadge({
  confidence,
  level,
  withBar = false,
  size = 'default',
}: {
  confidence: number | null | undefined
  level: string | null | undefined
  withBar?: boolean
  size?: 'small' | 'default'
}) {
  const text = confidenceText(confidence, level)
  const tone = confidenceTone(level)
  const label = level === 'high' ? '高' : level === 'low' ? '低' : level === 'medium' ? '中' : '未知'
  const aria = confidence === null || confidence === undefined ? '置信度未知' : `置信度 ${confidence.toFixed(2)}，${label}`
  return (
    <span className={`confidence-badge tone-${tone} ${size === 'small' ? 'is-small' : ''}`} aria-label={aria}>
      <span className="confidence-badge__value mono">{text}</span>
      {withBar && confidence !== null && confidence !== undefined ? (
        <span className="confidence-badge__bar" aria-hidden="true">
          <span style={{ width: `${Math.round(confidence * 100)}%` }} />
        </span>
      ) : null}
    </span>
  )
}
