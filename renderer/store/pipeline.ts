import { API_BASE } from '../utils/api'
/**
 * Pipeline store — manages record state across the UI
 */

import { create } from 'zustand'
import { wsStore } from './ws'

export type ConfidenceTier = 'green' | 'amber' | 'red'
export type RecordStage =
  | 'queued' | 'intake' | 'parsing' | 'context'
  | 'confidence' | 'reasoning' | 'validation' | 'enrichment'
  | 'hitl' | 'writing' | 'audit' | 'complete' | 'failed' | 'cancelled'

export interface RecordSummary {
  id: string
  stage: RecordStage
  source_type: string
  created_at: string
  updated_at: string
  confidence_tier: ConfidenceTier | null
  confidence_score: number | null
  has_errors: boolean
  retry_count: number
}

export interface HITLRequest {
  record_id: string
  questions: string[]
  flagged_fields: string[]
  parsed_fields: Record<string, unknown>
  reasoning_notes: string
  raw_text_excerpt: string
}

interface PipelineState {
  records: Record<string, RecordSummary>
  hitlQueue: HITLRequest[]
  paused: boolean
  backendConnected: boolean

  // Actions
  setRecord: (record: RecordSummary) => void
  removeRecord: (id: string) => void
  addHITL: (request: HITLRequest) => void
  resolveHITL: (record_id: string) => void
  setPaused: (paused: boolean) => void
  setBackendConnected: (connected: boolean) => void
  initWS: () => void
}

export const usePipelineStore = create<PipelineState>((set, get) => ({
  records: {},
  hitlQueue: [],
  paused: false,
  backendConnected: false,

  setRecord: (record) =>
    set((s) => ({ records: { ...s.records, [record.id]: record } })),

  removeRecord: (id) =>
    set((s) => {
      const { [id]: _, ...rest } = s.records
      return { records: rest }
    }),

  addHITL: (request) =>
    set((s) => ({ hitlQueue: [...s.hitlQueue, request] })),

  resolveHITL: (record_id) =>
    set((s) => ({ hitlQueue: s.hitlQueue.filter((r) => r.record_id !== record_id) })),

  setPaused: (paused) => set({ paused }),
  setBackendConnected: (connected) => set({ backendConnected: connected }),

  initWS: () => {
    wsStore.connect()

    wsStore.on('connection:status', (data: any) => {
      set({ backendConnected: data.connected })
      if (data.connected) {
        // Load initial queue state
        window.datamoa?.pipeline.getQueue().then((queue: RecordSummary[]) => {
          const records: Record<string, RecordSummary> = {}
          queue.forEach((r) => (records[r.id] = r))
          set({ records })
        })
        // Sync HITL queue from backend (handles restarts)
        fetch(`${API_BASE}/pipeline/queue/hitl`)
          .then(r => r.json())
          .then((items: HITLRequest[]) => {
            if (Array.isArray(items) && items.length) {
              set({ hitlQueue: items })
            }
          })
          .catch(() => {})
      }
    })

    wsStore.on('pipeline:record:update', (data: any) => {
      get().setRecord(data)
    })

    wsStore.on('pipeline:record:complete', (data: any) => {
      get().setRecord(data)
    })

    wsStore.on('pipeline:record:failed', (data: any) => {
      get().setRecord(data)
    })

    wsStore.on('pipeline:hitl:request', (data: any) => {
      get().addHITL(data)
    })

    wsStore.on('pipeline:paused', () => set({ paused: true }))
    wsStore.on('pipeline:resumed', () => set({ paused: false }))
  },
}))
