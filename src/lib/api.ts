// Typed client for the Dexter backend. Every call times out fast and
// throws ApiOffline so the UI can fall back to demo mode — the static
// GitHub Pages deploy has no backend and must keep working.

export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  localStorage.getItem('dexter.apiUrl') ??
  'http://localhost:8000'

export class ApiOffline extends Error {
  constructor() {
    super('Backend offline')
    this.name = 'ApiOffline'
  }
}

export function wsUrl(path: string): string {
  return API_URL.replace(/^http/, 'ws') + path
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 4000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(API_URL + path, {
      ...init,
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return (await res.json()) as T
  } catch (e) {
    if (e instanceof TypeError || (e instanceof DOMException && e.name === 'AbortError')) {
      throw new ApiOffline()
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}

// ---------- Types mirrored from server ----------

export interface SystemStatus {
  backend: { ok: boolean; version: string }
  ollama: { ok: boolean; url: string; model: string; models: string[] }
  database: { ok: boolean; url: string }
  searxng: { ok: boolean; url: string }
  voice: { torch: boolean; stt: boolean; tts: boolean }
  browser: { playwright: boolean }
  notifications: { configured: boolean; topic: string; server: string }
  providers: Record<string, boolean>
}

export interface Gate {
  task_id: string
  reason: string
  task_title: string
  created_at: string
  status: 'pending' | 'approved' | 'rejected'
  resolved_at: string | null
}

export interface TaskInfo {
  id: string
  title: string
  description: string
  status: 'draft' | 'queued' | 'running' | 'gated' | 'done' | 'killed'
  protocol: string
  executor_id: string | null
  budget_cap: number | null
  spend: number
  created_at: string
  completed_at: string | null
  result: string | null
  error: string | null
}

export interface BudgetSnapshot {
  daily_limit: number
  daily_spent: number
  daily_remaining: number
  active_tasks: number
  total_tasks_today: number
}

export interface SpendReport {
  total_today: number
  by_provider: Record<string, number>
  by_model: Record<string, number>
  budget_remaining: number
}

export interface ChatMessage {
  id: string
  role: string
  content: string
  protocol: string
  timestamp: string
}

// ---------- Endpoints ----------

export const api = {
  health: () => request<{ status: string; version: string }>('/', undefined, 2500),
  status: () => request<SystemStatus>('/api/status', undefined, 6000),

  sendChat: (message: string, protocol: string, sessionId?: string) =>
    request<{ session_id: string; message: ChatMessage }>('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({ message, protocol, session_id: sessionId ?? null }),
    }, 120000),

  gates: () => request<Gate[]>('/api/shadow/gates'),
  approveGate: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/api/shadow/gates/${taskId}/approve`, { method: 'POST' }),
  rejectGate: (taskId: string, reason = '') =>
    request<{ task_id: string; status: string }>(`/api/shadow/gates/${taskId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  testGate: () => request<Gate>('/api/shadow/gates/test', { method: 'POST' }),

  delegate: (title: string, description = '', budgetCap?: number) =>
    request<TaskInfo>('/api/shadow/delegate', {
      method: 'POST',
      body: JSON.stringify({ title, description, budget_cap: budgetCap ?? null }),
    }),
  tasks: () => request<TaskInfo[]>('/api/shadow/tasks'),
  killTask: (taskId: string) =>
    request<TaskInfo>(`/api/shadow/tasks/${taskId}/kill`, { method: 'POST' }),
  budget: () => request<BudgetSnapshot>('/api/shadow/budget'),

  spend: () => request<SpendReport>('/api/escalation/spend'),
  providers: () =>
    request<{ providers: { name: string; available: boolean; default_model: string }[] }>('/api/escalation/providers'),
}

export function setApiUrl(url: string) {
  localStorage.setItem('dexter.apiUrl', url)
  window.location.reload()
}
