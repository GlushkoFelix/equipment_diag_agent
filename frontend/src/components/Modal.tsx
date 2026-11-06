import { useEffect, useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import { createPortal } from 'react-dom'
import { Icon } from './Icon'

export function Modal({
  open,
  title,
  subtitle,
  onClose,
  width = 'var(--layout-modal-md)',
  children,
  footer,
  initialFocus,
  tone = 'default',
}: {
  open: boolean
  title: string
  subtitle?: ReactNode
  onClose: () => void
  width?: string
  children: ReactNode
  footer?: ReactNode
  initialFocus?: RefObject<HTMLElement | null>
  tone?: 'default' | 'danger'
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    previousFocus.current = document.activeElement as HTMLElement | null
    const target = initialFocus?.current || titleRef.current
    window.setTimeout(() => target?.focus(), 30)

    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (!focusables.length) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handler)
    document.body.classList.add('has-overlay')
    return () => {
      document.removeEventListener('keydown', handler)
      document.body.classList.remove('has-overlay')
      previousFocus.current?.focus()
    }
  }, [open, onClose, initialFocus])

  if (!open) return null

  return createPortal(
    <div className="overlay" role="presentation">
      <div
        className={`modal ${tone === 'danger' ? 'is-danger' : ''}`}
        style={{ width }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        ref={panelRef}
      >
        <header className="modal__header">
          <div>
            <h2 id="modal-title" ref={titleRef} tabIndex={-1}>
              {title}
            </h2>
            {subtitle ? <div className="modal__subtitle">{subtitle}</div> : null}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="收起面板">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer ? <footer className="modal__footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  )
}
