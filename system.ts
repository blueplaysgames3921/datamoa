import { IpcMain, app } from 'electron'
import { PYTHON_PORT } from '../main'
import fetch from 'node-fetch'

export function registerSystemHandlers(ipcMain: IpcMain) {
  ipcMain.handle('system:getHardware', async () => {
    try {
      const res = await fetch(`http://localhost:${PYTHON_PORT}/system/hardware`)
      return await res.json()
    } catch {
      return { error: 'Python backend not reachable' }
    }
  })

  ipcMain.handle('system:getPythonStatus', async () => {
    try {
      const res = await fetch(`http://localhost:${PYTHON_PORT}/health`)
      const data = await res.json() as { status: string }
      return { running: true, ...data }
    } catch {
      return { running: false }
    }
  })

  ipcMain.handle('system:getVersion', () => {
    return { version: app.getVersion() }
  })
}
