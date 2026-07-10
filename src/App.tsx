import { useState } from 'react'
import { TABS, type Mode } from './data'
import Hero from './screens/Hero'
import { OrchHome, Projects, Tasks, Team } from './screens/Orch'
import { ShadowOps, Swarm, Selector, Credits } from './screens/Shadow'
import Chat from './screens/Chat'

export default function App() {
  const [mode, setMode] = useState<Mode>('orch')
  const [active, setActive] = useState<Record<Mode, string>>({ orch: 'home', shadow: 'ops' })
  const tab = active[mode]
  const go = (t: string) => setActive((a) => ({ ...a, [mode]: t }))
  const isHome = tab === 'home' || tab === 'ops'

  return (
    <div className={`shell${mode === 'shadow' ? ' shadow-mode' : ''}`}>
      <div className="headband" />

      <header className="topbar">
        <div className="brand">
          <div className="orb"><i /></div>
          <div className="t">
            D.E.X.T.E.R
            <small>{mode === 'orch' ? 'Orchestrator · v1.0' : 'Shadow Protocol · v1.0'}</small>
          </div>
        </div>

        <nav className="topnav">
          {TABS[mode].map(([id, , label]) => (
            <button key={id} className={id === tab ? 'on' : ''} onClick={() => go(id)}>{label}</button>
          ))}
          <span className="live"><span className="dot-live" />Live</span>
        </nav>

        <div className="ptoggle">
          <button className={mode === 'orch' ? 'on' : ''} onClick={() => setMode('orch')}>Orch</button>
          <button className={mode === 'shadow' ? 'on' : ''} onClick={() => setMode('shadow')}>Shadow</button>
        </div>
      </header>

      <main className={`screens${isHome ? ' is-hero' : ''}`}>
        <div className="screen" key={`${mode}-${tab}`}>
          {isHome && (
            <div className="desktop-only">
              <Hero mode={mode} />
            </div>
          )}
          {mode === 'orch' ? (
            <>
              {tab === 'home' && <div className="mobile-only"><OrchHome go={go} enterShadow={() => setMode('shadow')} /></div>}
              {tab === 'projects' && <Projects />}
              {tab === 'tasks' && <Tasks />}
              {tab === 'team' && <Team />}
              {tab === 'chat' && <Chat mode="orch" />}
            </>
          ) : (
            <>
              {tab === 'ops' && <div className="mobile-only"><ShadowOps /></div>}
              {tab === 'swarm' && <Swarm />}
              {tab === 'selector' && <Selector />}
              {tab === 'credits' && <Credits />}
              {tab === 'chat' && <Chat mode="shadow" />}
            </>
          )}
        </div>
      </main>

      <nav className="tabbar">
        {TABS[mode].map(([id, glyph, label]) => (
          <button key={id} className={`tab${id === tab ? ' on' : ''}`} onClick={() => go(id)}>
            <span className="glyph">{glyph}</span>
            {label}
          </button>
        ))}
      </nav>
    </div>
  )
}
