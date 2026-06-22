import { useState, useEffect } from 'react'
import { API_BASE } from '../../utils/api'
import { toast } from '../shared/Toast'

interface Backup {
  name: string
  path: string
  size_mb: number
  created_at: string
  label: string
  files_count: number
  folder: string
}

interface BackupSchedule {
  interval_hours: number
  enabled: boolean
  backup_on_exit: boolean
}

const INTERVAL_PRESETS = [
  { label: '15 minutes', hours: 0.25 },
  { label: '1 hour', hours: 1 },
  { label: '6 hours', hours: 6 },
  { label: '12 hours', hours: 12 },
  { label: '24 hours (daily)', hours: 24 },
  { label: '72 hours (3 days)', hours: 72 },
  { label: '168 hours (weekly)', hours: 168 },
]

export default function BackupsTab() {
  const [backups, setBackups] = useState<Backup[]>([])
  const [schedule, setSchedule] = useState<BackupSchedule>({
    interval_hours: 24,
    enabled: true,
    backup_on_exit: true,
  })
  const [backupFolder, setBackupFolder] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [restoring, setRestoring] = useState<string | null>(null)
  const [customHours, setCustomHours] = useState('')

  useEffect(() => {
    loadAll()
  }, [])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [backupsRes, folderRes, configRes] = await Promise.all([
        fetch(`${API_BASE}/system/backups`).then(r => r.json()),
        fetch(`${API_BASE}/system/backups/folder`).then(r => r.json()),
        fetch(`${API_BASE}/system/config`).then(r => r.json()),
      ])
      setBackups(backupsRes as Backup[])
      setBackupFolder((folderRes as any).folder || '')
      const config = configRes as any
      setSchedule({
        interval_hours: config.backup_interval_hours ?? 24,
        enabled: config.backup_enabled ?? true,
        backup_on_exit: config.backup_on_exit ?? true,
      })
    } catch (e: any) {
      toast.error('Failed to load backups', e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateNow = async () => {
    setCreating(true)
    try {
      const res = await fetch(`${API_BASE}/system/backups/create?label=manual`, { method: 'POST' })
      const data = await res.json() as any
      toast.success(`Backup created: ${data.name}`, `${data.size_mb}MB — ${data.files_count} files`)
      await loadAll()
    } catch (e: any) {
      toast.error('Backup failed', e.message)
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await fetch(`${API_BASE}/system/backups/${encodeURIComponent(name)}`, { method: 'DELETE' })
      toast.info('Backup deleted')
      setBackups(b => b.filter(x => x.name !== name))
    } catch (e: any) {
      toast.error('Delete failed', e.message)
    }
  }

  const handleRestore = async (name: string) => {
    setRestoring(name)
    try {
      const res = await fetch(`${API_BASE}/system/backups/${encodeURIComponent(name)}/restore`, { method: 'POST' })
      const data = await res.json() as any
      if (data.success) {
        toast.success('Backup restored', `${data.restored_files} files restored. Safety backup: ${data.safety_backup}`)
      } else {
        toast.error('Restore failed', data.error)
      }
    } catch (e: any) {
      toast.error('Restore failed', e.message)
    } finally {
      setRestoring(null)
    }
  }

  const handleScheduleUpdate = async (update: Partial<BackupSchedule>) => {
    const newSchedule = { ...schedule, ...update }
    setSchedule(newSchedule)
    try {
      await fetch(`${API_BASE}/system/backups/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interval_hours: newSchedule.interval_hours,
          enabled: newSchedule.enabled,
        }),
      })
      // Also save backup_on_exit
      const configRes = await fetch(`${API_BASE}/system/config`).then(r => r.json()) as any
      await fetch(`${API_BASE}/system/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...configRes, backup_on_exit: newSchedule.backup_on_exit }),
      })
      toast.success('Schedule updated')
    } catch (e: any) {
      toast.error('Failed to update schedule', e.message)
    }
  }

  const handleOpenFolder = () => {
    // Use Electron shell.openPath via preload (if exposed), else show the path
    if ((window as any).electronAPI?.openPath) {
      (window as any).electronAPI.openPath(backupFolder)
    } else {
      // Fallback: copy path
      navigator.clipboard.writeText(backupFolder).then(() =>
        toast.info('Folder path copied', backupFolder)
      )
    }
  }

  const formatDate = (iso: string) => {
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  const selectedPreset = INTERVAL_PRESETS.find(p => p.hours === schedule.interval_hours)

  return (
    <div className="max-w-2xl space-y-6">
      {/* Backup folder */}
      <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs font-medium text-text-primary mb-1">Backup Location</div>
            <div className="text-[10px] font-mono text-text-muted break-all">{backupFolder || '—'}</div>
            <div className="text-[10px] text-text-muted mt-1">
              Backups are stored in a folder visible in your file manager
            </div>
          </div>
          <button
            onClick={handleOpenFolder}
            className="text-xs px-3 py-1.5 border border-border-default text-text-secondary rounded hover:border-border-strong hover:text-text-primary transition-colors shrink-0 ml-4"
          >
            📂 Open Folder
          </button>
        </div>
      </div>

      {/* Schedule */}
      <div className="p-4 bg-surface-2 rounded-lg border border-border-subtle space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-xs font-medium text-text-primary">Automatic Backup Schedule</div>
          <button
            onClick={() => handleScheduleUpdate({ enabled: !schedule.enabled })}
            className={`w-10 h-5 rounded-full transition-colors relative ${schedule.enabled ? 'bg-accent-blue' : 'bg-surface-4'}`}
          >
            <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${schedule.enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </button>
        </div>

        {schedule.enabled && (
          <>
            <div>
              <div className="text-[10px] text-text-muted mb-2">Backup Frequency</div>
              <div className="grid grid-cols-3 gap-1.5 mb-2">
                {INTERVAL_PRESETS.map(p => (
                  <button
                    key={p.hours}
                    onClick={() => handleScheduleUpdate({ interval_hours: p.hours })}
                    className={`py-1.5 text-[10px] rounded border transition-colors ${
                      schedule.interval_hours === p.hours
                        ? 'border-accent-blue/50 bg-accent-blue/10 text-accent-blue'
                        : 'border-border-subtle text-text-muted hover:border-border-default'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              {/* Custom interval */}
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="0.25"
                  step="0.25"
                  value={customHours}
                  onChange={e => setCustomHours(e.target.value)}
                  placeholder="Custom hours..."
                  className="w-32 bg-surface-3 border border-border-default rounded px-2.5 py-1.5 text-xs text-text-primary placeholder-text-muted focus:border-accent-blue/40 transition-colors"
                />
                <button
                  onClick={() => {
                    const h = parseFloat(customHours)
                    if (h > 0) { handleScheduleUpdate({ interval_hours: h }); setCustomHours('') }
                  }}
                  disabled={!customHours || parseFloat(customHours) <= 0}
                  className="px-3 py-1.5 text-xs bg-surface-3 border border-border-default text-text-secondary rounded hover:border-border-strong disabled:opacity-40 transition-colors"
                >
                  Set Custom
                </button>
                {!selectedPreset && (
                  <span className="text-[10px] text-accent-blue">
                    Every {schedule.interval_hours}h
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-text-secondary">Backup on exit</div>
                <div className="text-[10px] text-text-muted mt-0.5">Create a backup whenever the app closes</div>
              </div>
              <button
                onClick={() => handleScheduleUpdate({ backup_on_exit: !schedule.backup_on_exit })}
                className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ${schedule.backup_on_exit ? 'bg-accent-blue' : 'bg-surface-4'}`}
              >
                <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform ${schedule.backup_on_exit ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Manual backup */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleCreateNow}
          disabled={creating}
          className="px-4 py-2 bg-accent-blue text-white text-xs font-medium rounded hover:bg-blue-500 disabled:opacity-40 transition-colors flex items-center gap-2"
        >
          {creating ? (
            <><span className="animate-spin">↺</span> Creating...</>
          ) : (
            <><span>💾</span> Backup Now</>
          )}
        </button>
        <span className="text-[10px] text-text-muted">
          {backups.length} backup{backups.length !== 1 ? 's' : ''} stored
        </span>
      </div>

      {/* Backup list */}
      {loading ? (
        <div className="text-xs text-text-muted">Loading backups...</div>
      ) : backups.length === 0 ? (
        <div className="p-6 border-2 border-dashed border-border-default rounded-lg text-center">
          <div className="text-text-muted text-sm mb-1">No backups yet</div>
          <div className="text-text-muted text-xs">Your first backup will appear here</div>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Available Backups</div>
          {backups.map(backup => (
            <div key={backup.name} className="flex items-center gap-3 p-3 bg-surface-2 rounded border border-border-subtle">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-text-secondary truncate">{backup.name}</span>
                  {backup.label && backup.label !== 'manual' && backup.label !== 'scheduled' && (
                    <span className="text-[9px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded shrink-0">
                      {backup.label}
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5">
                  {formatDate(backup.created_at)} · {backup.size_mb}MB · {backup.files_count} files
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => handleRestore(backup.name)}
                  disabled={restoring === backup.name}
                  className="text-[10px] px-2 py-1 border border-border-subtle text-text-muted rounded hover:border-accent-blue/40 hover:text-accent-blue transition-colors disabled:opacity-40"
                >
                  {restoring === backup.name ? '...' : 'Restore'}
                </button>
                <button
                  onClick={() => handleDelete(backup.name)}
                  className="text-[10px] px-2 py-1 border border-border-subtle text-text-muted rounded hover:border-red-500/40 hover:text-accent-red transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
