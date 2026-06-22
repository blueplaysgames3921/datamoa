import { useState, useEffect } from 'react'
import { API_BASE } from '../../utils/api'
import { toast } from '../shared/Toast'

interface OptConfig {
  speculative_decoding_enabled: boolean
  prompt_caching_enabled: boolean
  context_trimming_enabled: boolean
  parallel_batch_window_ms: number
  router?: {
    draft_models: Record<string, string>
    cache_supported_providers: string[]
  }
}

export default function OptimizationTab() {
  const [config, setConfig] = useState<OptConfig>({
    speculative_decoding_enabled: true,
    prompt_caching_enabled: true,
    context_trimming_enabled: true,
    parallel_batch_window_ms: 50,
  })
  const [loading, setLoading] = useState(true)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [inferenceProfile, setInferenceProfile] = useState<any>(null)
  const [warmPool, setWarmPool] = useState<any[]>([])

  useEffect(() => {
    fetch(`${API_BASE}/system/optimization`)
      .then(r => r.json())
      .then((d: OptConfig) => {
        setConfig(d)
        if ((d as any).inference_profile) setInferenceProfile((d as any).inference_profile)
        if ((d as any).warm_pool_slots) setWarmPool((d as any).warm_pool_slots)
        setLoading(false)
      })
      .catch(() => setLoading(false))

    fetch(`${API_BASE}/system/inference-profile`)
      .then(r => r.json())
      .then(setInferenceProfile)
      .catch(() => {})

    fetch(`${API_BASE}/system/ollama/models`)
      .then(r => r.json())
      .then((models: any[]) => setOllamaModels(models.map(m => m.name)))
      .catch(() => {})
  }, [])

  const update = async (patch: Partial<OptConfig>) => {
    const next = { ...config, ...patch }
    setConfig(next)
    try {
      await fetch(`${API_BASE}/system/optimization`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      toast.success('Optimization settings updated')
    } catch (e: any) {
      toast.error('Update failed', e.message)
    }
  }

  const draftInstalled = (draft: string) => {
    const name = draft.replace('ollama/', '')
    return ollamaModels.some(m => m.startsWith(name.split(':')[0]))
  }

  if (loading) return <div className="text-xs text-text-muted">Loading...</div>

  const draftPairs = Object.entries(config.router?.draft_models || {})
    .filter(([k]) => k !== '_default')

  return (
    <div className="max-w-xl space-y-5">
      {/* Prompt Caching */}
      <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-text-primary">Prompt Caching</div>
            <div className="text-[10px] text-text-muted mt-0.5">
              Reuse cached system prompts on Anthropic, Google, and Groq — cuts latency and cost on repeated calls
            </div>
          </div>
          <Toggle
            value={config.prompt_caching_enabled}
            onChange={v => update({ prompt_caching_enabled: v })}
          />
        </div>
        {config.router?.cache_supported_providers && (
          <div className="flex gap-1.5 flex-wrap">
            {config.router.cache_supported_providers.map(p => (
              <span key={p} className="text-[9px] bg-accent-blue/10 text-accent-blue border border-accent-blue/20 px-1.5 py-0.5 rounded">
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Inference Engine */}
      {inferenceProfile && (
        <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-2">
          <div className="text-xs font-medium text-text-primary">Local Inference Engine</div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <span className="text-text-muted">Engine: </span>
              <span className={`font-medium ${inferenceProfile.engine === 'cloud_only' ? 'text-accent-amber' : 'text-accent-green'}`}>
                {inferenceProfile.engine}
              </span>
            </div>
            <div>
              <span className="text-text-muted">Tier: </span>
              <span className="text-text-secondary">{inferenceProfile.hardware_tier}</span>
            </div>
            <div>
              <span className="text-text-muted">Quantization: </span>
              <span className={`font-medium font-mono ${
                inferenceProfile.quantization === 'int8' ? 'text-accent-green' :
                inferenceProfile.quantization === 'int4' ? 'text-accent-amber' :
                'text-accent-red'
              }`}>{inferenceProfile.quantization.toUpperCase()}</span>
            </div>
            <div>
              <span className="text-text-muted">Speculative: </span>
              <span className={inferenceProfile.supports_speculative ? 'text-accent-green' : 'text-text-muted'}>
                {inferenceProfile.supports_speculative ? '✓' : '✗'}
              </span>
            </div>
            {inferenceProfile.supports_mlx && (
              <div className="col-span-2">
                <span className="text-accent-blue font-medium">✦ MLX (Apple Silicon) — unified memory active</span>
              </div>
            )}
          </div>
          {inferenceProfile.notes?.length > 0 && (
            <div className="space-y-1 pt-1 border-t border-border-subtle">
              {inferenceProfile.notes.map((note: string, i: number) => (
                <div key={i} className="text-[9px] text-text-muted leading-relaxed">→ {note}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Warm Model Pool */}
      {warmPool.length > 0 && (
        <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-2">
          <div className="text-xs font-medium text-text-primary">Warm Model Pool</div>
          <div className="text-[10px] text-text-muted mb-2">
            {warmPool.length} active slot{warmPool.length !== 1 ? 's' : ''} — agents sharing slots avoid re-initialization overhead
          </div>
          <div className="space-y-1.5">
            {warmPool.map((slot: any) => (
              <div key={slot.model_id} className="flex items-center gap-2">
                <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${slot.active_calls > 0 ? 'bg-accent-blue animate-pulse' : 'bg-surface-4'}`} />
                <span className="font-mono text-[9px] text-text-secondary truncate flex-1">{slot.model_id.split('/').pop()}</span>
                <span className="text-[9px] text-text-muted shrink-0">{slot.roles.join(', ')}</span>
                {slot.total_calls > 0 && (
                  <span className="text-[9px] text-text-muted font-mono shrink-0">{slot.avg_latency_ms}ms avg</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Speculative Decoding */}
      <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-text-primary">Speculative Decoding</div>
            <div className="text-[10px] text-text-muted mt-0.5">
              Use a tiny draft model to predict tokens, verified by the target model — 2–4× faster local inference
            </div>
          </div>
          <Toggle
            value={config.speculative_decoding_enabled}
            onChange={v => update({ speculative_decoding_enabled: v })}
          />
        </div>

        {config.speculative_decoding_enabled && (
          <>
            <div className="text-[10px] text-text-muted uppercase tracking-widest">Draft Model Pairs</div>
            <div className="space-y-1.5">
              {draftPairs.map(([target, draft]) => {
                const installed = draftInstalled(draft)
                return (
                  <div key={target} className="flex items-center gap-2 text-[10px]">
                    <span className="font-mono text-text-secondary w-36 truncate">{target}</span>
                    <span className="text-text-muted">→</span>
                    <span className={`font-mono ${installed ? 'text-accent-green' : 'text-accent-amber'}`}>
                      {draft.replace('ollama/', '')}
                    </span>
                    {!installed && (
                      <span className="text-accent-amber ml-1">
                        ⚠ not installed
                      </span>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Show pull instructions for missing draft models */}
            {draftPairs.some(([, d]) => !draftInstalled(d)) && (
              <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded text-[10px] text-accent-amber">
                <div className="font-medium mb-1">Install draft models to enable speculative decoding:</div>
                <div className="font-mono space-y-0.5">
                  {['ollama pull gemma4:e2b', 'ollama pull lfm2.5:1.2b'].map(cmd => (
                    <div
                      key={cmd}
                      className="cursor-pointer hover:text-white transition-colors"
                      onClick={() => { navigator.clipboard.writeText(cmd); toast.info('Copied to clipboard', cmd) }}
                    >
                      $ {cmd}
                    </div>
                  ))}
                </div>
                <div className="mt-1 opacity-70">Click a command to copy it</div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Context Trimming */}
      <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-text-primary">Context Window Trimming</div>
            <div className="text-[10px] text-text-muted mt-0.5">
              Trim long documents to fit the model's context window. Preserves start and end, removes redundant middle content.
            </div>
          </div>
          <Toggle
            value={config.context_trimming_enabled}
            onChange={v => update({ context_trimming_enabled: v })}
          />
        </div>
      </div>

      {/* Parallel Batching */}
      <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-3">
        <div>
          <div className="text-xs font-medium text-text-primary">Parallel Batch Window</div>
          <div className="text-[10px] text-text-muted mt-0.5">
            Records arriving within this window are processed in parallel. Higher values batch more records together.
          </div>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={500}
            step={10}
            value={config.parallel_batch_window_ms}
            onChange={e => setConfig(c => ({ ...c, parallel_batch_window_ms: Number(e.target.value) }))}
            onMouseUp={() => update({ parallel_batch_window_ms: config.parallel_batch_window_ms })}
            className="flex-1"
          />
          <span className="text-xs font-mono text-accent-blue w-16 text-right">
            {config.parallel_batch_window_ms}ms
          </span>
        </div>
        <div className="text-[10px] text-text-muted">
          {config.parallel_batch_window_ms === 0
            ? 'Disabled — records process one at a time'
            : config.parallel_batch_window_ms < 100
            ? 'Low — minimal batching, lowest latency'
            : config.parallel_batch_window_ms < 300
            ? 'Medium — good balance for mixed workloads'
            : 'High — maximum batching throughput'}
        </div>
      </div>

      {/* Token budgeting info */}
      <div className="p-3 bg-surface-1 rounded border border-border-subtle">
        <div className="text-[10px] text-text-muted leading-relaxed">
          <span className="text-text-secondary font-medium">Token budgeting</span> is always active —
          output tokens are automatically capped to 20% of each model's context window,
          preventing wasted compute and context overflow errors.
        </div>
      </div>
    </div>
  )
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ${value ? 'bg-accent-blue' : 'bg-surface-4'}`}
    >
      <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${value ? 'translate-x-5' : 'translate-x-0.5'}`} />
    </button>
  )
}
