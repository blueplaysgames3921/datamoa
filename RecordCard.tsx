import { useState } from 'react'
import { RecordSummary } from '../../store/pipeline'
import RecordDetail from './RecordDetail'

const STAGE_LABELS: Record<string, string> = {
  queued: 'Queued', intake: 'Intake', parsing: 'Parsing', context: 'Context',
  confidence: 'Scoring', reasoning: 'Reasoning', validation: 'Validating',
  enrichment: 'Enriching', hitl: 'Awaiting Review', writing: 'Writing',
  audit: 'Auditing', complete: 'Complete', failed: 'Failed', cancelled: 'Cancelled',
}

const STAGE_COLORS: Record<string, string> = {
  queued: 'text-text-muted', intake: 'text-accent-blue', parsing: 'text-accent-blue',
  context: 'text-accent-cyan', confidence: 'text-accent-cyan', reasoning: 'text-purple-400',
  validation: 'text-accent-cyan', enrichment: 'text-accent-cyan', hitl: 'text-accent-amber',
  writing: 'text-accent-blue', audit: 'text-text-secondary', complete: 'text-accent-green',
  failed: 'text-accent-red', cancelled: 'text-text-muted',
}

const STAGES_ORDER = [
  'intake', 'parsing', 'context', 'confidence',
  'reasoning', 'validation', 'enrichment', 'writing', 'audit',
]

interface RecordCardProps {
  record: RecordSummary
}

export default function RecordCard({ record }: RecordCardProps) {
  const [showDetail, setShowDetail] = useState(false)
  const isActive = !['complete', 'failed', 'cancelled'].includes(record.stage)

  const tierDot =
    record.confidence_tier === 'green' ? 'bg-accent-green' :
    record.confidence_tier === 'amber' ? 'bg-accent-amber' :
    record.confidence_tier === 'red' ? 'bg-accent-red' :
    'bg-surface-4'

  const idx = STAGES_ORDER.indexOf(record.stage)
  const pct = idx === -1 ? 0 : Math.round(((idx + 1) / STAGES_ORDER.length) * 100)

  return (
    <>
      <button
        onClick={() => setShowDetail(true)}
        className={`w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-white/[0.03] transition-colors ${isActive ? 'animate-fade-in' : ''}`}
      >
        {/* Tier dot */}
        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${tierDot} ${isActive && record.confidence_tier ? 'animate-pulse-slow' : ''}`} />

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-text-muted">{record.id.slice(0, 8)}</span>
            <span className="text-[10px] text-text-muted">·</span>
            <span className="text-[10px] text-text-muted uppercase">{record.source_type}</span>
            {record.retry_count > 0 && (
              <span className="text-[9px] text-accent-amber bg-amber-500/10 px-1 rounded">
                retry ×{record.retry_count}
              </span>
            )}
          </div>
          <div className={`text-xs font-medium mt-0.5 ${STAGE_COLORS[record.stage] || 'text-text-secondary'}`}>
            {STAGE_LABELS[record.stage] || record.stage}
          </div>
        </div>

        {/* Score */}
        {record.confidence_score !== null && (
          <span className="text-xs font-mono text-text-muted shrink-0">
            {Math.round((record.confidence_score || 0) * 100)}%
          </span>
        )}

        {/* Progress bar */}
        {isActive ? (
          <div className="w-12 h-1 bg-surface-4 rounded-full overflow-hidden shrink-0">
            <div
              className="h-full bg-accent-blue/60 rounded-full transition-all duration-700"
              style={{ width: `${pct}%` }}
            />
          </div>
        ) : record.stage === 'failed' ? (
          <span className="text-[10px] text-accent-red shrink-0">✗</span>
        ) : (
          <span className="text-[10px] text-accent-green shrink-0">✓</span>
        )}

        <span className="text-text-muted text-[10px] shrink-0">›</span>
      </button>

      {showDetail && (
        <RecordDetail record={record} onClose={() => setShowDetail(false)} />
      )}
    </>
  )
}
