import { useEffect, useState } from 'react'
import { RecordSummary } from '../../store/pipeline'

interface RecordDetailProps {
  record: RecordSummary
  onClose: () => void
}

interface FullRecord {
  id: string
  stage: string
  source_type: string
  source_raw: string
  created_at: string
  updated_at: string
  parsed?: {
    fields: Record<string, unknown>
    document_type: string
    field_confidences: Array<{ field: string; value: unknown; confidence: number; flagged: boolean; reason?: string }>
    parse_notes: string
  }
  confidence?: {
    overall_score: number
    tier: string
    flagged_fields: string[]
    routing_reason: string
  }
  reasoning?: {
    resolved_fields: Record<string, unknown>
    unresolved_fields: string[]
    confidence_after: number
    reasoning_notes: string
    requires_hitl: boolean
    hitl_questions: string[]
  }
  validation?: {
    passed: boolean
    errors: string[]
    warnings: string[]
    is_duplicate: boolean
  }
  hitl?: {
    resolved_fields: Record<string, unknown>
    notes: string
    resolved_at: string
  }
  write_result?: {
    success: boolean
    destination: string
    error?: string
    written_fields: Record<string, unknown>
  }
  resolved_data: Record<string, unknown>
  error_message?: string
  retry_count: number
}

const TIER_COLORS = {
  green: 'text-accent-green bg-green-500/10 border-green-500/20',
  amber: 'text-accent-amber bg-amber-500/10 border-amber-500/20',
  red: 'text-accent-red bg-red-500/10 border-red-500/20',
}

