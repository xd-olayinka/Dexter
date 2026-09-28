import { useEffect, useRef, useState } from 'react'
import { CHAT_SEED, type Mode } from '../data'
import avShadow from '../assets/img/avatar-shadow.jpg'
import avOrch from '../assets/img/avatar-orch.jpg'
import { useBackend } from '../lib/backend'
import { ChatWs, type ChatWsFrame } from '../lib/chatws'
import { api, ApiError } from '../lib/api'
import { MicButton } from '../components/MicButton'

type Proposal = { id: string; summary: string; state: 'open' | 'done' | 'dismissed' | 'failed'; detail?: string }
type Msg = { who: 'dexter' | 'me'; text: string; img?: string; warn?: boolean; streaming?: boolean; note?: boolean; proposal?: Proposal }

const LIVE_INTRO: Record<Mode, string> = {
  orch: "Live. Tell me what you need — or tell me how you like things done (\"remember…\", \"always…\", \"from now on…\") and I'll keep to it.",
  shadow: 'Live. Executors, gates and spend are real from here. Give me a task to run, or use the actions below.',
}

const PENDING_KEY = 'dexter.pendingMessage'

/** Replies are plain text, but models still write **bold** — render that, nothing else. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*\n]+\*\*)/g)
  return <>{parts.map((p, i) => (p.startsWith('**') && p.endsWith('**') && p.length > 4 ? <b key={i}>{p.slice(2, -2)}</b> : p))}</>
}

export default function Chat({ mode }: { mode: Mode }) {
  const seed = CHAT_SEED[mode]
  const [msgs, setMsgs] = useState<Msg[]>([
    { who: 'dexter', text: seed.m1 },
    { who: 'me', text: seed.me },
    { who: 'dexter', text: seed.m2 },
  ])
  const [held, setHeld] = useState(false)
  const [busy, setBusy] = useState(false)
  const touchedRef = useRef(false)
  const [draft, setDraft] = useState('')
  const [wsOpen, setWsOpen] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const avatar = mode === 'orch' ? avOrch : avShadow
  const { online, status } = useBackend()

  const wsRef = useRef<ChatWs | null>(null)
  const modeRef = useRef(mode)
  modeRef.current = mode
  const mountedRef = useRef(true)
  useEffect(() => () => { mountedRef.current = false }, [])

  // reseed when the protocol flips — each mask has its own thread voice. Live: no scripted
  // conversation, just an honest opener; the canned exchange is for demo mode only.
  useEffect(() => {
    touchedRef.current = false
  }, [mode])
  useEffect(() => {
    if (touchedRef.current) return
    setMsgs(online
      ? [{ who: 'dexter', text: LIVE_INTRO[mode] }]
      : [
          { who: 'dexter', text: seed.m1 },
          { who: 'me', text: seed.me },
          { who: 'dexter', text: seed.m2 },
        ])
  }, [mode, online]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!online) return
    api.hold().then((h) => setHeld(h.on)).catch(() => {})
  }, [online])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight })
  }, [msgs])

  // live connection management — only while the backend is reachable;
  // the client itself handles reconnect-with-backoff on unexpected drops.
  useEffect(() => {
    if (!online) {
      setWsOpen(false)
      return
    }
    let cancelled = false

    function handleFrame(frame: ChatWsFrame) {
      if (cancelled || !mountedRef.current) return
      if (frame.type === 'chunk') {
        setMsgs((m) => {
          const last = m[m.length - 1]
          if (last && last.who === 'dexter' && last.streaming) {
            // a status line ("Checking Prometheus…") is replaced by the reply, not appended to
            return [...m.slice(0, -1), last.note ? { who: 'dexter', text: frame.content, streaming: true } : { ...last, text: last.text + frame.content }]
          }
          return [...m, { who: 'dexter', text: frame.content, streaming: true }]
        })
      } else if (frame.type === 'done') {
        setMsgs((m) => {
          const last = m[m.length - 1]
          const finalMsg: Msg = { who: 'dexter', text: frame.message.content }
          // the reply may be followed by proposal cards; replace the streaming bubble wherever it is
          const i = m.findIndex((x) => x.who === 'dexter' && x.streaming)
          if (i >= 0) return [...m.slice(0, i), finalMsg, ...m.slice(i + 1)]
          if (last && last.who === 'dexter' && last.streaming) return [...m.slice(0, -1), finalMsg]
          return [...m, finalMsg]
        })
        setStreaming(false)
      } else if (frame.type === 'status') {
        // "Checking Prometheus…" while tools run — shown in the pending reply bubble
        setMsgs((m) => {
          const last = m[m.length - 1]
          if (last && last.who === 'dexter' && last.streaming && !last.text) return [...m.slice(0, -1), { ...last, note: true, text: frame.content }]
          if (last && last.who === 'dexter' && last.streaming && last.note) return [...m.slice(0, -1), { ...last, text: frame.content }]
          return m
        })
      } else if (frame.type === 'proposal') {
        const p = frame.proposal
        setMsgs((m) => [...m, { who: 'dexter', text: p.summary, proposal: { id: p.id, summary: p.summary, state: 'open' } }])
      } else if (frame.type === 'remembered') {
        setMsgs((m) => {
          const last = m[m.length - 1]
          const note: Msg = { who: 'dexter', text: frame.content, note: true }
          // keep the streaming reply last
          if (last && last.who === 'dexter' && last.streaming) return [...m.slice(0, -1), note, last]
          return [...m, note]
        })
      } else if (frame.type === 'error') {
        setMsgs((m) => {
          const last = m[m.length - 1]
          const errMsg: Msg = { who: 'dexter', text: frame.content, warn: true }
          if (last && last.who === 'dexter' && last.streaming) return [...m.slice(0, -1), errMsg]
          return [...m, errMsg]
        })
        setStreaming(false)
      }
    }

    const client = new ChatWs({
      onOpen: () => { if (!cancelled) setWsOpen(true) },
      onClose: () => { if (!cancelled) setWsOpen(false) },
      onFrame: handleFrame,
    })
    wsRef.current = client
    client.connect()

    return () => {
      cancelled = true
      client.close()
      if (wsRef.current === client) wsRef.current = null
      setWsOpen(false)
    }
  }, [online])

  // Home's quick-command bar drops a message here before routing into chat.
  useEffect(() => {
    const pending = sessionStorage.getItem(PENDING_KEY)
    if (pending) {
      sessionStorage.removeItem(PENDING_KEY)
      send(pending)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const say = (text: string, warn = false) => setMsgs((m) => [...m, { who: 'dexter', text, warn }])

  const setProposal = (id: string, patch: Partial<Proposal>) =>
    setMsgs((m) => m.map((x) => (x.proposal?.id === id ? { ...x, proposal: { ...x.proposal, ...patch } } : x)))

  async function confirmProposal(p: Proposal) {
    setProposal(p.id, { state: 'done', detail: 'Working…' })
    try {
      const r = await api.confirmAction(p.id)
      // an approval-required Prometheus connection holds the change in its Approvals queue
      const held = /"proposed":\s*true/.test(r.result)
      setProposal(p.id, { state: 'done', detail: held ? 'Sent to Prometheus Approvals — it applies once approved there' : 'Done in Prometheus' })
    } catch (err) {
      setProposal(p.id, { state: 'failed', detail: err instanceof ApiError ? err.message : 'Failed' })
    }
  }

  async function dismissProposal(p: Proposal) {
    setProposal(p.id, { state: 'dismissed', detail: 'Dismissed' })
    api.dismissAction(p.id).catch(() => {})
  }

  /** Live quick actions — each does the real thing through the API, then reports back. */
  async function act(label: string, fn: () => Promise<string>) {
    if (busy) return
    touchedRef.current = true
    setBusy(true)
    setMsgs((m) => [...m, { who: 'me', text: label }])
    try {
      say(await fn())
    } catch (err) {
      say(err instanceof ApiError ? err.message : 'That action failed — is the backend still up?', true)
    } finally {
      setBusy(false)
    }
  }

  const lastAsk = () => [...msgs].reverse().find((m) => m.who === 'me' && !m.img)?.text

  const approveAll = () => act('✓ Approve all gates', async () => {
    const pending = (await api.gates()).filter((g) => g.status === 'pending')
    if (!pending.length) return 'Nothing is waiting on you.'
    await Promise.all(pending.map((g) => api.approveGate(g.task_id)))
    return `Approved ${pending.length} gate${pending.length === 1 ? '' : 's'}: ${pending.map((g) => g.task_title || g.task_id).join(', ')}.`
  })
  const approveOldest = () => act('✓ Approve gate', async () => {
    const pending = (await api.gates()).filter((g) => g.status === 'pending').sort((a, b) => a.created_at.localeCompare(b.created_at))
    if (!pending.length) return 'No gates pending.'
    await api.approveGate(pending[0].task_id)
    return `Approved "${pending[0].task_title || pending[0].task_id}" — ${pending[0].reason}. ${pending.length - 1} still waiting.`
  })
  const delegate = (label: string) => act(label, async () => {
    const text = draft.trim() || lastAsk()
    if (!text) return 'Type the task first, then tap this — I\'ll hand it to an executor.'
    setDraft('')
    const t = await api.delegate(text.slice(0, 120), text)
    return `Delegated to Anthony: "${t.title}" on ${t.metadata?.model_route ?? 'the default brain'}, capped at $${(t.budget_cap ?? 0).toFixed(2)}.${t.metadata?.hold ? ' Hold is on, so it is waiting at a gate.' : ''}`
  })
  const latestResult = () => act('View latest result', async () => {
    const done = (await api.tasks()).filter((t) => t.status === 'done' && t.result).sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? ''))
    if (!done.length) return 'No finished work yet.'
    const t = done[0]
    return `"${t.title}" — finished, $${t.spend.toFixed(4)}:\n\n${t.result}`
  })
  const toggleHold = () => act(held ? 'Release hold' : 'Hold', async () => {
    const r = await api.setHold(!held)
    setHeld(r.on)
    return r.on
      ? 'Hold is on. Anything delegated from now waits at a gate until you approve it; running work continues.'
      : 'Hold released. New work runs straight away again (tasks already parked still need your approval).'
  })
  const killNewest = () => act('Kill executor', async () => {
    const running = (await api.tasks()).filter((t) => t.status === 'running' || t.status === 'queued').sort((a, b) => b.created_at.localeCompare(a.created_at))
    if (!running.length) return 'No executor is running.'
    await api.killTask(running[0].id)
    return `Killed "${running[0].title}" at $${running[0].spend.toFixed(4)}.`
  })
  const raiseCap = () => act('Raise cap', async () => {
    const cfg = await api.guardConfig()
    const next = Math.round(cfg.daily_budget * 1.25 * 100) / 100
    await api.patchGuardConfig({ daily_budget: next })
    return `Daily cap raised from $${cfg.daily_budget.toFixed(2)} to $${next.toFixed(2)} (+25%).`
  })

  const livePills: Array<[string, () => void]> = mode === 'orch'
    ? [['✓ Approve all', approveAll], ['Delegate to Anthony', () => delegate('Delegate to Anthony')], ['Latest result', latestResult], [held ? 'Release hold' : 'Hold', toggleHold]]
    : [['✓ Approve gate', approveOldest], ['Kill executor', killNewest], ['Force spawn', () => delegate('Force spawn')], ['Raise cap', raiseCap], [held ? 'Release hold' : 'Hold', toggleHold]]

  function send(text?: string) {
    const v = (text ?? draft).trim()
    if (!v || streaming) return
    touchedRef.current = true
    setDraft('')
    setMsgs((m) => [...m, { who: 'me', text: v }])

    const client = wsRef.current
    if (client?.isOpen) {
      setStreaming(true)
      setMsgs((m) => [...m, { who: 'dexter', text: '', streaming: true }])
      const sent = client.send(v, modeRef.current)
      if (sent) return
      setStreaming(false)
      setMsgs((m) => (m[m.length - 1]?.streaming ? m.slice(0, -1) : m))
    }

    // demo mode — backend offline or WS not open, keep the canned reply alive
    setTimeout(() => {
      if (!mountedRef.current) return
      setMsgs((m) => [...m, {
        who: 'dexter',
        text: modeRef.current === 'orch'
          ? 'Understood. Routing that now — I will report back with results and cost.'
          : 'Acknowledged. Executor assigned, budget capped. Log will show the receipt.',
      }])
    }, 500)
  }

  // Build Plan 2.5: images stay a local-only preview (no vision model wired into the
  // Brain yet); a document (pdf/txt/md/csv) goes to /api/files/upload for real —
  // extracted, embedded, and folded into chat context via memory recall (chat.py).
  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return

    if (f.type.startsWith('image/')) {
      const url = URL.createObjectURL(f)
      setMsgs((m) => [
        ...m,
        { who: 'me', text: `Uploaded: ${f.name}`, img: url },
        { who: 'dexter', text: 'Image received and attached to the active thread — Dexter can’t see images yet, so it won’t be able to describe this one.' },
      ])
      return
    }

    if (!online) {
      setMsgs((m) => [...m, { who: 'me', text: `Attach: ${f.name}` }, { who: 'dexter', text: 'Backend offline — connect to ingest documents.', warn: true }])
      return
    }

    setMsgs((m) => [...m, { who: 'me', text: `Ingesting: ${f.name}…` }])
    try {
      const doc = await api.uploadFile(f)
      setMsgs((m) => [...m, { who: 'dexter', text: `Ingested "${doc.title}" (${doc.char_count.toLocaleString()} chars) into memory. Ask me about it any time.` }])
    } catch (err) {
      setMsgs((m) => [...m, { who: 'dexter', text: err instanceof ApiError ? err.message : 'Could not ingest that file.', warn: true }])
    }
  }

  const modelName = status?.brain?.ready ? status.brain.model : status?.ollama.model
  const chipLabel = wsOpen ? (modelName ? `Live · ${modelName}` : 'Live') : 'Demo mode — backend offline'

  return (
    <div className="chatwrap">
      <div className="chip" style={{ margin: '0 0 12px', alignSelf: 'flex-start' }}>
        <span className={`dot${wsOpen ? '' : ' warn'}`} />
        {chipLabel}
      </div>
      <div className="chatlog" ref={logRef}>
        {msgs.map((m, i) =>
          m.who === 'me' ? (
            <div key={i} className="msg me">
              <div className="bub">
                {m.img && <img src={m.img} alt="" style={{ maxWidth: 180, borderRadius: 10, display: 'block', marginBottom: 6 }} />}
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="msg">
              <div className="av"><img src={avatar} alt="Dexter" /></div>
              <div className="bub" style={m.warn ? { borderColor: 'var(--warn)', color: 'var(--warn)' } : m.note ? { opacity: 0.75, fontSize: '0.9em' } : undefined}>
                <span className="tag">{m.proposal ? 'Proposed change · needs your OK' : m.note ? (m.streaming ? 'Working' : 'Standing preference') : `Dexter · ${seed.voice}`}</span>
                <Rich text={m.text} />
                {m.proposal && (
                  <span style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center' }}>
                    {m.proposal.state === 'open' ? (
                      <>
                        <button className="p" onClick={() => confirmProposal(m.proposal!)}>✓ Confirm</button>
                        <button className="p" onClick={() => dismissProposal(m.proposal!)}>Dismiss</button>
                      </>
                    ) : (
                      <span style={{ opacity: 0.75, color: m.proposal.state === 'failed' ? 'var(--warn)' : undefined }}>{m.proposal.detail}</span>
                    )}
                  </span>
                )}
                {m.streaming && '▍'}
              </div>
            </div>
          ),
        )}
      </div>
      <div className="pillrow">
        {online
          ? livePills.map(([label, fn]) => (
              <button key={label} className={`p${label === 'Release hold' ? ' on' : ''}`} disabled={busy} onClick={fn}>{label}</button>
            ))
          : seed.pills.map((p) => <button key={p} className="p" onClick={() => send(p)}>{p}</button>)}
      </div>
      <div className="chatinput">
        <label className="attach">
          ＋<input type="file" accept="image/*,.pdf,.txt,.md,.csv" hidden onChange={upload} />
        </label>
        <MicButton
          protocol={mode}
          onTranscript={(text) => setDraft((d) => (d ? `${d} ${text}` : text))}
          onError={(msg) => setMsgs((m) => [...m, { who: 'dexter', text: msg, warn: true }])}
        />
        <input
          type="text"
          placeholder="Command Dexter..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send() }}
        />
        <button className="send" onClick={() => send()} disabled={streaming} style={streaming ? { opacity: 0.5, cursor: 'default' } : undefined}>↑</button>
      </div>
    </div>
  )
}
