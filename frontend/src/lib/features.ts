import type { FeatureValues, MissingField } from '../api/client'

export const FEATURE_KEYS = [
  'device_id',
  'product_type',
  'air_temp_k',
  'process_temp_k',
  'rotational_speed_rpm',
  'torque_nm',
  'tool_wear_min',
] as const

export type FeatureKey = (typeof FEATURE_KEYS)[number]
export type FeatureDraft = Record<FeatureKey, string>

export const FEATURE_DEFS: Record<FeatureKey, { label: string; unit: string | null; example: string; kind: 'text' | 'number' | 'select'; min?: number; max?: number }> = {
  device_id: { label: '设备标识', unit: null, example: '3号机', kind: 'text' },
  product_type: { label: '产品类型', unit: 'L/M/H', example: 'M', kind: 'select' },
  air_temp_k: { label: '空气温度', unit: 'K', example: '298.1', kind: 'number', min: 250, max: 350 },
  process_temp_k: { label: '工艺温度', unit: 'K', example: '308.6', kind: 'number', min: 250, max: 350 },
  rotational_speed_rpm: { label: '转速', unit: 'rpm', example: '1551', kind: 'number', min: 0, max: 3000 },
  torque_nm: { label: '扭矩', unit: 'Nm', example: '42.8', kind: 'number', min: 0, max: 100 },
  tool_wear_min: { label: '刀具磨损', unit: 'min', example: '0', kind: 'number', min: 0, max: 300 },
}

export const EXAMPLE_DRAFT: FeatureDraft = {
  device_id: '3号机',
  product_type: 'M',
  air_temp_k: '298.1',
  process_temp_k: '308.6',
  rotational_speed_rpm: '1551',
  torque_nm: '42.8',
  tool_wear_min: '0',
}

export function emptyDraft(): FeatureDraft {
  return {
    device_id: '',
    product_type: '',
    air_temp_k: '',
    process_temp_k: '',
    rotational_speed_rpm: '',
    torque_nm: '',
    tool_wear_min: '',
  }
}

function stringify(value: unknown) {
  if (value === null || value === undefined) return ''
  return String(value)
}

export function draftFromValues(values: Partial<FeatureValues> | Record<string, unknown> | null | undefined): FeatureDraft {
  const source = (values ?? {}) as Record<string, unknown>
  const draft = emptyDraft()
  for (const key of FEATURE_KEYS) draft[key] = stringify(source[key])
  return draft
}

export function draftFromMissing(fields: MissingField[], values: Record<string, unknown> | null | undefined): FeatureDraft {
  const draft = draftFromValues(values)
  for (const key of FEATURE_KEYS) {
    if (!fields.some((field) => field.field === key)) {
      const value = (values ?? {})[key]
      if (value !== null && value !== undefined && value !== '') draft[key] = stringify(value)
    }
  }
  return draft
}

export type ValidationResult = {
  errors: Partial<Record<FeatureKey, string>>
  warnings: string[]
  blocking: string | null
  values: FeatureValues
  providedCount: number
  invalid: boolean
}

export function validateDraft(draft: FeatureDraft, required: FeatureKey[]): ValidationResult {
  const errors: Partial<Record<FeatureKey, string>> = {}
  const warnings: string[] = []
  const values: FeatureValues = {}
  let providedCount = 0

  for (const key of FEATURE_KEYS) {
    const raw = draft[key].trim()
    const def = FEATURE_DEFS[key]
    if (!raw) {
      if (required.includes(key)) errors[key] = `请填写${def.label}`
      continue
    }
    providedCount += 1
    if (key === 'device_id') {
      if (!/^[A-Za-z0-9_\-\u4e00-\u9fff]{1,64}$/.test(raw)) {
        errors[key] = '仅允许中文、字母、数字、-、_，长度 1–64'
      } else {
        values.device_id = raw
      }
      continue
    }
    if (key === 'product_type') {
      if (!['L', 'M', 'H'].includes(raw)) errors[key] = '仅支持 L / M / H'
      else values.product_type = raw
      continue
    }
    const num = Number(raw)
    if (!Number.isFinite(num)) {
      errors[key] = '请输入数值'
    } else if (def.min !== undefined && def.max !== undefined && (num < def.min || num > def.max)) {
      errors[key] = `允许范围 ${def.min}–${def.max}${def.unit ? ` ${def.unit}` : ''}`
    } else {
      values[key] = num as never
    }
  }

  let blocking: string | null = null
  const rpm = values.rotational_speed_rpm
  const torque = values.torque_nm
  const air = values.air_temp_k
  const process = values.process_temp_k
  if (rpm === 0 && torque === 0) blocking = '设备停机（转速与扭矩均为 0），无法诊断。'
  else if (rpm === 0 && torque !== null && torque !== undefined && torque > 0) blocking = '转速与扭矩矛盾，请核对数据。'
  if (torque === 0 && rpm !== null && rpm !== undefined && rpm > 0) warnings.push('空载/零扭矩，将在报告中标注。')
  if (air !== null && air !== undefined && process !== null && process !== undefined && process < air) {
    warnings.push('温度倒挂，将记录数据异常并在报告中说明。')
  }

  return {
    errors,
    warnings,
    blocking,
    values,
    providedCount,
    invalid: Object.keys(errors).length > 0 || blocking !== null,
  }
}

export function stripNulls(input: Partial<FeatureValues>): { device_id: string } & Partial<Omit<FeatureValues, 'device_id'>> {
  const output: Record<string, unknown> = {}
  for (const key of FEATURE_KEYS) {
    const value = input[key]
    if (value !== null && value !== undefined && value !== '') output[key] = value
  }
  return output as { device_id: string } & Partial<Omit<FeatureValues, 'device_id'>>
}

export function draftToValues(draft: FeatureDraft): Partial<FeatureValues> {
  const { values } = validateDraft(draft, [])
  return values
}

export function valuesFromInput(input: Record<string, unknown> | null | undefined): FeatureValues {
  const source = input ?? {}
  const values: FeatureValues = {}
  for (const key of FEATURE_KEYS) {
    const value = source[key]
    if (value === null || value === undefined || value === '') continue
    if (key === 'device_id' || key === 'product_type') values[key] = String(value)
    else {
      const num = Number(value)
      if (Number.isFinite(num)) values[key] = num
    }
  }
  return values
}
