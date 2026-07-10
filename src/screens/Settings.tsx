// Settings & Connections overlay — read-only status of every backend
// system, cloud escalation keys + spend, honest "planned" integration
// stubs, the Archive teaser, and the few things a user can actually
// change (backend URL, test push). No system here is faked: everything
// with a live dot is read straight from useBackend()/api.status().
import { useEffect, useState } from 'react'
import { api, setApiUrl, API_URL, type SpendReport } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'

type ConnState = 'on' | 'off' | 'unk'

function dotClass(state: ConnState): string {
  if (state === 'on') return 'dot'
  if (state === 'off') return 'dot off'
  return 'dot unk'
}

function stateLabel(state: ConnState): string {
  if (state === 'on') return 'Connected'
  if (state === 'off') return 'Offline'
  return '—'
}

function ConnRow({ icon, name, meta, state }: { icon: string; name: string; meta?: string; state: ConnState }) {
  return (
    <div className="row">
      <div className="ic">{icon}</div>
      <div className="body">
        <div className="nm">{name}</div>
        {meta && <div className="meta">{meta}</div>}
      </div>
      <div className="conn-status">
        <span className={dotClass(state)} />
        <span>{stateLabel(state)}</span>
      </div>
    </div>
  )
}

function ProviderRow({ icon, name, ok }: { icon: string; name: string; ok: boolean | null }) {
  return (
    <div className="row">
      <div className="ic">{icon}</div>
      <div className="body"><div className="nm">{name}</div></div>
      {ok === null ? (
        <span className="badge">—</span>
      ) : ok ? (
        <span className="badge grn">Key configured</span>
      ) : (
        <span className="badge red">No API key</span>
      )}
    </div>
  )
}

interface Integration {
  icon: string
  name: string
  blurb: string
}

const INTEGRATIONS: Integration[] = [
  { icon: '#', name: 'Slack', blurb: 'Ops channel: Dexter reports + you command from anywhere' },
  { icon: '@', name: 'Gmail', blurb: 'Inbound email triage feeds the ops queue' },
  { icon: '⎇', name: 'GitHub', blurb: 'Repo events + PR review delegation' },
  { icon: '▦', name: 'Google Calendar', blurb: 'Briefings aware of your day' },
  { icon: '✈', name: 'Telegram', blurb: 'Approval gates + voice notes on the go' },
  { icon: '✦', name: 'Claude Code seat', blurb: 'Engineering executor via headless SDK' },
  { icon: '◇', name: 'Codex seat', blurb: 'Second engineering executor, CLI-driven' },
  { icon: '▸', name: 'Cursor', blurb: 'Background agents for in-editor work' },
]

