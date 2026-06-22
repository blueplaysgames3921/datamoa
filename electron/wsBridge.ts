/**
 * WebSocket Bridge — Electron main process
 *
 * The Python backend emits events via WebSocket.
 * This bridge subscribes to those events and forwards them to the renderer
 * via ipcMain.emit, which the preload layer receives as ipcRenderer.on events.
 *
 * This allows the renderer to receive real-time events without any direct
 * Node.js or WebSocket access — all goes through the secure context bridge.
 */

import { BrowserWindow } from 'electron'

const WS_RECONNECT_DELAY_MS = 2000
const WS_MAX_RECONNECT_DELAY_MS = 15000

let ws: any = null
let mainWindow: BrowserWindow | null = null
let reconnectDelay = WS_RECONNECT_DELAY_MS
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let shouldReconnect = true

// Map WS event names → IPC channel names
const EVENT_CHANNEL_MAP: Record<string, string> = {
  'pipeline:update': 'pipeline:update',
  'pipeline:record:update': 'pipeline:record:update',
  'pipeline:record:complete': 'pipeline:record:update',
  'pipeline:record:failed': 'pipeline:record:update',
  'pipeline:hitl:request': 'pipeline:hitl:request',
  'pipeline:paused': 'pipeline:update',
  'pipeline:resumed': 'pipeline:update',
  'agent:status:update': 'agent:status:update',
  'agent:error': 'agent:status:update',
  'config:agent:progress': 'config:agent:progress',
  'config:agent:complete': 'config:agent:progress',
  'audit:new:entry': 'audit:new:entry',
  'audit:batch:complete': 'audit:batch:complete',
  'system:health': 'system:health',
  'ollama:pull:progress': 'ollama:pull:progress',
  'system:error': 'system:error',
}

export function initWebSocketBridge(window: BrowserWindow, port: number) {
  mainWindow = window
  shouldReconnect = true
  connect(port)
}

export function destroyWebSocketBridge() {
  shouldReconnect = false
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (ws) {
    ws.close()
    ws = null
  }
}

function connect(port: number) {
  if (!shouldReconnect) return

  try {
    // Use ws package (Node.js WebSocket client)
    const WebSocket = require('ws')
    ws = new WebSocket(`ws://localhost:${port}/ws`)

    ws.on('open', () => {
      reconnectDelay = WS_RECONNECT_DELAY_MS
      console.log('[WSBridge] Connected to Python backend')
      // Notify renderer
      forwardToRenderer('connection:status', { connected: true })

      // Keepalive ping
      const pingInterval = setInterval(() => {
        if (ws?.readyState === 1) {
          ws.send('ping')
        } else {
          clearInterval(pingInterval)
        }
      }, 25000)
    })

    ws.on('message', (data: Buffer | string) => {
      try {
        const { event, data: payload } = JSON.parse(data.toString())
        const channel = EVENT_CHANNEL_MAP[event] || event
        forwardToRenderer(channel, payload)
      } catch (e) {
        // Non-JSON message (e.g. pong) — ignore
      }
    })

    ws.on('close', () => {
      console.log('[WSBridge] Disconnected from Python backend')
      forwardToRenderer('connection:status', { connected: false })
      scheduleReconnect(port)
    })

    ws.on('error', (err: Error) => {
      // Connection refused — backend not ready yet, will reconnect
      if ((err as any).code !== 'ECONNREFUSED') {
        console.error('[WSBridge] Error:', err.message)
      }
    })

  } catch (e) {
    console.error('[WSBridge] Failed to create WebSocket:', e)
    scheduleReconnect(port)
  }
}

function scheduleReconnect(port: number) {
  if (!shouldReconnect) return
  if (reconnectTimer) clearTimeout(reconnectTimer)

  reconnectTimer = setTimeout(() => {
    reconnectDelay = Math.min(reconnectDelay * 1.5, WS_MAX_RECONNECT_DELAY_MS)
    connect(port)
  }, reconnectDelay)
}

function forwardToRenderer(channel: string, data: unknown) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}
