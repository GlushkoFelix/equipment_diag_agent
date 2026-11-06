import type { components } from './schema'

export type User = components['schemas']['User']
export type AuthResponse = components['schemas']['AuthResponse']
export type SystemConfig = components['schemas']['SystemConfig']
export type UploadPrecheck = components['schemas']['UploadPrecheck']
export type Mapping = components['schemas']['Mapping']
export type MappingScheme = components['schemas']['MappingScheme']
export type MappingPreviewResponse = components['schemas']['MappingPreviewResponse']
export type NlExtractResponse = components['schemas']['NlExtractResponse']
export type FeatureValues = components['schemas']['FeatureValues']
export type DiagnosisSnapshot = components['schemas']['DiagnosisSnapshot']
export type DiagnosisStatus = components['schemas']['DiagnosisStatus']
export type DiagnosisSummary = components['schemas']['DiagnosisSummary']
export type DiagnosisCreateResponse = components['schemas']['DiagnosisCreateResponse']
export type ChatSessionDetail = components['schemas']['ChatSessionDetail']
export type ChatMessage = components['schemas']['ChatMessage']
export type ChatMessageResponse = components['schemas']['ChatMessageResponse']
export type ChatExtraction = components['schemas']['ChatExtraction']
export type ChatConfirmResponse = components['schemas']['ChatConfirmResponse']
export type BatchTaskSummary = components['schemas']['BatchTaskSummary']
export type BatchRowSummary = components['schemas']['BatchRowSummary']
export type BatchRowDetail = components['schemas']['BatchRowDetail']
export type EvalBatchSummary = components['schemas']['EvalBatchSummary']
export type EvalDetail = components['schemas']['EvalDetail']
export type EvalSample = components['schemas']['EvalSample']
export type Interrupt = components['schemas']['Interrupt']
export type ClarificationPayload = components['schemas']['ClarificationPayload']
export type ReviewPayload = components['schemas']['ReviewPayload']
export type MissingField = components['schemas']['MissingField']
export type ElementsCheck = components['schemas']['ElementsCheck']
export type SourceSpan = components['schemas']['SourceSpan']

export class ApiError extends Error {
  status: number
  code: string
  requestId: string
  details?: Record<string, unknown>
  retryAfter: number | null

  constructor(status: number, payload: unknown, retryAfter: number | null = null) {
    const body = (payload ?? {}) as {
      error?: { code?: string; message?: string; request_id?: string; details?: Record<string, unknown> }
    }
    const error = body.error
    super(error?.message || '请求失败，请稍后重试')
    this.status = status
    this.code = error?.code || 'UNKNOWN_ERROR'
    this.requestId = error?.request_id || ''
    this.details = error?.details
    this.retryAfter = retryAfter
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: unknown
  formData?: FormData
  idempotencyKey?: string
  signal?: AbortSignal
  raw?: boolean
}

const API_BASE = '/api/v1'

export function notifyAuthExpired() {
  window.dispatchEvent(new CustomEvent('auth:expired'))
}

function newIdempotencyKey() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const method = options.method || 'GET'
  let body: BodyInit | undefined

  if (options.formData) {
    body = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body,
    credentials: 'same-origin',
    signal: options.signal,
  })

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    const error = new ApiError(response.status, payload, Number(response.headers.get('Retry-After')) || null)
    if (response.status === 401 && path !== '/auth/me' && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
      notifyAuthExpired()
    }
    throw error
  }

  if (response.status === 204) return undefined as T
  if (options.raw) return response as unknown as T
  return (await response.json()) as T
}

