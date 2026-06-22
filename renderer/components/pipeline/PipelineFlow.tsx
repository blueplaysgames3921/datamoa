import { useAgentStore } from '../../store/agents'
import { usePipelineStore } from '../../store/pipeline'

const PIPELINE_STAGES = [
  { agent: 'intake',      label: 'Intake',    icon: '↓',  color: 'blue' },
  { agent: 'parsing',     label: 'Parse',     icon: '⊞',  color: 'blue' },
  { agent: 'context',     label: 'Context',   icon: '◎',  color: 'cyan' },
  { agent: 'confidence',  label: 'Score',     icon: '◈',  color: 'cyan' },
  { agent: 'reasoning',   label: 'Reason',    icon: '⬡',  color: 'purple' },
  { agent: 'validation',  label: 'Validate',  icon: '✓',  color: 'cyan' },
  { agent: 'enrichment',  label: 'Enrich',    icon: '⊕',  color: 'cyan' },
  { agent: 'write',       label: 'Write',     icon: '→',  color: 'blue' },
  { agent: 'audit',       label: 'Audit',     icon: '◉',  color: 'gray' },
]

const COLOR_MAP: Record<string, { active: string; ring: string }> = {
  blue:   { active: 'border-accent-blue/50 bg-blue-500/10 text-accent-blue', ring: 'bg-accent-blue' },
  cyan:   { active: 'border-accent-cyan/50 bg-cyan-500/10 text-accent-cyan', ring: 'bg-accent-cyan' },
  purple: { active: 'border-purple-400/50 bg-purple-500/10 text-purple-400', ring: 'bg-purple-400' },
  gray:   { active: 'border-border-strong bg-surface-3 text-text-secondary',  ring: 'bg-text-muted' },
}

export default function PipelineFlow() {
  const agents = useAgentStore((s) => s.agents)
  const records = usePipelineStore((s) => s.records)

  const activeCount = Object.values(records).filter(
    r => !['complete', 'failed', 'cancelled'].includes(r.stage)
  ).length

  const hitlCount = Object.values(records).filter(r => r.stage === 'hitl').length

  return (
    <div className="px-4 py-3 select-none">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] text-text-muted uppercase tracking-widest">Pipeline</div>
        <div className="flex items-center gap-2">
          {activeCount > 0 && (
            <span className="text-[9px] text-accent-blue bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">
              {activeCount} active
            </span>
          )}
          {hitlCount > 0 && (
            <span className="text-[9px] text-accent-amber bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20 animate-pulse">
              {hitlCount} review
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-0.5 flex-wrap">
        {PIPELINE_STAGES.map((stage, idx) => {
          const agent = agents[stage.agent]
          const isRunning = agent?.status === 'running'
          const isError = agent?.status === 'error'
          const colors = COLOR_MAP[stage.color]

          return (
            <div key={stage.agent} className="flex items-center gap-0.5">
              <div
                title={`${stage.label}${agent?.model ? ` — ${agent.model.split('/').pop()}` : ''}`}
                className={`
                  relative flex flex-col items-center gap-0.5 px-2 py-1.5 rounded border text-center
                  transition-all duration-300 cursor-default min-w-[36px]
                  ${isRunning
                    ? colors.active
                    : isError
                    ? 'border-accent-red/30 bg-red-500/5 text-accent-red'
                    : 'border-border-subtle bg-surface-2 text-text-muted'
                  }
                `}
              >
                {/* Running ping ring */}
                {isRunning && (
                  <div className={`absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full ${colors.ring}`}>
                    <div className={`absolute inset-0 rounded-full ${colors.ring} animate-ping opacity-75`} />
                  </div>
                )}

                <div className={`text-[11px] leading-none ${isRunning ? 'animate-pulse' : ''}`}>
                  {stage.icon}
                </div>
                <div className="text-[8px] font-medium leading-none">{stage.label}</div>

                {/* Duration badge */}
                {agent?.lastDurationMs && !isRunning && (
                  <div className="text-[7px] text-text-muted leading-none">
                    {agent.lastDurationMs < 1000
                      ? `${agent.lastDurationMs}ms`
                      : `${(agent.lastDurationMs / 1000).toFixed(1)}s`}
                  </div>
                )}
              </div>

              {/* Connector */}
              {idx < PIPELINE_STAGES.length - 1 && (
                <div className="text-[9px] text-text-muted opacity-30 px-0.5">›</div>
              )}
            </div>
          )
        })}
      </div>

      {/* HITL branch legend */}
      <div className="mt-2.5 flex items-center gap-1.5 text-[9px] text-text-muted">
        <div className="flex items-center gap-1">
          <div className="w-1 h-1 rounded-full bg-accent-amber" />
          <span className="text-accent-amber">HITL</span>
        </div>
        <span>branches on Red tier or validation fail</span>
        <div className="ml-auto flex items-center gap-1">
          <div className="w-1 h-1 rounded-full bg-accent-green" />
          <span className="text-accent-green">Green</span>
          <span>→ auto-write</span>
        </div>
      </div>
    </div>
  )
}
