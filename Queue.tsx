import { useState, useMemo } from 'react'
import { usePipelineStore, RecordSummary } from '../store/pipeline'
import { toast } from '../components/shared/Toast'
import RecordDetail from '../components/pipeline/RecordDetail'
import { API_BASE } from '../utils/api'

const STAGE_PILL: Record<string, string> = {
  queued: 'text-text-muted bg-surface-3',
  intake: 'text-accent-blue bg-blue-500/10',
  parsing: 'text-accent-blue bg-blue-500/10',
  context: 'text-accent-cyan bg-cyan-500/10',
  confidence: 'text-accent-cyan bg-cyan-500/10',
  reasoning: 'text-purple-400 bg-purple-500/10',
  validation: 'text-accent-cyan bg-cyan-500/10',
  enrichment: 'text-accent-cyan bg-cyan-500/10',
  hitl: 'text-accent-amber bg-amber-500/10',
  writing: 'text-accent-blue bg-blue-500/10',
  audit: 'text-text-secondary bg-surface-3',
  complete: 'text-accent-green bg-green-500/10',
  failed: 'text-accent-red bg-red-500/10',
  cancelled: 'text-text-muted bg-surface-3',
}

type StageFilter = 'all' | 'active' | 'complete' | 'failed' | 'hitl'
type SortKey = 'created' | 'updated' | 'confidence' | 'stage'

export default function Queue() {
  const records = usePipelineStore((s) => s.records)
  const [stageFilter, setStageFilter] = useState<StageFilter>('all')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('created')
  const [sortAsc, setSortAsc] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = selectedId ? records[selectedId] ?? null : null

  const filtered = useMemo(() => {
    let list = Object.values(records)

    // Stage filter
    if (stageFilter === 'active') {
      list = list.filter(r => !['complete', 'failed', 'cancelled'].includes(r.stage))
    } else if (stageFilter === 'complete') {
      list = list.filter(r => r.stage === 'complete')
    } else if (stageFilter === 'failed') {
      list = list.filter(r => r.stage === 'failed')
    } else if (stageFilter === 'hitl') {
      list = list.filter(r => r.stage === 'hitl')
    }

    // Search
    if (search) {
      const q = search.toLowerCase()
      list = list.filter(r =>
        r.id.toLowerCase().includes(q) ||
        r.source_type.toLowerCase().includes(q) ||
        r.stage.toLowerCase().includes(q)
      )
    }

    // Sort
    list = [...list].sort((a, b) => {
      let val = 0
      if (sortKey === 'created') val = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      else if (sortKey === 'updated') val = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()
      else if (sortKey === 'confidence') val = (a.confidence_score || 0) - (b.confidence_score || 0)
      else if (sortKey === 'stage') val = a.stage.localeCompare(b.stage)
      return sortAsc ? val : -val
    })

    return list
  }, [records, stageFilter, search, sortKey, sortAsc])

  const handleCancel = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    await window.datamoa?.pipeline.cancel(id)
    toast.info('Record cancelled')
  }

  const handleExport = async (format: 'json' | 'csv') => {
    try {
      const res = await fetch(`${API_BASE}/pipeline/export?format=${format}&stage=${stageFilter === 'complete' ? 'complete' : 'all'}`)
      const data = await res.json() as any
      const count = data.count || 0
      if (count === 0) { toast.info('No records to export'); return }
      
      const content = format === 'csv' ? data.csv : JSON.stringify(data.records, null, 2)
      const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `datamoa-records-${new Date().toISOString().slice(0,10)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`Exported ${count} records`)
    } catch (e: any) {
      toast.error('Export failed', e.message)
    }
  }

  const handleRetry = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    await window.datamoa?.pipeline.retry(id)
    toast.success('Record requeued')
  }

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(a => !a)
    else { setSortKey(key); setSortAsc(false) }
  }

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? <span className="ml-1">{sortAsc ? '↑' : '↓'}</span> : null

  const counts = useMemo(() => ({
    all: Object.keys(records).length,
    active: Object.values(records).filter(r => !['complete', 'failed', 'cancelled'].includes(r.stage)).length,
    complete: Object.values(records).filter(r => r.stage === 'complete').length,
    failed: Object.values(records).filter(r => r.stage === 'failed').length,
    hitl: Object.values(records).filter(r => r.stage === 'hitl').length,
  }), [records])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-border-subtle bg-surface-1 shrink-0">
        <div className="flex items-center gap-3 mb-3">
          <div className="text-sm font-medium text-text-primary">Record Queue</div>
          <span className="text-xs text-text-muted">{filtered.length} of {counts.all} records</span>
          <div className="flex-1" />
          <div className="flex gap-1">
            <button onClick={() => handleExport('json')} className="text-[10px] text-text-muted px-2 py-1.5 border border-border-subtle rounded hover:border-border-default transition-colors">
              Export JSON
            </button>
            <button onClick={() => handleExport('csv')} className="text-[10px] text-text-muted px-2 py-1.5 border border-border-subtle rounded hover:border-border-default transition-colors">
              Export CSV
            </button>
          </div>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by ID, type, stage..."
            className="w-52 bg-surface-2 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
          />
        </div>

        {/* Stage filter tabs */}
        <div className="flex items-center gap-1">
          {([
            { id: 'all', label: `All (${counts.all})` },
            { id: 'active', label: `Active (${counts.active})` },
            { id: 'hitl', label: `Review (${counts.hitl})` },
            { id: 'complete', label: `Done (${counts.complete})` },
            { id: 'failed', label: `Failed (${counts.failed})` },
          ] as Array<{ id: StageFilter; label: string }>).map(f => (
            <button
              key={f.id}
              onClick={() => setStageFilter(f.id)}
              className={`px-3 py-1 text-[10px] rounded transition-colors ${
                stageFilter === f.id
                  ? 'bg-accent-blue/15 text-accent-blue'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-muted">
            <div className="text-3xl mb-3 opacity-20">≡</div>
            <div className="text-sm">No records match filter</div>
          </div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead className="sticky top-0 bg-surface-1 border-b border-border-subtle z-10">
              <tr>
                <th className="text-left px-5 py-2.5 text-text-muted font-medium w-28">
                  <button onClick={() => handleSort('created')} className="hover:text-text-secondary flex items-center">
                    ID <SortIcon k="created" />
                  </button>
                </th>
                <th className="text-left px-3 py-2.5 text-text-muted font-medium w-20">Type</th>
                <th className="text-left px-3 py-2.5 text-text-muted font-medium">
                  <button onClick={() => handleSort('stage')} className="hover:text-text-secondary flex items-center">
                    Stage <SortIcon k="stage" />
                  </button>
                </th>
                <th className="text-left px-3 py-2.5 text-text-muted font-medium">
                  <button onClick={() => handleSort('confidence')} className="hover:text-text-secondary flex items-center">
                    Confidence <SortIcon k="confidence" />
                  </button>
                </th>
                <th className="text-left px-3 py-2.5 text-text-muted font-medium">
                  <button onClick={() => handleSort('updated')} className="hover:text-text-secondary flex items-center">
                    Updated <SortIcon k="updated" />
                  </button>
                </th>
                <th className="px-3 py-2.5 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {filtered.map((record) => (
                <QueueRow
                  key={record.id}
                  record={record}
                  onSelect={() => setSelectedId(record.id)}
                  onCancel={handleCancel}
                  onRetry={handleRetry}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <RecordDetail record={selected} onClose={() => setSelectedId(null)} />
      )}
    </div>
  )
}