export const api = {
  login: (username: string, password: string) =>
    request<AuthResponse>('/auth/login', { method: 'POST', body: { username, password } }),
  register: (username: string, password: string, passwordConfirm: string) =>
    request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: { username, password, password_confirm: passwordConfirm },
    }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<AuthResponse>('/auth/me'),
  config: () => request<SystemConfig>('/system/config'),

  uploadCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<UploadPrecheck>('/uploads', { method: 'POST', formData: form })
  },
  mappingPreview: (
    uploadId: string,
    payload: { mapping: Mapping; mode: 'single' | 'batch'; row_no?: number | null; default_device_id?: string | null },
  ) =>
    request<MappingPreviewResponse>(`/uploads/${uploadId}/mapping/preview`, {
      method: 'POST',
      body: payload,
    }),

  nlExtract: (text: string) =>
    request<NlExtractResponse>('/nl/extract', { method: 'POST', body: { text, input_type: 'nl' } }),

  createChatSession: () => request<{ session_id: string; status: string; created_at: string }>('/chat/sessions', { method: 'POST' }),
  getChatSession: (sessionId: string) => request<ChatSessionDetail>(`/chat/sessions/${sessionId}`),
  sendChatMessage: (sessionId: string, text: string) =>
    request<ChatMessageResponse>(`/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: { text },
      idempotencyKey: newIdempotencyKey(),
    }),
  confirmChat: (
    sessionId: string,
    payload: {
      message_id?: string
      text: string
      features: { device_id: string } & Partial<Omit<FeatureValues, 'device_id'>>
    },
  ) =>
    request<ChatConfirmResponse>(`/chat/sessions/${sessionId}/confirm`, {
      method: 'POST',
      body: payload,
      idempotencyKey: newIdempotencyKey(),
    }),

  createDiagnosis: (payload: unknown) =>
    request<DiagnosisCreateResponse>('/diagnoses', {
      method: 'POST',
      body: payload,
      idempotencyKey: newIdempotencyKey(),
    }),
  listDiagnoses: (params: Record<string, string | number | undefined> = {}) => {
    const query = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join('&')
    return request<{ items: DiagnosisSummary[]; page: number; page_size: number; total: number; total_pages: number }>(
      `/diagnoses${query ? `?${query}` : ''}`,
    )
  },
  getDiagnosis: (id: string) => request<DiagnosisSnapshot>(`/diagnoses/${id}`),
  resume: (id: string, payload: { decision: 'confirm' | 'supplement' | 'abort'; version: number; supplement?: FeatureValues }) =>
    request<DiagnosisSnapshot>(`/diagnoses/${id}/resume`, {
      method: 'POST',
      body: payload,
      idempotencyKey: newIdempotencyKey(),
    }),
  deleteDiagnosis: (id: string) => request<void>(`/diagnoses/${id}`, { method: 'DELETE' }),
  reportUrl: (id: string) => `${API_BASE}/diagnoses/${id}/report.md`,

  createBatch: (payload: { upload_id: string; mapping: Mapping; default_device_id?: string | null }) =>
    request<{ batch_task_id: string; status: string; total_rows: number; created_at: string; stream_url: string; snapshot_url: string }>(
      '/batches',
      { method: 'POST', body: payload },
    ),
  getBatch: (id: string) => request<BatchTaskSummary>(`/batches/${id}`),
  getBatchRows: (id: string, page = 1, pageSize = 20) =>
    request<{ items: BatchRowSummary[]; page: number; page_size: number; total: number; total_pages: number }>(
      `/batches/${id}/rows?page=${page}&page_size=${pageSize}`,
    ),
  getBatchRow: (batchId: string, rowId: string) => request<BatchRowDetail>(`/batches/${batchId}/rows/${rowId}`),
  cancelBatch: (id: string) =>
    request<{ batch_task_id: string; status: string; cancel_requested: boolean }>(`/batches/${id}/cancel`, { method: 'POST' }),
  batchExportUrl: (id: string) => `${API_BASE}/batches/${id}/export.csv`,

  evalLatest: () => request<{ batch: EvalBatchSummary | null }>('/evaluations/latest'),
  evalList: () => request<{ items: EvalBatchSummary[]; page: number; page_size: number; total: number; total_pages: number }>('/evaluations'),
  evalDetail: (id: string) => request<EvalDetail>(`/evaluations/${id}`),
  evalSamples: (id: string, page = 1, pageSize = 20, onlyBadCases = true) =>
    request<{ items: EvalSample[]; page: number; page_size: number; total: number; total_pages: number }>(
      `/evaluations/${id}/samples?only_bad_cases=${onlyBadCases}&page=${page}&page_size=${pageSize}`,
    ),
}

export function eventSourceUrl(path: string) {
  return `${API_BASE}${path}`
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function filenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1])
    } catch {
      return utf8[1]
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  return plain?.[1] ?? null
}
