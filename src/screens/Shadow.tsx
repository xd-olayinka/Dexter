import { RUN_LOG, GATES, SWARM, MODEL_POOL, PICKS, BURN, GUARDS } from '../data'
import operative from '../assets/img/operative.png'

export function ShadowOps() {
  return (
    <div className="content" style={{ maxWidth: 560 }}>
      <div className="eyebrow">Ops Feed · Encrypted</div>
      <h1 className="bigtitle">
        The <em>Shadow</em> ran all night. <span className="hl">5 executors</span>,{' '}
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
          <div><div className="sub">Operative</div><div className="nm">D.E.X.T.E.R</div></div>
          <div className="mode">Shadow Protocol<br />Active</div>
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
      <div className="card tint">
        <div className="cardhead"><span className="label">Pending Approval Gates · 2</span></div>
        {GATES.map((g) => (
          <div key={g.nm} className="row">
            <div className="ic">{g.ic}</div>
            <div className="body"><div className="nm">{g.nm}</div><div className="meta">{g.meta}</div></div>
            <span className={`badge ${g.badge[0]}`}>{g.badge[1]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Swarm() {
  return (
    <div className="content">
      <h1 className="bigtitle">Executor Swarm</h1>
      <p className="subnote lead">Sub-agents Shadow created. Efficiency scores decide who survives.</p>
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
      <div className="card">
        <div className="cardhead"><span className="label">Swarm Totals</span></div>
        <div className="row">
          <div className="ic">Σ</div>
          <div className="body"><div className="nm">1,284 tasks terminated tonight</div><div className="meta">avg 0.87 efficiency · $14.20 total burn</div></div>
          <span className="badge grn">Healthy</span>
        </div>
      </div>
    </div>
  )
}

export function Selector() {
  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Selector Core</h1>
      <p className="subnote lead">Scores cost × capability × latency, then picks the cheapest capable executor. Every pick is explainable.</p>
      <div className="card">
        <div className="cardhead"><span className="label">Model Pool</span><span className="badge grn">All Reachable</span></div>
        {MODEL_POOL.map(([ic, nm, tag, meta, price, speed]) => (
          <div key={nm} className="row">
            <div className="ic">{ic}</div>
            <div className="body"><div className="nm">{nm} <span className={`badge${tag === 'Default' ? ' grn' : ''}`}>{tag}</span></div><div className="meta">{meta}</div></div>
            <div className="right"><div className="top">{price}</div><div className="bot">{speed}</div></div>
          </div>
        ))}
      </div>
      <div className="card tint">
        <div className="cardhead"><span className="label">Last 3 Picks · Explained</span></div>
        {PICKS.map(([nm, meta]) => (
          <div key={nm} className="row">
            <div className="ic">→</div>
            <div className="body"><div className="nm">{nm}</div><div className="meta">{meta}</div></div>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="cardhead"><span className="label">Spawn Templates</span><button className="more">+ Force Spawn</button></div>
        <div className="row"><div className="ic">⬢</div><div className="body"><div className="nm">Scraper · Parser · Mailer</div><div className="meta">Bulk ops family, Haiku default</div></div></div>
        <div className="row"><div className="ic">⬡</div><div className="body"><div className="nm">Coder · Researcher · Voice</div><div className="meta">Skilled family, Fable default with escalation</div></div></div>
      </div>
    </div>
  )
}

export function Credits() {
  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Telemetry &amp; Burn</h1>
      <p className="subnote lead">Live spend across providers. Caps are hard, kills are automatic.</p>
      <div className="card">
        <div className="cardhead"><span className="label">July Burn · $1,928</span><button className="more">Export →</button></div>
        {BURN.map(([nm, note, pct, hot]) => (
          <div key={nm} className="bar">
            <div className="lbl"><b>{nm}</b><span>{note}</span></div>
            <div className="track"><div className={`fill${hot ? ' hot' : ''}`} style={{ width: `${pct}%` }} /></div>
          </div>
        ))}
      </div>
      <div className="card tint">
        <div className="cardhead"><span className="label">Guards</span></div>
        {GUARDS.map((g) => (
          <div key={g.nm} className="row">
            <div className="ic">{g.ic}</div>
            <div className="body"><div className="nm">{g.nm}</div><div className="meta">{g.meta}</div></div>
            <span className={`badge ${g.badge[0]}`}>{g.badge[1]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
