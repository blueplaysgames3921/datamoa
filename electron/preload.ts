import { contextBridge, ipcRenderer } from 'electron'

// Expose a clean, typed API to the renderer
// Window controls and system actions
contextBridge.exposeInMainWorld('electronAPI', {
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  openPath: (path: string) => ipcRenderer.send('shell:openPath', path),
})


// No direct Node/Electron access from renderer — everything goes through this bridge

contextBridge.exposeInMainWorld('datamoa', {
  // --- Config ---
  config: {
    get: () => ipcRenderer.invoke('config:get'),
    save: (config: unknown) => ipcRenderer.invoke('config:save', config),
    getKeys: () => ipcRenderer.invoke('config:getKeys'),
    saveKey: (provider: string, key: string) => ipcRenderer.invoke('config:saveKey', provider, key),
    deleteKey: (provider: string) => ipcRenderer.invoke('config:deleteKey', provider),
  },

  // --- System / Hardware ---
  system: {
    getHardware: () => ipcRenderer.invoke('system:getHardware'),
    getPythonStatus: () => ipcRenderer.invoke('system:getPythonStatus'),
    getVersion: () => ipcRenderer.invoke('system:getVersion'),
  },

  // --- Pipeline ---
  pipeline: {
    submit: (input: unknown) => ipcRenderer.invoke('pipeline:submit', input),
    getQueue: () => ipcRenderer.invoke('pipeline:getQueue'),
    getRecord: (id: string) => ipcRenderer.invoke('pipeline:getRecord', id),
    resolveHITL: (id: string, resolution: unknown) => ipcRenderer.invoke('pipeline:resolveHITL', id, resolution),
    pause: () => ipcRenderer.invoke('pipeline:pause'),
    resume: () => ipcRenderer.invoke('pipeline:resume'),
    cancel: (id: string) => ipcRenderer.invoke('pipeline:cancel', id),
    retry: (id: string) => ipcRenderer.invoke('pipeline:retry', id),
    submitFile: (payload: unknown) => ipcRenderer.invoke('pipeline:submitFile', payload),
    submitUrl: (url: string) => ipcRenderer.invoke('pipeline:submitUrl', url),
  },

  // --- Agents ---
  agents: {
    getStatus: () => ipcRenderer.invoke('agents:getStatus'),
    getModels: () => ipcRenderer.invoke('agents:getModels'),
    assignModel: (agent: string, model: string) => ipcRenderer.invoke('agents:assignModel', agent, model),
    runConfigAgent: () => ipcRenderer.invoke('agents:runConfigAgent'),
  },

  // --- Audit ---
  audit: {
    getLogs: (filters?: unknown) => ipcRenderer.invoke('audit:getLogs', filters),
    exportLogs: (format: string) => ipcRenderer.invoke('audit:exportLogs', format),
  },

  // --- WebSocket events from Python backend ---
  on: (channel: string, callback: (...args: unknown[]) => void) => {
    const validChannels = [
      'pipeline:update',
      'pipeline:record:update',
      'pipeline:hitl:request',
      'agent:status:update',
      'audit:new:entry',
      'system:error',
      'config:agent:progress',
      'audit:batch:complete',
    ]
    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, (_event, ...args) => callback(...args))
    }
  },

  off: (channel: string, callback: (...args: unknown[]) => void) => {
    ipcRenderer.removeListener(channel, callback)
  },
})
