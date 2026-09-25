import { useEffect, useRef, useState } from 'react'
import { RUN_LOG, GATES, SWARM, MODEL_POOL, PICKS, BURN, GUARDS } from '../data'
import operative from '../assets/img/operative.png'
import { api, ApiError, type AgentRecord, type GuardConfig, type ModelRoute, type SpendReport, type TaskInfo } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Anthony did not respond'
}

function statusBadgeCls(status: TaskInfo['status']): string {
  if (status === 'running') return 'ylw'
  if (status === 'gated') return 'red'
  if (status === 'done') return 'grn'
  return '' // queued, draft, killed — dim/default
}

export function ShadowOps() {
  const { online, gates, budget, refreshGates } = useBackend()
  const toast = useToast()
  const [cmd, setCmd] = useState('')
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  async function loadTasks() {
    try {
      const t = await api.tasks()
      if (mountedRef.current) setTasks(t)
    } catch {
      /* transient — status poll owns the online flag */
    }
  }

  useEffect(() => {
    if (!online) return
    loadTasks()
    const t = setInterval(loadTasks, 8000)
    return () => clearInterval(t)
  }, [online])

  async function spawn() {
    const text = cmd.trim()
    if (!text) return
    if (!online) {
      toast.push({ title: 'Backend offline', body: 'Start the server to delegate real tasks', kind: 'warn' })
      return
    }
    try {
      await api.delegate(text)
      toast.push({ title: 'Executor spawned', body: text, kind: 'good' })
      setCmd('')
      loadTasks()
    } catch {
      toast.push({ title: 'Spawn failed', body: 'Anthony did not respond', kind: 'warn' })
    }
  }

  async function approve(taskId: string) {
    try {
      await api.approveGate(taskId)
      await refreshGates()
      toast.push({ title: 'Gate approved', kind: 'good' })
    } catch {
      toast.push({ title: 'Approve failed', body: 'Could not reach Anthony', kind: 'warn' })
    }
  }

  async function reject(taskId: string) {
    try {
      await api.rejectGate(taskId)
      await refreshGates()
      toast.push({ title: 'Gate rejected', kind: 'info' })
    } catch {
      toast.push({ title: 'Reject failed', body: 'Could not reach Anthony', kind: 'warn' })
    }
  }

  async function kill(taskId: string) {
    try {
      await api.killTask(taskId)
      toast.push({ title: 'Task killed', kind: 'good' })
      loadTasks()
    } catch {
      toast.push({ title: 'Kill failed', body: 'Could not reach Anthony', kind: 'warn' })
    }
  }

  const pendingGates = gates.filter((g) => g.status === 'pending')
  const spentPct = online && budget && budget.daily_limit > 0
    ? Math.min(100, (budget.daily_spent / budget.daily_limit) * 100)
    : 0

  return (
    <div className="content" style={{ maxWidth: 560 }}>
      <div className="label" style={{ marginBottom: 8 }}>ANTHONY COMMAND</div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="chatinput" style={{ paddingTop: 0 }}>
          <input
            type="text"
            placeholder="Order Anthony…"
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') spawn() }}
          />
        </div>
        <div className="pillrow" style={{ paddingTop: 8 }}>
          <button className="p" onClick={spawn}>⬢ Spawn</button>
        </div>
      </div>
      <div className="eyebrow">Ops Feed · Encrypted</div>
      <h1 className="bigtitle">
        <em>Anthony</em> ran all night. <span className="hl">5 executors</span>,{' '}
        <span className="hl">1 guard trip</span>, zero escalations.
      </h1>
      <div className="chiprow">
        <div className="chip"><span className="dot" />4 live</div>
        <div className="chip">1 queued</div>
        <div className="chip"><span className="dot warn" />1 killed</div>
        <div className="chip">$14.20 burn</div>
      </div>
      <div className="heromini mobile-only">
        <img src={operative} alt="Dexter" />
        <div className="tick tl" /><div className="tick tr" />
        <div className="plate">
          <div><div className="sub">Operative</div><div className="nm">A.N.T.H.O.N.Y</div></div>
          <div className="mode">Shadow Ops<br />Active</div>
        </div>
      </div>
      <div className="card">
        <div className="cardhead"><span className="label">Run Log · Live</span><button className="more">Stream →</button></div>
        {RUN_LOG.map(([ic, nm, meta, tag, cls]) => (
          <div key={nm} className="row">
            <div className="ic">{ic}</div>
            <div className="body"><div className="nm">{nm}</div><div className="meta">{meta}</div></div>
            <span className={`badge ${cls}`}>{tag}</span>
          </div>
        ))}
      </div>
      {online && (
        <div className="card">
          <div className="cardhead"><span className="label">Live Tasks · {tasks.length}</span></div>
          {tasks.length === 0 ? (
            <div className="row"><div className="body"><div className="meta">No tasks yet.</div></div></div>
          ) : tasks.map((t) => {
            const terminal = t.status === 'done' || t.status === 'killed'
            return (
              <div key={t.id} className="task">
                <div className="body">
                  <div className="nm">{t.title}</div>
                  <div className="meta">${t.spend.toFixed(2)} spent{t.budget_cap != null ? ` · cap $${t.budget_cap.toFixed(2)}` : ''}</div>
                </div>
                <span className={`badge ${statusBadgeCls(t.status)}`}>{t.status}</span>
                {!terminal && <button className="del" onClick={() => kill(t.id)}>Kill</button>}
              </div>
            )
          })}
        </div>
      )}
      <div className="card tint">
        <div className="cardhead">
          <span className="label">Pending Approval Gates{online ? ` · ${pendingGates.length}` : ' · 2'}</span>
        </div>
        {online ? (
          pendingGates.length === 0 ? (
            <div className="row"><div className="body"><div className="meta">No gates pending.</div></div></div>
          ) : pendingGates.map((g) => (
            <div key={g.task_id} className="row">
              <div className="ic">⬢</div>
              <div className="body"><div className="nm">{g.task_title}</div><div className="meta">{g.reason}</div></div>
              <div style={{ display: 'flex', gap: 6, flex: 'none' }}>
                <button className="badge grn" style={{ border: 'none', cursor: 'pointer' }} onClick={() => approve(g.task_id)}>Approve</button>
                <button className="badge red" style={{ border: 'none', cursor: 'pointer' }} onClick={() => reject(g.task_id)}>Reject</button>
              </div>
            </div>
          ))
        ) : (
          GATES.map((g) => (
            <div key={g.nm} className="row">
              <div className="ic">{g.ic}</div>
              <div className="body"><div className="nm">{g.nm}</div><div className="meta">{g.meta}</div></div>
              <span className={`badge ${g.badge[0]}`}>{g.badge[1]}</span>
            </div>
          ))
        )}
      </div>
      {online && budget && (
        <div className="card">
          <div className="cardhead"><span className="label">Daily Budget</span></div>
          <div className="bar">
            <div className="lbl">
              <b>${budget.daily_spent.toFixed(2)} / ${budget.daily_limit.toFixed(2)}</b>
              <span>{Math.round(spentPct)}%</span>
            </div>
            <div className="track"><div className={`fill${spentPct > 80 ? ' hot' : ''}`} style={{ width: `${spentPct}%` }} /></div>
          </div>
          <div className="row">
            <div className="body"><div className="meta">Active tasks: {budget.active_tasks} · Today: {budget.total_tasks_today}</div></div>
          </div>
        </div>
      )}
    </div>
  )
}

