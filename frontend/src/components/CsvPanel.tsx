import { useRef, useState } from 'react'
import { ApiError, api, type Mapping, type UploadPrecheck } from '../api/client'
import { sampleCsvFile } from '../lib/sample'
import { Icon } from './Icon'
import { MappingModal } from './MappingModal'

export function CsvPanel({
  mode,
  onModeChange,
  busy,
  locked = false,
  onCreateSingle,
  onCreateBatch,
}: {
  mode: 'single' | 'batch'
  onModeChange: (mode: 'single' | 'batch') => void
  busy: boolean
  locked?: boolean
  onCreateSingle: (payload: { upload: UploadPrecheck; mapping: Mapping; default_device_id: string | null; row_no: number }) => Promise<boolean>
  onCreateBatch: (payload: { upload: UploadPrecheck; mapping: Mapping; default_device_id: string | null }) => Promise<boolean>
}) {
  const [uploading, setUploading] = useState(false)
  const [upload, setUpload] = useState<UploadPrecheck | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    if (!/\.csv$/i.test(file.name)) {
      setError('仅支持 .csv 文件，请重新选择。')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('文件超过 5MB 上限，请拆分后重试。')
      return
    }
    setUploading(true)
    try {
      const result = await api.uploadCsv(file)
      setUpload(result)
      setMappingOpen(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '上传失败，请检查网络后重试。')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="panel-stack">
      <div className="mode-switch" role="group" aria-label="CSV 模式">
        <button type="button" className={mode === 'single' ? 'is-active' : ''} onClick={() => onModeChange('single')}>
          单条诊断
        </button>
        <button type="button" className={mode === 'batch' ? 'is-active' : ''} onClick={() => onModeChange('batch')}>
          批量任务
        </button>
      </div>

      <div
        className={`drop-zone ${dragOver ? 'is-over' : ''} ${uploading ? 'is-busy' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragOver(false)
          const file = event.dataTransfer.files?.[0]
          if (file) void handleFile(file)
        }}
      >
        <Icon name="upload" size={22} />
        <p className="drop-zone__title">{uploading ? '正在上传并预检…' : '拖入 CSV 文件，或选择文件'}</p>
        <p className="drop-zone__hint">仅 .csv · ≤5MB · ≤500 行 · UTF-8/GBK</p>
        <div className="drop-zone__actions">
          <button type="button" className="btn btn-secondary" onClick={() => inputRef.current?.click()} disabled={uploading || busy || locked}>
            选择文件
          </button>
          <button
            type="button"
            className="btn btn-text"
            disabled={uploading || busy || locked}
            onClick={() => void handleFile(sampleCsvFile())}
          >
            载入示例 CSV
          </button>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void handleFile(file)
            event.target.value = ''
          }}
        />
      </div>

      {error ? (
        <div className="error-card" role="alert">
          <div className="error-card__head">
            <Icon name="x" size={16} />
            <span>预检未通过</span>
          </div>
          <p>{error}</p>
          <div className="error-card__actions">
            <button type="button" className="btn btn-secondary" onClick={() => inputRef.current?.click()}>
              重新选择文件
            </button>
            {upload ? (
              <button type="button" className="btn btn-text" onClick={() => setMappingOpen(true)}>
                修改映射
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {upload && !mappingOpen ? (
        <div className="upload-summary">
          <div className="upload-summary__row">
            <Icon name="file" size={16} />
            <span>{upload.file_name}</span>
            <span className="mono">{upload.row_count} 行</span>
            <span className="mono">{upload.encoding.toUpperCase()}</span>
          </div>
          <div className="upload-summary__actions">
            <button type="button" className="btn btn-secondary" onClick={() => setMappingOpen(true)}>
              继续映射
            </button>
            <button
              type="button"
              className="btn btn-text"
              onClick={() => {
                setUpload(null)
                setError(null)
              }}
            >
              移除
            </button>
          </div>
        </div>
      ) : null}

      <p className="panel-note">
        {mode === 'single'
          ? '预检通过后进入字段映射；确认后只诊断指定行。'
          : '预检通过后进入字段映射；批量任务不进入人工中断，低置信自动生成待复核报告。'}
      </p>

      <MappingModal
        open={mappingOpen && !!upload}
        upload={upload}
        mode={mode}
        busy={busy || submitting}
        locked={locked}
        onClose={() => setMappingOpen(false)}
        onConfirm={async (payload) => {
          setSubmitting(true)
          try {
            const ok =
              mode === 'single'
                ? await onCreateSingle({
                    upload: upload as UploadPrecheck,
                    mapping: payload.mapping,
                    default_device_id: payload.default_device_id,
                    row_no: payload.row_no ?? 1,
                  })
                : await onCreateBatch({
                    upload: upload as UploadPrecheck,
                    mapping: payload.mapping,
                    default_device_id: payload.default_device_id,
                  })
            if (ok) setMappingOpen(false)
          } finally {
            setSubmitting(false)
          }
        }}
      />
    </div>
  )
}