function QueueRow({ record, onSelect, onCancel, onRetry }: {
  record: RecordSummary
  onSelect: () => void
  onCancel: (e: React.MouseEvent, id: string) => void
  onRetry: (e: React.MouseEvent, id: string) => void
}) {
  const stageClass = STAGE_PILL[record.stage] || 'text-text-muted bg-surface-3'
  const canCancel = !['complete', 'failed', 'cancelled'].includes(record.stage)
  const tier = record.confidence_tier

  return (
    <tr
      className="hover:bg-white/[0.025] transition-colors cursor-pointer"
      onClick={onSelect}
    >
      <td className="px-5 py-2.5 font-mono text-text-muted">{record.id.slice(0, 8)}</td>
      <td className="px-3 py-2.5 text-text-secondary uppercase text-[10px]">{record.source_type || '—'}</td>
      <td className="px-3 py-2.5">
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${stageClass}`}>
          {record.stage}
        </span>
      </td>
      <td className="px-3 py-2.5">
        {record.confidence_score !== null ? (
          <div className="flex items-center gap-2">
            <div className="w-14 h-1.5 bg-surface-4 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  tier === 'green' ? 'bg-accent-green' :
                  tier === 'amber' ? 'bg-accent-amber' : 'bg-accent-red'
                }`}
                style={{ width: `${Math.round((record.confidence_score || 0) * 100)}%` }}
              />
            </div>
            <span className="text-text-muted font-mono tabular-nums">
              {Math.round((record.confidence_score || 0) * 100)}%
            </span>
          </div>
        ) : <span className="text-text-muted">—</span>}
      </td>
      <td className="px-3 py-2.5 text-text-muted font-mono tabular-nums">
        {new Date(record.updated_at).toLocaleTimeString()}
      </td>
      <td className="px-3 py-2.5 text-right">
        <div className="flex items-center justify-end gap-1">
          {record.stage === 'failed' && (
            <button
              onClick={(e) => onRetry(e, record.id)}
              className="text-[10px] text-text-muted hover:text-accent-blue transition-colors px-1.5 py-0.5 rounded hover:bg-blue-500/10"
            >
              Retry
            </button>
          )}
          {canCancel && (
            <button
              onClick={(e) => onCancel(e, record.id)}
              className="text-[10px] text-text-muted hover:text-accent-red transition-colors px-1.5 py-0.5 rounded hover:bg-red-500/10"
            >
              Cancel
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}