function agentStCls(status: string): string {
  if (status === 'done') return 'live'
  if (status === 'killed') return 'dead'
  if (status === 'running' || status === 'gated') return 'live'
  return 'q'
}

export function Swarm() {
  const { online } = useBackend()
  const [agents, setAgents] = useState<AgentRecord[] | null>(null)

  async function load() {
    try {
      setAgents(await api.agents())
    } catch {
      /* transient */
    }
  }

  useEffect(() => {
    if (!online) { setAgents(null); return }
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [online])

  const usingLive = online && agents !== null
  const totalSpend = usingLive ? agents!.reduce((s, a) => s + a.spend, 0) : 0
  const avgEff = usingLive && agents!.length
    ? agents!.reduce((s, a) => s + (a.efficiency_normalized ?? 0), 0) / agents!.length
    : 0

  return (
    <div className="content">
      <h1 className="bigtitle">Executor Swarm</h1>
      <p className="subnote lead">
        {usingLive ? 'Real agents Anthony has spawned, with a computed efficiency score (outcome ÷ spend, normalized to this batch).' : "Sub-agents Anthony created. Efficiency scores decide who survives."}
      </p>
      {usingLive ? (
        agents!.length === 0 ? (
          <p className="subnote">No agents spawned yet — delegate a task from Home or Chat.</p>
        ) : (
          <div className="swarm">
            {agents!.map((a) => {
              const eff = a.efficiency_normalized ?? 0
              return (
                <div key={a.id} className="unit">
                  <span className={`st ${agentStCls(a.status)}`} />
                  <div className="id">{a.id.replace('agent_task_', 'EX-')}</div>
                  <div className="nm" style={a.status === 'killed' ? { textDecoration: 'line-through', textDecorationColor: 'rgba(199,54,31,.6)' } : undefined}>{a.name}</div>
                  <div className="eff">
                    <div className="k"><span>Efficiency</span><span>{a.efficiency_score != null ? eff.toFixed(2) : '—'}</span></div>
                    <div className="track"><div className={`fill${eff < 0.6 ? ' low' : ''}`} style={{ width: `${eff * 100}%` }} /></div>
                  </div>
                  <div className="foot"><span>{a.status}</span><span>${a.spend.toFixed(2)}</span></div>
                </div>
              )
            })}
          </div>
        )
      ) : (
        <div className="swarm">
          {SWARM.map(([id, nm, st, eff, work, cost]) => (
            <div key={id} className="unit">
              <span className={`st ${st}`} />
              <div className="id">{id}</div>
              <div className="nm" style={st === 'dead' ? { textDecoration: 'line-through', textDecorationColor: 'rgba(199,54,31,.6)' } : undefined}>{nm}</div>
              <div className="eff">
                <div className="k"><span>Efficiency</span><span>{eff.toFixed(2)}</span></div>
                <div className="track"><div className={`fill${eff < 0.6 ? ' low' : ''}`} style={{ width: `${eff * 100}%` }} /></div>
              </div>
              <div className="foot"><span>{work}</span><span>{cost}</span></div>
            </div>
          ))}
        </div>
      )}
      <div className="card">
        <div className="cardhead"><span className="label">Swarm Totals</span></div>
        <div className="row">
          <div className="ic">Σ</div>
          <div className="body">
            <div className="nm">{usingLive ? `${agents!.length} agent(s) on record` : '1,284 tasks terminated tonight'}</div>
            <div className="meta">{usingLive ? `avg ${avgEff.toFixed(2)} efficiency · $${totalSpend.toFixed(2)} total spend` : 'avg 0.87 efficiency · $14.20 total burn'}</div>
          </div>
          <span className="badge grn">{usingLive ? 'Live' : 'Healthy'}</span>
        </div>
      </div>
    </div>
  )
}

interface ProviderInfo { name: string; available: boolean; default_model: string }

function ProviderRow({ p }: { p: ProviderInfo }) {
  return (
    <div className="row">
      <div className="ic">{p.available ? '●' : '○'}</div>
      <div className="body"><div className="nm">{p.name} <span className={`badge${p.available ? ' grn' : ''}`}>{p.available ? 'Reachable' : 'No key'}</span></div><div className="meta">{p.default_model}</div></div>
    </div>
  )
}

export function Selector() {
  const { online } = useBackend()
  const toast = useToast()
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null)
  const [msg, setMsg] = useState('')
  const [route, setRoute] = useState<ModelRoute | null>(null)
  const [routing, setRouting] = useState(false)

  useEffect(() => {
    if (!online) { setProviders(null); return }
    let cancelled = false
    api.providers().then((r) => { if (!cancelled) setProviders(r.providers) }).catch(() => { if (!cancelled) setProviders(null) })
    return () => { cancelled = true }
  }, [online])

  async function tryRoute() {
    const v = msg.trim()
    if (!v || routing) return
    setRouting(true)
    try {
      setRoute(await api.routeDryRun(v))
    } catch (e) {
      toast.push({ title: 'Dry run failed', body: errMsg(e), kind: 'warn' })
    } finally {
      setRouting(false)
    }
  }

  const usingLive = online && providers !== null

  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Selector Core</h1>
      <p className="subnote lead">Scores cost × capability × latency, then picks the cheapest capable executor. Every pick is explainable.</p>
      <div className="card">
        <div className="cardhead">
          <span className="label">Model Pool</span>
          {usingLive
            ? <span className={`badge${providers!.some((p) => p.available) ? ' grn' : ' red'}`}>{providers!.filter((p) => p.available).length} / {providers!.length} reachable</span>
            : <span className="badge grn">All Reachable</span>}
        </div>
        {usingLive
          ? providers!.map((p) => <ProviderRow key={p.name} p={p} />)
          : MODEL_POOL.map(([ic, nm, tag, meta, price, speed]) => (
            <div key={nm} className="row">
              <div className="ic">{ic}</div>
              <div className="body"><div className="nm">{nm} <span className={`badge${tag === 'Default' ? ' grn' : ''}`}>{tag}</span></div><div className="meta">{meta}</div></div>
              <div className="right"><div className="top">{price}</div><div className="bot">{speed}</div></div>
            </div>
          ))}
      </div>
      {usingLive ? (
        <div className="card tint">
          <div className="cardhead"><span className="label">Try the Router</span></div>
          <div className="chatinput" style={{ paddingTop: 0 }}>
            <input
              type="text"
              placeholder="A sample message to route…"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') tryRoute() }}
            />
            <button className="send" aria-label="Route" onClick={tryRoute} disabled={routing}>↑</button>
          </div>
          {route && (
            <div className="row" style={{ marginTop: 8 }}>
              <div className="ic">→</div>
              <div className="body">
                <div className="nm">{route.level} · {route.provider} · {route.model}</div>
                <div className="meta">{route.reason}</div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="card tint">
          <div className="cardhead"><span className="label">Last 3 Picks · Explained</span></div>
          {PICKS.map(([nm, meta]) => (
            <div key={nm} className="row">
              <div className="ic">→</div>
              <div className="body"><div className="nm">{nm}</div><div className="meta">{meta}</div></div>
            </div>
          ))}
        </div>
      )}
      <div className="card">
        <div className="cardhead"><span className="label">Spawn Templates</span><button className="more">+ Force Spawn</button></div>
        <div className="row"><div className="ic">⬢</div><div className="body"><div className="nm">Scraper · Parser · Mailer</div><div className="meta">Bulk ops family, Haiku default</div></div></div>
        <div className="row"><div className="ic">⬡</div><div className="body"><div className="nm">Coder · Researcher · Voice</div><div className="meta">Skilled family, Fable default with escalation</div></div></div>
      </div>
    </div>
  )
}

export function Credits() {
  const { online } = useBackend()
  const [spend, setSpend] = useState<SpendReport | null>(null)
  const [guards, setGuards] = useState<GuardConfig | null>(null)

  useEffect(() => {
    if (!online) { setSpend(null); setGuards(null); return }
    let cancelled = false
    api.spend().then((s) => { if (!cancelled) setSpend(s) }).catch(() => { if (!cancelled) setSpend(null) })
    api.guardConfig().then((g) => { if (!cancelled) setGuards(g) }).catch(() => { if (!cancelled) setGuards(null) })
    return () => { cancelled = true }
  }, [online])

  const usingLive = online && spend !== null

  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Telemetry &amp; Burn</h1>
      <p className="subnote lead">Live spend across providers. Caps are hard, kills are automatic.</p>
      <div className="card">
        <div className="cardhead">
          <span className="label">{usingLive ? `Today's Burn · $${spend!.total_today.toFixed(2)}` : 'July Burn · $1,928'}</span>
        </div>
        {usingLive ? (
          Object.keys(spend!.by_provider).length === 0 ? (
            <div className="row"><div className="body"><div className="meta">No spend yet today.</div></div></div>
          ) : Object.entries(spend!.by_provider).map(([name, amt]) => {
            const pct = spend!.total_today > 0 ? Math.min(100, (amt / spend!.total_today) * 100) : 0
            return (
              <div key={name} className="bar">
                <div className="lbl"><b>{name}</b><span>${amt.toFixed(2)}</span></div>
                <div className="track"><div className={`fill${pct > 80 ? ' hot' : ''}`} style={{ width: `${pct}%` }} /></div>
              </div>
            )
          })
        ) : (
          BURN.map(([nm, note, pct, hot]) => (
            <div key={nm} className="bar">
              <div className="lbl"><b>{nm}</b><span>{note}</span></div>
              <div className="track"><div className={`fill${hot ? ' hot' : ''}`} style={{ width: `${pct}%` }} /></div>
            </div>
          ))
        )}
      </div>
      <div className="card tint">
        <div className="cardhead"><span className="label">Guards</span></div>
        {guards ? (
          <>
            <div className="row">
              <div className="ic">◍</div>
              <div className="body"><div className="nm">Daily cap · ${guards.daily_budget.toFixed(2)}</div><div className="meta">Per task default · ${guards.per_task_budget_default.toFixed(2)}</div></div>
              <span className="badge">Rule</span>
            </div>
            {guards.custom_rules.length === 0 ? (
              <div className="row"><div className="body"><div className="meta">No custom rules — add one in Settings.</div></div></div>
            ) : guards.custom_rules.map((r) => (
              <div key={r.id} className="row">
                <div className="ic">{r.enabled ? '✓' : '·'}</div>
                <div className="body">
                  <div className="nm">{r.name}</div>
                  <div className="meta">
                    {r.keyword ? `matches "${r.keyword}" · ` : 'all tasks · '}
                    {r.max_spend != null ? `caps at $${r.max_spend.toFixed(2)}` : ''}
                    {r.require_approval ? ' · always requires approval' : ''}
                  </div>
                </div>
                <span className={`badge${r.enabled ? '' : ' red'}`}>{r.enabled ? 'Active' : 'Disabled'}</span>
              </div>
            ))}
          </>
        ) : (
          GUARDS.map((g) => (
            <div key={g.nm} className="row">
              <div className="ic">{g.ic}</div>
              <div className="body"><div className="nm">{g.nm}</div><div className="meta">{g.meta}</div></div>
              <span className={`badge ${g.badge[0]}`}>{g.badge[1]}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
