import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api, type EvalBatchSummary, type EvalDetail, type EvalSample } from '../api/client'
import { EmptyState } from '../components/EmptyState'
import { Icon } from '../components/Icon'
import { useApp } from '../store/AppContext'
import { formatDuration } from '../lib/status'

const ERROR_CATEGORY: Record<string, string> = {
  feature_missing: '特征缺失',
  retrieval_miss: '检索未命中',
  rule_misjudge: '规则误判',
  llm_misjudge: 'LLM 误判',
  report_missing_element: '报告缺要素',
  latency_exceeded: '时延超标',
}

function percent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return 'N/A'
  return `${(value * 100).toFixed(digits)}%`
}

function seconds(value: number | null | undefined) {
  if (value === null || value === undefined) return 'N/A'
  return `${(value / 1000).toFixed(1)}s`
}

function levelFor(confidence: number | null | undefined) {
  if (confidence === null || confidence === undefined) return { label: '—', level: null as string | null }
  if (confidence >= 0.8) return { label: '高', level: 'high' }
  if (confidence >= 0.5) return { label: '中', level: 'medium' }
  return { label: '低', level: 'low' }
}

function MetricCard({
  label,
  value,
  sub,
  target,
  state,
}: {
  label: string
  value: string
  sub: string
  target: string
  state: 'ok' | 'fail' | 'reference'
}) {
  return (
    <article className="metric-card">
      <header>
        <span className="metric-card__label">{label}</span>
        <span className={`metric-card__state tone-${state === 'ok' ? 'success' : state === 'fail' ? 'danger' : 'neutral'}`}>
          <Icon name={state === 'ok' ? 'check' : state === 'fail' ? 'x' : 'info'} size={12} />
          {state === 'ok' ? '达标' : state === 'fail' ? '未达标' : '参考'}
        </span>
      </header>
      <p className="metric-card__value mono">{value}</p>
      <p className="metric-card__sub">
        {sub} · 目标 {target}
      </p>
    </article>
  )
}

function matrixLevel(count: number, max: number) {
  if (count <= 0) return 0
  const ratio = count / Math.max(1, max)
  if (ratio < 0.2) return 1
  if (ratio < 0.5) return 2
  return 3
}

