import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useApp } from '../store/AppContext'
import { Icon } from '../components/Icon'
import { PasswordRuleHint } from '../components/PasswordRuleHint'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordChecks } from '../lib/password'

function formatLock(seconds: number) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export function LoginPage() {
  const { user, booting, login, register } = useApp()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('zhangsan')
  const [password, setPassword] = useState('Abcd1234')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [lockUntil, setLockUntil] = useState<number | null>(null)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    if (!lockUntil) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [lockUntil])

  const lockSeconds = lockUntil ? Math.max(0, Math.ceil((lockUntil - now) / 1000)) : 0
  const locked = lockSeconds > 0
  const title = useMemo(() => (mode === 'login' ? '登录工作台' : '创建账号'), [mode])
  const checks = useMemo(() => passwordChecks(password), [password])

  if (!booting && user) return <Navigate to="/" replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (submitting || locked) return
    setError(null)
    if (!passwordChecks(password).valid) {
      setError(`密码需 ${PASSWORD_MIN_LENGTH}–${PASSWORD_MAX_LENGTH} 位，且同时包含字母和数字`)
      return
    }
    if (mode === 'register' && password !== confirm) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'login') await login(username.trim(), password)
      else await register(username.trim(), password, confirm)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 423) {
          setLockUntil(Date.now() + (err.retryAfter ?? 300) * 1000)
          setError(null)
        } else if (err.code === 'AUTH_INVALID_CREDENTIALS') {
          setError('用户名或密码错误')
        } else {
          setError(err.message)
        }
      } else {
        setError('登录失败，请检查网络后重试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-grid" aria-hidden="true" />
      <section className="login-intro">
        <div className="login-intro__brand">
          <span className="brand-mark brand-mark--large" aria-hidden="true">
            <svg width="26" height="26" viewBox="0 0 22 22" fill="none">
              <rect x="1.5" y="1.5" width="19" height="19" rx="2" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5 16.5V12h3.2v4.5M10.5 16.5V7.2h3.2v9.3M15.8 16.5V9.6" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </span>
          <div>
            <p className="login-intro__title">设备故障诊断</p>
            <p className="login-intro__sub mono">EDG · DIAGNOSTIC CONSOLE</p>
          </div>
        </div>
        <div className="login-intro__copy">
          <h1>先看状态，再看结论。</h1>
          <p>
            面向设备运维工程师的故障诊断工作台。输入传感器数据后，系统执行规则检索、诊断推理与报告生成；每一步状态、置信度与依据都可追溯。
          </p>
        </div>
        <ol className="login-loop">
          <li>
            <span className="mono">01</span>
            <span>输入数据</span>
            <small>CSV / 表单 / 自然语言 / 对话</small>
          </li>
          <li>
            <span className="mono">02</span>
            <span>检索与推理</span>
            <small>规则命中 · 知识覆盖 · 置信度分解</small>
          </li>
          <li>
            <span className="mono">03</span>
            <span>报告与依据</span>
            <small>8 要素报告 · Top-5 检索溯源</small>
          </li>
        </ol>
        <p className="login-intro__note">仅供设备运维参考，不构成正式检测结论。</p>
      </section>

      <section className="login-card" aria-label={title}>
        <header className="login-card__head">
          <p className="login-card__eyebrow">{mode === 'login' ? '会话登录' : '账户注册'}</p>
          <h2>{title}</h2>
          <p>{mode === 'login' ? '使用运维账号进入工作台。' : '注册成功后自动登录并进入工作台。'}</p>
        </header>

        <form onSubmit={submit} className="login-form">
          <label className="form-field">
            <span>用户名</span>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="3–32 位字母、数字或下划线"
              required
            />
          </label>
          <label className="form-field">
            <span>密码</span>
            <div className="password-field">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                placeholder="至少 8 位，含字母与数字"
                minLength={PASSWORD_MIN_LENGTH}
                maxLength={PASSWORD_MAX_LENGTH}
                pattern={'(?=.*[A-Za-z])(?=.*\\d).{8,64}'}
                aria-invalid={password.length > 0 && !checks.valid}
                aria-describedby="password-rule-hint"
                required
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
              >
                {showPassword ? '隐藏' : '显示'}
              </button>
            </div>
            <PasswordRuleHint id="password-rule-hint" value={password} />
          </label>
          {mode === 'register' ? (
            <label className="form-field">
              <span>确认密码</span>
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
                placeholder="再次输入密码"
                required
              />
            </label>
          ) : null}

          {error ? (
            <p className="login-error" role="alert">
              <Icon name="alert" size={14} />
              {error}
            </p>
          ) : null}
          {locked ? (
            <p className="login-error" role="alert">
              <Icon name="clock" size={14} />
              尝试次数过多，请在 <span className="mono">{formatLock(lockSeconds)}</span> 后重试
            </p>
          ) : null}

          <button type="submit" className="btn btn-primary btn-lg login-submit" disabled={submitting || locked || !checks.valid}>
            {submitting ? (mode === 'login' ? '登录中…' : '注册中…') : mode === 'login' ? '登录' : '注册并登录'}
          </button>

          <div className="login-switch">
            {mode === 'login' ? (
              <>
                没有账号？
                <button type="button" className="text-button" onClick={() => setMode('register')}>
                  注册
                </button>
              </>
            ) : (
              <>
                已有账号？
                <button type="button" className="text-button" onClick={() => setMode('login')}>
                  返回登录
                </button>
              </>
            )}
          </div>
        </form>
        <p className="login-card__demo mono">DEMO · zhangsan / Abcd1234</p>
      </section>
    </div>
  )
}
