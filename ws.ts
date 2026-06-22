import { API_BASE } from '../utils/api'
/**
 * WebSocket store — manages real-time connection to Python backend
 * All pipeline events flow through here to the UI
 */

type EventCallback = (data: unknown) => void

class WSStore {
  private ws: WebSocket | null = null
  private listeners: Map<string, Set<EventCallback>> = new Map()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectDelay = 1000
  private connected = false

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return

    try {
      this.ws = new WebSocket(API_BASE.replace('http', 'ws') + '/ws')

      this.ws.onopen = () => {
        this.connected = true
        this.reconnectDelay = 1000
        this.emit('connection:status', { connected: true })
        // Start keepalive ping
        this._startPing()
      }

      this.ws.onmessage = (event) => {
        try {
          const { event: name, data } = JSON.parse(event.data)
          this.emit(name, data)
        } catch (e) {
          console.error('WS parse error:', e)
        }
      }

      this.ws.onclose = () => {
        this.connected = false
        this.emit('connection:status', { connected: false })
        this._scheduleReconnect()
      }

      this.ws.onerror = () => {
        this.ws?.close()
      }
    } catch (e) {
      this._scheduleReconnect()
    }
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
  }

  on(event: string, callback: EventCallback): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback)
    // Return unsubscribe function
    return () => this.listeners.get(event)?.delete(callback)
  }

  private emit(event: string, data: unknown) {
    this.listeners.get(event)?.forEach(cb => {
      try { cb(data) } catch (e) { console.error(`WS handler error [${event}]:`, e) }
    })
    // Also emit to wildcard listeners
    this.listeners.get('*')?.forEach(cb => {
      try { cb({ event, data }) } catch (e) { console.error('WS wildcard error:', e) }
    })
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 10000)
      this.connect()
    }, this.reconnectDelay)
  }

  private _pingInterval: ReturnType<typeof setInterval> | null = null
  private _startPing() {
    if (this._pingInterval) clearInterval(this._pingInterval)
    this._pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping')
      }
    }, 25000)
  }

  get isConnected() {
    return this.connected
  }
}

export const wsStore = new WSStore()
