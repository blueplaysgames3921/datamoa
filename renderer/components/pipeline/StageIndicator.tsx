type Stage = string

const STAGE_ORDER = [
  'queued', 'intake', 'parsing', 'context', 'confidence',
  'reasoning', 'validation', 'enrichment', 'hitl', 'writing', 'audit', 'complete'
]

const STAGE_LABELS: Record<string, string> = {
  queued: 'Queued', intake: 'Intake', parsing: 'Parse',
  context: 'Context', confidence: 'Score', reasoning: 'Reason',
  validation: 'Validate', enrichment: 'Enrich', hitl: 'Review',
  writing: 'Write', audit: 'Audit', complete: 'Done',
  failed: 'Failed', cancelled: 'Cancelled',
}

interface StageIndicatorProps {
  stage: Stage
  compact?: boolean
}

export default function StageIndicator({ stage, compact = false }: StageIndicatorProps) {
  const idx = STAGE_ORDER.indexOf(stage)
  const isFailed = stage === 'failed'
  const isCancelled = stage === 'cancelled'
  const isTerminal = ['complete', 'failed', 'cancelled'].includes(stage)

  if (compact) {
    return (
      <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded uppercase ${
        stage === 'complete' ? 'text-accent-green bg-green-500/10' :
        stage === 'failed' ? 'text-accent-red bg-red-500/10' :
        stage === 'hitl' ? 'text-accent-amber bg-amber-500/10' :
        stage === 'cancelled' ? 'text-text-muted bg-surface-3' :
        'text-accent-blue bg-blue-500/10'
      }`}>
        {STAGE_LABELS[stage] || stage}
      </span>
    )
  }

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1">
        <span className={`text-[10px] font-medium ${
          isFailed ? 'text-accent-red' :
          isCancelled ? 'text-text-muted' :
          stage === 'complete' ? 'text-accent-green' :
          stage === 'hitl' ? 'text-accent-amber' :
          'text-accent-blue'
        }`}>
          {STAGE_LABELS[stage] || stage}
        </span>
        {!isTerminal && idx >= 0 && (
          <span className="text-[9px] text-text-muted tabular-nums">
            {idx + 1}/{STAGE_ORDER.length - 1}
          </span>
        )}
      </div>

      {!isFailed && !isCancelled && (
        <div className="h-1 bg-surface-4 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              stage === 'complete' ? 'bg-accent-green' :
              stage === 'hitl' ? 'bg-accent-amber' :
              'bg-accent-blue'
            }`}
            style={{
              width: stage === 'complete' ? '100%' :
                     idx < 0 ? '0%' :
                     `${Math.round((idx / (STAGE_ORDER.length - 2)) * 100)}%`
            }}
          />
        </div>
      )}
    </div>
  )
}
