import { AgentInfo } from '../../store/agents'
import AgentModelBadge from './AgentModelBadge'

const AGENT_LABELS: Record<string, string> = {
  intake: 'Intake', parsing: 'Parsing', context: 'Context',
  confidence: 'Confidence', reasoning: 'Reasoning', validation: 'Validation',
  enrichment: 'Enrichment', hitl: 'HITL', write: 'Write',
  audit: 'Audit', learning: 'Learning', orchestrator: 'Orchestrator',
}

interface AgentStatusProps {
  agent: AgentInfo
}

export default function AgentStatusRow({ agent }: AgentStatusProps) {
  const isRunning = agent.status === 'running'
  const isError = agent.status === 'error'

  return (
    <div className="px-4 py-2.5 flex items-start gap-2.5">
      {/* Status dot */}
      <div className="relative shrink-0 mt-0.5">
        <div className={`w-1.5 h-1.5 rounded-full transition-colors ${
          isRunning ? 'bg-accent-blue' :
          isError   ? 'bg-accent-red'  : 'bg-surface-4'
        }`} />
        {isRunning && (
          <div className="absolute inset-0 rounded-full bg-accent-blue animate-ping opacity-60" />
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1">
          <span className="text-xs font-medium text-text-secondary truncate">
            {AGENT_LABELS[agent.name] || agent.name}
          </span>
          {agent.lastDurationMs && !isRunning && (
            <span className="text-[9px] text-text-muted shrink-0 tabular-nums">
              {agent.lastDurationMs < 1000
                ? `${agent.lastDurationMs}ms`
                : `${(agent.lastDurationMs/1000).toFixed(1)}s`}
            </span>
          )}
          {isRunning && (
            <span className="text-[9px] text-accent-blue shrink-0 animate-pulse">●</span>
          )}
        </div>
        <div className="mt-0.5">
          {isError ? (
            <span className="text-[10px] text-accent-red truncate block">
              {agent.error?.slice(0, 35) || 'Error'}
            </span>
          ) : (
            <AgentModelBadge model={agent.model} />
          )}
        </div>
      </div>
    </div>
  )
}
