/**
 * Config IPC — proxies all config operations to the Python backend
 * Python is the single source of truth for config (stored in ~/.datamoa/config.json)
 * Keys are also stored by Python (encrypted in ~/.datamoa/keys.json)
 * Electron just ferries requests — no local electron-store for config
 */

import { IpcMain } from 'electron'
import { PYTHON_PORT } from '../main'
import fetch from 'node-fetch'

const API = () => `http://localhost:${PYTHON_PORT}`

export function registerConfigHandlers(ipcMain: IpcMain) {
  // ── Config ─────────────────────────────────────────────────────────────────

  ipcMain.handle('config:get', async () => {
    try {
      const res = await fetch(`${API()}/system/config`)
      return await res.json()
    } catch {
      return {}
    }
  })

  ipcMain.handle('config:save', async (_event, config: unknown) => {
    try {
      const res = await fetch(`${API()}/system/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      return await res.json()
    } catch (e: any) {
      return { success: false, error: e.message }
    }
  })

  // ── API Keys ────────────────────────────────────────────────────────────────
  // Keys are stored in ~/.datamoa/keys.json by the Python backend (never logged)

  ipcMain.handle('config:getKeys', async () => {
    try {
      const res = await fetch(`${API()}/system/keys`)
      return await res.json()
    } catch {
      return {}
    }
  })

  ipcMain.handle('config:saveKey', async (_event, provider: string, key: string) => {
    try {
      const res = await fetch(`${API()}/system/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, key }),
      })
      return await res.json()
    } catch (e: any) {
      return { success: false, error: e.message }
    }
  })

  ipcMain.handle('config:deleteKey', async (_event, provider: string) => {
    try {
      const res = await fetch(`${API()}/system/keys/${provider}`, {
        method: 'DELETE',
      })
      return await res.json()
    } catch (e: any) {
      return { success: false, error: e.message }
    }
  })
}
