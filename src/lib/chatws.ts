// Thin WebSocket client for the live `/ws/chat` protocol. Owns connect /
// reconnect-with-backoff / teardown; Chat.tsx owns all UI state and just
// wires up callbacks. One socket carries many turns — the server keeps
// session history per connection.
import { wsUrl } from './api'

export interface ChatWsMessage {
  id: string
  role: string
  content: string
  protocol: string
  timestamp: string
}

export type ChatWsFrame =
  | { type: 'chunk'; content: string }
  | { type: 'done'; message: ChatWsMessage }
  | { type: 'error'; content: string }

export interface ChatWsHandlers {
  onOpen?: () => void
  onClose?: () => void
  onFrame: (frame: ChatWsFrame) => void
}

const BACKOFF_STEPS_MS = [1000, 2000, 4000, 8000]

function isChatWsMessage(v: unknown): v is ChatWsMessage {
  if (typeof v !== 'object' || v === null) return false
  const m = v as Record<string, unknown>
  return (
    typeof m.id === 'string' &&
    typeof m.role === 'string' &&
    typeof m.content === 'string' &&
    typeof m.protocol === 'string' &&
    typeof m.timestamp === 'string'
  )
}

function isChatWsFrame(v: unknown): v is ChatWsFrame {
  if (typeof v !== 'object' || v === null) return false
  const f = v as Record<string, unknown>
  if (f.type === 'chunk') return typeof f.content === 'string'
  if (f.type === 'error') return typeof f.content === 'string'
  if (f.type === 'done') return isChatWsMessage(f.message)
  return false
}

/** Manages one `/ws/chat` connection with automatic backoff reconnect. */
export class ChatWs {
  private socket: WebSocket | null = null
  private closedByUser = false
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(private handlers: ChatWsHandlers) {}

  connect(): void {
    this.closedByUser = false
    this.open()
  }

  get isOpen(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN
  }

  send(content: string, protocol: 'orch' | 'shadow'): boolean {
    if (!this.isOpen || !this.socket) return false
    this.socket.send(JSON.stringify({ type: 'message', content, protocol }))
    return true
  }

  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.socket?.close()
    this.socket = null
  }

  private open(): void {
    if (this.socket) return
    const socket = new WebSocket(wsUrl('/ws/chat'))
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      this.handlers.onOpen?.()
    }

    socket.onmessage = (ev) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(String(ev.data))
      } catch {
        return
      }
      if (isChatWsFrame(parsed)) this.handlers.onFrame(parsed)
    }

    socket.onclose = () => {
      this.socket = null
      this.handlers.onClose?.()
      if (!this.closedByUser) this.scheduleReconnect()
    }

    socket.onerror = () => {
      socket.close()
    }
  }

  private scheduleReconnect(): void {
    const delay = BACKOFF_STEPS_MS[Math.min(this.attempt, BACKOFF_STEPS_MS.length - 1)]
    this.attempt += 1
    this.reconnectTimer = setTimeout(() => {
      if (!this.closedByUser) this.open()
    }, delay)
  }
}
