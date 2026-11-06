import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { FeatureValues, MissingField, SourceSpan } from '../api/client'
import { FeatureFields } from './FeatureFields'
import { Icon } from './Icon'
import { draftFromValues, validateDraft, type FeatureDraft } from '../lib/features'

export type ExtractionLike = {
  extraction_status: string
  features: FeatureValues
  missing_fields: MissingField[]
  recommended_action: string
  field_confidence?: Record<string, number>
  source_spans?: SourceSpan[]
}

function HighlightedText({ text, spans }: { text: string; spans?: SourceSpan[] }) {
  if (!spans?.length) return <p className="source-text">{text}</p>
  const sorted = [...spans].sort((a, b) => a.start - b.start)
  const parts: ReactNode[] = []
  let cursor = 0
  sorted.forEach((span, index) => {
    if (span.start > cursor) parts.push(text.slice(cursor, span.start))
    parts.push(
      <mark key={`${span.field}-${index}`} title={`抽取字段：${span.field}`}>
        {text.slice(span.start, span.end)}
      </mark>,
    )
    cursor = span.end
  })
  if (cursor < text.length) parts.push(text.slice(cursor))
  return <p className="source-text">{parts}</p>
}

export function ExtractionCard({
  extraction,
  text,
  disabled,
  onConfirm,
  onUseForm,
  onDismiss,
}: {
  extraction: ExtractionLike
  text: string
  disabled?: boolean
  onConfirm: (values: FeatureValues, text: string) => void
  onUseForm?: () => void
  onDismiss?: () => void
}) {
  const [draft, setDraft] = useState<FeatureDraft>(() => draftFromValues(extraction.features))
  const validation = useMemo(() => validateDraft(draft, ['device_id']), [draft])
  const missing = extraction.missing_fields ?? []
  const canConfirm = !disabled && !validation.invalid && !!draft.device_id.trim()
  const missingCount = missing.length

  return (
    <section className="extraction-card" aria-label="抽取确认卡">
      <header className="extraction-card__head">
        <div>
          <h3>抽取确认</h3>
          <p className="extraction-card__sub">
            已识别 {7 - missingCount} 项{missingCount ? `，${missingCount} 项待补充` : ''}。设备标识必填，其余缺失将在诊断中追问。
          </p>
        </div>
        <span className={`status-badge tone-${extraction.extraction_status === 'ok' ? 'success' : missingCount === 7 ? 'danger' : 'waiting'}`}>
          <Icon name={extraction.extraction_status === 'ok' ? 'check' : 'alert-triangle'} size={14} />
          {extraction.extraction_status === 'ok' ? '抽取完整' : extraction.extraction_status === 'failed' ? '抽取失败' : '部分抽取'}
        </span>
      </header>

      <div className="extraction-card__source">
        <p className="extraction-card__source-label">原文对照</p>
        <HighlightedText text={text} spans={extraction.source_spans} />
      </div>

      <FeatureFields
        draft={draft}
        onChange={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
        missingFields={missing}
        required={['device_id']}
        validation={validation}
        confidence={extraction.field_confidence}
        disabled={disabled}
      />

      <div className="extraction-card__actions">
        {onDismiss ? (
          <button type="button" className="btn btn-text" onClick={onDismiss} disabled={disabled}>
            收起
          </button>
        ) : (
          <span />
        )}
        <div className="extraction-card__actions-right">
          {onUseForm ? (
            <button type="button" className="btn btn-text" onClick={onUseForm} disabled={disabled}>
              改用表单
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canConfirm}
            title={!draft.device_id.trim() ? '设备标识缺失，请先补填' : undefined}
            onClick={() => onConfirm(validation.values, text)}
          >
            {disabled ? '提交中…' : '确认并诊断'}
          </button>
        </div>
      </div>
    </section>
  )
}
