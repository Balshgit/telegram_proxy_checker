import { useCallback, useRef, useState } from 'react'

export type ToastKind = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  kind: ToastKind
  text: string
  /** Необязательная вторая строка — поясняет, что делать дальше. */
  hint?: string
}

const TOAST_ICONS: Record<ToastKind, string> = {
  success: '✓',
  error: '⚠',
  info: 'ℹ',
}

/** Тост с подсказкой нужно успеть прочитать — держим его чуть дольше. */
const TOAST_TTL_MS = 4000
const TOAST_WITH_HINT_TTL_MS = 6000

export type PushToast = (kind: ToastKind, text: string, hint?: string) => void

/** Очередь тостов: общая для всех страниц. */
export function useToasts(): { toasts: Toast[]; pushToast: PushToast } {
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastSeq = useRef(0)

  const pushToast = useCallback<PushToast>((kind, text, hint) => {
    toastSeq.current += 1
    const id = toastSeq.current
    setToasts((current) => [...current, { id, kind, text, hint }])
    window.setTimeout(
      () => setToasts((current) => current.filter((toast) => toast.id !== id)),
      hint ? TOAST_WITH_HINT_TTL_MS : TOAST_TTL_MS,
    )
  }, [])

  return { toasts, pushToast }
}

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast--${toast.kind}`} role="status">
          <span className="toast__icon" aria-hidden="true">
            {TOAST_ICONS[toast.kind]}
          </span>
          <div className="toast__body">
            <span className="toast__text">{toast.text}</span>
            {toast.hint && <span className="toast__hint">{toast.hint}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}
