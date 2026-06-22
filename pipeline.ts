import { IpcMain } from 'electron'
import { PYTHON_PORT } from '../main'
import fetch from 'node-fetch'
import * as os from 'os'
import * as path from 'path'
import * as fs from 'fs'

const API = () => `http://localhost:${PYTHON_PORT}`

export function registerPipelineHandlers(ipcMain: IpcMain) {
  ipcMain.handle('pipeline:submit', async (_event, input: unknown) => {
    const res = await fetch(`${API()}/pipeline/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    return await res.json()
  })

  ipcMain.handle('pipeline:submitFile', async (_event, payload: {
    filename: string
    mime_type: string
    size: number
    data_b64: string
  }) => {
    const ext = payload.filename.split('.').pop() || 'bin'
    const tmpPath = path.join(os.tmpdir(), `datamoa_${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`)
    const buf = Buffer.from(payload.data_b64, 'base64')
    fs.writeFileSync(tmpPath, buf)
    try {
      const FormData = require('form-data')
      const form = new FormData()
      form.append('file', fs.createReadStream(tmpPath), {
        filename: payload.filename,
        contentType: payload.mime_type || 'application/octet-stream',
      })
      const res = await fetch(`${API()}/pipeline/submit/file`, {
        method: 'POST',
        body: form,
        headers: form.getHeaders(),
      })
      return await res.json()
    } finally {
      try { fs.unlinkSync(tmpPath) } catch {}
    }
  })

  ipcMain.handle('pipeline:getQueue', async () => {
    const res = await fetch(`${API()}/pipeline/queue`)
    return await res.json()
  })

  ipcMain.handle('pipeline:getRecord', async (_event, id: string) => {
    const res = await fetch(`${API()}/pipeline/record/${id}`)
    return await res.json()
  })

  ipcMain.handle('pipeline:resolveHITL', async (_event, id: string, resolution: unknown) => {
    const res = await fetch(`${API()}/pipeline/hitl/${id}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(resolution),
    })
    return await res.json()
  })

  ipcMain.handle('pipeline:pause', async () => {
    const res = await fetch(`${API()}/pipeline/pause`, { method: 'POST' })
    return await res.json()
  })

  ipcMain.handle('pipeline:resume', async () => {
    const res = await fetch(`${API()}/pipeline/resume`, { method: 'POST' })
    return await res.json()
  })

  ipcMain.handle('pipeline:cancel', async (_event, id: string) => {
    const res = await fetch(`${API()}/pipeline/cancel/${id}`, { method: 'POST' })
    return await res.json()
  })
}

  ipcMain.handle('pipeline:submitUrl', async (_event, url: string) => {
    const res = await fetch(`${API()}/pipeline/submit/url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    return await res.json()
  })

  ipcMain.handle('pipeline:retry', async (_event, id: string) => {
    const res = await fetch(`${API()}/pipeline/retry/${id}`, { method: 'POST' })
    return await res.json()
  })
