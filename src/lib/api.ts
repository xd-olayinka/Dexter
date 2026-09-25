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
  const base = API_URL.replace(/^http/, 'ws') + path
  return authToken ? `${base}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(authToken)}` : base
}

// ---------- Auth token (docs/PHASE_3_4_PLAN.md §1) ----------
// Only meaningful once the backend has DEXTER_REQUIRE_AUTH=true; harmless to carry
// around otherwise, same as `dexter.apiUrl` above.
let authToken: string | null = localStorage.getItem('dexter.authToken')

export function setAuthToken(token: string | null) {
  authToken = token
  if (token) localStorage.setItem('dexter.authToken', token)
  else localStorage.removeItem('dexter.authToken')
}

/** Thrown for a well-formed error response (4xx/5xx with a JSON `detail`) so callers
 *  can show the backend's actual reason instead of a generic failure toast. */
export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 4000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(API_URL + path, {
      ...init,
      signal: ctrl.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...init?.headers,
      },
    })
    if (!res.ok) throw new ApiError(res.status, await _errorDetail(res))
    if (res.status === 204) return undefined as T
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

/** Like `request`, but sends a `FormData` body (file upload) instead of JSON —
 *  the browser sets the multipart boundary itself, so no Content-Type header here. */
async function requestForm<T>(path: string, form: FormData, timeoutMs = 30000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(API_URL + path, {
      method: 'POST', body: form, signal: ctrl.signal,
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
    })
    if (!res.ok) throw new ApiError(res.status, await _errorDetail(res))
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

async function _errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string }
    return body.detail ?? `${res.status} ${res.statusText}`
  } catch {
    return `${res.status} ${res.statusText}`
  }
}

// ---------- Types mirrored from server ----------

export interface SystemStatus {
  backend: { ok: boolean; version: string }
  brain: { provider: string; model: string; ready: boolean }
  ollama: { ok: boolean; url: string; model: string; models: string[] }
  database: { ok: boolean; url: string }
  searxng: { ok: boolean; url: string }
  voice: { torch: boolean; stt: boolean; tts: boolean }
  browser: { playwright: boolean }
  notifications: { configured: boolean; topic: string; server: string }
  providers: Record<string, boolean>
  prometheus: { configured: boolean; connected: boolean; url: string | null }
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

export interface ProjectRecord {
  id: string
  name: string
  category: string
  status: string
  priority: string
  due_date: string | null
  people: string[]
  agents_note: string
  tasks_total: number
  tasks_done: number
  created_at: string
  updated_at: string
}

export interface TaskRecord {
  id: string
  project_id: string | null
  title: string
  meta: string
  when_bucket: 'today' | 'upcoming'
  status: 'open' | 'done' | 'blocked'
  delegated_task_id: string | null
  created_at: string
  updated_at: string
}

export interface BriefingToday {
  headline: string
  source: 'brain' | 'fallback'
  generated_at: string
  cached: boolean
  stats: {
    tasks_today: number
    tasks_done: number
    blocked: number
    gates_pending: number
    spend_today: number
  }
}

export interface DocumentRecord {
  id: string
  source: 'upload' | 'url'
  title: string
  origin: string
  char_count: number
  created_at: string
}

export interface ModelRoute {
  level: 'local' | 'fast' | 'cloud'
  provider: string
  model: string
  reason: string
}

export interface GuardRule {
  id: string
  name: string
  keyword: string
  max_spend: number | null
  require_approval: boolean
  enabled: boolean
}

export interface MeInfo {
  require_auth: boolean
  user: { id: string; email: string; name: string }
  business_id: string
  business_name: string
  role: string
}

export interface AuthResult {
  token: string
  user: { id: string; email: string; name: string }
  business_id: string
  business_name: string
  role: string
}

export interface MemberInfo {
  id: string
  email: string
  name: string
  role: string
  joined_at: string
}

export interface BusinessInfo {
  id: string
  name: string
  role: string
  current: boolean
}

export interface DependencyAgent {
  id: string
  name: string
  status: string
  owner_user_id: string | null
  owner_name: string | null
  task_id: string
  tools_used: string[]
}

export interface DependencyTool {
  name: string
  kind: 'builtin' | 'integration'
  connected: boolean | null
  used_by_agents: number
}

export interface DependencyMap {
  business: { id: string; name: string }
  members: Array<{ id: string; name: string; role: string }>
  agents: DependencyAgent[]
  tools: DependencyTool[]
}

export interface GuardConfig {
  daily_budget: number
  per_task_budget_default: number
  high_cost_multiplier: number
  long_running_minutes: number
  custom_rules: GuardRule[]
}

export interface AgentRecord {
  id: string
  name: string
  kind: 'orchestrated' | 'executor'
  model_route: string | null
  status: string
  efficiency_score: number | null
  efficiency_normalized: number | null
  budget_cap: number | null
  spend: number
  task_id: string
  created_at: string
  completed_at: string | null
}

export interface MetricsSummary {
  time_to_completion: { median_seconds: number | null; p90_seconds: number | null; sample_size: number; on_track: boolean | null }
  intervention_rate: { without_intervention_pct: number | null; sample_size: number; on_track: boolean | null }
  cost_trend: Array<{ week_start: string; avg_cost: number; count: number }>
  activity: { active_sessions_7d: number; approvals_7d: number }
  targets: { time_to_completion_minutes: number; without_intervention_pct: number }
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
  routeDryRun: (message: string) =>
    request<ModelRoute>('/api/escalation/route', { method: 'POST', body: JSON.stringify({ message }) }),

