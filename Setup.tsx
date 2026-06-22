import { API_BASE } from '../utils/api'
import { useState } from 'react'
import { wsStore } from '../store/ws'

interface SetupProps {
  onComplete: () => void
}

type Step = 'welcome' | 'hardware' | 'config' | 'keys' | 'done'

interface HardwareInfo {
  gpu_name: string
  gpu_vram_gb: number
  ram_gb: number
  cpu_name: string
  can_run_local: boolean
}

interface ConfigProgress {
  step: string
  message: string
  assignments?: Record<string, string>
  hardware?: HardwareInfo
  warnings?: string[]
  error?: string
}

const PRESETS = [
  { id: 'high_end_local', label: 'High End Local', desc: '16GB+ VRAM — full local inference', icon: '🖥' },
  { id: 'cloud_only', label: 'Cloud Only', desc: 'No local models — all cloud APIs', icon: '☁️' },
  { id: 'balanced', label: 'Balanced', desc: '8GB VRAM — hybrid local + cloud', icon: '⚖️' },
  { id: 'privacy_first', label: 'Privacy First', desc: 'Nothing leaves your machine', icon: '🔒' },
  { id: 'budget', label: 'Budget', desc: 'Minimize API costs, free tiers', icon: '💰' },
]

export default function Setup({ onComplete }: SetupProps) {
  const [step, setStep] = useState<Step>('welcome')
  const [hardware, setHardware] = useState<HardwareInfo | null>(null)
  const [configProgress, setConfigProgress] = useState<ConfigProgress[]>([])
  const [configDone, setConfigDone] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [hasApiKey, setHasApiKey] = useState(false)
  const [geminiKey, setGeminiKey] = useState('')
  const [perplexityKey, setPerplexityKey] = useState('')

  const handleDetectHardware = async () => {
    const hw = await window.datamoa?.system.getHardware()
    setHardware(hw)
    setStep('config')
  }

  const handleRunConfigAgent = async () => {
    if (geminiKey) {
      await window.datamoa?.config.saveKey('google', geminiKey)
    }
    if (perplexityKey) {
      await window.datamoa?.config.saveKey('perplexity', perplexityKey)
    }

    await window.datamoa?.agents.runConfigAgent()

    // Listen for config agent progress via WS
    const unsub = wsStore.on('config:agent:progress', (data: any) => {
      setConfigProgress((p) => [...p, data as ConfigProgress])
      if ((data as ConfigProgress).step === 'complete' || (data as ConfigProgress).step === 'error') {
        setConfigDone(true)
        unsub()
      }
    })
  }

  const handleApplyPreset = async (presetId: string) => {
    setSelectedPreset(presetId)
    await fetch(`${API_BASE}/system/presets/${presetId}/apply`, { method: 'POST' })
    setConfigDone(true)
  }

  const handleFinish = async () => {
    const config = await window.datamoa?.config.get()
    await window.datamoa?.config.save({ ...config, first_launch: false })
    onComplete()
  }

  return (
    <div className="flex flex-col items-center justify-center h-full bg-surface-0 animate-fade-in">
      <div className="w-full max-w-lg px-8">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent-blue to-accent-cyan flex items-center justify-center">
            <span className="text-lg font-bold text-white">M</span>
          </div>
          <div>
            <div className="text-xl font-semibold text-text-primary">DataMoA</div>
            <div className="text-xs text-text-muted">Multi-Agent Data Entry System</div>
          </div>
        </div>

        {/* Step: Welcome */}
        {step === 'welcome' && (
          <div className="animate-slide-up text-center">
            <h1 className="text-2xl font-semibold text-text-primary mb-3">Welcome</h1>
            <p className="text-sm text-text-secondary mb-8 leading-relaxed">
              DataMoA uses a pipeline of specialized AI agents to process data entry reliably — from trivial to ambiguous.
              Let's configure the system for your hardware.
            </p>
            <button
              onClick={() => setStep('hardware')}
              className="w-full py-3 bg-accent-blue text-white font-medium rounded-lg hover:bg-blue-500 transition-colors"
            >
              Get Started
            </button>
          </div>
        )}

        {/* Step: Hardware */}
        {step === 'hardware' && (
          <div className="animate-slide-up">
            <h2 className="text-lg font-semibold text-text-primary mb-2">Detect Hardware</h2>
            <p className="text-sm text-text-secondary mb-6">
              We'll scan your system to recommend the right models for your hardware.
            </p>

            {hardware && (
              <div className="mb-5 p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-2">
                <HardwareRow label="GPU" value={`${hardware.gpu_name} (${hardware.gpu_vram_gb}GB VRAM)`} />
                <HardwareRow label="RAM" value={`${hardware.ram_gb}GB`} />
                <HardwareRow label="CPU" value={hardware.cpu_name} />
                <HardwareRow
                  label="Local Inference"
                  value={hardware.can_run_local ? '✓ Supported' : '✗ Not supported'}
                  valueClass={hardware.can_run_local ? 'text-accent-green' : 'text-accent-red'}
                />
              </div>
            )}

            <button
              onClick={handleDetectHardware}
              className="w-full py-2.5 bg-accent-blue text-white font-medium rounded-lg hover:bg-blue-500 transition-colors"
            >
              {hardware ? 'Re-detect' : 'Detect Hardware'}
            </button>

            {hardware && (
              <button
                onClick={() => setStep('config')}
                className="w-full mt-2 py-2.5 border border-border-default text-text-secondary rounded-lg hover:border-border-strong hover:text-text-primary transition-colors"
              >
                Continue →
              </button>
            )}
          </div>
        )}

        {/* Step: Config */}
        {step === 'config' && (
          <div className="animate-slide-up">
            <h2 className="text-lg font-semibold text-text-primary mb-2">Configure Models</h2>

            <div className="mb-5 p-4 bg-surface-2 rounded-lg border border-border-subtle">
              <div className="text-xs text-text-muted mb-3">
                Optionally add a Gemini or Perplexity key to let the AI choose optimal models for your hardware.
              </div>
              <input
                type="password"
                placeholder="Gemini API key (AIza...)"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                className="w-full bg-surface-3 border border-border-default rounded px-3 py-2 text-xs text-text-primary placeholder-text-muted mb-2 font-mono focus:border-accent-blue/40"
              />
              <input
                type="password"
                placeholder="Perplexity API key (pplx-...)"
                value={perplexityKey}
                onChange={(e) => setPerplexityKey(e.target.value)}
                className="w-full bg-surface-3 border border-border-default rounded px-3 py-2 text-xs text-text-primary placeholder-text-muted font-mono focus:border-accent-blue/40"
              />
            </div>

            {/* Config agent progress */}
            {configProgress.length > 0 && (
              <div className="mb-4 p-3 bg-surface-2 rounded border border-border-subtle max-h-32 overflow-y-auto">
                {configProgress.map((p, i) => (
                  <div key={i} className={`text-xs ${p.step === 'error' ? 'text-accent-red' : 'text-text-secondary'}`}>
                    {p.message}
                  </div>
                ))}
              </div>
            )}

            {!configDone && (
              <>
                <button
                  onClick={handleRunConfigAgent}
                  disabled={configProgress.length > 0 && !configDone}
                  className="w-full py-2.5 bg-accent-blue text-white font-medium rounded-lg hover:bg-blue-500 disabled:opacity-50 transition-colors mb-2"
                >
                  {configProgress.length > 0 ? 'Running...' : 'Auto-configure with AI'}
                </button>
                <div className="text-center text-xs text-text-muted my-3">or choose a preset</div>
                <div className="space-y-2">
                  {PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      onClick={() => handleApplyPreset(preset.id)}
                      className={`w-full text-left p-3 rounded-lg border transition-colors ${
                        selectedPreset === preset.id
                          ? 'border-accent-blue/40 bg-accent-blue/10'
                          : 'border-border-subtle bg-surface-2 hover:border-border-strong'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span>{preset.icon}</span>
                        <span className="text-xs font-medium text-text-secondary">{preset.label}</span>
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5 ml-6">{preset.desc}</div>
                    </button>
                  ))}
                </div>
              </>
            )}

            {configDone && (
              <button
                onClick={() => setStep('keys')}
                className="w-full py-2.5 bg-accent-green text-white font-medium rounded-lg hover:bg-green-500 transition-colors"
              >
                ✓ Configuration Complete — Add API Keys →
              </button>
            )}
          </div>
        )}

        {/* Step: Keys */}
        {step === 'keys' && (
          <div className="animate-slide-up">
            <h2 className="text-lg font-semibold text-text-primary mb-2">API Keys</h2>
            <p className="text-sm text-text-secondary mb-4">
              Add keys for the providers your configured models use. You can update these anytime in Settings.
            </p>
            <button
              onClick={() => setStep('done')}
              className="w-full py-2.5 border border-border-default text-text-secondary rounded-lg hover:border-border-strong hover:text-text-primary transition-colors"
            >
              I'll add keys in Settings →
            </button>
            <button
              onClick={handleFinish}
              className="w-full mt-2 py-2.5 bg-accent-blue text-white font-medium rounded-lg hover:bg-blue-500 transition-colors"
            >
              Open Settings Now
            </button>
          </div>
        )}

        {/* Step: Done */}
        {step === 'done' && (
          <div className="animate-slide-up text-center">
            <div className="text-4xl mb-4">✓</div>
            <h2 className="text-xl font-semibold text-text-primary mb-2">Ready</h2>
            <p className="text-sm text-text-secondary mb-6">
              DataMoA is configured and ready. Submit your first record from the Dashboard.
            </p>
            <button
              onClick={handleFinish}
              className="w-full py-3 bg-accent-blue text-white font-medium rounded-lg hover:bg-blue-500 transition-colors"
            >
              Open Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function HardwareRow({ label, value, valueClass = 'text-text-secondary' }: {
  label: string; value: string; valueClass?: string
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-text-muted uppercase tracking-widest">{label}</span>
      <span className={`text-xs font-medium ${valueClass}`}>{value}</span>
    </div>
  )
}
