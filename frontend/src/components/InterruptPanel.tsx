import { useEffect, useMemo, useState } from 'react'
import type { ClarificationPayload, DiagnosisSnapshot, FeatureValues, ReviewPayload } from '../api/client'
import { CountdownChip } from './CountdownChip'
import { FeatureFields } from './FeatureFields'
import { Modal } from './Modal'
import { WarningBanner } from './WarningBanner'
import {
  FEATURE_KEYS,
  draftFromValues,
  validateDraft,
  type FeatureDraft,
  type FeatureKey,
} from '../lib/features'
import { confidenceText, formatDateTime } from '../lib/status'

type CommonProps = {
  snapshot: DiagnosisSnapshot
  version: number
  busy: boolean
  expired: boolean
  locked?: boolean
  inline?: boolean
  open?: boolean
  onClose?: () => void
  onSubmit: (decision: 'confirm' | 'supplement' | 'abort', supplement?: FeatureValues) => void
  onEvidence?: (entryId: string) => void
  onRestart: () => void
}

function PartialSummary({ values }: { values: Record<string, unknown> | null | undefined }) {
  if (!values) return null
  const provided = FEATURE_KEYS.filter((key) => values[key] !== null && values[key] !== undefined && values[key] !== '')
  if (!provided.length) return null
  return (
    <div className="partial-summary">
      <p className="partial-summary__title">已提供数据</p>
      <div className="partial-summary__grid">
        {provided.map((key) => (
          <span key={key} className="partial-summary__item mono">
            <span>{key}</span>
            {String(values[key])}
          </span>
        ))}
      </div>
    </div>
  )
}

function ClarificationBody({
  payload,
  version,
  busy,
  expired,
  locked,
  expiresAt,
  onSubmit,
  onRestart,
}: {
  payload: ClarificationPayload
  version: number
  busy: boolean
  expired: boolean
  locked?: boolean
  expiresAt: string
  onSubmit: CommonProps['onSubmit']
  onRestart: () => void
}) {
  const missing = payload.missing_fields ?? []
  const required = missing.map((field) => field.field).filter((field): field is FeatureKey => (FEATURE_KEYS as readonly string[]).includes(field))
  const [draft, setDraft] = useState<FeatureDraft>(() => draftFromValues(payload.partial_features))
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    setDraft(draftFromValues(payload.partial_features))
    setSubmitted(false)
  }, [payload.created_at, version])

  const validation = useMemo(() => validateDraft(draft, []), [draft])
  const canSubmit = !expired && !busy && !locked && validation.providedCount > 0 && !validation.invalid

  if (expired) {
    return (
      <div className="interrupt-body">
        <WarningBanner tone="neutral" title="本次中断已过期">
          等待已超时，最后载荷仅供查看。请以原输入重新发起一次新诊断。
        </WarningBanner>
        <dl className="readonly-facts">
          <div>
            <dt>设备标识</dt>
            <dd>{payload.device_id || '未记录'}</dd>
          </div>
          <div>
            <dt>到期时间</dt>
            <dd>{formatDateTime(expiresAt)}</dd>
          </div>
          <div>
            <dt>缺失字段</dt>
            <dd>{missing.map((field) => field.label).join('、') || '无'}</dd>
          </div>
        </dl>
        <button type="button" className="btn btn-primary" onClick={onRestart}>
          以原输入重新发起
        </button>
      </div>
    )
  }

  return (
    <div className="interrupt-body">
      <div className="interrupt-meta">
        <span>设备标识 {payload.device_id || '未记录'}</span>
        <span>{missing.length} 项缺失</span>
      </div>
      <PartialSummary values={payload.partial_features} />
      <FeatureFields
        draft={draft}
        onChange={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
        missingFields={missing}
        required={required}
        validation={validation}
        disabled={busy || submitted}
        readOnlyFields={FEATURE_KEYS.filter((key) => !required.includes(key))}
      />
      {submitted && validation.providedCount > 0 ? <p className="hint-text">已提交补充，等待服务端确认…</p> : null}
      <div className="interrupt-actions">
        <button type="button" className="btn btn-text btn-danger-text" onClick={() => onSubmit('abort')} disabled={busy || locked}>
          放弃诊断
        </button>
        <div className="interrupt-actions__right">
          <span className="hint-text">{locked ? '正在确认状态…' : '至少填写一个有效字段'}</span>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canSubmit}
            onClick={() => {
              setSubmitted(true)
              onSubmit('supplement', validation.values)
            }}
          >
            {busy ? '提交中…' : '提交补充'}
          </button>
        </div>
      </div>
    </div>
  )
}

