import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, type Mapping, type MappingPreviewResponse, type UploadPrecheck } from '../api/client'
import { FEATURE_DEFS, FEATURE_KEYS } from '../lib/features'
import { Modal } from './Modal'

export function MappingModal({
  open,
  upload,
  mode,
  busy,
  locked = false,
  onClose,
  onConfirm,
}: {
  open: boolean
  upload: UploadPrecheck | null
  mode: 'single' | 'batch'
  busy: boolean
  locked?: boolean
  onClose: () => void
  onConfirm: (payload: { mapping: Mapping; default_device_id: string | null; row_no?: number }) => void
}) {
  const [mapping, setMapping] = useState<Mapping>(() => ({
    device_id: null,
    product_type: null,
    air_temp_k: null,
    process_temp_k: null,
    rotational_speed_rpm: null,
    torque_nm: null,
    tool_wear_min: null,
  }))
  const [defaultDevice, setDefaultDevice] = useState('')
  const [rowNo, setRowNo] = useState('1')
  const [preview, setPreview] = useState<MappingPreviewResponse | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  useEffect(() => {
    if (!upload) return
    setMapping(upload.suggested_mapping)
    setDefaultDevice(upload.matched_scheme?.default_device_id || '')
    setRowNo('1')
    setPreview(null)
    setPreviewError(null)
  }, [upload])

  useEffect(() => {
    if (!open || !upload) return
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.mappingPreview(upload.upload_id, {
          mapping,
          mode,
          row_no: mode === 'single' ? Number(rowNo) : null,
          default_device_id: defaultDevice || null,
        })
        setPreview(result)
        setPreviewError(null)
      } catch (error) {
        if (error instanceof ApiError) setPreviewError(error.message)
        else setPreviewError('映射预览失败，请检查网络')
      }
    }, 350)
    return () => window.clearTimeout(timer)
  }, [open, upload, mapping, mode, rowNo, defaultDevice])

  const missing = useMemo(() => FEATURE_KEYS.filter((key) => !mapping[key]), [mapping])
  const needsDefault = !mapping.device_id && !defaultDevice.trim()
  const rowValid = mode === 'single' ? Number(rowNo) >= 1 && Number(rowNo) <= (upload?.row_count ?? 0) : true
  const canConfirm = !busy && !locked && missing.length === 0 && !needsDefault && rowValid

  if (!upload) return null

  return (
    <Modal
      open={open}
      title="字段映射"
      subtitle={`${upload.file_name} · ${upload.row_count} 行 · ${upload.encoding.toUpperCase()} · ${(upload.size_bytes / 1024).toFixed(0)} KB`}
      onClose={onClose}
      width="720px"
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canConfirm}
            title={locked ? '当前诊断运行中' : undefined}
            onClick={() =>
              onConfirm({
                mapping,
                default_device_id: defaultDevice.trim() || null,
                ...(mode === 'single' ? { row_no: Number(rowNo) } : {}),
              })
            }
          >
            {busy ? '正在提交…' : locked ? '当前诊断运行中' : mode === 'single' ? '确认并诊断' : '创建批量任务'}
          </button>
        </>
      }
    >
      <div className="mapping">
        <div className="mapping__toolbar">
          <label className="inline-field">
            <span>批次统一设备标识</span>
            <input
              type="text"
              value={defaultDevice}
              onChange={(event) => setDefaultDevice(event.target.value)}
              placeholder="行级值优先；为空时必须映射设备标识列"
            />
          </label>
          {mode === 'single' ? (
            <label className="inline-field inline-field--narrow">
              <span>诊断行号</span>
              <input type="number" min={1} max={upload.row_count} value={rowNo} onChange={(event) => setRowNo(event.target.value)} />
            </label>
          ) : null}
        </div>

        <table className="mapping-table">
          <thead>
            <tr>
              <th scope="col">目标字段</th>
              <th scope="col">文件列</th>
              <th scope="col">示例值</th>
              <th scope="col">状态</th>
            </tr>
          </thead>
          <tbody>
            {FEATURE_KEYS.map((key) => {
              const def = FEATURE_DEFS[key]
              const column = mapping[key]
              const example = column ? upload.preview_rows?.[0]?.[column] : null
              return (
                <tr key={key}>
                  <td>
                    {def.label}
                    <span className="required-mark">必填</span>
                  </td>
                  <td>
                    <select
                      value={column ?? ''}
                      onChange={(event) => setMapping((current) => ({ ...current, [key]: event.target.value || null }))}
                      aria-label={`${def.label} 对应文件列`}
                    >
                      <option value="">未映射</option>
                      {upload.headers.map((header) => (
                        <option key={header} value={header}>
                          {header}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="mono">{example ?? '—'}</td>
                  <td>
                    <span className={`status-badge ${column ? 'tone-success' : 'tone-waiting'}`}>
                      {column ? '已映射' : '待映射'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {missing.length ? (
          <p className="mapping__missing" role="alert">
            缺少必填映射：{missing.map((key) => FEATURE_DEFS[key].label).join('、')}
          </p>
        ) : null}
        {needsDefault ? (
          <p className="mapping__missing" role="alert">
            设备标识列未映射，请填写批次统一设备标识。
          </p>
        ) : null}
        {!rowValid ? (
          <p className="mapping__missing" role="alert">
            诊断行号需在 1–{upload.row_count} 之间。
          </p>
        ) : null}

        <section className="mapping__preview">
          <div className="mapping__preview-head">
            <h3>转换预览</h3>
            {preview?.row_summary ? (
              <span className="mono">
                有效 {preview.row_summary.valid} / 总 {preview.row_summary.total}，非法 {preview.row_summary.invalid}
              </span>
            ) : null}
          </div>
          {previewError ? <p className="form-error" role="alert">{previewError}</p> : null}
          {preview?.preview?.length ? (
            <table className="mapping-table">
              <thead>
                <tr>
                  <th scope="col">行号</th>
                  <th scope="col">设备标识</th>
                  <th scope="col">类型</th>
                  <th scope="col">空温</th>
                  <th scope="col">工温</th>
                  <th scope="col">转速</th>
                  <th scope="col">扭矩</th>
                  <th scope="col">磨损</th>
                </tr>
              </thead>
              <tbody>
                {preview.preview.map((row) => {
                  const features = (row.features ?? {}) as Record<string, unknown>
                  return (
                    <tr key={row.row_no}>
                      <td className="mono">{row.row_no}</td>
                      <td>{row.device_id || '—'}</td>
                      <td>{String(features.product_type ?? '—')}</td>
                      <td className="num mono">{String(features.air_temp_k ?? '—')}</td>
                      <td className="num mono">{String(features.process_temp_k ?? '—')}</td>
                      <td className="num mono">{String(features.rotational_speed_rpm ?? '—')}</td>
                      <td className="num mono">{String(features.torque_nm ?? '—')}</td>
                      <td className="num mono">{String(features.tool_wear_min ?? '—')}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <p className="hint-text">映射后显示前 3 行转换结果。</p>
          )}
          {preview?.row_summary?.first_invalid?.length ? (
            <ul className="mapping__issues">
              {preview.row_summary.first_invalid.map((raw, index) => {
                const issue = raw as { row_no?: number; message?: string }
                return (
                  <li key={`${issue.row_no}-${index}`}>
                    第 {issue.row_no} 行：{issue.message}
                  </li>
                )
              })}
            </ul>
          ) : null}
        </section>
      </div>
    </Modal>
  )
}
