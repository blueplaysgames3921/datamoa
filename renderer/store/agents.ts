import { API_BASE } from '../utils/api'
/**
 * Agent store — tracks live agent activity and model assignments
 */

import { create } from 'zustand'
import { wsStore } from './ws'

export type AgentStatus = 'idle' | 'running' | 'error'

export interface AgentInfo {
  name: string
  status: AgentStatus
  model: string
  lastRecordId?: string
  lastDurationMs?: number
  error?: string
}

export const AGENT_NAMES = [
  'intake', 'parsing', 'context', 'confidence',
  'reasoning', 'validation', 'enrichment', 'hitl',
  'write', 'audit', 'learning', 'orchestrator',
] as const

export type AgentName = typeof AGENT_NAMES[number]

interface AgentState {
  agents: Record<string, AgentInfo>
  models: Record<string, string>
  setAgentStatus: (name: string, info: Partial<AgentInfo>) => void
  setModels: (models: Record<string, string>) => void
  initWS: () => void
  loadModels: () => Promise<void>
  loadStatus: () => Promise<void>
}

const defaultAgents: Record<string, AgentInfo> = Object.fromEntries(
  AGENT_NAMES.map((name) => [name, { name, status: 'idle', model: '—' }])
)

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: defaultAgents,
  models: {},

  setAgentStatus: (name, info) =>
    set((s) => ({
      agents: {
        ...s.agents,
        [name]: { ...s.agents[name], ...info },
      },
    })),

  setModels: (models) => {
    set({ models })
    set((s) => ({
      agents: Object.fromEntries(
        Object.entries(s.agents).map(([name, agent]) => [
          name,
          { ...agent, model: models[name] || agent.model },
        ])
      ),
    }))
  },

  loadModels: async () => {
    try {
      const models = await window.datamoa?.agents.getModels()
      if (models) get().setModels(models)
    } catch {}
  },

  loadStatus: async () => {
    try {
      // GET /agents/status returns {agentName: {status, model}}
      const res = await fetch(`${API_BASE}/agents/status`)
      const data: Record<string, { status: AgentStatus; model: string }> = await res.json()
      set((s) => {
        const updated = { ...s.agents }
        for (const [name, info] of Object.entries(data)) {
          updated[name] = {
            name,
            status: info.status || 'idle',
            model: info.model || '—',
            lastRecordId: s.agents[name]?.lastRecordId,
            lastDurationMs: s.agents[name]?.lastDurationMs,
          }
        }
        return { agents: updated, models: Object.fromEntries(Object.entries(data).map(([k,v]) => [k, v.model])) }
      })
    } catch {}
  },

  initWS: () => {
    wsStore.on('agent:status:update', (data: any) => {
      get().setAgentStatus(data.agent, {
        status: data.status,
        lastRecordId: data.record_id,
        lastDurationMs: data.duration_ms,
        error: data.error,
        model: data.model || get().agents[data.agent]?.model,
      })
    })
  },
}))
