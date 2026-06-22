import { useState, useEffect } from 'react'
import { API_BASE } from '../../utils/api'
import { wsStore } from '../../store/ws'

export default function ThresholdBadge() {
  const [thresholds, setThresholds] = useState<{ green: number; amber: number } | null>(null)

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/system/config`)
      const config = await res.json() as any
      if (config?.pipeline) {
        setThresholds({
          green: config.pipeline.confidence_green_threshold ?? 0.85,
          amber: config.pipeline.confidence_amber_threshold ?? 0.60,
        })
      }
    } catch {}
  }

  useEffect(() => {
    load()
    // Refresh when config is saved
    const unsub = wsStore.on('system:health', () => {})
    return () => unsub()
  }, [])

  if (!thresholds) return null

  return (
    <div className="flex items-center gap-1.5 text-[9px] font-mono border border-border-subtle rounded px-2 py-1 bg-surface-2">
      <div className="flex items-center gap-1">
        <div className="w-1.5 h-1.5 rounded-full bg-accent-green" />
        <span className="text-text-muted">{Math.round(thresholds.green * 100)}%</span>
      </div>
      <span className="text-text-muted opacity-40">|</span>
      <div className="flex items-center gap-1">
        <div className="w-1.5 h-1.5 rounded-full bg-accent-amber" />
        <span className="text-text-muted">{Math.round(thresholds.amber * 100)}%</span>
      </div>
      <span className="text-text-muted opacity-40">|</span>
      <div className="flex items-center gap-1">
        <div className="w-1.5 h-1.5 rounded-full bg-accent-red" />
        <span className="text-text-muted">&lt;{Math.round(thresholds.amber * 100)}%</span>
      </div>
    </div>
  )
}
