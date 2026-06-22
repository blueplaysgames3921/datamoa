import { usePipelineStore } from '../../store/pipeline'
import { useAgentStore } from '../../store/agents'

// Detect platform from userAgent (Electron sets it)
const isMac = navigator.platform?.toLowerCase().includes('mac') || 
              navigator.userAgent?.includes('Macintosh')

export default function TitleBar() {
  const backendConnected = usePipelineStore((s) => s.backendConnected)
  const paused = usePipelineStore((s) => s.paused)
  const agents = useAgentStore((s) => s.agents)
  const runningAgents = Object.values(agents).filter(a => a.status === 'running').length

  const handleMinimize = () => (window as any).electronAPI?.minimize?.()
  const handleMaximize = () => (window as any).electronAPI?.maximize?.()
  const handleClose = () => (window as any).electronAPI?.close?.()

  return (
    <div className="titlebar-drag h-10 flex items-center shrink-0 border-b border-border-subtle bg-surface-1">
      {/* macOS traffic lights need space */}
      {isMac && <div className="w-20 shrink-0" />}

      {/* Windows/Linux controls on left */}
      {!isMac && (
        <div className="titlebar-no-drag flex items-center gap-1 px-3">
          {/* App icon */}
          <div className="w-5 h-5 rounded bg-gradient-to-br from-accent-blue to-accent-cyan flex items-center justify-center shrink-0 mr-1">
            <span className="text-[9px] font-bold text-white">M</span>
          </div>
        </div>
      )}

      {/* App name */}
      <div className="flex items-center gap-2 px-1">
        {isMac && (
          <div className="w-5 h-5 rounded bg-gradient-to-br from-accent-blue to-accent-cyan flex items-center justify-center shrink-0">
            <span className="text-[9px] font-bold text-white">M</span>
          </div>
        )}
        <span className="text-[11px] text-text-muted font-medium tracking-widest uppercase">
          DataMoA
        </span>
      </div>

      <div className="flex-1" />

      {/* Status indicators */}
      <div className="titlebar-no-drag flex items-center gap-3 px-4">
        {/* Agent activity */}
        {runningAgents > 0 && (
          <div className="flex items-center gap-1.5 text-[10px] text-accent-blue">
            <div className="w-1.5 h-1.5 rounded-full bg-accent-blue animate-pulse" />
            {runningAgents} running
          </div>
        )}

        {/* Paused indicator */}
        {paused && (
          <span className="text-[10px] text-accent-amber bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
            ⏸ Paused
          </span>
        )}

        {/* Backend connection */}
        <div className={`flex items-center gap-1.5 text-[10px] ${
          backendConnected ? 'text-accent-green' : 'text-accent-red'
        }`}>
          <div className={`w-1.5 h-1.5 rounded-full ${
            backendConnected ? 'bg-accent-green' : 'bg-accent-red animate-pulse'
          }`} />
          {backendConnected ? 'Connected' : 'Disconnected'}
        </div>

        {/* Windows/Linux window controls */}
        {!isMac && (
          <div className="flex items-center gap-0 ml-3">
            <button
              onClick={handleMinimize}
              className="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-white/[0.06] transition-colors"
              title="Minimize"
            >
              <svg viewBox="0 0 10 1" className="w-2.5 h-px" fill="currentColor">
                <rect width="10" height="1"/>
              </svg>
            </button>
            <button
              onClick={handleMaximize}
              className="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-white/[0.06] transition-colors"
              title="Maximize"
            >
              <svg viewBox="0 0 10 10" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="1">
                <rect x="0.5" y="0.5" width="9" height="9"/>
              </svg>
            </button>
            <button
              onClick={handleClose}
              className="w-10 h-10 flex items-center justify-center text-text-muted hover:text-white hover:bg-accent-red transition-colors"
              title="Close"
            >
              <svg viewBox="0 0 10 10" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="1.2">
                <line x1="0" y1="0" x2="10" y2="10"/>
                <line x1="10" y1="0" x2="0" y2="10"/>
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
