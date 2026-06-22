import { usePipelineStore } from '../../store/pipeline'

export default function BackendStatus() {
  const connected = usePipelineStore((s) => s.backendConnected)

  if (connected) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-accent-red/10 border-t border-accent-red/30 px-4 py-2 flex items-center gap-2 text-xs text-accent-red z-50">
      <div className="w-1.5 h-1.5 bg-accent-red rounded-full animate-pulse" />
      Backend disconnected — attempting to reconnect...
    </div>
  )
}
