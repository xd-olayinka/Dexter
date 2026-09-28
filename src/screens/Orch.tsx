import { useEffect, useState } from 'react'
import { PROJECTS, TASKS_TODAY, TASKS_UPCOMING, TEAM, LOAD } from '../data'
import heroOrch from '../assets/img/hero-orch.jpg'
import { useAuth } from '../lib/auth'
import { api, ApiError, type BriefingToday, type DependencyMap, type MemberInfo, type MetricsSummary, type ProjectRecord, type TaskRecord, type TeamWorkload, type AgentRecord, type LedgerSummary, type Role } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'
import { MicButton } from '../components/MicButton'

export function OrchHome({ go, enterShadow }: { go: (tab: string) => void; enterShadow: () => void }) {
  const { online } = useBackend()
  const toast = useToast()
  const [cmd, setCmd] = useState('')
  const [briefing, setBriefing] = useState<BriefingToday | null>(null)
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null)

  useEffect(() => {
    if (!online) { setBriefing(null); setMetrics(null); return }
    let cancelled = false
    api.briefing().then((b) => { if (!cancelled) setBriefing(b) }).catch(() => { if (!cancelled) setBriefing(null) })
    api.metrics().then((m) => { if (!cancelled) setMetrics(m) }).catch(() => { if (!cancelled) setMetrics(null) })
    return () => { cancelled = true }
  }, [online])

  function ask() {
    const text = cmd.trim()
    if (!text) return
    sessionStorage.setItem('dexter.pendingMessage', text)
    setCmd('')
    go('chat')
  }

  async function delegate() {
    const text = cmd.trim()
    if (!text) return
    if (!online) {
      toast.push({ title: 'Backend offline', body: 'Start the server to delegate real tasks', kind: 'warn' })
      return
    }
    try {
      await api.delegate(text)
      toast.push({ title: 'Delegated to Anthony', body: text, kind: 'good' })
      setCmd('')
    } catch {
      toast.push({ title: 'Delegate failed', body: 'Anthony did not respond', kind: 'warn' })
    }
  }

  // Build Plan 2.4: read from /api/briefing/today when online; keep the canned
  // line offline (demo mode) or while the first fetch is still in flight.
  const headline = online && briefing
    ? briefing.headline
    : <>Good morning, <em>Commander</em>. <span className="hl">3 priorities</span>,{' '}<span className="hl">1 revenue op</span> at 09:00.</>

  return (
    <div className="content" style={{ maxWidth: 560 }}>
      <div className="label" style={{ marginBottom: 8 }}>COMMAND INPUT</div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="chatinput" style={{ paddingTop: 0 }}>
          <input
            type="text"
            placeholder="Tell Dexter what you need…"
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') ask() }}
          />
          <MicButton protocol="orch" onTranscript={(text) => setCmd((c) => (c ? `${c} ${text}` : text))} onError={(msg) => toast.push({ title: 'Voice error', body: msg, kind: 'warn' })} />
          <button className="send" aria-label="Ask" onClick={ask}>↑</button>
        </div>
        <div className="pillrow" style={{ paddingTop: 8 }}>
          <button className="p" onClick={delegate}>⬢ Delegate</button>
        </div>
      </div>
      <div className="eyebrow">Briefing · {online && briefing ? (briefing.source === 'brain' ? 'Live' : 'No brain online') : 'Demo'}</div>
      <h1 className="bigtitle">{headline}</h1>
      {online && briefing && (
        <div className="chiprow">
          <div className="chip"><span className="dot" />{briefing.stats.tasks_today} tasks today</div>
          {briefing.stats.blocked > 0 && <div className="chip"><span className="dot warn" />{briefing.stats.blocked} blocked</div>}
          {briefing.stats.gates_pending > 0 && <div className="chip"><span className="dot warn" />{briefing.stats.gates_pending} gate(s) pending</div>}
          <div className="chip">${briefing.stats.spend_today.toFixed(2)} spent today</div>
        </div>
      )}
      {(!online || !briefing) && (
        <div className="chiprow">
          <div className="chip"><span className="dot" />4 projects on track</div>
          <div className="chip"><span className="dot warn" />2 tasks blocked</div>
          <div className="chip">Team 6 / 6 in</div>
        </div>
      )}
      <div className="heromini mobile-only">
        <img src={heroOrch} alt="Dexter" />
        <div className="tick tl" /><div className="tick tr" />
        <div className="plate">
          <div><div className="sub">Operative</div><div className="nm">D.E.X.T.E.R</div></div>
          <div className="mode">Orchestrator<br />Online</div>
        </div>
      </div>
      <div className="card tint">
        <div className="cardhead"><span className="label">Today's Focus</span><button className="more" onClick={() => go('tasks')}>Tasks →</button></div>
        <div className="row"><div className="ic">◎</div><div className="body"><div className="nm">Close Meridian deal <span className="badge red">Rev Op</span></div><div className="meta">Terms drafted, review at 09:00 · Marcus + you</div></div></div>
        <div className="row"><div className="ic">▤</div><div className="body"><div className="nm">Q3 pipeline audit <span className="badge grn">62%</span></div><div className="meta">Delegated to Anthony, Lena reviewing output</div></div></div>
        <div className="row"><div className="ic">✎</div><div className="body"><div className="nm">Landing page copy <span className="badge ylw">Blocked</span></div><div className="meta">Waiting on brand assets from Rina</div></div></div>
      </div>
      <div className="card dark">
        <div className="cardhead"><span className="label">Anthony Report · Overnight</span><button className="more" style={{ color: '#F5C063' }} onClick={enterShadow}>Enter →</button></div>
        <div className="row"><div className="ic">⬢</div><div className="body"><div className="nm" style={{ color: '#FFF6E8' }}>5 executors ran, 1 guard trip</div><div className="meta">1,284 tasks total · zero escalations · $14.20 burned</div></div></div>
      </div>
      {online && metrics && (
        <div className="card">
          <div className="cardhead"><span className="label">Vitals · PRD §8</span></div>
          <div className="row">
            <div className="ic">⏱</div>
            <div className="body">
              <div className="nm">Median time to completion</div>
              <div className="meta">
                {metrics.time_to_completion.median_seconds != null
                  ? `${Math.round(metrics.time_to_completion.median_seconds / 60)} min (n=${metrics.time_to_completion.sample_size}) · target ${metrics.targets.time_to_completion_minutes} min`
                  : `No completed missions yet · target ${metrics.targets.time_to_completion_minutes} min`}
              </div>
            </div>
            {metrics.time_to_completion.on_track != null && (
              <span className={`badge ${metrics.time_to_completion.on_track ? 'grn' : 'red'}`}>
                {metrics.time_to_completion.on_track ? 'On track' : 'Behind'}
              </span>
            )}
          </div>
          <div className="row">
            <div className="ic">✓</div>
            <div className="body">
              <div className="nm">Completed without intervention</div>
              <div className="meta">
                {metrics.intervention_rate.without_intervention_pct != null
                  ? `${metrics.intervention_rate.without_intervention_pct}% (n=${metrics.intervention_rate.sample_size}) · target ${metrics.targets.without_intervention_pct}%`
                  : `No terminal missions yet · target ${metrics.targets.without_intervention_pct}%`}
              </div>
            </div>
            {metrics.intervention_rate.on_track != null && (
              <span className={`badge ${metrics.intervention_rate.on_track ? 'grn' : 'red'}`}>
                {metrics.intervention_rate.on_track ? 'On track' : 'Behind'}
              </span>
            )}
          </div>
          <div className="row">
            <div className="ic">◈</div>
            <div className="body">
              <div className="nm">Active this week</div>
              <div className="meta">{metrics.activity.active_sessions_7d} session(s) · {metrics.activity.approvals_7d} approval(s)</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Anthony did not respond'
}

export function Projects() {
  const { online } = useBackend()
  const toast = useToast()
  const [live, setLive] = useState<ProjectRecord[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')

  async function load() {
    try {
      setLive(await api.projects())
    } catch {
      /* transient — status poll owns the online flag */
    }
  }

  useEffect(() => { if (online) load(); else setLive(null) }, [online])

  async function create() {
    const v = name.trim()
    if (!v) return
    try {
      await api.createProject(v)
      setName('')
      setCreating(false)
      load()
    } catch (e) {
      toast.push({ title: 'Could not create project', body: errMsg(e), kind: 'warn' })
    }
  }

  // Build Plan 2.3: swap the PROJECTS mock for a live fetch, same card markup —
  // demo data only when offline or the live list hasn't loaded yet.
  const usingLive = online && live !== null

  return (
    <div className="content">
      <h1 className="bigtitle">Projects</h1>
      <p className="subnote lead">Every project ties tasks, team members, and delegated agents into one thread.</p>
      <div className="chiprow">
        <div className="chip"><span className="dot" />Ongoing {usingLive ? live!.filter((p) => p.status !== 'Done').length : 4}</div>
        <div className="chip">Done {usingLive ? live!.filter((p) => p.status === 'Done').length : 12}</div>
        <button className="chip" style={{ cursor: 'pointer', border: 'none' }} onClick={() => setCreating((v) => !v)}>+ New</button>
      </div>
      {creating && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="chatinput" style={{ paddingTop: 0 }}>
            <input
              type="text"
              placeholder="Project name…"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') create() }}
              disabled={!online}
              autoFocus
            />
            <button className="send" aria-label="Create" onClick={create} disabled={!online}>↑</button>
          </div>
          {!online && <p className="subnote" style={{ marginTop: 8 }}>Backend offline — connect to create real projects.</p>}
        </div>
      )}
      <div className="grid-2">
        {usingLive
          ? live!.map((p) => (
            <div key={p.id} className="proj">
              <div className="top">
                <div className="mark">{p.name.charAt(0).toUpperCase()}</div>
                <div><div className="nm">{p.name}</div><div className="cat">{p.category || '—'}</div></div>
                <span className="badge" style={{ marginLeft: 'auto' }}>{p.priority}</span>
              </div>
              <div className="grid">
                <div className="cell"><div className="k">Due</div><div className="v">{p.due_date ?? '—'}</div></div>
                <div className="cell"><div className="k">Status</div><div className="v">{p.status}</div></div>
                <div className="cell"><div className="k">Tasks</div><div className="v">{p.tasks_done} / {p.tasks_total}</div></div>
              </div>
              <div className="foot">
                <div className="avstack">
                  {p.people.length ? p.people.map((i) => <span key={i}>{i}</span>) : <span className="meta">Unassigned</span>}
                </div>
                <div className="agents">{p.agents_note || 'no agents yet'}</div>
              </div>
            </div>
          ))
          : PROJECTS.map((p) => (
            <div key={p.name} className={`proj${p.dark ? ' dark' : ''}`}>
              <div className="top">
                <div className="mark">{p.mark}</div>
                <div><div className="nm">{p.name}</div><div className="cat">{p.cat}</div></div>
                <span className={`badge ${p.badge[0]}`} style={{ marginLeft: 'auto' }}>{p.badge[1]}</span>
              </div>
              <div className="grid">
                <div className="cell"><div className="k">Due</div><div className="v">{p.due}</div></div>
                <div className="cell"><div className="k">Status</div><div className={`v ${p.statusCls}`}>{p.status}</div></div>
                <div className="cell"><div className="k">Tasks</div><div className="v">{p.tasks}</div></div>
              </div>
              <div className="foot">
                <div className="avstack">
                  {p.people.map((i) => <span key={i}>{i}</span>)}
                  {p.plus && <span className="plus">+</span>}
                </div>
                <div className="agents"><b>{p.agents}</b> · {p.agentsNote}</div>
              </div>
            </div>
          ))}
      </div>
      {!online && <p className="subnote" style={{ marginTop: 12 }}>Demo data — connect to the backend to see your real projects.</p>}
    </div>
  )
}

type MockTaskItem = { nm: string; meta: string; tag: [string, string] | null }

function MockTaskRow({ t }: { t: MockTaskItem }) {
  const [done, setDone] = useState(false)
  const [delegated, setDelegated] = useState(t.tag?.[0] === 'sent')
  return (
    <div className={`task${done ? ' done' : ''}`}>
      <div className="chk" onClick={() => setDone(!done)}>✓</div>
      <div className="body"><div className="nm">{t.nm}</div><div className="meta">{t.meta}</div></div>
      {t.tag && (t.tag[0].startsWith('badge')
        ? <span className={t.tag[0]}>{t.tag[1]}</span>
        : <button className={`del${delegated ? ' sent' : ''}`} onClick={() => setDelegated(true)}>
            {delegated ? '⬢ Anthony' : t.tag[1]}
          </button>)}
    </div>
  )
}

function LiveTaskRow({ t, onChanged }: { t: TaskRecord; onChanged: () => void }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  async function toggleDone() {
    setBusy(true)
    try {
      await api.updateTask(t.id, { status: t.status === 'done' ? 'open' : 'done' })
      onChanged()
    } catch (e) {
      toast.push({ title: 'Could not update task', body: errMsg(e), kind: 'warn' })
    } finally {
      setBusy(false)
    }
  }

  async function delegateThis() {
    setBusy(true)
    try {
      const spawned = await api.delegate(t.title, t.meta)
      await api.updateTask(t.id, { delegated_task_id: spawned.id })
      toast.push({ title: 'Delegated to Anthony', body: t.title, kind: 'good' })
      onChanged()
    } catch (e) {
      toast.push({ title: 'Delegate failed', body: errMsg(e), kind: 'warn' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`task${t.status === 'done' ? ' done' : ''}`}>
      <div className="chk" onClick={busy ? undefined : toggleDone}>✓</div>
      <div className="body"><div className="nm">{t.title}</div><div className="meta">{t.meta || '—'}</div></div>
      {t.status === 'blocked' ? (
        <span className="badge ylw">Blocked</span>
      ) : t.delegated_task_id ? (
        <button className="del sent" disabled>⬢ Anthony</button>
      ) : (
        <button className="del" disabled={busy} onClick={delegateThis}>Delegate</button>
      )}
    </div>
  )
}

function LiveTaskList({ when, title }: { when: 'today' | 'upcoming'; title: string }) {
  const toast = useToast()
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [draft, setDraft] = useState('')

  async function load() {
    try {
      setTasks(await api.tasksList(when))
    } catch {
      /* transient */
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function add() {
    const v = draft.trim()
    if (!v) return
    try {
      await api.createTask(v, when)
      setDraft('')
      load()
    } catch (e) {
      toast.push({ title: 'Could not add task', body: errMsg(e), kind: 'warn' })
    }
  }

  return (
    <div className={`card${when === 'upcoming' ? ' tint' : ''}`}>
      <div className="cardhead">
        <span className="label">{title} · {tasks.length}</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input
            className="del"
            style={{ border: 'none', background: 'transparent', width: 140, fontSize: 12 }}
            placeholder="+ Add task…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') add() }}
          />
        </div>
      </div>
      {tasks.length === 0 ? (
        <div className="row"><div className="body"><div className="meta">Nothing here yet.</div></div></div>
      ) : tasks.map((t) => <LiveTaskRow key={t.id} t={t} onChanged={load} />)}
    </div>
  )
}

export function Tasks() {
  const { online } = useBackend()

  if (online) {
    return (
      <div className="content" style={{ maxWidth: 760 }}>
        <h1 className="bigtitle">Tasks</h1>
        <p className="subnote lead">Assign to a person, or hand it to Anthony and Dexter picks the executor.</p>
        <LiveTaskList when="today" title="Today" />
        <LiveTaskList when="upcoming" title="Upcoming" />
      </div>
    )
  }

  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Tasks</h1>
      <p className="subnote lead">Assign to a person, or hand it to Anthony and Dexter picks the executor.</p>
      <div className="card">
        <div className="cardhead"><span className="label">Today · 5</span><button className="more">+ Add</button></div>
        {TASKS_TODAY.map((t) => <MockTaskRow key={t.nm} t={t as MockTaskItem} />)}
      </div>
      <div className="card tint">
        <div className="cardhead"><span className="label">Upcoming · 3</span></div>
        {TASKS_UPCOMING.map((t) => <MockTaskRow key={t.nm} t={t as MockTaskItem} />)}
      </div>
      <p className="subnote">Demo data — connect to the backend for real tasks.</p>
    </div>
  )
}

/** Dependency map (PRD §4's `Dependency` object: business ↔ team ↔ agent ↔ tool).
 *  A labeled hierarchy, not a force-directed graph — the actual relationships here
 *  nest cleanly (one owner per agent, one task per tool call), and every edge shown
 *  is something that really happened (real agent_tool_calls rows), never a guess. */
function DependencyMapCard() {
  const [map, setMap] = useState<DependencyMap | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.dependencyMap().then((m) => { if (!cancelled) setMap(m) }).catch(() => { if (!cancelled) setMap(null) })
    return () => { cancelled = true }
  }, [])

  if (!map) return null

  const agentsByOwner = new Map<string, typeof map.agents>()
  for (const a of map.agents) {
    const key = a.owner_user_id ?? '—'
    agentsByOwner.set(key, [...(agentsByOwner.get(key) ?? []), a])
  }
  const builtinTools = map.tools.filter((t) => t.kind === 'builtin')
  const integrationTools = map.tools.filter((t) => t.kind === 'integration')

  return (
    <div className="card tint" style={{ marginTop: 16 }}>
      <div className="cardhead">
        <span className="label">Dependency Map</span>
        <button className="more" onClick={() => setExpanded((v) => !v)}>{expanded ? 'Collapse' : 'Expand'}</button>
      </div>
      <div className="row">
        <div className="ic">◈</div>
        <div className="body">
          <div className="nm">{map.business.name}</div>
          <div className="meta">{map.members.length} member(s) · {map.agents.length} recent agent(s) · {integrationTools.filter((t) => t.connected).length} integration(s) connected</div>
        </div>
      </div>
      {expanded && (
        <>
          {map.members.map((m) => {
            const owned = agentsByOwner.get(m.id) ?? []
            return (
              <div key={m.id} className="row" style={{ alignItems: 'flex-start' }}>
                <div className="ic" style={{ fontSize: 11, fontWeight: 700 }}>{initialsOf(m.name, '')}</div>
                <div className="body">
                  <div className="nm">{m.name} <span className="badge">{m.role}</span></div>
                  {owned.length === 0 ? (
                    <div className="meta">No agents yet</div>
                  ) : owned.map((a) => (
                    <div key={a.id} className="meta" style={{ marginTop: 4 }}>
                      → <b>{a.name}</b> ({a.status}){a.tools_used.length > 0 && <> — used {a.tools_used.join(', ')}</>}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <div className="ic">⚙</div>
            <div className="body">
              <div className="nm">Tools available to every agent</div>
              <div className="meta">{builtinTools.map((t) => t.name).join(', ') || 'none registered'}</div>
            </div>
          </div>
          {integrationTools.length > 0 && (
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <div className="ic">◭</div>
              <div className="body">
                <div className="nm">External integrations</div>
                {integrationTools.map((t) => (
                  <div key={t.name} className="meta">
                    {t.name} — <span className={t.connected ? '' : undefined} style={{ color: t.connected ? 'var(--good, #1BB57A)' : 'var(--dim-2)' }}>
                      {t.connected ? 'connected' : 'not configured'}
                    </span>
                    {t.used_by_agents > 0 && ` · used by ${t.used_by_agents} agent(s)`}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function initialsOf(name: string, email: string): string {
  const src = (name || email).trim()
  const parts = src.split(/\s+/)
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : src.slice(0, 2)).toUpperCase()
}

/** The Orchestrator's view of its agents: where this month's spend was routed (ledger
 *  by_model_month) and throughput — finished tasks today and over the last 7 days. */
function AgentsCard() {
  const [agents, setAgents] = useState<AgentRecord[] | null>(null)
  const [ledger, setLedger] = useState<LedgerSummary | null>(null)
  useEffect(() => {
    api.agents().then(setAgents).catch(() => setAgents([]))
    api.ledger().then(setLedger).catch(() => setLedger(null))
  }, [])
  if (!agents) return null
  const now = Date.now()
  const done = agents.filter((a) => a.status === 'done' && a.completed_at)
  const today = done.filter((a) => now - Date.parse(a.completed_at!) < 86_400_000).length
  const week = done.filter((a) => now - Date.parse(a.completed_at!) < 7 * 86_400_000).length
  const running = agents.filter((a) => a.status === 'running' || a.status === 'gated' || a.status === 'queued').length
  const split = Object.entries(ledger?.totals.by_model_month ?? {}).sort((a, b) => b[1] - a[1])
  const total = split.reduce((n, [, v]) => n + v, 0)
  return (
    <div className="card">
      <div className="cardhead"><span className="label">Agents · {agents.length}</span><span className="badge">{running} active</span></div>
      <div className="row">
        <div className="ic">⇶</div>
        <div className="body">
          <div className="nm">Throughput</div>
          <div className="meta">{today} finished today · {week} this week · {(week / 7).toFixed(1)}/day</div>
        </div>
      </div>
      {split.length === 0 ? (
        <div className="row"><div className="body"><div className="meta">No model spend routed this month yet.</div></div></div>
      ) : split.map(([model, spend]) => {
        const pct = total ? (spend / total) * 100 : 0
        return (
          <div key={model} className="bar">
            <div className="lbl"><b>{model}</b><span>${spend.toFixed(2)} · {Math.round(pct)}%</span></div>
            <div className="track"><div className="fill" style={{ width: `${pct}%` }} /></div>
          </div>
        )
      })}
    </div>
  )
}

interface WorkloadMember { userId: string; name?: string; committed: number; completed: number; capacity: number; pct: number }

/** Team load from Prometheus (list_teams + get_workload over the MCP bridge) — the active
 *  cycle's committed points against each person's capacity. */
function WorkloadCard({ workload }: { workload: TeamWorkload | null }) {
  if (!workload || !workload.connected) {
    return (
      <p className="subnote">
        Team load comes from Prometheus — connect it in Settings (PROMETHEUS_MCP_URL + token) and
        each person's committed vs. capacity for the active cycle shows here.
      </p>
    )
  }
  if (workload.error) return <p className="subnote">Prometheus didn't answer: {workload.error}</p>
  const teams = workload.teams.map((t) => ({ team: t.team, members: (Array.isArray(t.members) ? t.members : []) as WorkloadMember[] }))
  if (!teams.some((t) => t.members.length)) return <p className="subnote">Prometheus is connected, but no team has an active cycle with capacity set.</p>
  return (
    <>
      {teams.filter((t) => t.members.length).map((t) => (
        <div key={t.team} className="card tint">
          <div className="cardhead"><span className="label">Load · {t.team}</span><span className="badge grn">Prometheus</span></div>
          {t.members.map((m) => {
            const pct = m.capacity ? Math.min(100, m.pct) : 0
            return (
              <div key={m.userId} className="bar">
                <div className="lbl">
                  <b>{m.name ?? m.userId}</b>
                  <span>{m.capacity ? `${m.committed}/${m.capacity} pts · ${m.pct}%` : `${m.committed} pts · no capacity set`}</span>
                </div>
                <div className="track"><div className={`fill${m.pct > 100 ? ' hot' : ''}`} style={{ width: `${pct}%` }} /></div>
              </div>
            )
          })}
        </div>
      ))}
    </>
  )
}

export function Team() {
  const { online } = useBackend()
  const toast = useToast()
  const [members, setMembers] = useState<MemberInfo[] | null>(null)
  const [inviting, setInviting] = useState(false)
  const [inviteRole, setInviteRole] = useState<Role>('member')
  const { me } = useAuth()
  const myRole = me?.role ?? 'member'
  const canManage = myRole === 'owner' || myRole === 'admin'
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [lastInvite, setLastInvite] = useState<{ email: string; code: string } | null>(null)
  const [workload, setWorkload] = useState<TeamWorkload | null>(null)

  async function load() {
    try {
      setMembers(await api.members())
    } catch {
      /* transient */
    }
  }

  useEffect(() => {
    if (!online) { setMembers(null); setWorkload(null); return }
    load()
    api.teamWorkload().then(setWorkload).catch(() => setWorkload(null))
    const t = setInterval(load, 60000) // presence refresh
    return () => clearInterval(t)
  }, [online])

  async function invite() {
    const v = email.trim()
    if (!v || busy) return
    setBusy(true)
    try {
      const res = await api.invite(v, inviteRole)
      if (res.already_a_member && !res.invite_code) {
        toast.push({ title: `${v} is already on this team`, kind: 'info' })
      } else if (res.invite_code) {
        // New (or still-pending) account: they need this code to register. Shown once.
        setLastInvite({ email: v, code: res.invite_code })
        toast.push({ title: 'Invited', body: `Send ${v} their invite code`, kind: 'good' })
      } else {
        toast.push({ title: 'Invited', body: `${v} already has an account — they'll see this business after signing in`, kind: 'good' })
      }
      setEmail('')
      setInviting(false)
      load()
    } catch (e) {
      toast.push({ title: 'Could not invite', body: errMsg(e), kind: 'warn' })
    } finally {
      setBusy(false)
    }
  }

  async function changeRole(m: MemberInfo, role: Role) {
    if (role === m.role) return
    try {
      await api.setMemberRole(m.id, role)
      toast.push({ title: `${m.name || m.email} is now ${role}`, kind: 'good' })
      load()
    } catch (e) {
      toast.push({ title: 'Could not change role', body: errMsg(e), kind: 'warn' })
    }
  }

  const usingLive = online && members !== null

  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Team</h1>
      <p className="subnote lead">{usingLive ? "Who's in this business, and their role." : 'Six humans, their roles, load, and what each owns right now.'}</p>
      {usingLive && inviting && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="chatinput" style={{ paddingTop: 0 }}>
            <input
              type="email"
              placeholder="teammate@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') invite() }}
              autoFocus
            />
            <select className="set-input" style={{ width: 'auto' }} value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Role)} aria-label="Role">
              <option value="member">Member</option>
              <option value="admin">Admin</option>
              {myRole === 'owner' && <option value="owner">Owner</option>}
            </select>
            <button className="send" aria-label="Invite" onClick={invite} disabled={busy}>↑</button>
          </div>
          <p className="subnote" style={{ marginTop: 8 }}>
            No email is sent — new teammates get an invite code to enter when they register with this address, and they'll land in your business, not their own.
          </p>
        </div>
      )}
      {usingLive && lastInvite && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="cardhead">
            <span className="label">Invite code for {lastInvite.email}</span>
            <button className="more" onClick={() => setLastInvite(null)}>Done</button>
          </div>
          <p className="subnote" style={{ userSelect: 'all', fontFamily: 'monospace', fontSize: 16 }}>{lastInvite.code}</p>
          <p className="subnote">Shown once. Inviting the same email again issues a new code and voids this one.</p>
        </div>
      )}
      <div className="card">
        <div className="cardhead">
          <span className="label">Members · {usingLive ? members!.length : 6}</span>
          {usingLive
            ? <button className="more" onClick={() => setInviting((v) => !v)}>+ Invite</button>
            : <button className="more">+ Invite</button>}
        </div>
        {usingLive
          ? (members!.length === 0
            ? <div className="row"><div className="body"><div className="meta">Just you so far.</div></div></div>
            : members!.map((m) => (
              <div key={m.id} className="row">
                <div className="ic" style={{ fontSize: 11, fontWeight: 700 }}>{initialsOf(m.name, m.email)}</div>
                <div className="body">
                  <div className="nm">
                    {m.name || m.email}{' '}
                    {canManage && (myRole === 'owner' || m.role !== 'owner') ? (
                      <select
                        className="badge" style={{ border: 'none', cursor: 'pointer' }} value={m.role} aria-label={`Role for ${m.name || m.email}`}
                        onChange={(e) => changeRole(m, e.target.value as Role)}
                      >
                        <option value="member">member</option>
                        <option value="admin">admin</option>
                        {myRole === 'owner' && <option value="owner">owner</option>}
                      </select>
                    ) : <span className="badge">{m.role}</span>}
                  </div>
                  <div className="meta">{m.email}{!m.online && m.last_seen_at ? ` · last seen ${new Date(m.last_seen_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}` : ''}</div>
                </div>
                <span className={`badge${m.online ? ' grn' : ''}`}>{m.online ? 'Online' : 'Away'}</span>
              </div>
            )))
          : TEAM.map(([ini, nm, role, meta, status, cls]) => (
            <div key={ini} className="row">
              <div className="ic" style={{ fontSize: 11, fontWeight: 700 }}>{ini}</div>
              <div className="body">
                <div className="nm">{nm} <span className="badge">{role}</span></div>
                <div className="meta">{meta}</div>
              </div>
              <span className={`badge ${cls}`}>{status}</span>
            </div>
          ))}
      </div>
      {usingLive ? (
        <>
          <WorkloadCard workload={workload} />
          <AgentsCard />
          <DependencyMapCard />
        </>
      ) : (
        <div className="card tint">
          <div className="cardhead"><span className="label">Load Balance</span><button className="more">Rebalance →</button></div>
          {LOAD.map(([nm, pct, hot]) => (
            <div key={nm} className="bar">
              <div className="lbl"><b>{nm}</b><span>{pct}%</span></div>
              <div className="track"><div className={`fill${hot ? ' hot' : ''}`} style={{ width: `${pct}%` }} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
