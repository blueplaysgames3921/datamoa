import { useEffect, useState } from 'react'
import { API_BASE } from '../utils/api'
import { useAgentStore, AGENT_NAMES } from '../store/agents'
import { wsStore } from '../store/ws'
import ModelPicker from '../components/config/ModelPicker'
import DestinationsTab from '../components/config/DestinationsTab'
import BackupsTab from '../components/config/BackupsTab'
import OptimizationTab from '../components/config/OptimizationTab'

interface ApiKeys { [provider: string]: string | null }

interface PipelineConfig {
  confidence_green_threshold: number
  confidence_amber_threshold: number
  max_concurrent_records: number
  auto_write_on_green: boolean
  retry_max_attempts: number
  retry_delay_seconds: number
  enrichment_enabled: boolean
  context_enabled: boolean
  learning_enabled: boolean
  audit_batch_enabled: boolean
}

const PROVIDERS = [
  { id: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-...', docs: 'https://console.anthropic.com' },
  { id: 'google', label: 'Google (Gemini)', placeholder: 'AIza...', docs: 'https://aistudio.google.com' },
  { id: 'groq', label: 'Groq', placeholder: 'gsk_...', docs: 'https://console.groq.com' },
  { id: 'deepseek', label: 'DeepSeek', placeholder: 'sk-...', docs: 'https://platform.deepseek.com' },
  { id: 'perplexity', label: 'Perplexity', placeholder: 'pplx-...', docs: 'https://www.perplexity.ai/settings/api' },
  { id: 'moonshot', label: 'Moonshot (Kimi)', placeholder: 'sk-...', docs: 'https://platform.moonshot.cn' },
  { id: 'openai', label: 'OpenAI', placeholder: 'sk-...', docs: 'https://platform.openai.com' },
  { id: 'airtable', label: 'Airtable', placeholder: 'pat...', docs: 'https://airtable.com/account' },
  { id: 'google_client_id', label: 'Google Client ID', placeholder: 'XXXX.apps.googleusercontent.com', docs: 'https://console.cloud.google.com/apis/credentials' },
  { id: 'google_client_secret', label: 'Google Client Secret', placeholder: 'GOCSPX-...', docs: 'https://console.cloud.google.com/apis/credentials' },
]

const AGENT_DESCRIPTIONS: Record<string, string> = {
  intake: 'Extracts raw text from files and images',
  parsing: 'Identifies and extracts structured fields',
  context: 'Applies historical memory to enrich data',
  confidence: 'Scores records and routes them by tier',
  reasoning: 'Resolves ambiguous and conflicting data',
  validation: 'Checks fields against rules before writing',
  enrichment: 'Fills missing fields via web search',
  hitl: 'Formats questions for human reviewers',
  write: 'Writes resolved data to destination systems',
  audit: 'Reviews completed records for quality',
  learning: 'Extracts patterns from human corrections',
  orchestrator: 'Coordinates all agents and pipeline flow',
}

export default function Settings() {
  const [tab, setTab] = useState<'keys' | 'models' | 'pipeline' | 'destinations' | 'backups' | 'optimization'>('keys')
  const [keys, setKeys] = useState<ApiKeys>({})
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({})
  const [showKey, setShowKey] = useState<Record<string, boolean>>({})
  const [pipelineConfig, setPipelineConfig] = useState<PipelineConfig>({
    confidence_green_threshold: 0.85,
    confidence_amber_threshold: 0.60,
    max_concurrent_records: 5,
    auto_write_on_green: true,
    retry_max_attempts: 3,
    retry_delay_seconds: 2.0,
    enrichment_enabled: true,
    context_enabled: true,
    learning_enabled: true,
    audit_batch_enabled: true,
  })
  const [saved, setSaved] = useState(false)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [hardware, setHardware] = useState<any>(null)
  const [configAgentRunning, setConfigAgentRunning] = useState(false)
  const [configAgentLog, setConfigAgentLog] = useState<string[]>([])

  const models = useAgentStore((s) => s.models)
  const setModels = useAgentStore((s) => s.setModels)
  const loadModels = useAgentStore((s) => s.loadModels)

  useEffect(() => {
    window.datamoa?.config.getKeys().then(setKeys)
    window.datamoa?.config.get().then((config: any) => {
      if (config?.pipeline) setPipelineConfig(prev => ({ ...prev, ...config.pipeline }))
    })
    window.datamoa?.system.getHardware().then(setHardware)
    loadModels()

    // Listen for config agent progress
    window.datamoa?.on('config:agent:progress', (data: any) => {
      setConfigAgentLog(l => [...l, data.message])
      if (data.step === 'complete') {
        setConfigAgentRunning(false)
        loadModels()
        setTimeout(() => setConfigAgentLog([]), 5000)
      }
      if (data.step === 'error') setConfigAgentRunning(false)
    })
  }, [])

  const handleSaveKey = async (provider: string) => {
    const key = keyInputs[provider]
    if (!key?.trim()) return
    setSavingKey(provider)
    await window.datamoa?.config.saveKey(provider, key)
    setKeyInputs(k => ({ ...k, [provider]: '' }))
    const updated = await window.datamoa?.config.getKeys()
    setKeys(updated)
    setSavingKey(null)
  }

  const handleDeleteKey = async (provider: string) => {
    await window.datamoa?.config.deleteKey(provider)
    const updated = await window.datamoa?.config.getKeys()
    setKeys(updated)
  }

  const handleModelChange = async (agent: string, model: string) => {
    await window.datamoa?.agents.assignModel(agent, model)
    setModels({ ...models, [agent]: model })
  }

  const handleSavePipeline = async () => {
    const config = await window.datamoa?.config.get()
    await window.datamoa?.config.save({ ...config, pipeline: pipelineConfig })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleRunConfigAgent = async () => {
    setConfigAgentRunning(true)
    setConfigAgentLog(['Starting Config Agent...'])
    await window.datamoa?.agents.runConfigAgent()
  }

  const tabs = [
    { id: 'keys' as const, label: 'API Keys', icon: '🔑' },
    { id: 'models' as const, label: 'Models', icon: '🤖' },
    { id: 'pipeline' as const, label: 'Pipeline', icon: '⚙' },
    { id: 'destinations' as const, label: 'Destinations', icon: '📤' },
    { id: 'backups' as const, label: 'Backups', icon: '💾' },
    { id: 'optimization' as const, label: 'Performance', icon: '⚡' },
  ]

  return (
    <div className="flex h-full overflow-hidden">
      {/* Settings sidebar */}
      <div className="w-44 shrink-0 border-r border-border-subtle bg-surface-1 pt-2">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors ${
              tab === t.id
                ? 'bg-accent-blue/10 text-accent-blue border-r-2 border-accent-blue'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.04]'
            }`}
          >
            <span>{t.icon}</span>
            <span className="text-xs font-medium">{t.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">

        {/* ─── API Keys ─── */}
        {tab === 'keys' && (
          <div className="max-w-xl">
            <div className="mb-5">
              <h2 className="text-sm font-semibold text-text-primary mb-1">API Keys</h2>
              <p className="text-xs text-text-muted">
                Keys are stored locally on your machine, encrypted at rest. They never leave your device except to call their respective provider APIs.
              </p>
            </div>
            <div className="space-y-2">
              {PROVIDERS.map((provider) => {
                const hasKey = !!keys[provider.id]
                const isSaving = savingKey === provider.id
                return (
                  <div key={provider.id} className={`p-3 rounded border transition-colors ${hasKey ? 'border-accent-green/20 bg-green-500/[0.03]' : 'border-border-subtle bg-surface-2'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-text-secondary">{provider.label}</span>
                        {hasKey && (
                          <span className="text-[9px] text-accent-green bg-green-500/10 px-1.5 py-0.5 rounded border border-green-500/20">
                            ✓ Saved
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <a
                          href={provider.docs}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-text-muted hover:text-accent-blue transition-colors"
                        >
                          Get key ↗
                        </a>
                        {hasKey && (
                          <button
                            onClick={() => handleDeleteKey(provider.id)}
                            className="text-[10px] text-text-muted hover:text-accent-red transition-colors"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <input
                          type={showKey[provider.id] ? 'text' : 'password'}
                          placeholder={hasKey ? '••••••••••••' : provider.placeholder}
                          value={keyInputs[provider.id] || ''}
                          onChange={(e) => setKeyInputs(k => ({ ...k, [provider.id]: e.target.value }))}
                          onKeyDown={(e) => e.key === 'Enter' && handleSaveKey(provider.id)}
                          className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 pr-8 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors font-mono"
                        />
                        <button
                          onClick={() => setShowKey(s => ({ ...s, [provider.id]: !s[provider.id] }))}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary text-[10px]"
                        >
                          {showKey[provider.id] ? '🙈' : '👁'}
                        </button>
                      </div>
                      <button
                        onClick={() => handleSaveKey(provider.id)}
                        disabled={!keyInputs[provider.id]?.trim() || isSaving}
                        className="px-3 py-1.5 bg-accent-blue text-white text-xs rounded hover:bg-blue-500 disabled:opacity-40 transition-colors whitespace-nowrap"
                      >
                        {isSaving ? '...' : 'Save'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* ─── Models ─── */}
        {tab === 'models' && (
          <div className="max-w-3xl">
            <div className="flex items-start justify-between mb-5">
              <div>
                <h2 className="text-sm font-semibold text-text-primary mb-1">Model Assignment</h2>
                <p className="text-xs text-text-muted">
                  Each agent uses a dedicated model. Changes take effect immediately.
                </p>
              </div>
              <button
                onClick={handleRunConfigAgent}
                disabled={configAgentRunning}
                className="text-xs px-3 py-1.5 border border-border-default text-text-secondary rounded hover:border-border-strong hover:text-text-primary transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                <span className={configAgentRunning ? 'animate-spin' : ''}>↺</span>
                {configAgentRunning ? 'Running...' : 'Re-run Config Agent'}
              </button>
            </div>

            {/* Config agent log */}
            {configAgentLog.length > 0 && (
              <div className="mb-4 p-3 bg-surface-2 rounded border border-border-subtle">
                {configAgentLog.map((msg, i) => (
                  <div key={i} className="text-xs text-text-secondary leading-relaxed">{msg}</div>
                ))}
              </div>
            )}

            {/* Hardware notice */}
            {hardware && (
              <div className="mb-4 flex items-center gap-2 text-[10px] text-text-muted p-2 bg-surface-2 rounded border border-border-subtle">
                <span>🖥</span>
                <span>{hardware.gpu_name} · {hardware.gpu_vram_gb}GB VRAM · {hardware.ram_gb}GB RAM</span>
                <span className={`ml-auto font-medium ${hardware.can_run_local ? 'text-accent-green' : 'text-accent-amber'}`}>
                  {hardware.can_run_local ? '✓ Local inference available' : '⚡ Cloud-only recommended'}
                </span>
              </div>
            )}

            {/* Agent model rows */}
            <div className="space-y-2">
              {AGENT_NAMES.map((agent) => (
                <div key={agent} className="p-3 bg-surface-2 rounded border border-border-subtle">
                  <div className="flex items-start gap-3">
                    <div className="w-28 shrink-0 pt-0.5">
                      <div className="text-xs font-medium text-text-primary capitalize">{agent}</div>
                      <div className="text-[10px] text-text-muted mt-0.5 leading-relaxed">
                        {AGENT_DESCRIPTIONS[agent]}
                      </div>
                    </div>
                    <ModelPicker
                      value={models[agent] || ''}
                      agentName={agent}
                      onChange={(model) => handleModelChange(agent, model)}
                      hardware={hardware}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Ollama section */}
            <OllamaSection />

            {/* Legend */}
            <div className="mt-4 flex flex-wrap items-center gap-4 text-[10px] text-text-muted">
              <span>🔧 Tool use</span>
              <span>🧠 Reasoning</span>
              <span>🌐 Web search</span>
              <span className="text-accent-green">free = local/free tier</span>
              <span className="text-accent-cyan">very_low = &lt;$0.01/1K</span>
              <span className="text-accent-amber">medium = $0.01–$0.10/1K</span>
              <span className="text-accent-red">high = &gt;$0.10/1K</span>
            </div>
          </div>
        )}

        {/* ─── Pipeline ─── */}
        {tab === 'pipeline' && (
          <div className="max-w-md">
            <div className="mb-5">
              <h2 className="text-sm font-semibold text-text-primary mb-1">Pipeline Settings</h2>
              <p className="text-xs text-text-muted">Configure how records flow through the pipeline.</p>
            </div>

            <div className="space-y-3">
              {/* Confidence thresholds */}
              <div className="p-4 bg-surface-2 rounded border border-border-subtle space-y-4">
                <div className="text-xs font-medium text-text-secondary">Confidence Thresholds</div>

                <ConfigSlider
                  label="Green Threshold"
                  description="Records at or above this score proceed automatically without any model review"
                  value={pipelineConfig.confidence_green_threshold}
                  onChange={(v) => setPipelineConfig(c => ({ ...c, confidence_green_threshold: v }))}
                  color="text-accent-green"
                  min={50} max={100}
                />
                <ConfigSlider
                  label="Amber Threshold"
                  description="Records between amber and green go to the Reasoning Agent. Below amber goes to HITL."
                  value={pipelineConfig.confidence_amber_threshold}
                  onChange={(v) => setPipelineConfig(c => ({ ...c, confidence_amber_threshold: v }))}
                  color="text-accent-amber"
                  min={20} max={90}
                />

                {/* Visual tier preview */}
                <div className="flex items-center gap-0 rounded overflow-hidden text-[9px] font-medium h-5">
                  <div
                    className="bg-accent-red/30 text-accent-red flex items-center justify-center"
                    style={{ width: `${Math.round(pipelineConfig.confidence_amber_threshold * 100)}%` }}
                  >
                    {Math.round(pipelineConfig.confidence_amber_threshold * 100) > 10 ? 'HITL' : ''}
                  </div>
                  <div
                    className="bg-accent-amber/30 text-accent-amber flex items-center justify-center"
                    style={{ width: `${Math.round((pipelineConfig.confidence_green_threshold - pipelineConfig.confidence_amber_threshold) * 100)}%` }}
                  >
                    {Math.round((pipelineConfig.confidence_green_threshold - pipelineConfig.confidence_amber_threshold) * 100) > 8 ? 'REASON' : ''}
                  </div>
                  <div
                    className="bg-accent-green/30 text-accent-green flex items-center justify-center flex-1"
                  >
                    AUTO
                  </div>
                </div>
              </div>

              {/* Concurrency */}
              <div className="p-4 bg-surface-2 rounded border border-border-subtle">
                <div className="text-xs font-medium text-text-secondary mb-1">Max Concurrent Records</div>
                <div className="text-[10px] text-text-muted mb-3">
                  How many records process in parallel. Higher values use more API credits simultaneously.
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range" min={1} max={20}
                    value={pipelineConfig.max_concurrent_records}
                    onChange={e => setPipelineConfig(c => ({ ...c, max_concurrent_records: Number(e.target.value) }))}
                    className="flex-1"
                  />
                  <span className="text-sm font-semibold text-accent-blue w-6 text-center">
                    {pipelineConfig.max_concurrent_records}
                  </span>
                </div>
              </div>

              {/* Retry */}
              <div className="p-4 bg-surface-2 rounded border border-border-subtle">
                <div className="text-xs font-medium text-text-secondary mb-1">Retry Settings</div>
                <div className="grid grid-cols-2 gap-3 mt-2">
                  <div>
                    <div className="text-[10px] text-text-muted mb-1">Max Attempts</div>
                    <input
                      type="number" min={0} max={10}
                      value={pipelineConfig.retry_max_attempts}
                      onChange={e => setPipelineConfig(c => ({ ...c, retry_max_attempts: Number(e.target.value) }))}
                      className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary"
                    />
                  </div>
                  <div>
                    <div className="text-[10px] text-text-muted mb-1">Retry Delay (s)</div>
                    <input
                      type="number" min={0.5} max={30} step={0.5}
                      value={pipelineConfig.retry_delay_seconds}
                      onChange={e => setPipelineConfig(c => ({ ...c, retry_delay_seconds: Number(e.target.value) }))}
                      className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary"
                    />
                  </div>
                </div>
              </div>

              {/* Agent feature flags */}
              <div className="p-4 bg-surface-2 rounded border border-border-subtle space-y-3">
                <div className="text-xs font-medium text-text-secondary">Agent Pipeline Features</div>
                <div className="text-[10px] text-text-muted">Toggle agents on/off. Disabled agents are skipped entirely.</div>
                {([
                  { key: 'enrichment_enabled', label: 'Enrichment Agent', desc: 'Fill missing fields via web search (adds latency + API cost)' },
                  { key: 'context_enabled', label: 'Context Agent', desc: 'Apply historical memory to improve accuracy on known sources' },
                  { key: 'learning_enabled', label: 'Learning Agent', desc: 'Extract patterns from HITL corrections (runs in background)' },
                  { key: 'audit_batch_enabled', label: 'Batch Audit', desc: 'Periodic quality analysis over completed records' },
                ] as const).map(({ key, label, desc }) => (
                  <div key={key} className="flex items-center justify-between">
                    <div className="flex-1 min-w-0 mr-4">
                      <div className="text-xs text-text-secondary">{label}</div>
                      <div className="text-[10px] text-text-muted mt-0.5">{desc}</div>
                    </div>
                    <button
                      onClick={() => setPipelineConfig(c => ({ ...c, [key]: !(c as any)[key] }))}
                      className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ${(pipelineConfig as any)[key] !== false ? 'bg-accent-blue' : 'bg-surface-4'}`}
                    >
                      <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${(pipelineConfig as any)[key] !== false ? 'translate-x-5' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                ))}
              </div>

              {/* Auto-write toggle */}
              <div className="p-4 bg-surface-2 rounded border border-border-subtle flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-text-secondary">Auto-write on Green</div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    Automatically write records that score above the green threshold
                  </div>
                </div>
                <button
                  onClick={() => setPipelineConfig(c => ({ ...c, auto_write_on_green: !c.auto_write_on_green }))}
                  className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ml-4 ${
                    pipelineConfig.auto_write_on_green ? 'bg-accent-blue' : 'bg-surface-4'
                  }`}
                >
                  <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${
                    pipelineConfig.auto_write_on_green ? 'translate-x-5' : 'translate-x-0.5'
                  }`} />
                </button>
              </div>

              <button
                onClick={handleSavePipeline}
                className={`w-full py-2.5 text-sm font-medium rounded transition-colors ${
                  saved ? 'bg-accent-green text-white' : 'bg-accent-blue text-white hover:bg-blue-500'
                }`}
              >
                {saved ? '✓ Saved' : 'Save Pipeline Settings'}
              </button>
            </div>
          </div>
        )}

        {/* ─── Backups ─── */}
        {tab === 'backups' && (
          <div>
            <div className="mb-5">
              <h2 className="text-sm font-semibold text-text-primary mb-1">Backups</h2>
              <p className="text-xs text-text-muted">
                Automatic backups of your configuration, memory, and audit logs. Stored in a folder you can access directly.
              </p>
            </div>
            <BackupsTab />
          </div>
        )}

        {/* ─── Performance ─── */}
        {tab === 'optimization' && (
          <div>
            <div className="mb-5">
              <h2 className="text-sm font-semibold text-text-primary mb-1">Performance</h2>
              <p className="text-xs text-text-muted">
                Prompt caching, speculative decoding, context trimming, and parallel batching.
                Changes take effect immediately without restart.
              </p>
            </div>
            <OptimizationTab />
          </div>
        )}

        {/* ─── Destinations ─── */}
        {tab === 'destinations' && (
          <div>
            <div className="mb-5">
              <h2 className="text-sm font-semibold text-text-primary mb-1">Write Destinations</h2>
              <p className="text-xs text-text-muted">
                Where the Write Agent sends completed records. The first enabled destination is used.
              </p>
            </div>
            <DestinationsTab />
          </div>
        )}
      </div>
    </div>
  )
}

function ConfigSlider({ label, description, value, onChange, color, min = 0, max = 100 }: {
  label: string; description: string; value: number
  onChange: (v: number) => void; color: string; min?: number; max?: number
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-0.5">
        <span className="text-xs text-text-secondary">{label}</span>
        <span className={`text-xs font-mono font-semibold ${color}`}>{Math.round(value * 100)}%</span>
      </div>
      <div className="text-[10px] text-text-muted mb-2">{description}</div>
      <input
        type="range" min={min} max={max}
        value={Math.round(value * 100)}
        onChange={e => onChange(Number(e.target.value) / 100)}
        className="w-full"
      />
    </div>
  )
}


function OllamaSection() {
  const [status, setStatus] = useState<{ running: boolean; version?: string } | null>(null)
  const [models, setModels] = useState<Array<{ name: string; size_gb: number }>>([])
  const [pulling, setPulling] = useState<string | null>(null)
  const [pullInput, setPullInput] = useState('')
  const [pullProgress, setPullProgress] = useState<string | null>(null)

  useEffect(() => {
    const check = async () => {
      const res = await fetch(`${API_BASE}/system/ollama/status`)
      const d = await res.json() as any
      setStatus(d)
      if (d.running) {
        const mres = await fetch(`${API_BASE}/system/ollama/models`)
        setModels(await mres.json())
      }
    }
    check()

    // Listen for pull progress
    const unsub = wsStore.on('ollama:pull:progress', (data: any) => {
      if (data.status === 'success') {
        setPulling(null)
        setPullProgress(null)
        check() // refresh model list
      } else {
        setPullProgress(data.status || '')
      }
    })
    return () => unsub()
  }, [])

  const handlePull = async () => {
    if (!pullInput.trim()) return
    setPulling(pullInput.trim())
    setPullProgress('Starting...')
    await fetch(`${API_BASE}/system/ollama/pull/${encodeURIComponent(pullInput.trim())}`, { method: 'POST' })
    setPullInput('')
  }

  return (
    <div className="mt-6 p-4 bg-surface-2 rounded-lg border border-border-subtle">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xs font-medium text-text-secondary">Ollama (Local Models)</div>
          <div className={`text-[10px] mt-0.5 ${status?.running ? 'text-accent-green' : 'text-accent-red'}`}>
            {status === null ? 'Checking...' : status.running ? `✓ Running${status.version ? ` v${status.version}` : ''}` : '✗ Not running — install from ollama.ai'}
          </div>
        </div>
        {status?.running && (
          <span className="text-[9px] text-text-muted">{models.length} model{models.length !== 1 ? 's' : ''} installed</span>
        )}
      </div>

      {status?.running && (
        <>
          {/* Installed models */}
          {models.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {models.map(m => (
                <span key={m.name} className="text-[9px] font-mono bg-surface-3 border border-border-subtle text-text-muted px-1.5 py-0.5 rounded">
                  {m.name} <span className="text-text-muted opacity-60">{m.size_gb}GB</span>
                </span>
              ))}
            </div>
          )}

          {/* Pull model */}
          <div className="flex gap-2">
            <input
              type="text"
              value={pullInput}
              onChange={e => setPullInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handlePull()}
              placeholder="gemma3:4b, llama3.3:70b, qwen2.5:7b..."
              disabled={!!pulling}
              className="flex-1 bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs font-mono text-text-primary placeholder-text-muted focus:border-accent-blue/40 disabled:opacity-50 transition-colors"
            />
            <button
              onClick={handlePull}
              disabled={!pullInput.trim() || !!pulling}
              className="px-3 py-1.5 text-xs bg-accent-blue text-white rounded hover:bg-blue-500 disabled:opacity-40 transition-colors whitespace-nowrap"
            >
              {pulling ? 'Pulling...' : 'Pull Model'}
            </button>
          </div>
          {pullProgress && (
            <div className="text-[10px] text-text-muted mt-1.5 font-mono truncate">
              {pulling && <span className="text-accent-blue mr-1">↓</span>}{pullProgress}
            </div>
          )}
        </>
      )}
    </div>
  )
}
