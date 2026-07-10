import { useState } from 'react'
import { PROJECTS, TASKS_TODAY, TASKS_UPCOMING, TEAM, LOAD } from '../data'
import heroOrch from '../assets/img/hero-orch.jpg'
import { api } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'

export function OrchHome({ go, enterShadow }: { go: (tab: string) => void; enterShadow: () => void }) {
  const { online } = useBackend()
  const toast = useToast()
  const [cmd, setCmd] = useState('')

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
      toast.push({ title: 'Delegated to Shadow', body: text, kind: 'good' })
      setCmd('')
    } catch {
      toast.push({ title: 'Delegate failed', body: 'Shadow did not respond', kind: 'warn' })
    }
  }

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
          <button className="send" aria-label="Ask" onClick={ask}>↑</button>
        </div>
        <div className="pillrow" style={{ paddingTop: 8 }}>
          <button className="p" onClick={delegate}>⬢ Delegate</button>
        </div>
      </div>
      <div className="eyebrow">Briefing · 06:47 Local</div>
      <h1 className="bigtitle">
        Good morning, <em>Commander</em>. <span className="hl">3 priorities</span>,{' '}
        <span className="hl">1 revenue op</span> at 09:00.
      </h1>
      <div className="chiprow">
        <div className="chip"><span className="dot" />4 projects on track</div>
        <div className="chip"><span className="dot warn" />2 tasks blocked</div>
        <div className="chip">Team 6 / 6 in</div>
      </div>
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
        <div className="row"><div className="ic">▤</div><div className="body"><div className="nm">Q3 pipeline audit <span className="badge grn">62%</span></div><div className="meta">Delegated to Shadow, Lena reviewing output</div></div></div>
        <div className="row"><div className="ic">✎</div><div className="body"><div className="nm">Landing page copy <span className="badge ylw">Blocked</span></div><div className="meta">Waiting on brand assets from Rina</div></div></div>
      </div>
      <div className="card dark">
        <div className="cardhead"><span className="label">Shadow Report · Overnight</span><button className="more" style={{ color: '#F5C063' }} onClick={enterShadow}>Enter →</button></div>
        <div className="row"><div className="ic">⬢</div><div className="body"><div className="nm" style={{ color: '#FFF6E8' }}>5 executors ran, 1 guard trip</div><div className="meta">1,284 tasks total · zero escalations · $14.20 burned</div></div></div>
      </div>
    </div>
  )
}

export function Projects() {
  return (
    <div className="content">
      <h1 className="bigtitle">Projects</h1>
      <p className="subnote lead">Every project ties tasks, team members, and delegated agents into one thread.</p>
      <div className="chiprow">
        <div className="chip"><span className="dot" />Ongoing 4</div>
        <div className="chip">Done 12</div>
        <div className="chip">+ New</div>
      </div>
      <div className="grid-2">
        {PROJECTS.map((p) => (
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
    </div>
  )
}

type TaskItem = { nm: string; meta: string; tag: [string, string] | null }

function TaskRow({ t }: { t: TaskItem }) {
  const [done, setDone] = useState(false)
  const [delegated, setDelegated] = useState(t.tag?.[0] === 'sent')
  return (
    <div className={`task${done ? ' done' : ''}`}>
      <div className="chk" onClick={() => setDone(!done)}>✓</div>
      <div className="body"><div className="nm">{t.nm}</div><div className="meta">{t.meta}</div></div>
      {t.tag && (t.tag[0].startsWith('badge')
        ? <span className={t.tag[0]}>{t.tag[1]}</span>
        : <button className={`del${delegated ? ' sent' : ''}`} onClick={() => setDelegated(true)}>
            {delegated ? '⬢ Shadow' : t.tag[1]}
          </button>)}
    </div>
  )
}

export function Tasks() {
  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Tasks</h1>
      <p className="subnote lead">Assign to a person, or hand it to Shadow and Dexter picks the executor.</p>
      <div className="card">
        <div className="cardhead"><span className="label">Today · 5</span><button className="more">+ Add</button></div>
        {TASKS_TODAY.map((t) => <TaskRow key={t.nm} t={t as TaskItem} />)}
      </div>
      <div className="card tint">
        <div className="cardhead"><span className="label">Upcoming · 3</span></div>
        {TASKS_UPCOMING.map((t) => <TaskRow key={t.nm} t={t as TaskItem} />)}
      </div>
    </div>
  )
}

export function Team() {
  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Team</h1>
      <p className="subnote lead">Six humans, their roles, load, and what each owns right now.</p>
      <div className="card">
        <div className="cardhead"><span className="label">Members · 6</span><button className="more">+ Invite</button></div>
        {TEAM.map(([ini, nm, role, meta, status, cls]) => (
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
      <div className="card tint">
        <div className="cardhead"><span className="label">Load Balance</span><button className="more">Rebalance →</button></div>
        {LOAD.map(([nm, pct, hot]) => (
          <div key={nm} className="bar">
            <div className="lbl"><b>{nm}</b><span>{pct}%</span></div>
            <div className="track"><div className={`fill${hot ? ' hot' : ''}`} style={{ width: `${pct}%` }} /></div>
          </div>
        ))}
      </div>
    </div>
  )
}