const FACTORS = [
  { key: 'rule', label: '规则证据', weight: 0.35 },
  { key: 'coverage', label: '知识覆盖', weight: 0.2 },
  { key: 'llm_self', label: 'LLM 自评', weight: 0.25 },
  { key: 'completeness', label: '数据完整度', weight: 0.2 },
] as const

function ReviewBody({
  payload,
  version,
  busy,
  expired,
  locked,
  onSubmit,
  onEvidence,
  onRestart,
  currentFeatures,
}: {
  payload: ReviewPayload
  version: number
  busy: boolean
  expired: boolean
  locked?: boolean
  onSubmit: CommonProps['onSubmit']
  onEvidence?: (entryId: string) => void
  onRestart: () => void
  currentFeatures?: FeatureValues
}) {
  const round = payload.review_round
  const [supplementOpen, setSupplementOpen] = useState(false)
  const [draft, setDraft] = useState<FeatureDraft>(() => draftFromValues(currentFeatures))
  const [warningSeen, setWarningSeen] = useState(false)

  useEffect(() => {
    setDraft(draftFromValues(currentFeatures))
    setSupplementOpen(false)
    setWarningSeen(false)
  }, [payload.created_at, version, currentFeatures])

  const validation = useMemo(() => validateDraft(draft, []), [draft])
  const canSupplement = round === 1 && !expired && !busy && !locked && validation.providedCount > 0 && !validation.invalid

  if (expired) {
    return (
      <div className="interrupt-body">
        <WarningBanner tone="neutral" title="本次中断已过期">
          等待已超时，结论草案仅供查看。请以原输入重新发起一次新诊断。
        </WarningBanner>
        <div className="review-draft">
          <p className="review-draft__type">{payload.primary_type}</p>
          <p className="review-draft__confidence">置信度 {confidenceText(payload.confidence, payload.confidence_level)}</p>
          <p className="review-draft__reason">{payload.reason}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onRestart}>
          以原输入重新发起
        </button>
      </div>
    )
  }

  return (
    <div className="interrupt-body">
      <div className="review-draft">
        <div className="review-draft__head">
          <div>
            <p className="review-draft__eyebrow">结论草案</p>
            <p className="review-draft__type">{payload.primary_type}</p>
          </div>
          <div className="review-draft__confidence">
            <span className="mono">{confidenceText(payload.confidence, payload.confidence_level)}</span>
            <span className="review-draft__level">需人工确认</span>
          </div>
        </div>
        <p className="review-draft__reason">{payload.reason}</p>
        {(payload.secondary_types ?? []).length ? (
          <p className="review-draft__secondary">候选：{payload.secondary_types.join('、')}</p>
        ) : null}
      </div>

      <section className="review-section">
        <h3>置信度分解</h3>
        {payload.confidence_breakdown ? (
          <table className="mini-table">
            <thead>
              <tr>
                <th scope="col">因子</th>
                <th scope="col">权重</th>
                <th scope="col">取值</th>
                <th scope="col">加权</th>
              </tr>
            </thead>
            <tbody>
              {FACTORS.map((factor) => {
                const value = Number((payload.confidence_breakdown as Record<string, number>)[factor.key] ?? 0)
                return (
                  <tr key={factor.key}>
                    <td>{factor.label}</td>
                    <td className="num mono">{factor.weight.toFixed(2)}</td>
                    <td className="num mono">{value.toFixed(2)}</td>
                    <td className="num mono">{(value * factor.weight).toFixed(3)}</td>
                  </tr>
                )
              })}
              <tr>
                <td>扣分</td>
                <td className="num">—</td>
                <td className="num mono">-{Number(payload.confidence_breakdown.penalties ?? 0).toFixed(2)}</td>
                <td className="num mono">-{Number(payload.confidence_breakdown.penalties ?? 0).toFixed(3)}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="hint-text">分解数据缺失</p>
        )}
      </section>

      <section className="review-section">
        <h3>证据</h3>
        {(payload.evidence_refs ?? []).length ? (
          <ul className="evidence-list">
            {payload.evidence_refs.map((item) => (
              <li key={item.entry_id}>
                <button type="button" className="link-button" onClick={() => onEvidence?.(item.entry_id)}>
                  {item.entry_id}
                </button>
                <span>{item.title}</span>
                {item.feature ? (
                  <span className="mono evidence-list__value">
                    {item.feature} {String(item.value)} {item.unit || ''}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint-text">本次诊断无检索命中</p>
        )}
      </section>

      {round === 1 ? (
        supplementOpen ? (
          <section className="review-section">
            <div className="review-supplement">
              <WarningBanner tone="waiting" title="补充后将重建检索、推理与报告">
                诊断修订号 +1；旧版本诊断结果不可导出。
              </WarningBanner>
              <FeatureFields
                draft={draft}
                onChange={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
                required={[]}
                validation={validation}
                disabled={busy}
              />
              <div className="interrupt-actions">
                <button type="button" className="btn btn-text" onClick={() => setSupplementOpen(false)} disabled={busy}>
                  收起补充
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={!canSupplement}
                  onClick={() => {
                    setWarningSeen(true)
                    onSubmit('supplement', validation.values)
                  }}
                >
                  {busy ? '重建中…' : '提交补充并重建'}
                </button>
              </div>
              {warningSeen ? <p className="hint-text">已提交补充，下游重建中…</p> : null}
            </div>
          </section>
        ) : null
      ) : (
        <p className="hint-text">第 2 轮确认仅保留确认与放弃；补充入口已关闭。</p>
      )}

      <div className="interrupt-actions">
        <button type="button" className="btn btn-text btn-danger-text" onClick={() => onSubmit('abort')} disabled={busy || locked}>
          放弃诊断
        </button>
        <div className="interrupt-actions__right">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={round === 2 || busy || locked}
            title={round === 2 ? '本次诊断已补充过一次，请确认或放弃' : locked ? '正在确认状态…' : undefined}
            onClick={() => setSupplementOpen(true)}
          >
            补充数据
          </button>
          <button type="button" className="btn btn-primary" onClick={() => onSubmit('confirm')} disabled={busy || locked}>
            {busy ? '提交中…' : '确认结论'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function InterruptPanel(props: CommonProps) {
  const { snapshot, inline, open, onClose } = props
  const interrupt = snapshot.interrupt
  if (!interrupt) return null
  const isClarification = interrupt.type === 'clarification'
  const title = isClarification ? `需要补充数据` : '需要你确认'
  const subtitle = isClarification ? (
    <>
      本次诊断缺少 {interrupt.payload.missing_fields?.length ?? 0} 项关键数据，补充后可继续。
      <CountdownChip expiresAt={interrupt.expires_at} />
    </>
  ) : (
    <>
      置信度 {confidenceText((interrupt.payload as ReviewPayload).confidence, (interrupt.payload as ReviewPayload).confidence_level)} · 系统建议人工确认后发布。
      {(interrupt.payload as ReviewPayload).review_round === 2 ? <span className="inline-flag">第 2 轮确认</span> : null}
      <CountdownChip expiresAt={interrupt.expires_at} />
    </>
  )

  const body = isClarification ? (
    <ClarificationBody
      payload={interrupt.payload as ClarificationPayload}
      version={interrupt.version}
      busy={props.busy}
      expired={props.expired}
      locked={props.locked}
      expiresAt={interrupt.expires_at}
      onSubmit={props.onSubmit}
      onRestart={props.onRestart}
    />
  ) : (
    <ReviewBody
      payload={interrupt.payload as ReviewPayload}
      version={interrupt.version}
      busy={props.busy}
      expired={props.expired}
      locked={props.locked}
      onSubmit={props.onSubmit}
      onEvidence={props.onEvidence}
      onRestart={props.onRestart}
      currentFeatures={snapshot.features?.normalized as FeatureValues | undefined}
    />
  )

  if (inline) {
    return (
      <section className={`interrupt-inline ${props.expired ? 'is-expired' : ''}`} aria-label={title}>
        <header className="interrupt-inline__head">
          <div>
            <h3>{title}</h3>
            <div className="interrupt-inline__subtitle">{subtitle}</div>
          </div>
          {props.expired ? <span className="inline-flag">已过期</span> : null}
        </header>
        {body}
      </section>
    )
  }

  return (
    <Modal
      open={!!open}
      title={title}
      subtitle={subtitle}
      onClose={() => onClose?.()}
      width={isClarification ? 'var(--layout-modal-md)' : 'var(--layout-modal-lg)'}
    >
      {body}
    </Modal>
  )
}
