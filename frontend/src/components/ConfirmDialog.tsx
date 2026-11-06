import { useRef } from 'react'
import { Modal } from './Modal'

export function ConfirmDialog({
  open,
  title,
  description,
  confirmText,
  cancelText,
  tone = 'danger',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  description: string
  confirmText: string
  cancelText: string
  tone?: 'danger' | 'default'
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      width="var(--layout-modal-sm)"
      initialFocus={cancelRef}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onCancel} ref={cancelRef} disabled={busy}>
            {cancelText}
          </button>
          <button type="button" className={`btn ${tone === 'danger' ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm} disabled={busy}>
            {busy ? '提交中…' : confirmText}
          </button>
        </>
      }
    >
      <p className="confirm-text">{description}</p>
    </Modal>
  )
}
