import type { BatchTaskSummary } from '../api/client'
import { batchSegments } from '../lib/status'

export function SegmentedProgress({ batch }: { batch: BatchTaskSummary }) {
  const { segments, completed, total, percent } = batchSegments(batch)
  if (total === 0) {
    return <p className="hint-text">文件无有效数据行</p>
  }
  const frozen = batch.status === 'cancelled' || batch.status === 'timed_out'
  return (
    <div className="segmented-progress">
      <div
        className={`segmented-progress__track ${batch.status === 'running' ? 'is-running' : ''} ${frozen ? 'is-frozen' : ''}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`已完成 ${completed} / ${total} 行，${percent}%`}
      >
        {segments.map((segment) =>
          segment.count > 0 ? (
            <span
              key={segment.key}
              className={`segmented-progress__segment ${segment.className}`}
              style={{ width: `${(segment.count / total) * 100}%` }}
              title={`${segment.label} ${segment.count}`}
            />
          ) : null,
        )}
      </div>
      <div className="segmented-progress__legend" aria-hidden="true">
        {segments.map((segment) => (
          <span key={segment.key} className="legend-item">
            <span className={`legend-swatch ${segment.className}`} />
            {segment.label}
            <span className="mono">{segment.count}</span>
          </span>
        ))}
      </div>
      <div className="segmented-progress__caption">
        <span className="mono">
          已完成 {completed} / {total} 行，{percent}%
        </span>
        <span className="hint-text">已取消与待执行不计入已完成</span>
      </div>
    </div>
  )
}
