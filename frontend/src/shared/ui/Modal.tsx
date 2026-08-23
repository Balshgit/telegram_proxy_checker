import type { ReactNode } from 'react'
import { useEffect } from 'react'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  /** Кнопки внизу модалки. */
  actions: ReactNode
  /** Модалка с формой шире обычной — в ней несколько полей. */
  wide?: boolean
}

/** Диалог поверх страницы: закрывается по клику мимо и по Escape. */
export function Modal({ title, onClose, children, actions, wide = false }: ModalProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={`modal${wide ? ' modal--wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="modal__title">{title}</h2>
        {children}
        <div className="modal__actions">{actions}</div>
      </div>
    </div>
  )
}

interface ConfirmDialogProps {
  title: string
  text: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}

/** Частный случай `Modal`: «точно удалить?» с одной опасной кнопкой. */
export function ConfirmDialog({ title, text, confirmLabel, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      actions={
        <>
          <button type="button" className="btn btn--ghost" onClick={onCancel}>
            Отмена
          </button>
          <button type="button" className="btn btn--red" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="modal__text">{text}</p>
    </Modal>
  )
}