export default function RecordDetail({ record, onClose }: RecordDetailProps) {
  const [full, setFull] = useState<FullRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'fields' | 'raw' | 'reasoning' | 'validation' | 'write'>('fields')

  useEffect(() => {
    setLoading(true)
    window.datamoa?.pipeline.getRecord(record.id).then((data: unknown) => {
      setFull(data as FullRecord)
      setLoading(false)
    })
  }, [record.id])

  const tierKey = (record.confidence_tier || 'red') as keyof typeof TIER_COLORS

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-[480px] h-full bg-surface-1 border-l border-border-default shadow-2xl flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle shrink-0">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-text-muted">{record.id.slice(0, 8)}</span>
              <span className="text-[10px] text-text-muted uppercase">{record.source_type}</span>
              {record.confidence_tier && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded border font-medium uppercase ${TIER_COLORS[tierKey]}`}>
                  {record.confidence_tier}
                </span>
              )}
            </div>
            <div className="text-xs text-text-secondary capitalize mt-0.5">{record.stage}</div>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-xs text-text-muted animate-pulse">Loading...</div>
          </div>
        ) : !full ? (
          <div className="flex-1 flex items-center justify-center text-xs text-text-muted">
            Record not found
          </div>
        ) : (
          <>
            {/* Confidence bar */}
            {record.confidence_score !== null && (
              <div className="px-4 py-2 border-b border-border-subtle shrink-0">
                <div className="flex items-center justify-between text-[10px] text-text-muted mb-1">
                  <span>Confidence</span>
                  <span className="font-mono font-medium">{Math.round((record.confidence_score || 0) * 100)}%</span>
                </div>
                <div className="h-1.5 bg-surface-4 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      tierKey === 'green' ? 'bg-accent-green' :
                      tierKey === 'amber' ? 'bg-accent-amber' : 'bg-accent-red'
                    }`}
                    style={{ width: `${Math.round((record.confidence_score || 0) * 100)}%` }}
                  />
                </div>
                {full.confidence?.routing_reason && (
                  <div className="text-[10px] text-text-muted mt-1 leading-relaxed">
                    {full.confidence.routing_reason}
                  </div>
                )}
              </div>
            )}

            {/* Error banner */}
            {full.error_message && (
              <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-xs text-accent-red">
                {full.error_message}
                {full.retry_count > 0 && ` (retried ${full.retry_count}×)`}
              </div>
            )}

            {/* Tab bar */}
            <div className="flex border-b border-border-subtle px-4 shrink-0">
              {[
                { id: 'fields', label: 'Fields' },
                { id: 'raw', label: 'Raw Text' },
                { id: 'reasoning', label: 'Reasoning' },
                { id: 'validation', label: 'Validation' },
                { id: 'write', label: 'Write' },
              ].map(t => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id as any)}
                  className={`px-3 py-2 text-[10px] transition-colors ${
                    tab === t.id
                      ? 'text-accent-blue border-b border-accent-blue'
                      : 'text-text-muted hover:text-text-secondary'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-4">

              {/* Fields */}
              {tab === 'fields' && (
                <div className="space-y-1.5">
                  {full.parsed?.field_confidences && full.parsed.field_confidences.length > 0 ? (
                    full.parsed.field_confidences.map((fc) => {
                      const resolved = full.resolved_data?.[fc.field]
                      const wasChanged = resolved !== undefined && String(resolved) !== String(fc.value)
                      return (
                        <div
                          key={fc.field}
                          className={`p-2.5 rounded border text-xs ${
                            fc.flagged
                              ? 'border-accent-amber/30 bg-amber-500/[0.05]'
                              : 'border-border-subtle bg-surface-2'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-[10px] font-medium ${fc.flagged ? 'text-accent-amber' : 'text-text-muted'}`}>
                              {fc.flagged && '⚑ '}{fc.field}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <ConfidencePip score={fc.confidence} />
                              <span className="text-[9px] text-text-muted font-mono">
                                {Math.round(fc.confidence * 100)}%
                              </span>
                            </div>
                          </div>
                          <div className="font-mono text-text-secondary truncate">
                            {String(fc.value ?? '—')}
                          </div>
                          {wasChanged && (
                            <div className="mt-1 text-[10px] text-accent-green">
                              → Resolved to: {String(resolved)}
                            </div>
                          )}
                          {fc.reason && (
                            <div className="mt-1 text-[10px] text-text-muted italic">{fc.reason}</div>
                          )}
                        </div>
                      )
                    })
                  ) : full.parsed?.fields ? (
                    Object.entries(full.parsed.fields).map(([k, v]) => (
                      <div key={k} className="p-2.5 rounded border border-border-subtle bg-surface-2">
                        <div className="text-[10px] text-text-muted mb-0.5">{k}</div>
                        <div className="text-xs font-mono text-text-secondary">{String(v ?? '—')}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-text-muted">No fields extracted yet</div>
                  )}
                </div>
              )}

              {/* Raw text */}
              {tab === 'raw' && (
                <div>
                  <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">
                    Source Text ({full.source_raw?.length || 0} chars)
                  </div>
                  <pre className="text-[11px] font-mono text-text-muted bg-surface-2 rounded border border-border-subtle p-3 whitespace-pre-wrap leading-relaxed overflow-x-auto">
                    {full.source_raw || 'No raw text available'}
                  </pre>
                </div>
              )}

              {/* Reasoning */}
              {tab === 'reasoning' && (
                <div className="space-y-3">
                  {!full.reasoning ? (
                    <div className="text-xs text-text-muted">Reasoning agent was not invoked (record was Green tier)</div>
                  ) : (
                    <>
                      <div className="text-[10px] text-text-muted uppercase tracking-widest">Agent Notes</div>
                      <div className="text-xs text-text-secondary leading-relaxed bg-surface-2 rounded border border-border-subtle p-3">
                        {full.reasoning.reasoning_notes || 'No notes'}
                      </div>

                      {Object.keys(full.reasoning.resolved_fields || {}).length > 0 && (
                        <div>
                          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Resolved Fields</div>
                          <div className="space-y-1">
                            {Object.entries(full.reasoning.resolved_fields).map(([k, v]) => (
                              <div key={k} className="flex items-center gap-2 p-2 bg-accent-green/5 rounded border border-accent-green/20">
                                <span className="text-[10px] text-text-muted">{k}</span>
                                <span className="text-xs text-accent-green font-mono ml-auto">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {full.reasoning.unresolved_fields?.length > 0 && (
                        <div>
                          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Unresolved</div>
                          <div className="flex flex-wrap gap-1">
                            {full.reasoning.unresolved_fields.map(f => (
                              <span key={f} className="text-[10px] text-accent-red bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
                                {f}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {full.reasoning.hitl_questions?.length > 0 && (
                        <div>
                          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">HITL Questions</div>
                          <div className="space-y-1.5">
                            {full.reasoning.hitl_questions.map((q, i) => (
                              <div key={i} className="text-xs text-accent-amber bg-amber-500/10 rounded border border-amber-500/20 p-2.5">
                                {q}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  {/* HITL Resolution */}
                  {full.hitl && (
                    <div>
                      <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Human Resolution</div>
                      <div className="p-3 bg-surface-2 rounded border border-border-subtle">
                        <div className="text-[10px] text-text-muted mb-2">
                          Resolved {new Date(full.hitl.resolved_at).toLocaleString()}
                        </div>
                        {Object.entries(full.hitl.resolved_fields).map(([k, v]) => (
                          <div key={k} className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] text-text-muted">{k}</span>
                            <span className="text-xs font-mono text-text-secondary ml-auto">{String(v)}</span>
                          </div>
                        ))}
                        {full.hitl.notes && (
                          <div className="text-[10px] text-text-muted mt-2 italic">{full.hitl.notes}</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Validation */}
              {tab === 'validation' && (
                <div className="space-y-3">
                  {!full.validation ? (
                    <div className="text-xs text-text-muted">Validation not yet run</div>
                  ) : (
                    <>
                      <div className={`flex items-center gap-2 p-3 rounded border ${
                        full.validation.passed
                          ? 'border-accent-green/30 bg-green-500/5'
                          : 'border-accent-red/30 bg-red-500/5'
                      }`}>
                        <span className={full.validation.passed ? 'text-accent-green' : 'text-accent-red'}>
                          {full.validation.passed ? '✓ Passed' : '✗ Failed'}
                        </span>
                        {full.validation.is_duplicate && (
                          <span className="text-accent-amber text-xs">· Possible duplicate</span>
                        )}
                      </div>

                      {full.validation.errors?.length > 0 && (
                        <div>
                          <div className="text-[10px] text-accent-red uppercase tracking-widest mb-1.5">Errors</div>
                          <div className="space-y-1">
                            {full.validation.errors.map((e, i) => (
                              <div key={i} className="text-xs text-accent-red bg-red-500/10 rounded p-2">{e}</div>
                            ))}
                          </div>
                        </div>
                      )}

                      {full.validation.warnings?.length > 0 && (
                        <div>
                          <div className="text-[10px] text-accent-amber uppercase tracking-widest mb-1.5">Warnings</div>
                          <div className="space-y-1">
                            {full.validation.warnings.map((w, i) => (
                              <div key={i} className="text-xs text-accent-amber bg-amber-500/10 rounded p-2">{w}</div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Write result */}
              {tab === 'write' && (
                <div className="space-y-3">
                  {!full.write_result ? (
                    <div className="text-xs text-text-muted">Not yet written</div>
                  ) : (
                    <>
                      <div className={`flex items-center gap-2 p-3 rounded border ${
                        full.write_result.success
                          ? 'border-accent-green/30 bg-green-500/5'
                          : 'border-accent-red/30 bg-red-500/5'
                      }`}>
                        <span className={full.write_result.success ? 'text-accent-green' : 'text-accent-red'}>
                          {full.write_result.success ? '✓ Written' : '✗ Write Failed'}
                        </span>
                        <span className="text-xs text-text-muted ml-auto">{full.write_result.destination}</span>
                      </div>

                      {full.write_result.error && (
                        <div className="text-xs text-accent-red bg-red-500/10 rounded border border-red-500/20 p-2.5">
                          {full.write_result.error}
                        </div>
                      )}

                      {full.write_result.success && Object.keys(full.write_result.written_fields || {}).length > 0 && (
                        <div>
                          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Written Fields</div>
                          <div className="space-y-1">
                            {Object.entries(full.write_result.written_fields).map(([k, v]) => (
                              <div key={k} className="flex items-center gap-2 p-2 bg-surface-2 rounded border border-border-subtle">
                                <span className="text-[10px] text-text-muted truncate">{k}</span>
                                <span className="text-xs font-mono text-text-secondary ml-auto truncate max-w-[200px]">
                                  {String(v ?? '—')}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function ConfidencePip({ score }: { score: number }) {
  const color = score >= 0.85 ? 'bg-accent-green' : score >= 0.6 ? 'bg-accent-amber' : 'bg-accent-red'
  return <div className={`w-1.5 h-1.5 rounded-full ${color}`} />
}