export default function Settings({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { online, checked, status } = useBackend()
  const { push } = useToast()
  const [urlInput, setUrlInput] = useState(API_URL)
  const [spend, setSpend] = useState<SpendReport | null>(null)
  const [sendingTest, setSendingTest] = useState(false)

  useEffect(() => {
    if (open) setUrlInput(API_URL)
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  useEffect(() => {
    if (!open || !online) return
    let cancelled = false
    api.spend().then((s) => {
      if (!cancelled) setSpend(s)
    }).catch(() => {
      if (!cancelled) setSpend(null)
    })
    return () => { cancelled = true }
  }, [open, online])

  if (!open) return null

  const sys = (ok: boolean): ConnState => (!online ? 'unk' : ok ? 'on' : 'off')
  const backendState: ConnState = !checked ? 'unk' : online ? 'on' : 'off'

  const ollama = online ? status?.ollama : undefined
  const ollamaMeta = ollama
    ? `${ollama.model}${ollama.models.length ? ` · also: ${ollama.models.slice(0, 4).join(', ')}${ollama.models.length > 4 ? '…' : ''}` : ''}`
    : undefined

  const db = online ? status?.database : undefined
  const searx = online ? status?.searxng : undefined
  const voice = online ? status?.voice : undefined
  const browser = online ? status?.browser : undefined
  const notif = online ? status?.notifications : undefined

  const providers = online ? status?.providers : undefined
  const providerOk = (key: string): boolean | null => (providers ? Boolean(providers[key]) : null)

  const topic = notif?.topic ?? null
  const canSaveUrl = urlInput.trim() !== '' && urlInput.trim() !== API_URL

  function handleSaveUrl() {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    setApiUrl(trimmed)
  }

  async function handleTestGate() {
    if (sendingTest) return
    setSendingTest(true)
    try {
      await api.testGate()
      push({
        title: 'Test gate fired',
        body: 'Check the bell — and your phone if subscribed to the ntfy topic',
        kind: 'good',
      })
    } catch {
      push({ title: 'Could not fire test gate', body: 'Backend unreachable', kind: 'warn' })
    } finally {
      setSendingTest(false)
    }
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <aside
        className="settings-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Settings & connections"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-head">
          <div className="settings-title">Settings &amp; Connections</div>
          <button className="settings-close" aria-label="Close settings" onClick={onClose}>✕</button>
        </div>

        <div className="settings-body">
          {/* ---------- Core Systems ---------- */}
          <div className="card">
            <div className="cardhead"><span className="label">Core Systems</span></div>
            {checked && !online && (
              <p className="subnote">Backend offline — start the server to see live status.</p>
            )}
            <ConnRow icon="⌁" name="Backend API" meta={API_URL} state={backendState} />
            <ConnRow icon="◆" name="Ollama" meta={ollamaMeta} state={ollama ? sys(ollama.ok) : 'unk'} />
            <ConnRow icon="▤" name="PostgreSQL" meta={db?.url} state={db ? sys(db.ok) : 'unk'} />
            <ConnRow icon="⌕" name="SearXNG Search" meta={searx?.url} state={searx ? sys(searx.ok) : 'unk'} />
            <div className="row">
              <div className="ic">◐</div>
              <div className="body">
                <div className="nm">Voice pipeline</div>
                <div className="voice-chips">
                  <span className="chip"><span className={dotClass(voice ? sys(voice.torch) : 'unk')} />VAD / Torch</span>
                  <span className="chip"><span className={dotClass(voice ? sys(voice.stt) : 'unk')} />Whisper STT</span>
                  <span className="chip"><span className={dotClass(voice ? sys(voice.tts) : 'unk')} />Piper TTS</span>
                </div>
              </div>
            </div>
            <ConnRow icon="⧉" name="Browser automation" meta={browser ? 'Playwright driver' : undefined} state={browser ? sys(browser.playwright) : 'unk'} />
            <ConnRow
              icon="✉"
              name="Phone push · ntfy"
              meta={notif ? `${notif.topic} @ ${notif.server}` : undefined}
              state={notif ? sys(notif.configured) : 'unk'}
            />
          </div>

          {/* ---------- Cloud Escalation ---------- */}
          <div className="card">
            <div className="cardhead"><span className="label">Cloud Escalation</span></div>
            <ProviderRow icon="◈" name="Anthropic" ok={providerOk('anthropic')} />
            <ProviderRow icon="○" name="OpenAI" ok={providerOk('openai')} />
            <ProviderRow icon="»" name="Groq" ok={providerOk('groq')} />

            {online && spend && (
              <div className="set-spend">
                <div className="set-spend-row"><span>Spent today</span><b>${spend.total_today.toFixed(2)}</b></div>
                <div className="set-spend-row"><span>Budget remaining</span><b>${spend.budget_remaining.toFixed(2)}</b></div>
                {Object.entries(spend.by_provider).map(([name, amt]) => {
                  const pct = spend.total_today > 0 ? Math.min(100, (amt / spend.total_today) * 100) : 0
                  return (
                    <div className="bar" key={name}>
                      <div className="lbl"><b>{name}</b><span>${amt.toFixed(2)}</span></div>
                      <div className="track"><div className="fill" style={{ width: `${pct}%` }} /></div>
                    </div>
                  )
                })}
              </div>
            )}
            {online && !spend && <p className="subnote">Loading today's spend…</p>}
            {!online && <p className="subnote">Connect to the backend to see provider keys and today's spend.</p>}
          </div>

          {/* ---------- Integrations ---------- */}
          <div className="card">
            <div className="cardhead"><span className="label">Integrations</span></div>
            <div className="integ-grid">
              {INTEGRATIONS.map((i) => (
                <div className="integ-card" key={i.name}>
                  <div className="integ-top">
                    <span className="integ-ic">{i.icon}</span>
                    <span className="integ-nm">{i.name}</span>
                  </div>
                  <p className="integ-blurb">{i.blurb}</p>
                  <span className="badge">Planned</span>
                </div>
              ))}
            </div>
          </div>

          {/* ---------- Archive teaser ---------- */}
          <div className="card archive-card">
            <div className="cardhead">
              <span className="label">Archive</span>
              <span className="badge ylw">Phase 6 · Planned</span>
            </div>
            <div className="archive-title">Personal Intelligence Vault</div>
            <p className="subnote">
              Drop PDFs, links and notes into notebooks. Chat over your sources with citations, and generate
              two-voice audio briefings using Dexter and Shadow. Built on the same Postgres + pgvector memory
              the backend already runs — no subscription.
            </p>
          </div>

          {/* ---------- Preferences ---------- */}
          <div className="card">
            <div className="cardhead"><span className="label">Preferences</span></div>

            <div className="set-field">
              <label className="label set-label" htmlFor="set-backend-url">Backend URL</label>
              <div className="set-inline">
                <input
                  id="set-backend-url"
                  className="set-input"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="http://localhost:8000"
                  spellCheck={false}
                />
                <button className="set-btn" disabled={!canSaveUrl} onClick={handleSaveUrl}>Save &amp; reconnect</button>
              </div>
            </div>

            <div className="set-field">
              <button className="set-btn wide" disabled={!online || sendingTest} onClick={handleTestGate}>
                {sendingTest ? 'Sending…' : 'Send test notification'}
              </button>
              {!online && <p className="set-hint">Backend offline — connect to send a test push.</p>}
            </div>

            <p className="subnote">
              Phone push: install the ntfy app and subscribe to topic '{topic ?? '—'}'. Change the topic in
              server/.env — the default is public.
            </p>
          </div>
        </div>
      </aside>
    </div>
  )
}
