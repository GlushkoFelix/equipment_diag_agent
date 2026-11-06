import { useEffect, useMemo, useRef, useState } from 'react'
import type { DiagnosisSnapshot } from '../api/client'
import type { StepView } from '../hooks/useDiagnosisStream'
import { NODE_LABEL, NODE_ORDER } from '../lib/status'
import { Icon } from './Icon'

type NodeState = 'pending' | 'running' | 'done' | 'failed' | 'timeout' | 'skipped' | 'interrupted' | 'unknown'

const PHASE_LABEL: Record<string, string> = {
  retry: '重试',
  rebuild: '重建',
  interrupt: '等待人工',
  resume: '已恢复',
  degrade: '缺项降级',
  auto_degrade: '批量自动复核',
  timeout: '全局超时',
  user_correct: '用户修正',
}

function nodeStatus(node: string, steps: StepView[], snapshot: DiagnosisSnapshot, index: number): NodeState {
  const nodeSteps = steps.filter((step) => step.node === node)
  const last = nodeSteps[nodeSteps.length - 1]
  if (!last) {
    if (snapshot.status === 'succeeded' || snapshot.status === 'degraded' || snapshot.status === 'degraded_review') {
      return 'unknown'
    }
    if (snapshot.status === 'failed_timeout' || snapshot.status === 'failed') {
      const failedIndex = NODE_ORDER.findIndex((n) =>
        steps.some((s) => s.node === n && (s.phase === 'timeout' || s.phase === 'error')),
      )
      if (failedIndex >= 0 && index > failedIndex) return 'skipped'
      if (failedIndex >= 0 && index < failedIndex) return 'unknown'
    }
    return 'pending'
  }
  if (last.phase === 'timeout') return 'timeout'
  if (last.phase === 'error') return 'failed'
  if (last.phase === 'interrupt') return 'interrupted'
  if (last.phase === 'start') return 'running'
  if (['end', 'resume', 'rebuild', 'degrade', 'retry', 'auto_degrade', 'user_correct'].includes(last.phase)) return 'done'
  return 'pending'
}

function iconFor(state: NodeState) {
  switch (state) {
    case 'running':
      return 'loader'
    case 'done':
      return 'check'
    case 'failed':
    case 'timeout':
      return 'x'
    case 'skipped':
    case 'unknown':
      return 'slash'
    case 'interrupted':
      return 'circle-help'
    default:
      return 'square'
  }
}

export function StepFlow({
  snapshot,
  steps,
  collapsed,
  onToggle,
}: {
  snapshot: DiagnosisSnapshot | null
  steps: StepView[]
  collapsed: boolean
  onToggle: () => void
}) {
  const [expandedNode, setExpandedNode] = useState<string | null>(null)
  const currentRef = useRef<HTMLLIElement>(null)
  const states = useMemo(
    () => (snapshot ? NODE_ORDER.map((node, index) => nodeStatus(node, steps, snapshot, index)) : []),
    [snapshot, steps],
  )
  const executed = states.filter((state) => state === 'done' || state === 'failed' || state === 'timeout').length
  const currentIndex = states.findIndex((state) => state === 'running' || state === 'interrupted')
  const currentLabel = snapshot && currentIndex >= 0 ? NODE_LABEL[NODE_ORDER[currentIndex]] : null

  useEffect(() => {
    if (currentIndex >= 0) {
      currentRef.current?.scrollIntoView({ block: 'nearest' })
    }
  }, [currentIndex, steps.length])

  if (!snapshot) return null

  return (
    <section className={`step-flow ${collapsed ? 'is-collapsed' : ''}`} aria-label="Agent 步骤流">
      <button type="button" className="step-flow__summary" onClick={onToggle} aria-expanded={!collapsed}>
        <span className="step-flow__summary-left">
          <Icon name="checkmark" size={14} />
          <span>
            已执行 {executed}/5 步{currentLabel ? ` · 当前：${currentLabel}` : ''}
          </span>
        </span>
        <span className="step-flow__chevron" aria-hidden="true">
          {collapsed ? '展开' : '收起'}
        </span>
      </button>
      {!collapsed ? (
        <ol className="step-flow__list">
          {NODE_ORDER.map((node, index) => {
            const state = states[index]
            const nodeSteps = steps.filter((step) => step.node === node)
            const last = nodeSteps[nodeSteps.length - 1]
            const tags = [...new Set(nodeSteps.map((step) => step.phase).filter((phase) => PHASE_LABEL[phase]))]
            const isCurrent = state === 'running' || state === 'interrupted'
            return (
              <li
                key={node}
                ref={isCurrent ? currentRef : undefined}
                className={`step-node state-${state}`}
                aria-current={isCurrent ? 'step' : undefined}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setExpandedNode(expandedNode === node ? null : node)
                  }
                }}
                onClick={() => setExpandedNode(expandedNode === node ? null : node)}
              >
                <span className="step-node__rail" aria-hidden="true" />
                <span className="step-node__icon">
                  <Icon name={iconFor(state)} size={16} className={state === 'running' ? 'spin' : undefined} />
                </span>
                <div className="step-node__main">
                  <div className="step-node__title-row">
                    <span className="step-node__title">{NODE_LABEL[node]}</span>
                    {tags.map((tag) => (
                      <span key={tag} className="step-node__tag">
                        {PHASE_LABEL[tag]}
                      </span>
                    ))}
                    {state === 'timeout' ? (
                      <span className="step-node__tag tag-danger">超时中断</span>
                    ) : null}
                    <span className="step-node__duration mono">
                      {last?.duration_ms ? `${last.duration_ms}ms` : state === 'running' ? '执行中' : '—'}
                    </span>
                  </div>
                  <p className="step-node__desc">
                    {last?.summary || (state === 'pending' ? '未开始执行' : state === 'skipped' ? '未执行' : state === 'unknown' ? '未记录' : state === 'interrupted' ? '等待人工处理' : '—')}
                  </p>
                  {expandedNode === node && last?.rule_id ? (
                    <p className="step-node__meta">规则 {last.rule_id}</p>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>
      ) : null}
    </section>
  )
}
