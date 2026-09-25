// Settings & Connections overlay — read-only status of every backend
// system, cloud escalation keys + spend, honest "planned" integration
// stubs, the Archive teaser, and the few things a user can actually
// change (backend URL, test push). No system here is faked: everything
// with a live dot is read straight from useBackend()/api.status().
import { useEffect, useState } from 'react'
import { api, ApiError, setApiUrl, API_URL, type ArchiveAnswer, type BriefingScript, type DocumentRecord, type GuardConfig, type Notebook, type SpendReport } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Backend unreachable'
}

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

// ---------- Guardrails (Build Plan 2.7 · P6) ----------

function NumField({ label, value, onCommit, step = 0.5, prefix = '' }: {
  label: string; value: number; onCommit: (v: number) => void; step?: number; prefix?: string
}) {
  const [draft, setDraft] = useState(String(value))
  useEffect(() => setDraft(String(value)), [value])
  return (
    <div className="set-field">
      <label className="label set-label">{label}</label>
      <div className="set-inline">
        <input
          className="set-input"
          type="number"
          step={step}
          min={0}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            const n = parseFloat(draft)
            if (!Number.isNaN(n) && n !== value) onCommit(n)
            else setDraft(String(value))
          }}
        />
        {prefix && <span className="subnote" style={{ alignSelf: 'center' }}>{prefix}</span>}
      </div>
    </div>
  )
}

