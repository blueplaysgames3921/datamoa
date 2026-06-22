interface AgentModelBadgeProps {
  model: string
  size?: 'xs' | 'sm'
}

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  google:    'bg-blue-500/20 text-blue-300 border-blue-500/30',
  groq:      'bg-green-500/20 text-green-300 border-green-500/30',
  deepseek:  'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  perplexity:'bg-purple-500/20 text-purple-300 border-purple-500/30',
  moonshot:  'bg-pink-500/20 text-pink-300 border-pink-500/30',
  openai:    'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  ollama:    'bg-surface-4 text-text-secondary border-border-default',
}

export default function AgentModelBadge({ model, size = 'xs' }: AgentModelBadgeProps) {
  if (!model || model === '—') {
    return <span className="text-[9px] text-text-muted">—</span>
  }

  const [provider, ...rest] = model.split('/')
  const modelName = rest.join('/').split(':')[0] // strip quantization tag

  const colorClass = PROVIDER_COLORS[provider] || 'bg-surface-3 text-text-muted border-border-subtle'
  const textSize = size === 'xs' ? 'text-[8px]' : 'text-[10px]'

  return (
    <div className="flex items-center gap-1 min-w-0">
      <span className={`${textSize} px-1 py-0.5 rounded border font-medium shrink-0 ${colorClass}`}>
        {provider}
      </span>
      <span className={`${textSize} text-text-muted truncate`}>
        {modelName || model}
      </span>
    </div>
  )
}
