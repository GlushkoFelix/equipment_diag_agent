import { useState } from 'react'
import { ApiError, api, type FeatureValues, type NlExtractResponse } from '../api/client'
import { ExtractionCard } from './ExtractionCard'
import { Icon } from './Icon'

const PLACEHOLDER =
  '3号机 M 型，空气温度 298.1K，工艺温度 308.6K，转速 1551rpm，扭矩 42.8Nm，刀具磨损 0min，最近有异响和发热。'

export function NlPanel({
  busy,
  locked = false,
  onConfirm,
  onUseForm,
}: {
  busy: boolean
  locked?: boolean
  onConfirm: (values: FeatureValues, text: string) => Promise<boolean>
  onUseForm: () => void
}) {
  const [text, setText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extraction, setExtraction] = useState<NlExtractResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function extract() {
    if (!text.trim()) return
    setExtracting(true)
    setError(null)
    try {
      const result = await api.nlExtract(text.trim())
      setExtraction(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '抽取失败，请稍后重试')
    } finally {
      setExtracting(false)
    }
  }

  return (
    <div className="panel-stack">
      <label className="textarea-label" htmlFor="nl-text">
        设备描述
      </label>
      <textarea
        id="nl-text"
        className="nl-textarea"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={PLACEHOLDER}
        maxLength={2000}
        readOnly={extracting || busy}
      />
      <div className="panel-toolbar">
        <span className="panel-toolbar__hint">抽取结果不会直接创建诊断，需人工确认。</span>
        <button type="button" className="btn btn-secondary" onClick={() => void extract()} disabled={!text.trim() || extracting || busy || locked} title={locked ? '当前诊断运行中' : undefined}>
          {extracting ? '正在抽取…' : '抽取数据'}
        </button>
      </div>

      {error ? (
        <div className="error-card" role="alert">
          <div className="error-card__head">
            <Icon name="x" size={16} />
            <span>抽取失败</span>
          </div>
          <p>{error}</p>
          <div className="error-card__actions">
            <button type="button" className="btn btn-secondary" onClick={onUseForm}>
              改用表单
            </button>
          </div>
        </div>
      ) : null}

      {extraction ? (
        <>
          {extraction.extraction_status === 'failed' ? (
            <div className="error-card" role="alert">
              <div className="error-card__head">
                <Icon name="alert-triangle" size={16} />
                <span>未能识别足够字段</span>
              </div>
              <p>未能识别足够字段，请补充描述或改用表单。</p>
              <div className="error-card__actions">
                <button type="button" className="btn btn-secondary" onClick={onUseForm}>
                  改用表单
                </button>
              </div>
            </div>
          ) : (
            <ExtractionCard
              extraction={extraction}
              text={text}
              disabled={busy || locked}
              onConfirm={(values, sourceText) => void onConfirm(values, sourceText)}
              onUseForm={onUseForm}
            />
          )}
        </>
      ) : null}
    </div>
  )
}
