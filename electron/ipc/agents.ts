import { IpcMain } from 'electron'
import { PYTHON_PORT } from '../main'
import fetch from 'node-fetch'

const API = () => `http://localhost:${PYTHON_PORT}`

export function registerAgentHandlers(ipcMain: IpcMain) {
  ipcMain.handle('agents:getStatus', async () => {
    const res = await fetch(`${API()}/agents/status`)
    return await res.json()
  })

  ipcMain.handle('agents:getModels', async () => {
    const res = await fetch(`${API()}/agents/models`)
    return await res.json()
  })

  ipcMain.handle('agents:assignModel', async (_event, agent: string, model: string) => {
    const res = await fetch(`${API()}/agents/models/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent, model }),
    })
    return await res.json()
  })

  ipcMain.handle('agents:runConfigAgent', async () => {
    const res = await fetch(`${API()}/agents/config/run`, { method: 'POST' })
    return await res.json()
  })

  ipcMain.handle('audit:getLogs', async (_event, filters: unknown) => {
    const params = filters ? `?${new URLSearchParams(filters as Record<string, string>)}` : ''
    const res = await fetch(`${API()}/audit/logs${params}`)
    return await res.json()
  })

  ipcMain.handle('audit:exportLogs', async (_event, format: string) => {
    const res = await fetch(`${API()}/audit/export?format=${format}`)
    return await res.json()
  })

}
