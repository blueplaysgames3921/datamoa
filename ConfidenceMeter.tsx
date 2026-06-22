interface ConfidenceMeterProps {
  score: number
  tier: 'green' | 'amber' | 'red'
  greenThreshold?: number
  amberThreshold?: number
  showLabel?: boolean
  size?: 'sm' | 'md' | 'lg'
}

const SIZE = {
  sm: { height: 'h-1', text: 'text-[9px]' },
  md: { height: 'h-1.5', text: 'text-xs' },
  lg: { height: 'h-2', text: 'text-sm' },
}

export default function ConfidenceMeter({
  score,
  tier,
  greenThreshold = 0.85,
  amberThreshold = 0.60,
  showLabel = true,
  size = 'md',
}: ConfidenceMeterProps) {
  const pct = Math.round(score * 100)
  const { height, text } = SIZE[size]

  const barColor =
    tier === 'green' ? 'bg-accent-green' :
    tier === 'amber' ? 'bg-accent-amber' : 'bg-accent-red'

  const labelColor =
    tier === 'green' ? 'text-accent-green' :
    tier === 'amber' ? 'text-accent-amber' : 'text-accent-red'

  const tierLabel =
    tier === 'green' ? 'Auto' :
    tier === 'amber' ? 'Reason' : 'Review'

  return (
    <div className="w-full">
      {showLabel && (
        <div className="flex items-center justify-between mb-1">
          <span className={`${text} font-mono font-semibold ${labelColor}`}>{pct}%</span>
          <span className={`text-[9px] px-1.5 py-0.5 rounded border font-medium uppercase ${
            tier === 'green' ? 'border-accent-green/30 bg-green-500/10 text-accent-green' :
            tier === 'amber' ? 'border-accent-amber/30 bg-amber-500/10 text-accent-amber' :
            'border-accent-red/30 bg-red-500/10 text-accent-red'
          }`}>
            {tierLabel}
          </span>
        </div>
      )}

      {/* Track */}
      <div className={`w-full ${height} bg-surface-4 rounded-full overflow-hidden relative`}>
        {/* Threshold markers */}
        <div
          className="absolute top-0 bottom-0 w-px bg-accent-amber/30 z-10"
          style={{ left: `${Math.round(amberThreshold * 100)}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-px bg-accent-green/30 z-10"
          style={{ left: `${Math.round(greenThreshold * 100)}%` }}
        />
        {/* Fill */}
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