function GuardsCard({ online }: { online: boolean }) {
  const toast = useToast()
  const [config, setConfig] = useState<GuardConfig | null>(null)
  const [ruleName, setRuleName] = useState('')
  const [ruleCap, setRuleCap] = useState('')

  async function load() {
    try {
      setConfig(await api.guardConfig())
    } catch {
      setConfig(null)
    }
  }

  useEffect(() => { if (online) load(); else setConfig(null) }, [online])

  async function patch(update: Partial<Omit<GuardConfig, 'custom_rules'>>) {
    try {
      setConfig(await api.patchGuardConfig(update))
      toast.push({ title: 'Guardrails updated', kind: 'good' })
    } catch (e) {
      toast.push({ title: 'Could not update guardrails', body: errMsg(e), kind: 'warn' })
    }
  }

  async function addRule() {
    const name = ruleName.trim()
    const cap = parseFloat(ruleCap)
    if (!name || Number.isNaN(cap)) return
    try {
      setConfig(await api.addGuardRule({ name, max_spend: cap }))
      setRuleName('')
      setRuleCap('')
    } catch (e) {
      toast.push({ title: 'Could not add rule', body: errMsg(e), kind: 'warn' })
    }
  }

  async function removeRule(id: string) {
    try {
      setConfig(await api.removeGuardRule(id))
    } catch (e) {
      toast.push({ title: 'Could not remove rule', body: errMsg(e), kind: 'warn' })
    }
  }

  return (
    <div className="card">
      <div className="cardhead"><span className="label">Guardrails</span></div>
      {!online && <p className="subnote">Connect to the backend to view and edit spend caps.</p>}
      {online && !config && <p className="subnote">Loading guardrails…</p>}
      {config && (
        <>
          <NumField label="Daily budget ($)" value={config.daily_budget} step={1} onCommit={(v) => patch({ daily_budget: v })} />
          <NumField label="Per-task default ($)" value={config.per_task_budget_default} step={0.1} onCommit={(v) => patch({ per_task_budget_default: v })} />
          <NumField label="High-cost multiplier (×)" value={config.high_cost_multiplier} step={0.5} onCommit={(v) => patch({ high_cost_multiplier: v })} />
          <NumField label="Long-running limit (minutes)" value={config.long_running_minutes} step={5} onCommit={(v) => patch({ long_running_minutes: v })} />
          <NumField label="Monthly budget ($)" value={config.monthly_budget} step={5} onCommit={(v) => patch({ monthly_budget: v })} />
          <NumField label="Per-agent daily cap ($, 0 = off)" value={config.agent_daily_cap ?? 0} step={0.5} onCommit={(v) => patch({ agent_daily_cap: v > 0 ? v : null })} />
          <NumField label="Burn-rate alert ($/hour, 0 = off)" value={config.burn_rate_alert_per_hour ?? 0} step={0.5} onCommit={(v) => patch({ burn_rate_alert_per_hour: v > 0 ? v : null })} />
          <div className="cardhead" style={{ marginTop: 8 }}><span className="label" style={{ fontSize: 12 }}>Provider monthly caps</span></div>
          <p className="subnote">The Selector stops routing to a provider once its cap is reached; a running task on it is stopped.</p>
          {['anthropic', 'openai', 'deepseek', 'groq'].map((prov) => (
            <NumField
              key={prov}
              label={`${prov} ($/month, 0 = no cap)`}
              value={config.provider_monthly_caps[prov] ?? 0}
              step={5}
              onCommit={(v) => {
                const caps = { ...config.provider_monthly_caps }
                if (v > 0) caps[prov] = v
                else delete caps[prov]
                patch({ provider_monthly_caps: caps })
              }}
            />
          ))}

          <div className="cardhead" style={{ marginTop: 8 }}><span className="label" style={{ fontSize: 12 }}>Custom rules</span></div>
          {config.custom_rules.length === 0 && <p className="subnote">No custom rules yet.</p>}
          {config.custom_rules.map((r) => (
            <div key={r.id} className="row">
              <div className="body"><div className="nm">{r.name}</div><div className="meta">caps at ${r.max_spend?.toFixed(2) ?? '—'}</div></div>
              <button className="set-btn" onClick={() => removeRule(r.id)}>Remove</button>
            </div>
          ))}
          <div className="set-field">
            <div className="set-inline">
              <input className="set-input" placeholder="Rule name" value={ruleName} onChange={(e) => setRuleName(e.target.value)} />
              <input className="set-input" placeholder="Max $" type="number" step={0.1} style={{ maxWidth: 90 }} value={ruleCap} onChange={(e) => setRuleCap(e.target.value)} />
              <button className="set-btn" disabled={!ruleName.trim() || !ruleCap} onClick={addRule}>Add rule</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ---------- Ingested documents (Build Plan 2.5 · P5) ----------

function DocumentsCard({ online }: { online: boolean }) {
  const toast = useToast()
  const [docs, setDocs] = useState<DocumentRecord[] | null>(null)
  const [url, setUrl] = useState('')
  const [ingesting, setIngesting] = useState(false)

  async function load() {
    try {
      setDocs(await api.files())
    } catch {
      setDocs(null)
    }
  }

  useEffect(() => { if (online) load(); else setDocs(null) }, [online])

  async function ingest() {
    const v = url.trim()
    if (!v || ingesting) return
    setIngesting(true)
    try {
      await api.ingestUrl(v)
      setUrl('')
      load()
      toast.push({ title: 'URL ingested', kind: 'good' })
    } catch (e) {
      toast.push({ title: 'Could not ingest URL', body: errMsg(e), kind: 'warn' })
    } finally {
      setIngesting(false)
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteFile(id)
      load()
    } catch (e) {
      toast.push({ title: 'Could not delete', body: errMsg(e), kind: 'warn' })
    }
  }

  return (
    <div className="card">
      <div className="cardhead"><span className="label">Ingested Documents{docs ? ` · ${docs.length}` : ''}</span></div>
      <p className="subnote">Uploaded from Chat's attach button, or added here by URL. Feeds Dexter's memory recall.</p>
      {online && (
        <div className="set-field">
          <div className="set-inline">
            <input className="set-input" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') ingest() }} />
            <button className="set-btn" disabled={!url.trim() || ingesting} onClick={ingest}>{ingesting ? 'Ingesting…' : 'Ingest URL'}</button>
          </div>
        </div>
      )}
      {!online && <p className="subnote">Connect to the backend to see and manage ingested documents.</p>}
      {online && docs?.length === 0 && <p className="subnote">Nothing ingested yet.</p>}
      {docs?.map((d) => (
        <div key={d.id} className="row">
          <div className="ic">{d.source === 'url' ? '⎘' : '▤'}</div>
          <div className="body"><div className="nm">{d.title}</div><div className="meta">{d.char_count.toLocaleString()} chars · {d.origin}</div></div>
          <button className="set-btn" onClick={() => remove(d.id)}>Delete</button>
        </div>
      ))}
    </div>
  )
}

// ---------- Archive (Phase 6 · v1) ----------

function ArchiveCard({ online }: { online: boolean }) {
  const toast = useToast()
  const [notebooks, setNotebooks] = useState<Notebook[] | null>(null)
  const [title, setTitle] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [nbDocs, setNbDocs] = useState<Array<{ id: string; title: string }>>([])
  const [allDocs, setAllDocs] = useState<DocumentRecord[]>([])
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<ArchiveAnswer | null>(null)
  const [script, setScript] = useState<BriefingScript | null>(null)
  const [busy, setBusy] = useState<'' | 'ask' | 'brief'>('')

  async function load() {
    try {
      setNotebooks(await api.notebooks())
      setAllDocs(await api.files())
    } catch {
      setNotebooks(null)
    }
  }
  useEffect(() => { if (online) load(); else setNotebooks(null) }, [online])

  async function open(id: string) {
    setOpenId(id === openId ? null : id)
    setAnswer(null)
    setScript(null)
    if (id !== openId) setNbDocs(await api.notebookDocuments(id).catch(() => []))
  }

  async function create() {
    if (!title.trim()) return
    try {
      await api.createNotebook(title.trim())
      setTitle('')
      load()
    } catch (e) {
      toast.push({ title: 'Could not create notebook', body: errMsg(e), kind: 'warn' })
    }
  }

  async function add(docId: string) {
    if (!openId || !docId) return
    await api.addToNotebook(openId, docId).catch((e) => toast.push({ title: 'Could not add', body: errMsg(e), kind: 'warn' }))
    setNbDocs(await api.notebookDocuments(openId).catch(() => []))
    load()
  }

  async function ask() {
    if (!openId || !question.trim() || busy) return
    setBusy('ask')
    try {
      setAnswer(await api.askNotebook(openId, question.trim()))
    } catch (e) {
      toast.push({ title: 'Could not answer', body: errMsg(e), kind: 'warn' })
    } finally {
      setBusy('')
    }
  }

  async function brief() {
    if (!openId || busy) return
    setBusy('brief')
    try {
      setScript(await api.notebookBriefing(openId, question.trim()))
    } catch (e) {
      toast.push({ title: 'Could not build briefing', body: errMsg(e), kind: 'warn' })
    } finally {
      setBusy('')
    }
  }

  const inNotebook = new Set(nbDocs.map((d) => d.id))

  return (
    <div className="card">
      <div className="cardhead"><span className="label">Archive · Notebooks{notebooks ? ` · ${notebooks.length}` : ''}</span></div>
      <p className="subnote">Group ingested documents into notebooks, ask questions answered only from them (with citations), or get a two-voice Dexter + Anthony audio briefing.</p>
      {!online && <p className="subnote">Connect to the backend to use the Archive.</p>}
      {online && (
        <div className="set-field">
          <div className="set-inline">
            <input className="set-input" placeholder="New notebook title" value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') create() }} />
            <button className="set-btn" disabled={!title.trim()} onClick={create}>Create</button>
          </div>
        </div>
      )}
      {notebooks?.map((nb) => (
        <div key={nb.id}>
          <div className="row">
            <div className="ic">▤</div>
            <div className="body"><div className="nm">{nb.title}</div><div className="meta">{nb.document_count} document(s)</div></div>
            <button className="set-btn" onClick={() => open(nb.id)}>{openId === nb.id ? 'Close' : 'Open'}</button>
          </div>
          {openId === nb.id && (
            <div style={{ paddingLeft: 12 }}>
              {nbDocs.map((d) => (
                <div key={d.id} className="row">
                  <div className="body"><div className="meta">{d.title}</div></div>
                  <button className="set-btn" onClick={async () => { await api.removeFromNotebook(nb.id, d.id).catch(() => {}); setNbDocs(await api.notebookDocuments(nb.id).catch(() => [])); load() }}>Remove</button>
                </div>
              ))}
              <div className="set-field">
                <select className="set-input" value="" onChange={(e) => add(e.target.value)}>
                  <option value="">+ Add an ingested document…</option>
                  {allDocs.filter((d) => !inNotebook.has(d.id)).map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
                </select>
              </div>
              <div className="set-field">
                <div className="set-inline">
                  <input className="set-input" placeholder="Ask this notebook… (or a focus for the briefing)" value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') ask() }} />
                  <button className="set-btn" disabled={!question.trim() || !!busy} onClick={ask}>{busy === 'ask' ? 'Reading…' : 'Ask'}</button>
                  <button className="set-btn" disabled={!!busy || nbDocs.length === 0} onClick={brief}>{busy === 'brief' ? 'Writing…' : 'Audio briefing'}</button>
                </div>
              </div>
              {answer && (
                <div className="row" style={{ display: 'block' }}>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</p>
                  {answer.citations.map((c) => (
                    <p key={c.n} className="subnote">[{c.n}] {c.title} — “{c.excerpt.slice(0, 160)}{c.excerpt.length > 160 ? '…' : ''}”</p>
                  ))}
                </div>
              )}
              {script && (
                <div className="row" style={{ display: 'block' }}>
                  {script.audio_wav_base64
                    ? <audio controls src={`data:audio/wav;base64,${script.audio_wav_base64}`} style={{ width: '100%' }} />
                    : <p className="subnote">Voice isn't installed (piper-tts) — here's the script.</p>}
                  {script.script.map((l, i) => <p key={i}><b>{l.speaker === 'DEXTER' ? 'Dexter' : 'Anthony'}:</b> {l.text}</p>)}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
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
  const { requireAuth, me: identity, businesses, logout, switchBusiness } = useAuth()
  const [switching, setSwitching] = useState(false)
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

  const prometheus = online ? status?.prometheus : undefined
  const prometheusState: ConnState = !prometheus ? 'unk' : !prometheus.configured ? 'off' : sys(prometheus.connected)

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
            <ConnRow
              icon="◉"
              name="Intelligence · Brain"
              meta={online && status?.brain ? `${status.brain.provider} · ${status.brain.model}` : undefined}
              state={online && status?.brain ? (status.brain.ready ? 'on' : 'off') : 'unk'}
            />
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
            <ConnRow
              icon="◭"
              name="Prometheus · PM"
              meta={prometheus?.configured ? prometheus.url ?? undefined : 'Set DEXTER_PROMETHEUS_MCP_URL / _TOKEN in server/.env'}
              state={prometheusState}
            />
          </div>

          {/* ---------- Cloud Escalation ---------- */}
          <div className="card">
            <div className="cardhead"><span className="label">Cloud Escalation</span></div>
            <ProviderRow icon="◎" name="DeepSeek" ok={providerOk('deepseek')} />
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

          <GuardsCard online={online} />
          <DocumentsCard online={online} />
          <ArchiveCard online={online} />

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
              two-voice audio briefings using Dexter and Anthony. Built on the same Postgres + pgvector memory
              the backend already runs — no subscription.
            </p>
          </div>

          {/* ---------- Account (Phase 4 · only meaningful once auth is on) ---------- */}
          {requireAuth && identity && (
            <div className="card">
              <div className="cardhead"><span className="label">Account</span></div>
              <div className="row">
                <div className="body">
                  <div className="nm">{identity.user.name || identity.user.email} <span className="badge">{identity.role}</span></div>
                  <div className="meta">{identity.user.email} · {identity.business_name}</div>
                </div>
                <button className="set-btn" onClick={logout}>Sign out</button>
              </div>
              {businesses.length > 1 && (
                <div className="set-field">
                  <label className="label set-label" htmlFor="set-business-switch">Business</label>
                  <select
                    id="set-business-switch"
                    className="set-input"
                    value={identity.business_id}
                    disabled={switching}
                    onChange={async (e) => {
                      setSwitching(true)
                      try {
                        await switchBusiness(e.target.value)
                        push({ title: 'Switched business', kind: 'good' })
                      } catch (err) {
                        push({ title: 'Could not switch', body: errMsg(err), kind: 'warn' })
                      } finally {
                        setSwitching(false)
                      }
                    }}
                  >
                    {businesses.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.role})</option>)}
                  </select>
                  <p className="subnote">Everything below — Team, Dependency Map, Projects, Tasks, Agents — reflects whichever business is selected.</p>
                </div>
              )}
            </div>
          )}

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
