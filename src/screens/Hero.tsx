import type { Mode } from '../data'
import operative from '../assets/img/operative.png'
import heroOrch from '../assets/img/hero-orch.jpg'

// Desktop Briefing hero — faithful rebuild of the Shadow Protocol
// reference frame: split gradient/white bands, HUD-arc operative
// card in the middle column, stats strip pinned to the bottom.
export default function Hero({ mode }: { mode: Mode }) {
  const orch = mode === 'orch'
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
            {orch ? 'Operative Ready' : '5 Executors Live'}
          </div>

          {orch ? (
            <h1 className="hero-h1">Command<br />the <em>Shadow</em>.<br />Own the Day.</h1>
          ) : (
            <h1 className="hero-h1">The <em>Shadow</em><br />ran all<br />night.</h1>
          )}

          <p className="hero-sub">
            {orch
              ? 'Your silent operative. Delegator. Executor. Task terminator. Revenue enabler.'
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
              alt={orch ? 'Dexter · Orchestrator' : 'Dexter · Shadow operative'}
            />
            <div className="tick tl" /><div className="tick tr" />
            <div className="tick bl" /><div className="tick br" />
            <div className="idstrip"><span>ID · 0071</span><span>SEC ●●●●</span></div>
            <div className="plate">
              <div>
                <div className="sub">Operative</div>
                <div className="nm">D.E.X.T.E.R</div>
              </div>
              <div className="proto">
                {orch ? (<><div>ORCH</div><div className="red">ONLINE</div></>)
                  : (<><div>SHADOW</div><div className="red">PROTOCOL</div></>)}
              </div>
            </div>
          </div>
          <div className="uptime">
            <div className="k">{orch ? 'Uptime' : 'Executors'}</div>
            <div className="v">{orch ? '24 : 00' : '5 · LIVE'}</div>
          </div>
        </div>

        {/* ===== right column ===== */}
        <div className="hero-right">
          <div className="hero-greet">
            <div className="eyebrow2">— {orch ? 'Briefing · 06:47 Local' : 'Ops Feed · Encrypted'}</div>
            {orch ? (
              <h2>Good morning, Commander. You have <span className="hl">3 priorities</span> today,
                including <span className="hl">1 revenue op</span> at 09:00. Ready to move?</h2>
            ) : (
              <h2>Overnight run complete, Commander. <span className="hl">1,284 tasks</span> terminated,
                <span className="hl"> 2 gates</span> await your word.</h2>
            )}
            <div className="verbs">{orch ? 'Delegate · Execute · Terminate' : 'Spawn · Score · Terminate'}</div>
          </div>

          {orch ? (
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
          <div className="v">1,284<sup>↑</sup></div>
        </div>
        <div className="stat">
          <div className="head"><span className="k">{orch ? 'Revenue Enabled' : 'Burn · Tonight'}</span><span className="ic">$</span></div>
          <div className="v">{orch ? '$482K' : '$14.20'}</div>
        </div>
        <div className="stat-glass">
          <div className="k">
            <div className="t">Channels</div>
            <div className="b">Slack · GH · Email</div>
          </div>
          <div className="icons"><span>#</span><span>✕</span><span>◉</span></div>
        </div>
        <div className="stat alt">
          <div className="head"><span className="k">Hours Reclaimed</span><span className="ic">⏱</span></div>
          <div className="v">312<span className="unit-sm">hrs</span></div>
        </div>
      </div>

      <div className="hero-corner">D.E.X.T.E.R · v0.1 · // {orch ? 'operative standing by' : 'shadow protocol active'}</div>
      <div className="hero-marker">
        <div>OP · 24/7</div>
        <div className="enc">● Encrypted</div>
      </div>
    </div>
  )
}
