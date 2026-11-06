import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppProvider, useApp } from './store/AppContext'
import { ToastStack } from './components/ToastStack'
import { LoginPage } from './pages/LoginPage'
import { WorkbenchPage } from './pages/WorkbenchPage'
import { EvalPage } from './pages/EvalPage'

function BootSplash() {
  return (
    <div className="boot-splash" role="status">
      <span className="boot-splash__mark" aria-hidden="true" />
      <p>正在检查会话…</p>
    </div>
  )
}

function Protected({ children }: { children: ReactNode }) {
  const { user, booting } = useApp()
  if (booting) return <BootSplash />
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Protected>
            <WorkbenchPage />
          </Protected>
        }
      />
      <Route
        path="/eval"
        element={
          <Protected>
            <EvalPage />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <AppRoutes />
        <ToastStack />
      </BrowserRouter>
    </AppProvider>
  )
}
