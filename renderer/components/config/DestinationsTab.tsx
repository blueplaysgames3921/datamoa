import { useToastStore } from '../shared/Toast'
import { useState, useEffect } from 'react'
import { API_BASE, apiGet, apiPost, apiDelete } from '../../utils/api'

type DestType = 'csv' | 'google_sheets' | 'airtable' | 'database' | 'api'

interface Destination {
  id: string
  type: DestType
  name: string
  config: Record<string, string>
  enabled: boolean
  field_mapping?: Record<string, string>
  exclude_fields?: string[]
}

const DEST_TYPES: { id: DestType; label: string; icon: string; description: string }[] = [
  { id: 'csv', label: 'CSV File', icon: '📄', description: 'Append rows to a local CSV file' },
  { id: 'google_sheets', label: 'Google Sheets', icon: '🟢', description: 'Append rows to a Google Sheet' },
  { id: 'airtable', label: 'Airtable', icon: '🟠', description: 'Create records in an Airtable base' },
  { id: 'database', label: 'Database', icon: '🗄', description: 'Insert rows into a SQL database' },
  { id: 'api', label: 'REST API', icon: '🔗', description: 'POST data to a custom endpoint' },
]

const DEST_FIELDS: Record<DestType, Array<{ key: string; label: string; placeholder: string; type?: string }>> = {
  csv: [
    { key: 'file_path', label: 'File Path', placeholder: '/Users/you/output.csv' },
  ],
  google_sheets: [
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', placeholder: '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms' },
    { key: 'sheet_name', label: 'Sheet Name', placeholder: 'Sheet1' },
  ],
  airtable: [
    { key: 'base_id', label: 'Base ID', placeholder: 'appXXXXXXXXXXXXXX' },
    { key: 'table_name', label: 'Table Name', placeholder: 'Records' },
  ],
  database: [
    { key: 'connection_string', label: 'Connection String', placeholder: 'postgresql://user:pass@localhost/db', type: 'password' },
    { key: 'table', label: 'Table Name', placeholder: 'data_entries' },
  ],
  api: [
    { key: 'url', label: 'Endpoint URL', placeholder: 'https://api.example.com/records' },
    { key: 'auth_header', label: 'Authorization Header', placeholder: 'Bearer your-token-here', type: 'password' },
    { key: 'method', label: 'HTTP Method', placeholder: 'POST' },
  ],
}

