import { usePipelineStore } from '../../store/pipeline'
import { useAgentStore } from '../../store/agents'

type Page = 'dashboard' | 'queue' | 'review' | 'audit' | 'settings'

interface SidebarProps {
  current: Page
  onNavigate: (page: Page) => void
  hitlCount: number
}

export default function Sidebar({ current, onNavigate, hitlCount }: SidebarProps) {
  const records = usePipelineStore((s) => s.records)
  const agents = useAgentStore((s) => s.agents)

  const activeCount = Object.values(records).filter(
    r => !['complete', 'failed', 'cancelled'].includes(r.stage)
  ).length

  const runningAgents = Object.values(agents).filter(a => a.status === 'running').length

  const navItems = [
    {
      id: 'dashboard' as Page,
      label: 'Dashboard',
      icon: (
        <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
          <rect x="2" y="2" width="5" height="5" rx="1"/>
          <rect x="9" y="2" width="5" height="5" rx="1"/>
          <rect x="2" y="9" width="5" height="5" rx="1"/>
          <rect x="9" y="9" width="5" height="5" rx="1"/>
        </svg>
      ),
      badge: activeCount > 0 ? activeCount : null,
      badgeColor: runningAgents > 0 ? 'bg-accent-blue' : 'bg-surface-4 text-text-muted',
    },
    {
      id: 'queue' as Page,
      label: 'Queue',
      icon: (
        <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="3" y1="4" x2="13" y2="4"/>
          <line x1="3" y1="8" x2="13" y2="8"/>
          <line x1="3" y1="12" x2="10" y2="12"/>
        </svg>
      ),
      badge: Object.keys(records).length > 0 ? Object.keys(records).length : null,
      badgeColor: 'bg-surface-3 text-text-muted',
    },
    {
      id: 'review' as Page,
      label: 'Review',
      icon: (
        <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="8" cy="8" r="5"/>
          <line x1="8" y1="5" x2="8" y2="8"/>
          <circle cx="8" cy="11" r="0.5" fill="currentColor"/>
        </svg>
      ),
      badge: hitlCount > 0 ? hitlCount : null,
      badgeColor: 'bg-accent-amber text-surface-0',
      pulse: hitlCount > 0,
    },
    {
      id: 'audit' as Page,
      label: 'Audit',
      icon: (
        <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="8" cy="8" r="5"/>
          <polyline points="5,8 7,10 11,6"/>
        </svg>
      ),
      badge: null,
      badgeColor: '',
    },
    {
      id: 'settings' as Page,
      label: 'Settings',
      icon: (
        <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="8" cy="8" r="2"/>
          <path d="M8 2v1M8 13v1M2 8h1M13 8h1M3.5 3.5l.7.7M11.8 11.8l.7.7M3.5 12.5l.7-.7M11.8 4.2l.7-.7"/>
        </svg>
      ),
      badge: null,
      badgeColor: '',
    },
  ]

  return (
    <aside className="w-48 shrink-0 border-r border-border-subtle bg-surface-1 flex flex-col select-none">
      {/* Nav items */}
      <nav className="flex-1 py-2">
        {navItems.map((item) => {
          const isActive = current === item.id
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`
                w-full flex items-center gap-3 px-4 py-2.5 text-left transition-all duration-150
                ${isActive
                  ? 'bg-accent-blue/10 text-accent-blue border-r-2 border-accent-blue'
                  : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.04] border-r-2 border-transparent'
                }
              `}
            >
              <span className={`shrink-0 ${isActive ? 'text-accent-blue' : 'text-text-muted'}`}>
                {item.icon}
              </span>
              <span className="text-xs font-medium flex-1">{item.label}</span>
              {item.badge !== null && item.badge !== undefined && (
                <span className={`
                  text-[9px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center tabular-nums
                  ${item.badgeColor}
                  ${item.pulse ? 'animate-pulse' : ''}
                `}>
                  {item.badge}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Bottom status */}
      <div className="border-t border-border-subtle px-4 py-3">
        {runningAgents > 0 ? (
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-accent-blue animate-pulse shrink-0" />
            <span className="text-[10px] text-text-muted">
              {runningAgents} agent{runningAgents !== 1 ? 's' : ''} running
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-surface-4 shrink-0" />
            <span className="text-[10px] text-text-muted">Idle</span>
          </div>
        )}
        <div className="text-[9px] text-text-muted mt-1">v0.1.0</div>
      </div>
    </aside>
  )
}
