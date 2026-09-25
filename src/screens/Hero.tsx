import { useEffect, useState } from 'react'
import type { Mode } from '../data'
import operative from '../assets/img/operative.png'
import heroOrch from '../assets/img/hero-orch.jpg'
import { api, type BriefingToday, type Headline, type TaskInfo } from '../lib/api'
import { useBackend } from '../lib/backend'

type Live = { headline: Headline | null; briefing: BriefingToday | null; tasks: TaskInfo[] }

const money = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}K` : `$${v.toFixed(2)}`)
const hhmm = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')

/** Real numbers when the backend is up (PRD §5.2); the showcase values only in offline demo mode. */
function useHeroData(): Live | null {
  const { online } = useBackend()
  const [live, setLive] = useState<Live | null>(null)
  useEffect(() => {
    if (!online) { setLive(null); return }
    let cancelled = false
    Promise.all([
      api.headline().catch(() => null),
      api.briefing().catch(() => null),
      api.tasks().catch(() => [] as TaskInfo[]),
    ]).then(([headline, briefing, tasks]) => { if (!cancelled) setLive({ headline, briefing, tasks }) })
    return () => { cancelled = true }
  }, [online])
  return live
}

// Desktop Briefing hero — faithful rebuild of the Shadow Protocol
// reference frame: split gradient/white bands, HUD-arc operative
// card in the middle column, stats strip pinned to the bottom.
export default function Hero({ mode }: { mode: Mode }) {
  const orch = mode === 'orch'
  const live = useHeroData()
  const { status } = useBackend()
  const h = live?.headline
  const tasks = live?.tasks ?? []
  const active = tasks.filter((t) => t.status === 'running' || t.status === 'queued' || t.status === 'gated')
  const gated = tasks.filter((t) => t.status === 'gated').length
  const killed = tasks.filter((t) => t.status === 'killed').length
  const recent = [...tasks].sort((a, b) => (b.completed_at ?? b.created_at).localeCompare(a.completed_at ?? a.created_at)).slice(0, 3)
  const lastDone = tasks.filter((t) => t.status === 'done' && t.result).sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? ''))[0]
  const channels = status?.prometheus?.connected ? 'Prometheus' : null

  const stat = {
    terminated: live ? String(h?.tasks_terminated.total ?? 0) : '1,284',
    money: live
      ? (orch
        ? (h?.revenue_enabled.total != null ? money(h.revenue_enabled.total) : '—')
        : money(h?.model_spend.last_12h ?? 0))
      : (orch ? '$482K' : '$14.20'),
    moneyTitle: live && orch
      ? (h?.revenue_enabled.tagged_tasks ? `Sum of revenue tagged on ${h.revenue_enabled.tagged_tasks} completed task(s)` : 'Tag delegated tasks with a revenue value to track this')
      : undefined,
    hours: live ? String(h?.hours_reclaimed.hours ?? 0) : '312',
    hoursTitle: live && h?.hours_reclaimed.estimated_tasks ? `Includes ${h.hours_reclaimed.estimated_tasks} task(s) at the default: ${h.hours_reclaimed.assumption}` : undefined,
  }

  return (
    <div className="hero-frame">
      <div className="hero-bands" aria-hidden="true">
        <div className="left">
          <div className="rings" />
          <div className="grain" />
        </div>
        <div className="right" />
      </div>

      <div className="hero-grid">
        {/* ===== left column ===== */}
        <div className="hero-left">
          <div className="hero-pill">
            <span className="dot-live" />
            {orch ? 'Operative Ready' : `${live ? active.length : 5} Executor${live && active.length === 1 ? '' : 's'} Live`}
          </div>

          {orch ? (
            <h1 className="hero-h1">Command<br /><em>Anthony</em>.<br />Own the Day.</h1>
          ) : (
            <h1 className="hero-h1"><em>Anthony</em><br />ran all<br />night.</h1>
          )}

          <p className="hero-sub">
            {orch
              ? 'Your silent operative. Delegator. Executor. Task terminator. Revenue enabler.'
              : live
                ? `${active.length} running, ${killed} killed, ${gated} awaiting your word. Every action logged, costed, and explained.`
                : '5 executors, 1 guard trip, zero escalations. Every action logged, costed, and explained.'}
            <br />
            <span className="code">{orch ? '// deploy once. execute forever.' : '// silent. logged. explained.'}</span>
          </p>

          <button className="hero-cta">
            {orch ? 'Deploy Dexter' : 'Force Spawn'}
            <span className="arrow">→</span>
          </button>
        </div>

        {/* ===== middle character column ===== */}
        <div className="hero-char">
          <div className="arc1" aria-hidden="true" />
          <div className="arc2" aria-hidden="true" />
          <div className={`op-card${orch ? ' orch' : ''}`}>
            <img
              src={orch ? heroOrch : operative}
              alt={orch ? 'Dexter · Orchestrator' : 'Anthony · Shadow operative'}
            />
            <div className="tick tl" /><div className="tick tr" />
            <div className="tick bl" /><div className="tick br" />
            <div className="idstrip"><span>ID · 0071</span><span>SEC ●●●●</span></div>
            <div className="plate">
              <div>
                <div className="sub">Operative</div>
                <div className="nm">{orch ? 'D.E.X.T.E.R' : 'A.N.T.H.O.N.Y'}</div>
              </div>
              <div className="proto">
                {orch ? (<><div>ORCH</div><div className="red">ONLINE</div></>)
                  : (<><div>ANTHONY</div><div className="red">ONLINE</div></>)}
              </div>
            </div>
          </div>
          <div className="uptime">
            <div className="k">{orch ? 'Uptime' : 'Executors'}</div>
            <div className="v">{orch ? '24 : 00' : `${live ? active.length : 5} · LIVE`}</div>
          </div>
        </div>

        {/* ===== right column ===== */}
        <div className="hero-right">
          <div className="hero-greet">
            <div className="eyebrow2">— {orch ? 'Briefing · 06:47 Local' : 'Ops Feed · Encrypted'}</div>
            {live ? (
              orch ? (
                <h2>{live.briefing?.headline ?? 'Good morning, Commander. Nothing on the board yet — delegate something to Anthony.'}</h2>
              ) : (
                <h2><span className="hl">{h?.tasks_terminated.last_7d ?? 0} tasks</span> terminated this week,
                  <span className="hl"> {gated} gate{gated === 1 ? '' : 's'}</span> await your word.</h2>
              )
            ) : orch ? (
              <h2>Good morning, Commander. You have <span className="hl">3 priorities</span> today,
                including <span className="hl">1 revenue op</span> at 09:00. Ready to move?</h2>
            ) : (
              <h2>Overnight run complete, Commander. <span className="hl">1,284 tasks</span> terminated,
                <span className="hl"> 2 gates</span> await your word.</h2>
            )}
            <div className="verbs">{orch ? 'Delegate · Execute · Terminate' : 'Spawn · Score · Terminate'}</div>
          </div>

          {live ? (
            <div className="testimonial">
              <div className="head">
                <div className="avatar">{orch ? '✦' : '⬢'}</div>
                <div className="who">
                  <div className="nm">{orch ? 'Latest from Anthony' : 'Ops Log'}</div>
                  <div className="role">{orch ? (lastDone ? lastDone.title : 'no completed tasks yet') : 'live · this session'}</div>
                </div>
                <div className="num">/ {orch ? hhmm(lastDone?.completed_at ?? null) || '—' : 'NOW'}</div>
              </div>
              {orch ? (
                <blockquote>{lastDone ? `${(lastDone.result ?? '').slice(0, 180)}${(lastDone.result ?? '').length > 180 ? '…' : ''}` : 'Delegate a task and its report lands here.'}</blockquote>
              ) : recent.length === 0 ? (
                <div className="row"><div className="body"><div className="meta">No executor activity yet.</div></div></div>
              ) : recent.map((t) => (
                <div className="row" key={t.id}>
                  <div className="body">
                    <div className="nm">{t.status === 'done' ? '✓' : t.status === 'killed' ? '✕' : '▸'} {t.title}</div>
                    <div className="meta">{hhmm(t.completed_at ?? t.created_at)} · ${t.spend.toFixed(4)}{t.metadata?.model_route ? ` · ${t.metadata.model_route}` : ''}{t.error ? ` · ${t.error.slice(0, 40)}` : ''}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : orch ? (
            <div className="testimonial">
              <div className="head">
                <div className="avatar">JH</div>
                <div className="who">
                  <div className="nm">Jacki Hernanzo</div>
                  <div className="role">Founder · Ledger&amp;Co.</div>
                </div>
                <div className="num">/ 001</div>
              </div>
              <blockquote>
                "Dexter runs the boring war so I fight the interesting one. Deals close while I sleep."
              </blockquote>
            </div>
          ) : (
            <div className="testimonial">
              <div className="head">
                <div className="avatar">⬢</div>
                <div className="who">
                  <div className="nm">Ops Log</div>
                  <div className="role">live · encrypted</div>
                </div>
                <div className="num">/ 24H</div>
              </div>
              <div className="row"><div className="body"><div className="nm">✓ EX-071 closed Stripe upgrade</div><div className="meta">06:47 · $1,240</div></div></div>
              <div className="row"><div className="body"><div className="nm">▸ EX-082 spawned · Fable</div><div className="meta">06:31</div></div></div>
              <div className="row"><div className="body"><div className="nm">✕ EX-063 killed · guard trip</div><div className="meta">03:22 · cost/task 4× median</div></div></div>
            </div>
          )}
        </div>
      </div>

      {/* ===== bottom stats strip ===== */}
      <div className="hero-stats">
        <div className="stat">
          <div className="head"><span className="k">Tasks Terminated</span><span className="ic">✓</span></div>
          <div className="v">{stat.terminated}<sup>↑</sup></div>
        </div>
        <div className="stat">
          <div className="head"><span className="k">{orch ? 'Revenue Enabled' : 'Burn · 12h'}</span><span className="ic">$</span></div>
          <div className="v" title={stat.moneyTitle}>{stat.money}</div>
        </div>
        <div className="stat-glass">
          <div className="k">
            <div className="t">Channels</div>
            <div className="b">{live ? (channels ?? 'None connected') : 'Slack · GH · Email'}</div>
          </div>
          <div className="icons"><span>#</span><span>✕</span><span>◉</span></div>
        </div>
        <div className="stat alt">
          <div className="head"><span className="k">Hours Reclaimed</span><span className="ic">⏱</span></div>
          <div className="v" title={stat.hoursTitle}>{stat.hours}<span className="unit-sm">hrs</span></div>
        </div>
      </div>

      <div className="hero-corner">{orch ? 'D.E.X.T.E.R' : 'A.N.T.H.O.N.Y'} · v0.1 · // {live ? (orch ? 'operative standing by' : 'anthony online') : 'demo data — backend offline'}</div>
      <div className="hero-marker">
        <div>OP · 24/7</div>
        <div className="enc">● Encrypted</div>
      </div>
    </div>
  )
}
