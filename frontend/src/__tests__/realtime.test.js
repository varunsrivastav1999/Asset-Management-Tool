import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { backoffDelay, RealtimeClient } from '@/services/realtime'

class FakeSocket {
  static instances = []
  constructor(url) {
    this.url = url
    this.readyState = 0
    this.sent = []
    FakeSocket.instances.push(this)
  }
  send(data) {
    this.sent.push(JSON.parse(data))
  }
  close() {
    this.readyState = 3
    this.onclose?.()
  }
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  receive(msg) {
    this.onmessage?.({ data: JSON.stringify(msg) })
  }
}

describe('backoffDelay', () => {
  it('grows exponentially with jitter and is capped', () => {
    expect(backoffDelay(0, { random: () => 0 })).toBe(500)
    expect(backoffDelay(0, { random: () => 1 })).toBe(1000)
    expect(backoffDelay(3, { random: () => 1 })).toBe(8000)
    expect(backoffDelay(20, { random: () => 1 })).toBe(30000)
  })
})

describe('RealtimeClient', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeSocket.instances = []
  })
  afterEach(() => vi.useRealTimers())

  it('authenticates with a first message, never in the URL', () => {
    const client = new RealtimeClient({ url: 'ws://x/ws/realtime/', getToken: () => 'tok', WebSocketImpl: FakeSocket })
    client.start()
    const ws = FakeSocket.instances[0]
    expect(ws.url).not.toContain('tok')
    ws.open()
    expect(ws.sent[0]).toEqual({ type: 'auth', token: 'tok' })
    client.stop()
  })

  it('reports status, forwards messages, heartbeats and reconnects', () => {
    const onMessage = vi.fn()
    const statuses = []
    const client = new RealtimeClient({
      url: 'ws://x',
      getToken: () => 'tok',
      WebSocketImpl: FakeSocket,
      onMessage,
      onStatus: (s) => statuses.push(s),
    })
    client.start()
    const ws = FakeSocket.instances[0]
    ws.open()
    ws.receive({ type: 'auth.ok', unread: 2 })
    ws.receive({ type: 'notification', notification: { id: 1 } })
    ws.receive({ type: 'pong' })
    expect(statuses).toContain('online')
    expect(onMessage).toHaveBeenCalledTimes(2) // pong is swallowed
    vi.advanceTimersByTime(25000)
    expect(ws.sent.at(-1)).toEqual({ type: 'ping' })

    ws.close()
    expect(statuses.at(-1)).toBe('reconnecting')
    vi.advanceTimersByTime(1000)
    expect(FakeSocket.instances).toHaveLength(2)
    client.stop()
    expect(statuses.at(-1)).toBe('offline')
  })

  it('stops reconnecting after stop()', () => {
    const client = new RealtimeClient({ url: 'ws://x', getToken: () => 'tok', WebSocketImpl: FakeSocket })
    client.start()
    client.stop()
    vi.advanceTimersByTime(60000)
    expect(FakeSocket.instances).toHaveLength(1)
  })
})
