// In-app toast pop-ups. Gate toasts persist until acted on; the rest
// auto-dismiss. Rendered inside .shell so protocol tokens apply.
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

export interface ToastAction {
  label: string
  onClick: () => void | Promise<void>
  kind?: 'primary' | 'ghost'
}

export interface Toast {
  id: number
  title: string
  body?: string
  kind: 'info' | 'good' | 'warn' | 'gate'
  actions?: ToastAction[]
  sticky?: boolean
}

interface ToastState {
  toasts: Toast[]
  push: (t: Omit<Toast, 'id'>) => number
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastState>({ toasts: [], push: () => 0, dismiss: () => {} })

const AUTO_DISMISS_MS = 6000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id))
  }, [])

  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = nextId.current++
    setToasts((ts) => [...ts.slice(-3), { ...t, id }])
    if (!t.sticky) setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
    return id
  }, [dismiss])

  return (
    <ToastContext.Provider value={{ toasts, push, dismiss }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <div className="toast-stripe" />
            <div className="toast-body">
              <div className="toast-title">{t.title}</div>
              {t.body && <div className="toast-text">{t.body}</div>}
              {t.actions && t.actions.length > 0 && (
                <div className="toast-actions">
                  {t.actions.map((a) => (
                    <button
                      key={a.label}
                      className={`toast-btn${a.kind === 'primary' ? ' primary' : ''}`}
                      onClick={async () => { await a.onClick(); dismiss(t.id) }}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="toast-x" aria-label="Dismiss" onClick={() => dismiss(t.id)}>✕</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
