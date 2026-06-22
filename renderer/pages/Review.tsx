import { useState, useEffect } from 'react'
import { usePipelineStore, HITLRequest } from '../store/pipeline'
import ConfidenceMeter from '../components/pipeline/ConfidenceMeter'
import { toast } from '../components/shared/Toast'

export default function Review() {
  const hitlQueue = usePipelineStore((s) => s.hitlQueue)
  const resolveHITL = usePipelineStore((s) => s.resolveHITL)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [resolutions, setResolutions] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const current = hitlQueue.find(r => r.record_id === selectedId) || hitlQueue[0] || null

  // Auto-select first when queue changes
  useEffect(() => {
    if (hitlQueue.length > 0 && !hitlQueue.find(r => r.record_id === selectedId)) {
      setSelectedId(hitlQueue[0].record_id)
    }
  }, [hitlQueue])

  if (hitlQueue.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text-muted">
        <div className="text-5xl mb-4 opacity-15">◈</div>
        <div className="text-sm font-medium text-text-secondary">No records awaiting review</div>
        <div className="text-xs mt-1.5 max-w-xs text-center leading-relaxed">
          Records that the system cannot resolve automatically will appear here
        </div>
      </div>
    )
  }

  const handleSubmit = async () => {
    if (!current) return
    setSubmitting(true)
    try {
      // Separate question answers (q_*) from field overrides (field_*)
      const fieldOverrides: Record<string, string> = {}
      const questionAnswers: string[] = []
      for (const [key, value] of Object.entries(resolutions)) {
        if (key.startsWith('q_') && value) {
          const qIdx = parseInt(key.replace('q_', ''))
          const question = current.questions[qIdx] || `Question ${qIdx + 1}`
          questionAnswers.push(`${question.slice(0,60)}: ${value}`)
        } else if (key.startsWith('field_') && value) {
          fieldOverrides[key] = value
        }
      }
      const combinedNotes = [
        ...questionAnswers,
        ...(notes ? [notes] : [])
      ].join(' | ')

      await window.datamoa?.pipeline.resolveHITL(current.record_id, {
        resolved_fields: fieldOverrides,
        notes: combinedNotes,
      })
      resolveHITL(current.record_id)
      setResolutions({})
      setNotes('')
      toast.success(`Record ${current.record_id.slice(0, 8)} resolved`)

      // Select next
      const next = hitlQueue.find(r => r.record_id !== current.record_id)
      setSelectedId(next?.record_id || null)
    } catch (e: any) {
      toast.error('Resolution failed', e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleSkip = () => {
    if (!current) return
    const next = hitlQueue.find(r => r.record_id !== current.record_id)
    setSelectedId(next?.record_id || null)
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Queue sidebar */}
      <div className="w-56 shrink-0 border-r border-border-subtle bg-surface-1 flex flex-col">
        <div className="px-4 py-3 border-b border-border-subtle shrink-0">
          <div className="text-[10px] text-text-muted uppercase tracking-widest">Review Queue</div>
          <div className="text-xs text-text-primary font-medium mt-0.5">
            {hitlQueue.length} record{hitlQueue.length !== 1 ? 's' : ''}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-border-subtle">
          {hitlQueue.map((item) => (
            <button
              key={item.record_id}
              onClick={() => { setSelectedId(item.record_id); setResolutions({}); setNotes('') }}
              className={`w-full text-left px-4 py-3 transition-colors ${
                current?.record_id === item.record_id
                  ? 'bg-accent-amber/10 border-r-2 border-r-accent-amber'
                  : 'hover:bg-white/[0.03]'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1.5 h-1.5 rounded-full bg-accent-amber animate-pulse shrink-0" />
                <span className="text-xs font-mono text-text-secondary">{item.record_id.slice(0, 8)}</span>
              </div>
              <div className="text-[10px] text-text-muted leading-snug truncate">
                {item.questions[0]?.slice(0, 50) || 'Review needed'}
              </div>
              <div className="text-[9px] text-accent-amber mt-1">
                {item.questions.length} question{item.questions.length !== 1 ? 's' : ''}
                {item.flagged_fields.length > 0 && ` · ${item.flagged_fields.length} flagged`}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Review panel */}
      {current && (
        <div className="flex-1 overflow-y-auto">
          <div className="p-5 max-w-3xl mx-auto">
            {/* Header */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-2 h-2 rounded-full bg-accent-amber animate-pulse" />
              <span className="text-sm font-semibold text-text-primary">
                Record <span className="font-mono text-accent-blue">{current.record_id.slice(0, 8)}</span>
              </span>
              <div className="flex-1" />
              <button
                onClick={handleSkip}
                className="text-xs text-text-muted hover:text-text-secondary transition-colors"
              >
                Skip →
              </button>
            </div>

            {/* Reasoning context */}
            {current.reasoning_notes && (
              <div className="mb-5 p-4 bg-surface-2 rounded-lg border border-border-subtle">
                <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">
                  Why this record needs review
                </div>
                <div className="text-xs text-text-secondary leading-relaxed">
                  {current.reasoning_notes}
                </div>
              </div>
            )}

            {/* Questions requiring resolution */}
            <div className="mb-5">
              <div className="text-[10px] text-text-muted uppercase tracking-widest mb-3">
                Questions ({current.questions.length})
              </div>
              <div className="space-y-3">
                {current.questions.map((q, i) => (
                  <div key={i} className="p-4 bg-surface-2 rounded-lg border border-accent-amber/20">
                    <div className="text-xs text-accent-amber mb-3 leading-relaxed">{q}</div>
                    <input
                      type="text"
                      placeholder="Your answer..."
                      value={resolutions[`q_${i}`] || ''}
                      onChange={(e) => setResolutions(r => ({ ...r, [`q_${i}`]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && i === current.questions.length - 1) handleSubmit()
                      }}
                      className="w-full bg-surface-3 border border-border-default rounded px-3 py-2 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Two-column: flagged fields + field override */}
            {Object.keys(current.parsed_fields).length > 0 && (
              <div className="mb-5">
                <div className="text-[10px] text-text-muted uppercase tracking-widest mb-3">
                  Extracted Fields
                  {current.flagged_fields.length > 0 && (
                    <span className="ml-2 text-accent-amber">
                      ({current.flagged_fields.length} flagged ⚑)
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(current.parsed_fields).map(([key, value]) => {
                    const isFlagged = current.flagged_fields.includes(key)
                    const overrideKey = `field_${key}`
                    return (
                      <div
                        key={key}
                        className={`p-3 rounded-lg border ${
                          isFlagged
                            ? 'border-accent-amber/30 bg-amber-500/[0.05]'
                            : 'border-border-subtle bg-surface-2'
                        }`}
                      >
                        <div className={`text-[9px] mb-1 uppercase tracking-wide font-medium ${
                          isFlagged ? 'text-accent-amber' : 'text-text-muted'
                        }`}>
                          {isFlagged && '⚑ '}{key}
                        </div>
                        <div className="text-xs font-mono text-text-secondary truncate mb-2">
                          {String(value ?? '—')}
                        </div>
                        {isFlagged && (
                          <input
                            type="text"
                            placeholder="Override value..."
                            value={resolutions[overrideKey] || ''}
                            onChange={(e) => setResolutions(r => ({ ...r, [overrideKey]: e.target.value }))}
                            className="w-full bg-surface-3 border border-border-default rounded px-2 py-1 text-[10px] text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Raw text excerpt */}
            {current.raw_text_excerpt && (
              <div className="mb-5">
                <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">
                  Source Text (excerpt)
                </div>
                <pre className="text-[11px] font-mono text-text-muted bg-surface-2 rounded-lg border border-border-subtle p-3 whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed">
                  {current.raw_text_excerpt}
                </pre>
              </div>
            )}

            {/* Notes */}
            <div className="mb-5">
              <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">
                Notes (optional — logged to audit)
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Any additional context for the audit trail..."
                className="w-full bg-surface-2 border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder-text-muted resize-none h-16 focus:border-accent-blue/40 transition-colors"
              />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3">
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="px-6 py-2.5 bg-accent-blue text-white text-sm font-medium rounded-lg hover:bg-blue-500 disabled:opacity-40 transition-colors"
              >
                {submitting ? 'Submitting...' : 'Submit Resolution'}
              </button>
              <button
                onClick={handleSkip}
                className="px-4 py-2.5 border border-border-default text-text-secondary text-sm rounded-lg hover:border-border-strong hover:text-text-primary transition-colors"
              >
                Skip for Now
              </button>
              <div className="text-[10px] text-text-muted ml-auto">
                ↩ Enter on last question to submit
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
