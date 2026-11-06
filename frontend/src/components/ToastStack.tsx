import { createPortal } from 'react-dom'
import { useApp } from '../store/AppContext'
import { Icon } from './Icon'

export function ToastStack() {
  const { toasts, dismissToast } = useApp()
  if (!toasts.length) return null
  return createPortal(
    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast tone-${toast.tone === 'error' ? 'danger' : toast.tone === 'success' ? 'success' : 'info'}`} role="status">
          <Icon name={toast.tone === 'error' ? 'x' : toast.tone === 'success' ? 'check' : 'alert'} size={16} />
          <span>{toast.text}</span>
          <button type="button" className="icon-button icon-button--tiny" aria-label="关闭提示" onClick={() => dismissToast(toast.id)}>
            <Icon name="x" size={12} />
          </button>
        </div>
      ))}
    </div>,
    document.body,
  )
}
