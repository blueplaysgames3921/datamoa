import { useEffect, useState } from 'react'
import { wsStore } from '../store/ws'
import { API_BASE } from '../utils/api'

interface AuditLog {
  record_id: string
  retry_count: number
  completed_at: string
  stage: string
  entries: AuditEntry[]
  final_confidence: number | null
  write_success: boolean | null
}

interface AuditEntry {
  id: string
  record_id: string
  timestamp: string
  stage: string
  agent: string
  model: string
  action: string
  input_summary: string
  output_summary: string
  confidence_before: number | null
  confidence_after: number | null
  duration_ms: number
  error: string | null
}

interface AuditReport {
  batch_size: number
  issues_found: number
  critical_issues: string[]
  warnings: string[]
  patterns: string[]
  recommendations: string[]
  overall_assessment: string
  records_requiring_review: string[]
}

type SubTab = 'trail' | 'reports'

export default function Audit() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [reports, setReports] = useState<AuditReport[]>([])
  const [selected, setSelected] = useState<AuditLog | null>(null)
  const [selectedReport, setSelectedReport] = useState<AuditReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [subTab, setSubTab] = useState<SubTab>('trail')
  const [batchRunning, setBatchRunning] = useState(false)
  const [filter, setFilter] = useState<'all' | 'failed' | 'success'>('all')
  const [search, setSearch] = useState('')
  const [batchResult, setBatchResult] = useState<string | null>(null)

  useEffect(() => {
    loadLogs()
    loadReports()

    const unsub = wsStore.on('audit:batch:complete', (data: any) => {
      setBatchRunning(false)
      setBatchResult(`Analyzed ${data.records_analyzed} records. Found ${data.audit?.issues_found || 0} issues, learned ${data.learning?.learned || 0} patterns.`)
      loadReports()
      setTimeout(() => setBatchResult(null), 8000)
    })

    // Live: new audit entries
    const unsub2 = wsStore.on('audit:new:entry', () => {
      loadLogs()
    })

    return () => { unsub(); unsub2() }
  }, [])

  const loadLogs = async () => {
    const data = await window.datamoa?.audit.getLogs() as AuditLog[]
    setLogs(data || [])
    setLoading(false)
  }

  const loadReports = async () => {
    const res = await fetch(`${API_BASE}/audit/reports`)
    const data = await res.json()
    setReports(data || [])
  }

  const handleRunBatchAudit = async () => {
    setBatchRunning(true)
    setBatchResult(null)
    await fetch(`${API_BASE}/pipeline/audit/batch`, { method: 'POST' })
  }

  const handleExport = async (format: 'json' | 'csv') => {
    const data = await window.datamoa?.audit.exportLogs(format) as any
    const content = format === 'csv' ? data.csv : JSON.stringify(data, null, 2)
    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `datamoa-audit.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filteredLogs = logs.filter(log => {
    if (filter === 'failed' && log.write_success !== false) return false
    if (filter === 'success' && log.write_success !== true) return false
    if (search && !log.record_id.includes(search)) return false
    return true
  })

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-border-subtle bg-surface-1 shrink-0">
        <div className="flex gap-1">
          {(['trail', 'reports'] as SubTab[]).map(t => (
            <button
              key={t}
              onClick={() => setSubTab(t)}
              className={`px-3 py-1.5 text-xs rounded capitalize transition-colors ${
                subTab === t ? 'bg-accent-blue/15 text-accent-blue' : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {t === 'trail' ? `Audit Trail (${logs.length})` : `Reports (${reports.length})`}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {batchResult && (
          <div className="text-xs text-accent-green animate-fade-in">{batchResult}</div>
        )}

        <button
          onClick={handleRunBatchAudit}
          disabled={batchRunning}
          className="text-xs px-3 py-1.5 border border-border-default text-text-secondary rounded hover:border-border-strong hover:text-text-primary transition-colors disabled:opacity-50 flex items-center gap-1.5"
        >
          <span className={batchRunning ? 'animate-spin inline-block' : ''}>⚙</span>
          {batchRunning ? 'Running...' : 'Run Batch Audit'}
        </button>

        <div className="flex gap-1">
          <button onClick={() => handleExport('json')} className="text-xs px-2 py-1.5 border border-border-subtle text-text-muted rounded hover:border-border-default transition-colors">
            Export JSON
          </button>
          <button onClick={() => handleExport('csv')} className="text-xs px-2 py-1.5 border border-border-subtle text-text-muted rounded hover:border-border-default transition-colors">
            Export CSV
          </button>
        </div>
      </div>

      {/* Audit trail view */}
      {subTab === 'trail' && (
        <div className="flex flex-1 overflow-hidden">
          {/* Log list */}
          <div className="w-64 shrink-0 border-r border-border-subtle bg-surface-1 flex flex-col">
            {/* Filters */}
            <div className="p-2 border-b border-border-subtle space-y-1.5">
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search record ID..."
                className="w-full bg-surface-2 border border-border-default rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40"
              />
              <div className="flex gap-1">
                {(['all', 'success', 'failed'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`flex-1 py-1 text-[10px] rounded capitalize transition-colors ${
                      filter === f ? 'bg-surface-3 text-text-primary' : 'text-text-muted hover:text-text-secondary'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto divide-y divide-border-subtle">
              {loading ? (
                <div className="p-4 text-xs text-text-muted">Loading...</div>
              ) : filteredLogs.length === 0 ? (
                <div className="p-4 text-xs text-text-muted">No records match filter</div>
              ) : (
                filteredLogs.map((log) => (
                  <button
                    key={`${log.record_id}-${log.retry_count}`}
                    onClick={() => setSelected(log)}
                    className={`w-full text-left px-3 py-2.5 transition-colors ${
                      selected?.record_id === log.record_id && selected?.retry_count === log.retry_count
                        ? 'bg-accent-blue/10 border-r-2 border-r-accent-blue'
                        : 'hover:bg-white/[0.03]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        log.write_success ? 'bg-accent-green' : log.write_success === false ? 'bg-accent-red' : 'bg-text-muted'
                      }`} />
                      <span className="text-xs font-mono text-text-muted">{log.record_id.slice(0, 8)}</span>
                      {log.retry_count > 0 && (
                        <span className="text-[10px] font-mono text-text-muted/70">attempt {log.retry_count + 1}</span>
                      )}
                    </div>
                    <div className="text-[10px] text-text-muted mt-1 ml-3.5">
                      {new Date(log.completed_at).toLocaleString()}
                    </div>
                    {log.final_confidence !== null && (
                      <div className="text-[10px] text-text-muted ml-3.5 font-mono">
                        {Math.round((log.final_confidence || 0) * 100)}% confidence
                      </div>
                    )}
                    <div className="text-[10px] text-text-muted ml-3.5">
                      {log.entries?.length || 0} events
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Detail panel */}
          <div className="flex-1 overflow-y-auto">
            {!selected ? (
              <div className="flex flex-col items-center justify-center h-full text-text-muted">
                <div className="text-4xl mb-3 opacity-20">◉</div>
                <div className="text-sm">Select a record to view its audit trail</div>
              </div>
            ) : (
              <div className="p-5 max-w-2xl">
                {/* Record header */}
                <div className="flex items-center gap-3 mb-5 pb-4 border-b border-border-subtle">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-text-primary font-mono">
                        {selected.record_id.slice(0, 8)}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${
                        selected.write_success
                          ? 'border-accent-green/30 bg-green-500/10 text-accent-green'
                          : 'border-accent-red/30 bg-red-500/10 text-accent-red'
                      }`}>
                        {selected.write_success ? '✓ Written' : '✗ Not written'}
                      </span>
                      {selected.final_confidence !== null && (
                        <span className="text-xs text-text-muted font-mono">
                          {Math.round((selected.final_confidence || 0) * 100)}% final confidence
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-text-muted">
                      Completed {new Date(selected.completed_at).toLocaleString()}
                    </div>
                  </div>
                </div>

                {/* Timeline */}
                <div className="text-[10px] text-text-muted uppercase tracking-widest mb-3">
                  Agent Timeline ({selected.entries?.length || 0} events)
                </div>
                <div className="relative pl-6">
                  <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border-default" />
                  <div className="space-y-4">
                    {(selected.entries || []).map((entry, i) => (
                      <AuditEntryRow key={entry.id || i} entry={entry} />
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reports view */}
      {subTab === 'reports' && (
        <div className="flex flex-1 overflow-hidden">
          {/* Reports list */}
          <div className="w-52 shrink-0 border-r border-border-subtle bg-surface-1 overflow-y-auto divide-y divide-border-subtle">
            {reports.length === 0 ? (
              <div className="p-4 text-xs text-text-muted">
                No reports yet. Run a batch audit to generate one.
              </div>
            ) : (
              reports.map((report, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedReport(report)}
                  className={`w-full text-left px-3 py-3 transition-colors ${
                    selectedReport === report ? 'bg-accent-blue/10 border-r-2 border-r-accent-blue' : 'hover:bg-white/[0.03]'
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <div className={`w-1.5 h-1.5 rounded-full ${report.issues_found > 0 ? 'bg-accent-amber' : 'bg-accent-green'}`} />
                    <span className="text-xs text-text-secondary">{report.batch_size} records</span>
                  </div>
                  {report.issues_found > 0 && (
                    <div className="text-[10px] text-accent-amber">{report.issues_found} issues found</div>
                  )}
                  {report.critical_issues?.length > 0 && (
                    <div className="text-[10px] text-accent-red">{report.critical_issues.length} critical</div>
                  )}
                </button>
              ))
            )}
          </div>

          {/* Report detail */}
          <div className="flex-1 overflow-y-auto">
            {!selectedReport ? (
              <div className="flex flex-col items-center justify-center h-full text-text-muted">
                <div className="text-4xl mb-3 opacity-20">📋</div>
                <div className="text-sm">Select a report to view</div>
              </div>
            ) : (
              <div className="p-5 max-w-2xl space-y-4">
                {/* Summary */}
                <div className="p-4 bg-surface-2 rounded border border-border-subtle">
                  <div className="text-xs font-medium text-text-primary mb-2">Overall Assessment</div>
                  <div className="text-xs text-text-secondary leading-relaxed">
                    {selectedReport.overall_assessment}
                  </div>
                  <div className="flex gap-4 mt-3 text-xs">
                    <div>
                      <span className="text-text-muted">Records analyzed: </span>
                      <span className="text-text-primary font-medium">{selectedReport.batch_size}</span>
                    </div>
                    <div>
                      <span className="text-text-muted">Issues found: </span>
                      <span className={`font-medium ${selectedReport.issues_found > 0 ? 'text-accent-amber' : 'text-accent-green'}`}>
                        {selectedReport.issues_found}
                      </span>
                    </div>
                  </div>
                </div>

                {selectedReport.critical_issues?.length > 0 && (
                  <ReportSection title="Critical Issues" items={selectedReport.critical_issues} color="text-accent-red" bg="bg-red-500/5 border-red-500/20" />
                )}
                {selectedReport.warnings?.length > 0 && (
                  <ReportSection title="Warnings" items={selectedReport.warnings} color="text-accent-amber" bg="bg-amber-500/5 border-amber-500/20" />
                )}
                {selectedReport.patterns?.length > 0 && (
                  <ReportSection title="Patterns Identified" items={selectedReport.patterns} color="text-accent-blue" bg="bg-blue-500/5 border-blue-500/20" />
                )}
                {selectedReport.recommendations?.length > 0 && (
                  <ReportSection title="Recommendations" items={selectedReport.recommendations} color="text-accent-cyan" bg="bg-cyan-500/5 border-cyan-500/20" />
                )}
                {selectedReport.records_requiring_review?.length > 0 && (
                  <div>
                    <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Records Flagged for Review</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedReport.records_requiring_review.map(id => (
                        <span key={id} className="font-mono text-[10px] text-accent-amber bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                          {id.slice(0, 8)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function AuditEntryRow({ entry }: { entry: AuditEntry }) {
  const hasError = !!entry.error
  const hasConfidenceChange = entry.confidence_before !== null && entry.confidence_after !== null

  return (
    <div className="flex gap-3">
      <div className={`w-5 h-5 rounded-full border shrink-0 flex items-center justify-center text-[9px] font-bold z-10 -ml-6 ${
        hasError
          ? 'border-accent-red/50 bg-red-500/15 text-accent-red'
          : 'border-border-default bg-surface-2 text-text-muted'
      }`}>
        {entry.agent.slice(0, 2).toUpperCase()}
      </div>

      <div className="flex-1 pb-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-text-secondary capitalize">{entry.agent}</span>
          <span className="text-[10px] text-text-muted">·</span>
          <span className="text-[10px] text-text-muted">{entry.action.replace(/_/g, ' ')}</span>
          <span className="text-[10px] text-text-muted ml-auto">{entry.duration_ms}ms</span>
        </div>

        <div className="text-[10px] text-text-muted font-mono truncate mt-0.5">{entry.model}</div>

        {entry.input_summary && (
          <div className="text-[11px] text-text-muted mt-1">→ {entry.input_summary}</div>
        )}
        {entry.output_summary && (
          <div className="text-[11px] text-text-secondary">← {entry.output_summary}</div>
        )}

        {hasConfidenceChange && (
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-[10px] font-mono text-text-muted">
              {Math.round((entry.confidence_before! * 100))}%
            </span>
            <span className="text-[10px] text-text-muted">→</span>
            <span className={`text-[10px] font-mono font-medium ${
              entry.confidence_after! > entry.confidence_before!
                ? 'text-accent-green'
                : entry.confidence_after! < entry.confidence_before!
                ? 'text-accent-red'
                : 'text-text-muted'
            }`}>
              {Math.round((entry.confidence_after! * 100))}%
            </span>
            <span className="text-[10px] text-text-muted">
              ({entry.confidence_after! >= entry.confidence_before!
                ? `+${Math.round((entry.confidence_after! - entry.confidence_before!) * 100)}`
                : Math.round((entry.confidence_after! - entry.confidence_before!) * 100)}pp)
            </span>
          </div>
        )}

        {hasError && (
          <div className="text-[10px] text-accent-red mt-1 p-1.5 bg-red-500/10 rounded">
            {entry.error}
          </div>
        )}
      </div>
    </div>
  )
}

function ReportSection({ title, items, color, bg }: {
  title: string; items: string[]; color: string; bg: string
}) {
  return (
    <div>
      <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">{title}</div>
      <div className={`p-3 rounded border ${bg} space-y-1.5`}>
        {items.map((item, i) => (
          <div key={i} className={`text-xs ${color} leading-relaxed flex gap-2`}>
            <span className="shrink-0 opacity-60">·</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