export function EvalPage() {
  const navigate = useNavigate()
  const { pushToast } = useApp()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [batch, setBatch] = useState<EvalBatchSummary | null>(null)
  const [trend, setTrend] = useState<EvalBatchSummary[]>([])
  const [detail, setDetail] = useState<EvalDetail | null>(null)
  const [samples, setSamples] = useState<EvalSample[]>([])
  const [badPage, setBadPage] = useState(1)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const latest = await api.evalLatest()
      if (!latest.batch) {
        setBatch(null)
        setDetail(null)
        setSamples([])
        return
      }
      const [list, evalDetail] = await Promise.all([api.evalList(), api.evalDetail(latest.batch.eval_batch_id)])
      setBatch(latest.batch)
      setTrend(list.items)
      setDetail(evalDetail)
      const first = await api.evalSamples(latest.batch.eval_batch_id, 1, 100, false)
      const pages = first.total_pages > 1 ? await Promise.all(Array.from({ length: first.total_pages - 1 }, (_, index) => api.evalSamples(latest.batch!.eval_batch_id, index + 2, 100, false))) : []
      setSamples([...first.items, ...pages.flatMap((page) => page.items)])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '评测数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const counts = useMemo(() => {
    const result = { failed_timeout: 0, failed: 0, degraded: 0, succeeded: 0, degraded_review: 0 }
    for (const sample of samples) {
      if (sample.status === 'failed_timeout') result.failed_timeout += 1
      else if (sample.status === 'failed') result.failed += 1
      else if (sample.status === 'degraded') result.degraded += 1
      else if (sample.status === 'succeeded') result.succeeded += 1
    }
    return result
  }, [samples])

  const timeoutSamples = useMemo(() => samples.filter((sample) => sample.status === 'failed_timeout'), [samples])
  const badCases = detail?.bad_cases ?? []
  const badTotalPages = Math.max(1, Math.ceil(badCases.length / 20))
  const pageBadCases = badCases.slice((badPage - 1) * 20, badPage * 20)
  const matrix = detail?.confusion_matrix
  const maxCell = matrix ? Math.max(1, ...matrix.counts.flat()) : 1

  if (loading) {
    return (
      <div className="eval-page">
        <header className="eval-head">
          <button type="button" className="btn btn-text" onClick={() => navigate('/')}>
            <Icon name="arrow-left" size={16} />
            返回工作台
          </button>
          <h1>评测结果</h1>
        </header>
        <div className="eval-loading">
          <div className="skeleton-line skeleton-line--title" />
          <div className="metric-grid">
            {[0, 1, 2, 3, 4, 5].map((index) => (
              <div key={index} className="metric-card skeleton-card" />
            ))}
          </div>
          <div className="skeleton-block" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="eval-page">
        <header className="eval-head">
          <button type="button" className="btn btn-text" onClick={() => navigate('/')}>
            <Icon name="arrow-left" size={16} />
            返回工作台
          </button>
          <h1>评测结果</h1>
        </header>
        <div className="error-card">
          <div className="error-card__head">
            <Icon name="x" size={16} />
            <span>评测数据加载失败</span>
          </div>
          <p>{error}</p>
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
            刷新
          </button>
        </div>
      </div>
    )
  }

  if (!batch) {
    return (
      <div className="eval-page">
        <header className="eval-head">
          <button type="button" className="btn btn-text" onClick={() => navigate('/')}>
            <Icon name="arrow-left" size={16} />
            返回工作台
          </button>
          <h1>评测结果</h1>
          <span className="readonly-badge">只读</span>
        </header>
        <EmptyState
          title="暂无评测结果"
          description="运行离线评测脚本后刷新；本页只读，不提供重跑或删除。"
          action={
            <button type="button" className="btn btn-primary" onClick={() => void load()}>
              刷新
            </button>
          }
        />
      </div>
    )
  }

  return (
    <div className="eval-page">
      <header className="eval-head">
        <button type="button" className="btn btn-text" onClick={() => navigate('/')}>
          <Icon name="arrow-left" size={16} />
          返回工作台
        </button>
        <div className="eval-head__title">
          <h1>评测结果</h1>
          <span className="readonly-badge">只读</span>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void load()}>
          <Icon name="refresh" size={16} />
          刷新
        </button>
      </header>

      <section className="version-bar" aria-label="版本信息">
        <span>
          数据集 <strong>{batch.dataset_version || '未记录'}</strong>
        </span>
        <span>
          样本数 <strong className="mono">{batch.sample_total}</strong>
        </span>
        <span>
          提示词 <strong>{batch.prompt_version || '未记录'}</strong>
        </span>
        <span>
          知识库 <strong>{batch.kb_version || '未记录'}</strong>
        </span>
        <span>
          模型 <strong>{batch.model_name || '未记录'}</strong>
        </span>
        <span>
          生成时间 <strong className="mono">{batch.created_at?.replace('T', ' ').slice(0, 16) || '未记录'}</strong>
        </span>
      </section>

      <section className="metric-grid" aria-label="核心指标">
        <MetricCard
          label="故障识别准确率"
          value={percent(batch.accuracy)}
          sub={`${Math.round((batch.accuracy ?? 0) * batch.sample_total)} / ${batch.sample_total}`}
          target="≥90%"
          state={batch.accuracy !== null && batch.accuracy !== undefined && batch.accuracy >= 0.9 ? 'ok' : 'fail'}
        />
        <MetricCard
          label="报告要素完整率"
          value={percent(batch.completeness_rate)}
          sub={`${batch.report_count} 份报告 × 8 要素`}
          target="≥95%"
          state={batch.completeness_rate !== null && batch.completeness_rate !== undefined && batch.completeness_rate >= 0.95 ? 'ok' : 'fail'}
        />
        <MetricCard
          label="平均时延"
          value={seconds(batch.latency_avg_ms)}
          sub={`成功时延样本 ${batch.latency_sample_count}`}
          target="≤10s"
          state={batch.latency_avg_ms !== null && batch.latency_avg_ms !== undefined && batch.latency_avg_ms <= 10000 ? 'ok' : 'fail'}
        />
        <MetricCard label="P50 时延" value={seconds(batch.latency_p50_ms)} sub="中位数" target="参考" state="reference" />
        <MetricCard
          label="P95 时延"
          value={seconds(batch.latency_p95_ms)}
          sub={`样本量 ${batch.latency_sample_count}`}
          target="≤10s"
          state={batch.latency_p95_ms !== null && batch.latency_p95_ms !== undefined && batch.latency_p95_ms <= 10000 ? 'ok' : 'fail'}
        />
        <MetricCard
          label="超时率"
          value={batch.timeout_rate !== null && batch.timeout_rate !== undefined ? `${(batch.timeout_rate * 100).toFixed(1)}%` : 'N/A'}
          sub={`${batch.failed_timeout_count} / ${batch.sample_total}`}
          target="≤1%"
          state={batch.timeout_rate !== null && batch.timeout_rate !== undefined && batch.timeout_rate <= 0.01 ? 'ok' : 'fail'}
        />
      </section>

      <section className="eval-section">
        <div className="eval-section__head">
          <h2>批次趋势</h2>
          <span className="hint-text">最近 {Math.min(10, trend.length)} 个批次 · 只读对照</span>
        </div>
        {trend.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">最近评测批次指标趋势</caption>
              <thead>
                <tr>
                  <th scope="col">生成时间</th>
                  <th scope="col">样本数</th>
                  <th scope="col">准确率</th>
                  <th scope="col">要素完整率</th>
                  <th scope="col">平均时延</th>
                  <th scope="col">P95</th>
                  <th scope="col">超时率</th>
                </tr>
              </thead>
              <tbody>
                {trend.slice(0, 10).map((item) => (
                  <tr key={item.eval_batch_id} className={item.eval_batch_id === batch.eval_batch_id ? 'is-current' : ''}>
                    <td className="mono">
                      {item.eval_batch_id === batch.eval_batch_id ? <span className="current-mark" aria-label="当前批次" /> : null}
                      {item.created_at?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td className="num mono">{item.sample_total}</td>
                    <td className="num mono">{percent(item.accuracy)}</td>
                    <td className="num mono">{percent(item.completeness_rate)}</td>
                    <td className="num mono">{seconds(item.latency_avg_ms)}</td>
                    <td className="num mono">{seconds(item.latency_p95_ms)}</td>
                    <td className="num mono">{percent(item.timeout_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint-text">暂无历史批次，运行离线评测脚本后刷新</p>
        )}
      </section>

      <section className="eval-section">
        <div className="eval-section__head">
          <h2>超时与执行质量</h2>
          <span className="hint-text">评测样本不做待复核</span>
        </div>
        <div className="quality-grid">
          <div className="quality-card">
            <span>超时样本</span>
            <strong className="mono">
              {counts.failed_timeout} / {batch.sample_total}
            </strong>
          </div>
          <div className="quality-card">
            <span>失败样本</span>
            <strong className="mono">
              {counts.failed} / {batch.sample_total}
            </strong>
          </div>
          <div className="quality-card">
            <span>缺项降级</span>
            <strong className="mono">
              {counts.degraded} / {batch.sample_total}
            </strong>
          </div>
          <div className="quality-card">
            <span>待复核</span>
            <strong className="mono">0 / {batch.sample_total}</strong>
            <small>评测样本不做待复核</small>
          </div>
        </div>

        <h3 className="eval-subtitle">超时样本明细</h3>
        {timeoutSamples.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">超时样本明细</caption>
              <thead>
                <tr>
                  <th scope="col">样本序号</th>
                  <th scope="col">标注</th>
                  <th scope="col">预测</th>
                  <th scope="col">状态</th>
                  <th scope="col">耗时</th>
                  <th scope="col">备注</th>
                </tr>
              </thead>
              <tbody>
                {timeoutSamples.map((sample) => (
                  <tr key={sample.eval_sample_id}>
                    <td className="mono">{sample.sample_no}</td>
                    <td>{sample.expected_primary}</td>
                    <td>{sample.predicted_primary || '—'}</td>
                    <td>
                      <span className="status-badge tone-danger-deep is-small">
                        <Icon name="timer-off" size={14} />
                        超时失败
                      </span>
                    </td>
                    <td className="num mono">{formatDuration(sample.latency_ms)}</td>
                    <td>无报告；不计入成功时延样本</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint-text">本期无超时样本</p>
        )}
      </section>

      <section className="eval-section">
        <h2>混淆矩阵</h2>
        {matrix ? (
          <div className="table-wrap">
            <table className="matrix-table">
              <caption>人工标注主类型 × 预测主类型（计数，括号内为行占比）</caption>
              <thead>
                <tr>
                  <th scope="col">标注 \ 预测</th>
                  {matrix.predicted_labels.map((label) => (
                    <th key={label} scope="col">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.row_labels.map((rowLabel, rowIndex) => {
                  const row = matrix.counts[rowIndex] ?? []
                  const total = row.reduce((sum, value) => sum + value, 0)
                  return (
                    <tr key={rowLabel}>
                      <th scope="row">{rowLabel}</th>
                      {matrix.predicted_labels.map((columnLabel, columnIndex) => {
                        const count = row[columnIndex] ?? 0
                        const isDiagonal = rowLabel === columnLabel
                        const level = matrixLevel(count, maxCell)
                        return (
                          <td
                            key={columnLabel}
                            className={`matrix-cell ${count === 0 ? 'is-zero' : isDiagonal ? `correct level-${level}` : `error level-${level}`}`}
                            title={`${rowLabel} → ${columnLabel}: ${count}`}
                          >
                            <span className="mono">{count}</span>
                            {count > 0 && total > 0 ? <small className="mono">{((count / total) * 100).toFixed(0)}%</small> : null}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint-text">矩阵数据缺失</p>
        )}
      </section>

      <section className="eval-section">
        <h2>分类别召回</h2>
        <table className="data-table">
          <caption className="sr-only">分类别召回率</caption>
          <thead>
            <tr>
              <th scope="col">类别</th>
              <th scope="col">样本量</th>
              <th scope="col">正确数</th>
              <th scope="col">召回率</th>
              <th scope="col">内联条</th>
            </tr>
          </thead>
          <tbody>
            {(detail?.per_class_recall ?? []).map((item) => {
              const correct = item.sample_count && item.recall !== null ? Math.round(item.sample_count * (item.recall ?? 0)) : null
              return (
                <tr key={item.label}>
                  <td>{item.label}</td>
                  <td className="num mono">{item.sample_count || 'N/A'}</td>
                  <td className="num mono">{correct ?? 'N/A'}</td>
                  <td className="num mono">{item.recall === null ? 'N/A' : percent(item.recall)}</td>
                  <td>
                    <span className="recall-bar" aria-hidden="true">
                      <span style={{ width: `${Math.round((item.recall ?? 0) * 100)}%` }} />
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      <section className="eval-section">
        <div className="eval-section__head">
          <h2>bad case</h2>
          <span className="hint-text">共 {badCases.length} 条</span>
        </div>
        {pageBadCases.length ? (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">bad case 明细</caption>
                <thead>
                  <tr>
                    <th scope="col">样本序号</th>
                    <th scope="col">标注</th>
                    <th scope="col">预测</th>
                    <th scope="col">置信度</th>
                    <th scope="col">错误归因</th>
                    <th scope="col">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {pageBadCases.map((item) => {
                    const level = levelFor(item.confidence)
                    return (
                      <tr key={`${item.sample_no}-${item.sample_id}`}>
                        <td className="mono">{item.sample_no}</td>
                        <td>{item.expected_primary}</td>
                        <td>{item.predicted_primary || '—'}</td>
                        <td>
                          <span className={`confidence-badge tone-${level.level === 'high' ? 'success' : level.level === 'low' ? 'danger' : 'waiting'} is-small`}>
                            <span className="mono">
                              {item.confidence === null ? '—' : item.confidence.toFixed(2)} · {level.label}
                            </span>
                          </span>
                        </td>
                        <td>{item.error_category ? ERROR_CATEGORY[item.error_category] || item.error_category : '—'}</td>
                        <td className="num mono">{formatDuration(item.latency_ms)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="eval-pagination">
              <button type="button" className="btn btn-text" disabled={badPage <= 1} onClick={() => setBadPage((page) => page - 1)}>
                上一页
              </button>
              <span className="mono">
                第 {badPage} / {badTotalPages} 页
              </span>
              <button type="button" className="btn btn-text" disabled={badPage >= badTotalPages} onClick={() => setBadPage((page) => page + 1)}>
                下一页
              </button>
            </div>
          </>
        ) : (
          <p className="hint-text">本期无 bad case</p>
        )}
      </section>

      <section className="eval-section">
        <h2>检索调参记录</h2>
        {(detail?.retrieval_tuning ?? []).length ? (
          <table className="data-table">
            <caption className="sr-only">检索调参记录</caption>
            <thead>
              <tr>
                <th scope="col">参数组合</th>
                <th scope="col">Top-5 命中率</th>
                <th scope="col">知识库版本</th>
              </tr>
            </thead>
            <tbody>
              {detail?.retrieval_tuning.map((item, index) => (
                <tr key={`${item.kb_version}-${index}`}>
                  <td className="mono">
                    chunk {item.params?.chunk_size ?? '—'} / overlap {item.params?.overlap ?? '—'} / top_k {item.params?.top_k ?? '—'}
                  </td>
                  <td className="num mono">{item.top5_hit_rate === null ? 'N/A' : percent(item.top5_hit_rate)}</td>
                  <td>{item.kb_version || '未记录'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="hint-text">暂无调参记录</p>
        )}
      </section>

      <footer className="eval-footer">
        <button
          type="button"
          className="text-button"
          onClick={() => {
            void navigator.clipboard?.writeText(batch.eval_batch_id).then(() => pushToast('批次号已复制', 'success')).catch(() => undefined)
          }}
        >
          批次 {batch.eval_batch_id}
        </button>
        <span>页面只读，刷新仅重新拉取已有结果。</span>
      </footer>
    </div>
  )
}
