import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, api, type SystemConfig, type User } from '../api/client'

export type ToastTone = 'success' | 'error' | 'info'
export type ToastItem = { id: number; tone: ToastTone; text: string }

type AppContextValue = {
  user: User | null
  config: SystemConfig | null
  booting: boolean
  online: boolean
  toasts: ToastItem[]
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, passwordConfirm: string) => Promise<void>
  logout: () => Promise<void>
  pushToast: (text: string, tone?: ToastTone) => void
  dismissToast: (id: number) => void
}

const AppContext = createContext<AppContextValue | null>(null)

let toastSeq = 1

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [config, setConfig] = useState<SystemConfig | null>(null)
  const [booting, setBooting] = useState(true)
  const [online, setOnline] = useState(navigator.onLine)
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const pushToast = useCallback((text: string, tone: ToastTone = 'info') => {
    const id = toastSeq++
    setToasts((current) => [...current, { id, tone, text }])
    window.setTimeout(() => dismissToast(id), 3600)
  }, [dismissToast])

  useEffect(() => {
    let cancelled = false
    api
      .me()
      .then(({ user: next }) => {
        if (cancelled) return
        setUser(next)
        api
          .config()
          .then((config) => {
            if (!cancelled) setConfig(config)
          })
          .catch(() => undefined)
      })
      .catch((error: unknown) => {
        if (!cancelled && !(error instanceof ApiError && error.status === 401)) {
          pushToast('会话检查失败，请刷新页面重试', 'error')
        }
      })
      .finally(() => {
        if (!cancelled) setBooting(false)
      })
    return () => {
      cancelled = true
    }
  }, [pushToast])

  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])

  useEffect(() => {
    const handler = () => {
      setUser(null)
      pushToast('登录已过期，请重新登录', 'error')
    }
    window.addEventListener('auth:expired', handler)
    return () => window.removeEventListener('auth:expired', handler)
  }, [pushToast])

  const login = useCallback(async (username: string, password: string) => {
    const { user: next } = await api.login(username, password)
    setUser(next)
  }, [])

  const register = useCallback(async (username: string, password: string, passwordConfirm: string) => {
    const { user: next } = await api.register(username, password, passwordConfirm)
    setUser(next)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, config, booting, online, toasts, login, register, logout, pushToast, dismissToast }),
    [user, config, booting, online, toasts, login, register, logout, pushToast, dismissToast],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useApp must be used inside AppProvider')
  return value
}
