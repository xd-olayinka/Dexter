// Hold-to-record push-to-talk button (Build Plan 2.1). Lazily opens the /ws/voice
// connection on first press and keeps it for the component's lifetime.
import { useEffect, useRef, useState } from 'react'
import { wsUrl } from '../lib/api'
import { VoiceSession, type VoiceCapabilities } from '../lib/voice'

type Phase = 'idle' | 'connecting' | 'recording' | 'processing'

export function MicButton({
  protocol,
  onTranscript,
  onError,
}: {
  protocol: 'orch' | 'shadow'
  onTranscript: (text: string) => void
  onError?: (message: string) => void
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [caps, setCaps] = useState<VoiceCapabilities | 'unknown' | 'unreachable'>('unknown')
  const sessionRef = useRef<VoiceSession | null>(null)

  useEffect(() => () => { sessionRef.current?.close() }, [])

  async function ensureSession(): Promise<VoiceSession | null> {
    if (sessionRef.current) return sessionRef.current
    setPhase('connecting')
    const session = new VoiceSession(wsUrl('/ws/voice'), protocol, (e) => {
      if (e.type === 'transcription') {
        setPhase('idle')
        if (e.text && !e.text.startsWith('[')) onTranscript(e.text)
        else if (e.text) onError?.(e.text)
      } else if (e.type === 'processing') {
        setPhase('processing')
      } else if (e.type === 'error') {
        setPhase('idle')
        onError?.(e.message)
      } else if (e.type === 'closed') {
        sessionRef.current = null
        setPhase('idle')
      }
    })
    try {
      const capabilities = await session.connect()
      setCaps(capabilities)
      sessionRef.current = session
      return session
    } catch {
      setCaps('unreachable')
      setPhase('idle')
      return null
    }
  }

  async function press() {
    if (phase !== 'idle') return
    const session = await ensureSession()
    if (!session) return
    try {
      await session.startRecording()
      setPhase('recording')
    } catch {
      onError?.('Microphone permission denied')
      setPhase('idle')
    }
  }

  function release() {
    if (phase !== 'recording') return
    sessionRef.current?.stopRecording()
    setPhase('processing')
  }

  const disabled = caps !== 'unknown' && caps !== 'unreachable' && !caps.stt
  const title =
    caps === 'unreachable' ? "Couldn't reach the voice pipeline"
      : disabled ? 'Voice not installed — see Settings → Core Systems'
        : phase === 'recording' ? 'Release to send'
          : 'Hold to talk';

  return (
    <button
      type="button"
      className={`mic-btn${phase === 'recording' ? ' live' : ''}`}
      title={title}
      disabled={disabled || phase === 'connecting' || phase === 'processing'}
      onPointerDown={(e) => { e.preventDefault(); void press() }}
      onPointerUp={release}
      onPointerLeave={release}
      onPointerCancel={release}
    >
      {phase === 'processing' ? '…' : phase === 'recording' ? '●' : '🎙'}
    </button>
  )
}