export default function DestinationsTab() {
  const [destinations, setDestinations] = useState<Destination[]>([])
  const [adding, setAdding] = useState(false)
  const [newType, setNewType] = useState<DestType>('csv')
  const [newName, setNewName] = useState('')
  const [newConfig, setNewConfig] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string }>>({})

  useEffect(() => {
    loadDestinations()
  }, [])

  const loadDestinations = async () => {
    const config = await window.datamoa?.config.get() as any
    setDestinations(config?.destinations || [])
  }

  const saveDestinations = async (dests: Destination[]) => {
    const config = await window.datamoa?.config.get() as any
    await window.datamoa?.config.save({ ...config, destinations: dests })
    setDestinations(dests)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleAdd = async () => {
    if (!newName.trim()) return
    // Parse field mapping from _field_mapping textarea
    const fieldMappingRaw = newConfig['_field_mapping'] || ''
    const fieldMapping: Record<string, string> = {}
    for (const line of fieldMappingRaw.split('\n')) {
      const [src, dst] = line.split('=').map(s => s.trim())
      if (src && dst) fieldMapping[src] = dst
    }
    const cleanConfig = { ...newConfig }
    delete cleanConfig['_field_mapping']

    const dest: Destination = {
      id: `dest_${Date.now()}`,
      type: newType,
      name: newName,
      config: cleanConfig,
      enabled: true,
      field_mapping: fieldMapping,
      exclude_fields: [],
    }
    await saveDestinations([...destinations, dest])
    setAdding(false)
    setNewName('')
    setNewConfig({})
  }

  const handleToggle = async (id: string) => {
    const updated = destinations.map(d =>
      d.id === id ? { ...d, enabled: !d.enabled } : d
    )
    await saveDestinations(updated)
  }

  const handleDelete = async (id: string) => {
    await saveDestinations(destinations.filter(d => d.id !== id))
  }

  const handleTest = async (dest: Destination) => {
    setTesting(dest.id)
    try {
      // Send a test ping to the backend
      const res = await fetch(`${API_BASE}/pipeline/test-destination`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dest),
      })
      const data = await res.json() as any
      setTestResults(r => ({ ...r, [dest.id]: { ok: data.ok, message: data.message || 'Connected' } }))
    } catch (e: any) {
      setTestResults(r => ({ ...r, [dest.id]: { ok: false, message: e.message || 'Connection failed' } }))
    } finally {
      setTesting(null)
    }
  }

  const typeInfo = DEST_TYPES.find(t => t.id === newType)!

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-4">
        <div className="text-xs text-text-muted">
          Configure where the Write Agent sends completed records. The first enabled destination is used.
        </div>
        <button
          onClick={() => setAdding(true)}
          className="text-xs px-3 py-1.5 bg-accent-blue text-white rounded hover:bg-blue-500 transition-colors"
        >
          + Add Destination
        </button>
      </div>

      {/* Existing destinations */}
      {destinations.length === 0 && !adding && (
        <div className="p-6 border-2 border-dashed border-border-default rounded-lg text-center">
          <div className="text-text-muted text-sm mb-1">No destinations configured</div>
          <div className="text-text-muted text-xs">Add a destination to enable the Write Agent</div>
        </div>
      )}

      <div className="space-y-2 mb-4">
        {destinations.map((dest) => {
          const typeInfo = DEST_TYPES.find(t => t.id === dest.type)
          const testResult = testResults[dest.id]
          return (
            <div
              key={dest.id}
              className={`p-3 rounded border transition-colors ${
                dest.enabled ? 'border-border-default bg-surface-2' : 'border-border-subtle bg-surface-1 opacity-60'
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="text-base">{typeInfo?.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-text-primary">{dest.name}</span>
                    <span className="text-[10px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded">
                      {typeInfo?.label}
                    </span>
                    {dest.enabled && (
                      <span className="text-[10px] text-accent-green bg-green-500/10 px-1.5 py-0.5 rounded border border-green-500/20">
                        Active
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5 font-mono truncate">
                    {Object.entries(dest.config)
                      .filter(([k]) => !k.includes('password') && !k.includes('auth') && !k.includes('connection'))
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(' · ')}
                  </div>
                  {testResult && (
                    <div className={`text-[10px] mt-1 ${testResult.ok ? 'text-accent-green' : 'text-accent-red'}`}>
                      {testResult.ok ? '✓' : '✗'} {testResult.message}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleTest(dest)}
                    disabled={testing === dest.id}
                    className="text-[10px] text-text-muted hover:text-accent-blue transition-colors px-2 py-1 rounded border border-border-subtle hover:border-accent-blue/30"
                  >
                    {testing === dest.id ? '...' : 'Test'}
                  </button>
                  <button
                    onClick={() => handleToggle(dest.id)}
                    className={`w-8 h-4 rounded-full transition-colors relative ${dest.enabled ? 'bg-accent-blue' : 'bg-surface-4'}`}
                  >
                    <div className={`w-3 h-3 rounded-full bg-white absolute top-0.5 transition-transform ${dest.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                  </button>
                  <button
                    onClick={() => handleDelete(dest.id)}
                    className="text-[10px] text-text-muted hover:text-accent-red transition-colors"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Add destination form */}
      {adding && (
        <div className="p-4 bg-surface-2 rounded border border-accent-blue/30 animate-slide-up">
          <div className="text-xs font-medium text-text-primary mb-3">New Destination</div>

          {/* Type selector */}
          <div className="grid grid-cols-5 gap-1.5 mb-3">
            {DEST_TYPES.map((t) => (
              <button
                key={t.id}
                onClick={() => { setNewType(t.id); setNewConfig({}) }}
                className={`p-2 rounded border text-center transition-colors ${
                  newType === t.id
                    ? 'border-accent-blue/50 bg-accent-blue/10'
                    : 'border-border-subtle hover:border-border-default'
                }`}
              >
                <div className="text-base mb-0.5">{t.icon}</div>
                <div className="text-[9px] text-text-muted leading-tight">{t.label}</div>
              </button>
            ))}
          </div>

          <div className="text-[10px] text-text-muted mb-3">{typeInfo.description}</div>

          {/* Name */}
          <div className="mb-2">
            <label className="text-[10px] text-text-muted uppercase tracking-widest block mb-1">Name</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={`My ${typeInfo.label}`}
              className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
            />
          </div>

          {/* Type-specific fields */}
          {DEST_FIELDS[newType].map((field) => (
            <div key={field.key} className="mb-2">
              <label className="text-[10px] text-text-muted uppercase tracking-widest block mb-1">{field.label}</label>
              <input
                type={field.type || 'text'}
                value={newConfig[field.key] || ''}
                onChange={(e) => setNewConfig(c => ({ ...c, [field.key]: e.target.value }))}
                placeholder={field.placeholder}
                className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors font-mono"
              />
            </div>
          ))}

          {/* Google Sheets OAuth note */}
          {newType === 'google_sheets' && (
            <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded text-[10px] text-accent-amber mb-3">
              Requires Google OAuth. You'll be prompted to authenticate after saving. Make sure your Google API key is set in the Keys tab.
            </div>
          )}

          {/* Field mapping */}
          <div className="mb-2">
            <div className="text-[10px] text-text-muted uppercase tracking-widest mb-1">
              Field Mapping (optional)
            </div>
            <div className="text-[9px] text-text-muted mb-1.5">
              Map extracted field names → destination column names. One per line: source_field=dest_field
            </div>
            <textarea
              value={newConfig['_field_mapping'] || ''}
              onChange={(e) => setNewConfig(c => ({ ...c, _field_mapping: e.target.value }))}
              placeholder={"invoice_number=Invoice No\ntotal_amount=Amount\nvendor_name=Supplier"}
              className="w-full bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-[10px] font-mono text-text-primary placeholder-text-muted resize-none h-16 focus:border-accent-blue/40 transition-colors"
            />
          </div>

          <div className="flex gap-2 mt-3">
            <button
              onClick={handleAdd}
              disabled={!newName.trim()}
              className="px-4 py-1.5 bg-accent-blue text-white text-xs rounded hover:bg-blue-500 disabled:opacity-40 transition-colors"
            >
              Add Destination
            </button>
            <button
              onClick={() => { setAdding(false); setNewName(''); setNewConfig({}) }}
              className="px-4 py-1.5 border border-border-default text-text-secondary text-xs rounded hover:border-border-strong transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {saved && (
        <div className="text-xs text-accent-green mt-2 animate-fade-in">✓ Destinations saved</div>
      )}
    </div>
  )
}

function GoogleSheetsOAuth() {
  const [status, setStatus] = useState<{ authenticated: boolean } | null>(null)
  const [loading, setLoading] = useState(false)
  const [code, setCode] = useState('')
  const [step, setStep] = useState<'check' | 'enter_code'>('check')

  const checkStatus = async () => {
    const res = await fetch(`${API_BASE}/system/google/status`)
    setStatus(await res.json())
  }

  useEffect(() => { checkStatus() }, [])

  const handleGetAuthUrl = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/system/google/auth-url`)
      const data = await res.json() as any
      if (data.error) { useToastStore.getState().add({ type: 'error', message: data.error }); return }
      window.open(data.url, '_blank')
      setStep('enter_code')
    } finally {
      setLoading(false)
    }
  }

  const handleExchangeCode = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/system/google/exchange-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      const data = await res.json() as any
      if (data.success) {
        setStep('check')
        setCode('')
        await checkStatus()
      } else {
        useToastStore.getState().add({ type: 'error', message: data.error || 'Exchange failed' })
      }
    } finally {
      setLoading(false)
    }
  }

  const handleRevoke = async () => {
    await fetch(`${API_BASE}/system/google/revoke`, { method: 'DELETE' })
    await checkStatus()
    setStep('check')
  }

  if (status?.authenticated) {
    return (
      <div className="p-2.5 bg-green-500/10 border border-green-500/20 rounded mb-3 flex items-center justify-between">
        <span className="text-[10px] text-accent-green">✓ Google Sheets authenticated</span>
        <button onClick={handleRevoke} className="text-[10px] text-text-muted hover:text-accent-red transition-colors">
          Revoke
        </button>
      </div>
    )
  }

  if (step === 'enter_code') {
    return (
      <div className="p-2.5 bg-surface-3 border border-border-default rounded mb-3 space-y-2">
        <div className="text-[10px] text-text-muted">
          A browser tab opened. Authorize the app, then paste the code below:
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={code}
            onChange={e => setCode(e.target.value)}
            placeholder="Paste authorization code..."
            className="flex-1 bg-surface-2 border border-border-default rounded px-2 py-1 text-xs text-text-primary font-mono"
          />
          <button
            onClick={handleExchangeCode}
            disabled={!code || loading}
            className="px-2 py-1 text-[10px] bg-accent-blue text-white rounded disabled:opacity-40"
          >
            {loading ? '...' : 'Submit'}
          </button>
        </div>
        <button onClick={() => setStep('check')} className="text-[10px] text-text-muted hover:text-text-secondary">
          ← Back
        </button>
      </div>
    )
  }

  return (
    <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded mb-3">
      <div className="text-[10px] text-accent-amber mb-2">
        Google Sheets requires OAuth authentication. Set your Google Client ID and Secret in Settings → API Keys first.
      </div>
      <button
        onClick={handleGetAuthUrl}
        disabled={loading}
        className="text-[10px] px-2.5 py-1 bg-accent-blue text-white rounded hover:bg-blue-500 disabled:opacity-40 transition-colors"
      >
        {loading ? '...' : 'Authenticate with Google →'}
      </button>
    </div>
  )
}
