/**
 * Resilient WebSocket client.
 * - authenticates with a first message (no token in the URL)
 * - exponential backoff with jitter, capped at 30s
 * - heartbeat ping every 25s, re-auth when the access token refreshes
 */
export function backoffDelay(attempt, { base = 1000, max = 30000, random = Math.random } = {}) {
  const exp = Math.min(max, base * 2 ** attempt)
  return Math.round(exp / 2 + random() * (exp / 2))
}

export class RealtimeClient {
  constructor({ url, getToken, onMessage, onStatus, WebSocketImpl } = {}) {
    this.url = url
    this.getToken = getToken
    this.onMessage = onMessage || (() => {})
    this.onStatus = onStatus || (() => {})
    this.WS = WebSocketImpl || globalThis.WebSocket
    this.ws = null
    this.attempt = 0
    this.stopped = true
    this.timers = { reconnect: null, heartbeat: null }
    this._onVisible = () => {
      if (document.visibilityState === 'visible' && !this.stopped && (!this.ws || this.ws.readyState > 1)) this._connect()
    }
    this._onOnline = () => !this.stopped && this._connect()
  }

  start() {
    if (!this.stopped) return
    this.stopped = false
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', this._onVisible)
    if (typeof window !== 'undefined') window.addEventListener('online', this._onOnline)
    this._connect()
  }

  stop() {
    this.stopped = true
    clearTimeout(this.timers.reconnect)
    clearInterval(this.timers.heartbeat)
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this._onVisible)
    if (typeof window !== 'undefined') window.removeEventListener('online', this._onOnline)
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close(1000)
      this.ws = null
    }
    this.onStatus('offline')
  }

  reauth() {
    const token = this.getToken()
    if (token && this.ws?.readyState === 1) this._send({ type: 'auth', token })
  }

  _send(obj) {
    try {
      this.ws?.send(JSON.stringify(obj))
    } catch {
      /* socket closing */
    }
  }

  _connect() {
    clearTimeout(this.timers.reconnect)
    if (this.ws && this.ws.readyState <= 1) return
    const token = this.getToken()
    if (!token) return this._scheduleReconnect()
    this.onStatus('connecting')
    const ws = new this.WS(this.url)
    this.ws = ws
    ws.onopen = () => {
      this._send({ type: 'auth', token: this.getToken() })
    }
    ws.onmessage = (event) => {
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        return
      }
      if (msg.type === 'auth.ok') {
        this.attempt = 0
        this.onStatus('online')
        clearInterval(this.timers.heartbeat)
        this.timers.heartbeat = setInterval(() => this._send({ type: 'ping' }), 25000)
      }
      if (msg.type !== 'pong') this.onMessage(msg)
    }
    ws.onclose = () => {
      clearInterval(this.timers.heartbeat)
      this.ws = null
      if (!this.stopped) this._scheduleReconnect()
    }
    ws.onerror = () => ws.close()
  }

  _scheduleReconnect() {
    if (this.stopped) return
    this.onStatus('reconnecting')
    const delay = backoffDelay(this.attempt++)
    this.timers.reconnect = setTimeout(() => this._connect(), delay)
  }
}

export function realtimeUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/realtime/`
}
