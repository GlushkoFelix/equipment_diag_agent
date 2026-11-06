import { useId } from 'react'
import type { MissingField } from '../api/client'
import { FEATURE_DEFS, FEATURE_KEYS, type FeatureDraft, type FeatureKey, type ValidationResult } from '../lib/features'

export function FeatureFields({
  draft,
  onChange,
  missingFields = [],
  required,
  validation,
  confidence,
  disabled = false,
  readOnlyFields = [],
  showRequiredErrors = false,
}: {
  draft: FeatureDraft
  onChange: (key: FeatureKey, value: string) => void
  missingFields?: MissingField[]
  required: FeatureKey[]
  validation: ValidationResult
  confidence?: Record<string, number>
  disabled?: boolean
  readOnlyFields?: FeatureKey[]
  showRequiredErrors?: boolean
}) {
  const uid = useId()
  return (
    <div className="feature-fields">
      {FEATURE_KEYS.map((key) => {
        const def = FEATURE_DEFS[key]
        const inputId = `${uid}-${key}`
        const missing = missingFields.find((field) => field.field === key)
        const present = draft[key] !== ''
        const requiredEmpty = required.includes(key) && !draft[key].trim()
        const shownError = validation.errors[key] && !(requiredEmpty && !showRequiredErrors) ? validation.errors[key] : undefined
        const lowConfidence = present && confidence?.[key] !== undefined && confidence[key] < 0.8
        const readOnly = disabled || readOnlyFields.includes(key)
        return (
          <div
            key={key}
            className={`field-row ${missing ? 'is-missing' : ''} ${shownError ? 'has-error' : ''} ${readOnly ? 'is-readonly' : ''}`}
          >
            <div className="field-row__meta">
              <label htmlFor={inputId}>
                {def.label}
                {required.includes(key) ? <span className="required-mark">必填</span> : null}
              </label>
              <span className="field-row__unit">{def.unit || '—'}</span>
            </div>
            <div className="field-row__control">
              {def.kind === 'select' ? (
                <select
                  id={inputId}
                  value={draft[key]}
                  onChange={(event) => onChange(key, event.target.value)}
                  disabled={readOnly}
                  aria-invalid={!!shownError}
                  aria-describedby={shownError ? `${uid}-error-${key}` : undefined}
                >
                  <option value="">请选择</option>
                  <option value="L">L</option>
                  <option value="M">M</option>
                  <option value="H">H</option>
                </select>
              ) : (
                <input
                  id={inputId}
                  type={def.kind === 'number' ? 'text' : 'text'}
                  inputMode={def.kind === 'number' ? 'decimal' : undefined}
                  value={draft[key]}
                  placeholder={def.example}
                  onChange={(event) => onChange(key, event.target.value)}
                  disabled={readOnly}
                  aria-invalid={!!shownError}
                  aria-describedby={shownError ? `${uid}-error-${key}` : undefined}
                />
              )}
              <div className="field-row__hint">
                {shownError ? (
                  <span className="field-error" id={`${uid}-error-${key}`}>
                    {shownError}
                  </span>
                ) : missing ? (
                  <span className="field-reason">
                    {missing.reason === 'MISSING' ? '缺失' : missing.reason === 'INVALID' ? '非法值' : '超出范围'} · 示例 {String(missing.example)}
                  </span>
                ) : lowConfidence ? (
                  <span className="field-low">待确认 · 抽取置信度偏低</span>
                ) : (
                  <span className="field-example">示例 {def.example}</span>
                )}
              </div>
            </div>
          </div>
        )
      })}
      {validation.warnings.length ? (
        <div className="field-warning" role="status">
          {validation.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}
      {validation.blocking ? (
        <div className="field-error field-error--blocking" role="alert">
          {validation.blocking}
        </div>
      ) : null}
    </div>
  )
}
