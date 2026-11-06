import { useEffect, useMemo, useState } from 'react'
import type { FeatureValues } from '../api/client'
import { EXAMPLE_DRAFT, FEATURE_KEYS, draftFromValues, emptyDraft, validateDraft, type FeatureDraft } from '../lib/features'
import { FeatureFields } from './FeatureFields'

export function FormPanel({
  busy,
  locked = false,
  initialValues,
  onSubmit,
}: {
  busy: boolean
  locked?: boolean
  initialValues?: FeatureValues | null
  onSubmit: (values: FeatureValues) => Promise<boolean>
}) {
  const [draft, setDraft] = useState<FeatureDraft>(() => (initialValues ? draftFromValues(initialValues) : emptyDraft()))
  const validation = useMemo(() => validateDraft(draft, [...FEATURE_KEYS]), [draft])
  const missingCount = Object.keys(validation.errors).length
  const canSubmit = !busy && !locked && !validation.invalid

  useEffect(() => {
    if (initialValues) setDraft(draftFromValues(initialValues))
  }, [initialValues])

  return (
    <form
      className="panel-stack"
      onSubmit={async (event) => {
        event.preventDefault()
        if (!canSubmit) return
        await onSubmit(validation.values)
      }}
    >
      <div className="panel-toolbar">
        <span className="panel-toolbar__title">7 项标准特征</span>
        <button type="button" className="text-button" onClick={() => setDraft(EXAMPLE_DRAFT)} disabled={busy}>
          填入示例
        </button>
      </div>
      <FeatureFields
        draft={draft}
        onChange={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
        required={[...FEATURE_KEYS]}
        validation={validation}
        disabled={busy}
      />
      <div className="form-footer">
        <span className={`form-footer__hint ${missingCount ? 'is-error' : ''}`}>
          {locked ? '当前诊断运行中，请等待完成后再提交' : missingCount ? `还有 ${missingCount} 项待填写或修正` : '字段校验通过'}
        </span>
        <button type="submit" className="btn btn-primary btn-lg" disabled={!canSubmit} title={locked ? '当前诊断运行中' : undefined}>
          {busy ? '正在提交…' : '开始诊断'}
        </button>
      </div>
    </form>
  )
}
