import { useState, useCallback, useEffect } from 'react'
import { usePipelineStore, RecordSummary } from '../store/pipeline'
import { useAgentStore } from '../store/agents'
import RecordCard from '../components/pipeline/RecordCard'
import AgentStatusRow from '../components/agents/AgentStatus'
import FileDropZone from '../components/pipeline/FileDropZone'
import { wsStore } from '../store/ws'
import { uploadFiles } from '../utils/fileUpload'
import PipelineFlow from '../components/pipeline/PipelineFlow'
import ThresholdBadge from '../components/pipeline/ThresholdBadge'

type Page = 'dashboard' | 'queue' | 'review' | 'audit' | 'settings'

interface DashboardProps {
  onNavigate: (page: Page) => void
}

export default function Dashboard({ onNavigate }: DashboardProps) {
  const records = usePipelineStore((s) => s.records)
  const paused = usePipelineStore((s) => s.paused)
  const setPaused = usePipelineStore((s) => s.setPaused)
  const hitlQueue = usePipelineStore((s) => s.hitlQueue)
  const agents = useAgentStore((s) => s.agents)

  const [inputText, setInputText] = useState('')
  const [urlInput, setUrlInput] = useState('')
  const [health, setHealth] = useState<{ cpu_pct?: number; ram_pct?: number } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [uploadResults, setUploadResults] = useState<Array<{ filename: string; status: string }>>([])
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number; current: string } | null>(null)

  const recordList = Object.values(records).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )

  const active = recordList.filter((r) => !['complete', 'failed', 'cancelled'].includes(r.stage))
  const completed = recordList.filter((r) => r.stage === 'complete')
  const failed = recordList.filter((r) => r.stage === 'failed')

  const handleSubmitText = useCallback(async () => {
    if (!inputText.trim()) return
    setSubmitting(true)
    try {
      await window.datamoa?.pipeline.submit({ text: inputText, source_label: 'manual_input' })
      setInputText('')
    } finally {
      setSubmitting(false)
    }
  }, [inputText])

  const handleFilesDropped = useCallback(async (files: File[]) => {
    setSubmitting(true)
    setUploadResults([])
    setUploadProgress({ done: 0, total: files.length, current: files[0]?.name || '' })
    try {
      const results = await uploadFiles(files, (done, total, current) => {
        setUploadProgress({ done, total, current })
      })
      setUploadProgress(null)
      setUploadResults(results.map(r => ({ filename: r.filename, status: r.status })))
      setTimeout(() => setUploadResults([]), 5000)
    } finally {
      setSubmitting(false)
      setUploadProgress(null)
    }
  }, [])

  useEffect(() => {
    const unsub = wsStore.on('system:health', (data: any) => {
      setHealth(data?.system || null)
    })
    return () => unsub()
  }, [])

  const handleSubmitUrl = useCallback(async () => {
    const url = urlInput.trim()
    if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) return
    setSubmitting(true)
    try {
      await window.datamoa?.pipeline.submitUrl(url)
      setUrlInput('')
    } finally {
      setSubmitting(false)
    }
  }, [urlInput])

  const handleTogglePause = async () => {
    if (paused) {
      await window.datamoa?.pipeline.resume()
      setPaused(false)
    } else {
      await window.datamoa?.pipeline.pause()
      setPaused(true)
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-border-subtle">

        {/* Stats bar */}
        <div className="flex items-center gap-6 px-5 py-3 border-b border-border-subtle bg-surface-1 shrink-0">
          <Stat label="Active" value={active.length} color="text-accent-blue" />
          <Stat label="Complete" value={completed.length} color="text-accent-green" />
          <Stat label="Failed" value={failed.length} color="text-accent-red" />
          <Stat label="Review" value={hitlQueue.length} color="text-accent-amber" />
          <ThresholdBadge />
          {health && (
            <div className="flex items-center gap-3 text-[10px] text-text-muted ml-2 pl-3 border-l border-border-subtle">
              <span title="CPU Usage">CPU {health.cpu_pct?.toFixed(0)}%</span>
              <span title="RAM Usage">RAM {health.ram_pct?.toFixed(0)}%</span>
            </div>
          )}
          {completed.length + failed.length > 0 && (
            <Stat
              label="Success Rate"
              value={Math.round(completed.length / (completed.length + failed.length) * 100)}
              color={completed.length / (completed.length + failed.length) >= 0.9 ? 'text-accent-green' : 'text-accent-amber'}
              suffix="%"
            />
          )}
          <div className="flex-1" />
          <button
            onClick={handleTogglePause}
            className={`text-xs px-3 py-1.5 rounded border transition-colors ${
              paused
                ? 'border-accent-green/40 text-accent-green hover:bg-accent-green/10'
                : 'border-border-default text-text-secondary hover:border-border-strong hover:text-text-primary'
            }`}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          {hitlQueue.length > 0 && (
            <button
              onClick={() => onNavigate('review')}
              className="text-xs px-3 py-1.5 rounded border border-accent-amber/40 text-accent-amber hover:bg-accent-amber/10 transition-colors animate-pulse"
            >
              {hitlQueue.length} Awaiting Review →
            </button>
          )}
        </div>

        {/* Pipeline flow visualizer */}
        <div className="border-b border-border-subtle shrink-0 bg-surface-1">
          <PipelineFlow />
        </div>

        {/* Input area */}
        <div className="px-4 py-3 border-b border-border-subtle shrink-0 bg-surface-1 space-y-2">
          {/* File drop */}
          <FileDropZone onFilesDropped={handleFilesDropped} submitting={submitting} />

          {/* Upload progress */}
          {uploadProgress && uploadProgress.total > 1 && (
            <div className="flex items-center gap-2 text-xs animate-fade-in">
              <div className="flex-1 h-1 bg-surface-4 rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent-blue transition-all duration-300"
                  style={{ width: `${Math.round(uploadProgress.done / uploadProgress.total * 100)}%` }}
                />
              </div>
              <span className="text-text-muted shrink-0 tabular-nums text-[10px]">
                {uploadProgress.done}/{uploadProgress.total}
              </span>
              {uploadProgress.current && (
                <span className="text-text-muted text-[10px] truncate max-w-[120px]">{uploadProgress.current}</span>
              )}
            </div>
          )}

          {/* Upload feedback */}
          {uploadResults.length > 0 && (
            <div className="flex flex-wrap gap-1.5 animate-fade-in">
              {uploadResults.map((r, i) => (
                <span
                  key={i}
                  className={`text-[10px] px-2 py-0.5 rounded-full ${
                    r.status === 'queued'
                      ? 'bg-accent-green/10 text-accent-green border border-accent-green/20'
                      : 'bg-accent-red/10 text-accent-red border border-accent-red/20'
                  }`}
                >
                  {r.status === 'queued' ? '✓' : '✗'} {r.filename}
                </span>
              ))}
            </div>
          )}

          {/* Divider */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-px bg-border-subtle" />
            <span className="text-[10px] text-text-muted">or paste text</span>
            <div className="flex-1 h-px bg-border-subtle" />
          </div>

          {/* URL input */}
          <div className="flex gap-2">
            <input
              type="url"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmitUrl()}
              placeholder="https://example.com/data-page"
              className="flex-1 bg-surface-2 border border-border-default rounded px-3 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
            />
            <button
              onClick={handleSubmitUrl}
              disabled={submitting || !urlInput.trim().startsWith('http')}
              className="px-3 py-1.5 border border-border-default text-text-secondary text-xs rounded hover:border-border-strong hover:text-text-primary disabled:opacity-40 transition-colors shrink-0"
            >
              Fetch URL
            </button>
          </div>

          {/* Text input */}
          <div className="flex gap-2">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmitText()
              }}
              placeholder="Paste raw text, document content, or data to process..."
              className="flex-1 bg-surface-2 border border-border-default rounded px-3 py-2 text-xs text-text-primary placeholder-text-muted resize-none h-14 focus:border-accent-blue/40 transition-colors"
            />
            <button
              onClick={handleSubmitText}
              disabled={submitting || !inputText.trim()}
              className="px-4 py-2 bg-accent-blue text-white text-xs font-medium rounded hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors self-end"
            >
              {submitting ? '...' : 'Submit'}
            </button>
          </div>
          <div className="text-[10px] text-text-muted">⌘+Enter to submit text</div>
        </div>

        {/* Record list */}
        <div className="flex-1 overflow-y-auto">
          {recordList.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-text-muted">
              <div className="text-4xl mb-3 opacity-20">⬡</div>
              <div className="text-sm">No records yet</div>
              <div className="text-xs mt-1">Drop a file or paste text above to begin</div>
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {recordList.slice(0, 100).map((record) => (
                <RecordCard key={record.id} record={record} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right panel — agent status */}
      <div className="w-52 shrink-0 flex flex-col overflow-hidden bg-surface-1">
        <div className="px-4 py-3 border-b border-border-subtle">
          <div className="text-[10px] text-text-muted uppercase tracking-widest">Agent Activity</div>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-border-subtle">
          {Object.values(agents).map((agent) => (
            <AgentStatusRow key={agent.name} agent={agent} />
          ))}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, color, suffix = '' }: { label: string; value: number; color: string; suffix?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={`text-lg font-semibold tabular-nums ${color}`}>{value}{suffix}</span>
      <span className="text-[11px] text-text-muted">{label}</span>
    </div>
  )
}
