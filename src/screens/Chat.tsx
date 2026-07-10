import { useEffect, useRef, useState } from 'react'
import { CHAT_SEED, type Mode } from '../data'
import avShadow from '../assets/img/avatar-shadow.jpg'
import avOrch from '../assets/img/avatar-orch.jpg'

type Msg = { who: 'dexter' | 'me'; text: string; img?: string }

export default function Chat({ mode }: { mode: Mode }) {
  const seed = CHAT_SEED[mode]
  const [msgs, setMsgs] = useState<Msg[]>([
    { who: 'dexter', text: seed.m1 },
    { who: 'me', text: seed.me },
    { who: 'dexter', text: seed.m2 },
  ])
  const [draft, setDraft] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const avatar = mode === 'orch' ? avOrch : avShadow

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

  function send(text?: string) {
    const v = (text ?? draft).trim()
    if (!v) return
    setDraft('')
    setMsgs((m) => [...m, { who: 'me', text: v }])
    setTimeout(() => {
      setMsgs((m) => [...m, {
        who: 'dexter',
        text: mode === 'orch'
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

  return (
    <div className="chatwrap">
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
              <div className="bub">
                <span className="tag">Dexter · {seed.voice}</span>
                {m.text}
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
        <button className="send" onClick={() => send()}>↑</button>
      </div>
    </div>
  )
}