  // ---------- Projects / Tasks (Build Plan 2.3) ----------
  projects: () => request<ProjectRecord[]>('/api/projects'),
  createProject: (name: string, category = '') =>
    request<ProjectRecord>('/api/projects', { method: 'POST', body: JSON.stringify({ name, category }) }),
  updateProject: (id: string, patch: Partial<Pick<ProjectRecord, 'name' | 'category' | 'status' | 'priority'>>) =>
    request<ProjectRecord>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),

  tasksList: (when?: 'today' | 'upcoming') =>
    request<TaskRecord[]>(`/api/tasks${when ? `?when=${when}` : ''}`),
  createTask: (title: string, whenBucket: 'today' | 'upcoming' = 'today', projectId?: string) =>
    request<TaskRecord>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify({ title, when_bucket: whenBucket, project_id: projectId ?? null }),
    }),
  updateTask: (id: string, patch: Partial<Pick<TaskRecord, 'title' | 'status' | 'delegated_task_id'>>) =>
    request<TaskRecord>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteTask: (id: string) => request<void>(`/api/tasks/${id}`, { method: 'DELETE' }),

  // ---------- Briefing (Build Plan 2.4) ----------
  briefing: (refresh = false) => request<BriefingToday>(`/api/briefing/today${refresh ? '?refresh=true' : ''}`, undefined, 30000),

  // ---------- Files / memory ingest (Build Plan 2.5) ----------
  uploadFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<DocumentRecord>('/api/files/upload', form)
  },
  ingestUrl: (url: string) =>
    request<DocumentRecord>('/api/files/url', { method: 'POST', body: JSON.stringify({ url }) }, 20000),
  files: () => request<DocumentRecord[]>('/api/files'),
  deleteFile: (id: string) => request<void>(`/api/files/${id}`, { method: 'DELETE' }),

  // ---------- Guard config (Build Plan 2.7) ----------
  guardConfig: () => request<GuardConfig>('/api/shadow/guards'),
  patchGuardConfig: (patch: Partial<Omit<GuardConfig, 'custom_rules'>>) =>
    request<GuardConfig>('/api/shadow/guards', { method: 'PATCH', body: JSON.stringify(patch) }),
  addGuardRule: (rule: { name: string; keyword?: string; max_spend?: number | null; require_approval?: boolean }) =>
    request<GuardConfig>('/api/shadow/guards/rules', { method: 'POST', body: JSON.stringify(rule) }),
  removeGuardRule: (ruleId: string) =>
    request<GuardConfig>(`/api/shadow/guards/rules/${ruleId}`, { method: 'DELETE' }),

  // ---------- Auth / Business (Phase 4) ----------
  me: () => request<MeInfo>('/api/auth/me'),
  login: (email: string, password: string) =>
    request<AuthResult>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, name: string, businessName: string, inviteCode = '') =>
    request<AuthResult>('/api/auth/register', {
      method: 'POST', body: JSON.stringify({ email, password, name, business_name: businessName, invite_code: inviteCode }),
    }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  members: () => request<MemberInfo[]>('/api/auth/members'),
  invite: (email: string, role: 'admin' | 'member', name = '') =>
    request<{ email: string; already_a_member: boolean; invite_code: string | null }>('/api/auth/invite', {
      method: 'POST', body: JSON.stringify({ email, role, name }),
    }),
  businesses: () => request<BusinessInfo[]>('/api/auth/businesses'),
  switchBusiness: (businessId: string) =>
    request<MeInfo>('/api/auth/switch-business', { method: 'POST', body: JSON.stringify({ business_id: businessId }) }),

  // ---------- Dependency map (Phase 4 §7) ----------
  dependencyMap: () => request<DependencyMap>('/api/dependencies/map'),

  // ---------- Agents (Phase 4 §2) ----------
  agents: () => request<AgentRecord[]>('/api/shadow/agents'),

  // ---------- Metrics (Phase 4 §3) ----------
  metrics: () => request<MetricsSummary>('/api/metrics/summary', undefined, 8000),
}

export function setApiUrl(url: string) {
  localStorage.setItem('dexter.apiUrl', url)
  window.location.reload()
}
