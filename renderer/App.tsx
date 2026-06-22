import { useEffect, useState } from 'react'
import { usePipelineStore } from './store/pipeline'
import { useAgentStore } from './store/agents'
import Dashboard from './pages/Dashboard'
import Queue from './pages/Queue'
import Review from './pages/Review'
import Audit from './pages/Audit'
import Settings from './pages/Settings'
import Setup from './pages/Setup'
import Sidebar from './components/shared/Sidebar'
import TitleBar from './components/shared/TitleBar'
import BackendStatus from './components/shared/BackendStatus'
import ToastContainer, { toast } from './components/shared/Toast'
import { wsStore } from './store/ws'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import ShortcutsHelp from './components/shared/ShortcutsHelp'

type Page = 'dashboard' | 'queue' | 'review' | 'audit' | 'settings'

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [showSetup, setShowSetup] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const initWS = usePipelineStore((s) => s.initWS)
  const initAgentWS = useAgentStore((s) => s.initWS)
  const loadModels = useAgentStore((s) => s.loadModels)
  const hitlQueue = usePipelineStore((s) => s.hitlQueue)

  useEffect(() => {
    initWS()
    initAgentWS()

    // Check backend + first launch
    window.datamoa?.system.getPythonStatus().then((status: any) => {
      if (status.running) {
        loadModels()
        useAgentStore.getState().loadStatus()
        window.datamoa?.config.get().then((config: any) => {
          if (config?.first_launch) setShowSetup(true)
        })
      } else {
        toast.error('Backend not running', 'DataMoA Python backend failed to start')
      }
    })

    // Global keyboard shortcuts
  useKeyboardShortcuts({
    'cmd+1': () => setPage('dashboard'),
    'cmd+2': () => setPage('queue'),
    'cmd+3': () => setPage('review'),
    'cmd+4': () => setPage('audit'),
    'cmd+5': () => setPage('settings'),
    'cmd+p': () => {
      const paused = usePipelineStore.getState().paused
      if (paused) {
        window.datamoa?.pipeline.resume()
        usePipelineStore.getState().setPaused(false)
      } else {
        window.datamoa?.pipeline.pause()
        usePipelineStore.getState().setPaused(true)
      }
    },
    'cmd+r': () => useAgentStore.getState().loadModels(),
    '?': () => setShowShortcuts(s => !s),
    'Escape': () => setShowShortcuts(false),
  }, [])

  // Global WS event → toasts
    wsStore.on('pipeline:record:complete', (data: any) => {
      toast.success(`Record ${data.id?.slice(0, 8)} complete`, `Written to destination`)
    })

    wsStore.on('pipeline:record:failed', (data: any) => {
      toast.error(`Record ${data.id?.slice(0, 8)} failed`, data.error?.slice(0, 60))
    })

    wsStore.on('system:error', (data: any) => {
      toast.error('System error', data?.message || 'Unknown error')
    })

    wsStore.on('agent:error', (data: any) => {
      toast.error(`${data.agent} agent error`, data.error?.slice(0, 60))
    })
  }, [])

  // Toast + navigate when HITL arrives
  useEffect(() => {
    if (hitlQueue.length > 0) {
      const item = hitlQueue[hitlQueue.length - 1]
      toast.action(
        `Record ${item.record_id.slice(0, 8)} needs review`,
        'Review Now',
        () => setPage('review'),
        'warning'
      )
    }
  }, [hitlQueue.length])

  if (showSetup) {
    return (
      <>
        <Setup onComplete={() => setShowSetup(false)} />
        <ToastContainer />
      </>
    )
  }

  const pages: Record<Page, JSX.Element> = {
    dashboard: <Dashboard onNavigate={setPage} />,
    queue: <Queue />,
    review: <Review />,
    audit: <Audit />,
    settings: <Settings />,
  }

  return (
    <div className="flex flex-col h-full bg-surface-0">
      <TitleBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          current={page}
          onNavigate={setPage}
          hitlCount={hitlQueue.length}
        />
        <main className="flex-1 overflow-hidden">
          {pages[page]}
        </main>
      </div>
      <BackendStatus />
      {showShortcuts && <ShortcutsHelp onClose={() => setShowShortcuts(false)} />}
      <ToastContainer />
    </div>
  )
}
