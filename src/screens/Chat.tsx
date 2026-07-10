import { useEffect, useRef, useState } from 'react'
import { CHAT_SEED, type Mode } from '../data'
import avShadow from '../assets/img/avatar-shadow.jpg'
import avOrch from '../assets/img/avatar-orch.jpg'
import { useBackend } from '../lib/backend'
import { ChatWs, type ChatWsFrame } from '../lib/chatws'

type Msg = { who: 'dexter' | 'me'; text: string; img?: string; warn?: boolean; streaming?: boolean }

const PENDING_KEY = 'dexter.pendingMessage'

export default function Chat({ mode }: { mode: Mode }) {
  const seed = CHAT_SEED[mode]
  const [msgs, setMsgs] = useState<Msg[]>([
    { who: 'dexter', text: seed.m1 },
    { who: 'me', text: seed.me },
    { who: 'dexter', text: seed.m2 },
  ])
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

  // reseed when the protocol flips — each mask has its own thread voice
  useEffect(() => {
    setMsgs([
      { who: 'dexter', text: seed.m1 },
      { who: 'me', text: seed.me },
      { who: 'dexter', text: seed.m2 },
    ])
  }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

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
            return [...m.slice(0, -1), { ...last, text: last.text + frame.content }]
          }
          return [...m, { who: 'dexter', text: frame.content, streaming: true }]
        })
      } else if (frame.type === 'done') {
        setMsgs((m) => {
          const last = m[m.length - 1]
          const finalMsg: Msg = { who: 'dexter', text: frame.message.content }
          if (last && last.who === 'dexter' && last.streaming) return [...m.slice(0, -1), finalMsg]
          return [...m, finalMsg]
        })
        setStreaming(false)
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

  function send(text?: string) {
    const v = (text ?? draft).trim()
    if (!v || streaming) return
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

  function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const url = URL.createObjectURL(f)
    setMsgs((m) => [
      ...m,
      { who: 'me', text: `Uploaded: ${f.name}`, img: url },
      { who: 'dexter', text: 'Image received and attached to the active thread.' },
    ])
    e.target.value = ''
  }

  const modelName = status?.ollama.model
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
              <div className="bub" style={m.warn ? { borderColor: 'var(--warn)', color: 'var(--warn)' } : undefined}>
                <span className="tag">Dexter · {seed.voice}</span>
                {m.text}
                {m.streaming && '▍'}
              </div>
            </div>
          ),
        )}
      </div>
      <div className="pillrow">
        {seed.pills.map((p) => <button key={p} className="p" onClick={() => send(p)}>{p}</button>)}
      </div>
      <div className="chatinput">
        <label className="attach">
          ＋<input type="file" accept="image/*" hidden onChange={upload} />
        </label>
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
