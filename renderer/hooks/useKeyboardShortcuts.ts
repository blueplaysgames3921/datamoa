import { useEffect } from 'react'

type ShortcutMap = Record<string, (e: KeyboardEvent) => void>

/**
 * useKeyboardShortcuts — register keyboard shortcuts with automatic cleanup
 * 
 * Usage:
 *   useKeyboardShortcuts({
 *     'cmd+k': () => openSearch(),
 *     'Escape': () => closeModal(),
 *     'cmd+Enter': () => submit(),
 *   })
 */
export function useKeyboardShortcuts(shortcuts: ShortcutMap, deps: unknown[] = []) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMac = navigator.platform?.toLowerCase().includes('mac')
      const meta = isMac ? e.metaKey : e.ctrlKey

      for (const [combo, action] of Object.entries(shortcuts)) {
        const parts = combo.toLowerCase().split('+')
        const key = parts[parts.length - 1]
        const needsCmd = parts.includes('cmd') || parts.includes('ctrl')
        const needsShift = parts.includes('shift')
        const needsAlt = parts.includes('alt')

        if (
          e.key.toLowerCase() === key &&
          (!needsCmd || meta) &&
          (!needsShift || e.shiftKey) &&
          (!needsAlt || e.altKey) &&
          (needsCmd === meta || !needsCmd)
        ) {
          e.preventDefault()
          action(e)
          break
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, deps)
}

/**
 * Global shortcuts reference (shown in UI)
 */
export const GLOBAL_SHORTCUTS = [
  { combo: '⌘1', description: 'Dashboard' },
  { combo: '⌘2', description: 'Queue' },
  { combo: '⌘3', description: 'Review' },
  { combo: '⌘4', description: 'Audit' },
  { combo: '⌘5', description: 'Settings' },
  { combo: '⌘P', description: 'Pause / Resume pipeline' },
  { combo: '⌘Enter', description: 'Submit text input' },
  { combo: 'Esc', description: 'Close panel / modal' },
  { combo: '⌘R', description: 'Refresh models' },
]
