import { useState, useEffect, useRef } from 'react'
import { API_BASE } from '../../utils/api'

interface ModelInfo {
  id: string
  provider: string
  label: string
  category: 'cloud' | 'local'
  context_k: number
  tool_use: boolean
  reasoning: boolean
  cost_tier: string
  recommended_for: string[]
  vram_required_gb?: number
}

interface ModelPickerProps {
  value: string
  agentName: string
  onChange: (model: string) => void
  hardware?: { gpu_vram_gb: number; ram_gb: number }
}

const COST_COLORS: Record<string, string> = {
  free: 'text-accent-green',
  very_low: 'text-accent-cyan',
  low: 'text-accent-blue',
  medium: 'text-accent-amber',
  high: 'text-accent-red',
}

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: 'bg-orange-500/15 text-orange-400',
  google: 'bg-blue-500/15 text-blue-400',
  groq: 'bg-green-500/15 text-green-400',
  deepseek: 'bg-cyan-500/15 text-cyan-400',
  perplexity: 'bg-purple-500/15 text-purple-400',
  moonshot: 'bg-pink-500/15 text-pink-400',
  openai: 'bg-emerald-500/15 text-emerald-400',
  ollama: 'bg-surface-4 text-text-secondary',
}

export default function ModelPicker({ value, agentName, onChange, hardware }: ModelPickerProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [recommended, setRecommended] = useState<ModelInfo[]>([])
  const [tab, setTab] = useState<'recommended' | 'all'>('recommended')
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [ollamaRunning, setOllamaRunning] = useState<boolean | null>(null)
  const [customInput, setCustomInput] = useState('')
  const [showCustom, setShowCustom] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Check Ollama status
    fetch(`${API_BASE}/system/ollama/status`)
      .then(r => r.json())
      .then((d: any) => {
        setOllamaRunning(d.running)
        if (d.running) {
          fetch(`${API_BASE}/system/ollama/models`)
            .then(r => r.json())
            .then((models: any[]) => setOllamaModels(models.map((m: any) => m.name)))
            .catch(() => {})
        }
      })
      .catch(() => setOllamaRunning(false))

    fetch(`${API_BASE}/models/registry`)
      .then(r => r.json())
      .then(setModels)
      .catch(() => {})

    fetch(`${API_BASE}/models/registry/agent/${agentName}`)
      .then(r => r.json())
      .then(setRecommended)
      .catch(() => {})
  }, [agentName])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const currentModel = models.find(m => m.id === value)
  const searchLower = search.toLowerCase()

  const filteredList = (tab === 'recommended' ? recommended : models).filter(m =>
    !search || m.label.toLowerCase().includes(searchLower) || m.id.toLowerCase().includes(searchLower)
  )

  // Group by provider
  const grouped = filteredList.reduce((acc, m) => {
    if (!acc[m.provider]) acc[m.provider] = []
    acc[m.provider].push(m)
    return acc
  }, {} as Record<string, ModelInfo[]>)

  const handleSelect = (modelId: string) => {
    onChange(modelId)
    setOpen(false)
    setSearch('')
  }

  return (
    <div ref={ref} className="relative flex-1">
      {/* Trigger */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`w-full flex items-center gap-2 bg-surface-3 border rounded px-2.5 py-1.5 text-left transition-colors ${
          open ? 'border-accent-blue/50' : 'border-border-default hover:border-border-strong'
        }`}
      >
        {currentModel ? (
          <>
            <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${PROVIDER_COLORS[currentModel.provider] || 'bg-surface-4 text-text-muted'}`}>
              {currentModel.provider}
            </span>
            <span className="text-xs text-text-primary truncate">{currentModel.label}</span>
            <div className="flex items-center gap-1 ml-auto shrink-0">
              {currentModel.tool_use && (
                <span title="Tool use" className="text-[9px] text-accent-green opacity-70">🔧</span>
              )}
              {currentModel.reasoning && (
                <span title="Reasoning" className="text-[9px] text-accent-purple opacity-70">🧠</span>
              )}
              <span className={`text-[9px] font-medium ${COST_COLORS[currentModel.cost_tier]}`}>
                {currentModel.cost_tier === 'free' ? 'free' : `$${currentModel.cost_tier}`}
              </span>
            </div>
          </>
        ) : (
          <span className="text-xs text-text-muted font-mono truncate">{value || 'Select model...'}</span>
        )}
        <span className="text-text-muted ml-1 shrink-0">{open ? '▲' : '▼'}</span>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-surface-2 border border-border-default rounded-lg shadow-xl overflow-hidden animate-slide-up min-w-[320px]">
          {/* Search */}
          <div className="p-2 border-b border-border-subtle">
            <input
              autoFocus
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search models..."
              className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
            />
          </div>

          {/* Ollama status */}
          {ollamaRunning === false && (
            <div className="px-3 py-1.5 bg-amber-500/10 border-b border-amber-500/20 text-[9px] text-accent-amber">
              ⚠ Ollama not running — local models unavailable
            </div>
          )}
          {ollamaRunning && ollamaModels.length === 0 && (
            <div className="px-3 py-1.5 bg-surface-1 border-b border-border-subtle text-[9px] text-text-muted">
              Ollama running but no models installed
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-b border-border-subtle px-2 pt-1">
            {(['recommended', 'all'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 text-[10px] font-medium capitalize transition-colors ${
                  tab === t ? 'text-accent-blue border-b border-accent-blue' : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {t} {t === 'recommended' ? `(${recommended.length})` : `(${models.length})`}
              </button>
            ))}
            {/* Custom model input */}
            <button
              onClick={() => {
                const custom = prompt('Enter model string (e.g. ollama/custom-model):')
                if (custom?.trim()) handleSelect(custom.trim())
              }}
              className="ml-auto text-[10px] text-text-muted hover:text-accent-blue transition-colors px-2"
            >
              + custom
            </button>
          </div>

          {/* Custom model input */}
          {showCustom && (
            <div className="px-2 py-1.5 border-b border-border-subtle bg-surface-1">
              <div className="flex gap-1.5">
                <input
                  autoFocus={showCustom}
                  type="text"
                  value={customInput}
                  onChange={e => setCustomInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && customInput.trim()) {
                      handleSelect(customInput.trim())
                      setCustomInput('')
                      setShowCustom(false)
                    }
                    if (e.key === 'Escape') setShowCustom(false)
                  }}
                  placeholder="provider/model-name (e.g. ollama/llama3.3:70b)"
                  className="flex-1 bg-surface-3 border border-border-default rounded px-2 py-1 text-[10px] text-text-primary font-mono focus:border-accent-blue/40 transition-colors"
                />
                <button
                  onClick={() => { if (customInput.trim()) { handleSelect(customInput.trim()); setCustomInput(''); setShowCustom(false) } }}
                  disabled={!customInput.trim()}
                  className="px-2 py-1 text-[9px] bg-accent-blue text-white rounded disabled:opacity-40"
                >
                  Use
                </button>
              </div>
              <div className="text-[9px] text-text-muted mt-1">Enter to confirm · Esc to cancel</div>
            </div>
          )}

          {/* Model list */}
          <div className="max-h-72 overflow-y-auto">
            {Object.entries(grouped).length === 0 ? (
              <div className="p-4 text-center text-xs text-text-muted">No models found</div>
            ) : (
              Object.entries(grouped).map(([provider, providerModels]) => (
                <div key={provider}>
                  <div className="px-3 py-1.5 text-[9px] text-text-muted uppercase tracking-widest bg-surface-1 sticky top-0">
                    {provider}
                  </div>
                  {providerModels.map(model => {
                    const isSelected = model.id === value
                    const ollamaUnavailable = model.provider === 'ollama' && ollamaRunning === false
                    const cantRun = ollamaUnavailable || (model.category === 'local' && hardware
                      ? hardware.gpu_vram_gb > 0
                        ? hardware.gpu_vram_gb < (model.vram_required_gb || 0)
                        : hardware.ram_gb < ((model.vram_required_gb || 0) * 1.5)
                      : false)

                    return (
                      <button
                        key={model.id}
                        onClick={() => !cantRun && handleSelect(model.id)}
                        disabled={cantRun}
                        className={`w-full text-left px-3 py-2 flex items-center gap-2 transition-colors ${
                          isSelected
                            ? 'bg-accent-blue/15 text-text-primary'
                            : cantRun
                            ? 'opacity-40 cursor-not-allowed'
                            : 'hover:bg-white/[0.04] text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs truncate">{model.label}</span>
                            {cantRun && (
                              <span className="text-[9px] text-accent-red">insufficient VRAM</span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="text-[9px] text-text-muted font-mono">{model.id.split('/')[1]}</span>
                            <span className="text-[9px] text-text-muted">·</span>
                            <span className="text-[9px] text-text-muted">{model.context_k}K ctx</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {model.tool_use && <span title="Tool use" className="text-[10px]">🔧</span>}
                          {model.reasoning && <span title="Reasoning" className="text-[10px]">🧠</span>}
                          {(model as any).web_search && <span title="Web search" className="text-[10px]">🌐</span>}
                          <span className={`text-[9px] font-medium ${COST_COLORS[model.cost_tier]}`}>
                            {model.cost_tier}
                          </span>
                          {isSelected && <span className="text-accent-blue text-[10px]">✓</span>}
                        </div>
                      </button>
                    )
                  })}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
