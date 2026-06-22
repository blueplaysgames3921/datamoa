/**
 * Type declarations for the Electron context bridge API
 * window.datamoa is injected by preload.ts
 */

interface DataMoaAPI {
  config: {
    get: () => Promise<Record<string, unknown>>
    save: (config: unknown) => Promise<{ success: boolean }>
    getKeys: () => Promise<Record<string, string | null>>
    saveKey: (provider: string, key: string) => Promise<{ success: boolean }>
    deleteKey: (provider: string) => Promise<{ success: boolean }>
  }
  system: {
    getHardware: () => Promise<Record<string, unknown>>
    getPythonStatus: () => Promise<{ running: boolean; status?: string }>
    getVersion: () => Promise<{ version: string }>
  }
  pipeline: {
    submit: (input: unknown) => Promise<{ record_id: string; status: string }>
    submitFile: (payload: { filename: string; mime_type: string; size: number; data_b64: string }) => Promise<{ record_id: string; status: string }>
    submitUrl: (url: string) => Promise<{ record_id: string; status: string }>
    getQueue: () => Promise<unknown[]>
    getRecord: (id: string) => Promise<unknown>
    resolveHITL: (id: string, resolution: unknown) => Promise<{ status: string }>
    pause: () => Promise<{ status: string }>
    resume: () => Promise<{ status: string }>
    cancel: (id: string) => Promise<{ status: string }>
    retry: (id: string) => Promise<{ status: string }>
  }
  agents: {
    getStatus: () => Promise<Record<string, string>>
    getModels: () => Promise<Record<string, string>>
    assignModel: (agent: string, model: string) => Promise<{ status: string }>
    runConfigAgent: () => Promise<{ status: string }>
  }
  audit: {
    getLogs: (filters?: unknown) => Promise<unknown[]>
    exportLogs: (format: string) => Promise<unknown>
  }
  on: (channel: string, callback: (...args: unknown[]) => void) => void
  off: (channel: string, callback: (...args: unknown[]) => void) => void
}

declare global {
  interface Window {
    datamoa: DataMoaAPI
  }
}

export {}
