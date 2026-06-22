import { create } from 'zustand'

type ToastType = 'info' | 'success' | 'warning' | 'error'

interface Toast {
  id: string
  type: ToastType
  message: string
  detail?: string
  action?: { label: string; onClick: () => void }
  duration?: number
}

interface ToastState {
  toasts: Toast[]
  add: (toast: Omit<Toast, 'id'>) => void
  remove: (id: string) => void
  clear: () => void
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  add: (toast) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2)}`
    set((s) => ({ toasts: [...s.toasts.slice(-4), { ...toast, id }] }))
    // Auto remove
    const duration = toast.duration ?? (toast.type === 'error' ? 8000 : 4000)
    if (duration > 0) {
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
      }, duration)
    }
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}))

// Convenience
export const toast = {
  info: (message: string, detail?: string) =>
    useToastStore.getState().add({ type: 'info', message, detail }),
  success: (message: string, detail?: string) =>
    useToastStore.getState().add({ type: 'success', message, detail }),
  warning: (message: string, detail?: string) =>
    useToastStore.getState().add({ type: 'warning', message, detail }),
  error: (message: string, detail?: string) =>
    useToastStore.getState().add({ type: 'error', message, detail }),
  action: (message: string, actionLabel: string, onClick: () => void, type: ToastType = 'info') =>
    useToastStore.getState().add({ type, message, action: { label: actionLabel, onClick }, duration: 10000 }),
}

const TOAST_STYLES: Record<ToastType, string> = {
  info: 'border-accent-blue/30 bg-blue-500/10 text-text-primary',
  success: 'border-accent-green/30 bg-green-500/10 text-text-primary',
  warning: 'border-accent-amber/30 bg-amber-500/10 text-text-primary',
  error: 'border-accent-red/30 bg-red-500/10 text-text-primary',
}

const TOAST_ICONS: Record<ToastType, string> = {
  info: '●', success: '✓', warning: '⚑', error: '✗',
}

const ICON_COLORS: Record<ToastType, string> = {
  info: 'text-accent-blue', success: 'text-accent-green',
  warning: 'text-accent-amber', error: 'text-accent-red',
}

export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const remove = useToastStore((s) => s.remove)

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 items-end pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border shadow-lg max-w-sm animate-slide-up ${TOAST_STYLES[t.type]}`}
        >
          <span className={`text-sm shrink-0 mt-0.5 ${ICON_COLORS[t.type]}`}>
            {TOAST_ICONS[t.type]}
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium leading-snug">{t.message}</div>
            {t.detail && (
              <div className="text-[10px] text-text-muted mt-0.5 leading-snug">{t.detail}</div>
            )}
            {t.action && (
              <button
                onClick={() => { t.action!.onClick(); remove(t.id) }}
                className={`text-[10px] font-medium mt-1 ${ICON_COLORS[t.type]} hover:underline`}
              >
                {t.action.label} →
              </button>
            )}
          </div>
          <button
            onClick={() => remove(t.id)}
            className="text-text-muted hover:text-text-secondary text-xs shrink-0 leading-none mt-0.5"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
