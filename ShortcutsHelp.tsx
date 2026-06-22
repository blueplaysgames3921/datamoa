import { useEffect } from 'react'
import { GLOBAL_SHORTCUTS } from '../../hooks/useKeyboardShortcuts'

interface ShortcutsHelpProps {
  onClose: () => void
}

export default function ShortcutsHelp({ onClose }: ShortcutsHelpProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-surface-2 border border-border-default rounded-xl shadow-2xl p-6 w-72 animate-slide-up">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-text-primary">Keyboard Shortcuts</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <svg viewBox="0 0 14 14" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="1" y1="1" x2="13" y2="13"/>
              <line x1="13" y1="1" x2="1" y2="13"/>
            </svg>
          </button>
        </div>
        <div className="space-y-2">
          {GLOBAL_SHORTCUTS.map((s) => (
            <div key={s.combo} className="flex items-center justify-between">
              <span className="text-xs text-text-muted">{s.description}</span>
              <kbd className="text-[10px] font-mono bg-surface-3 border border-border-default text-text-secondary px-1.5 py-0.5 rounded">
                {s.combo}
              </kbd>
            </div>
          ))}
          <div className="flex items-center justify-between pt-1 border-t border-border-subtle">
            <span className="text-xs text-text-muted">Show shortcuts</span>
            <kbd className="text-[10px] font-mono bg-surface-3 border border-border-default text-text-secondary px-1.5 py-0.5 rounded">?</kbd>
          </div>
        </div>
      </div>
    </div>
  )
}
