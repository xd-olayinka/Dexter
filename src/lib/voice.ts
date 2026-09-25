// Push-to-talk client for /ws/voice (Build Plan 2.1). Wire protocol (server/voice/ws_handler.py):
//   client → binary frames: raw PCM16LE mono @ 16kHz, streamed while recording
//   client → {"type":"commit"} on release (finalizes the turn regardless of VAD state —
//             a real VAD would otherwise never see the silence needed to trigger on its own)
//   server → {"type":"ready", capabilities} once, right after connect
//   server → {"type":"processing"} then {"type":"transcription", text}
//   client → {"type":"synthesize", text, protocol} to speak a reply
//   server → {"type":"audio_start", sample_rate}, binary PCM16LE frames, {"type":"audio_end"}
//
// TTS playback buffers the whole utterance before playing (one AudioBufferSourceNode)
// rather than scheduling per-chunk — simpler and gap-free; the trade-off is playback
// starts once the full reply has synthesized, not on the first chunk.

export interface VoiceCapabilities {
  vad: boolean
  stt: boolean
  tts_orch: boolean
  tts_shadow: boolean
}

export type VoiceEvent =
  | { type: 'ready'; capabilities: VoiceCapabilities }
  | { type: 'processing' }
  | { type: 'transcription'; text: string }
  | { type: 'speaking'; speaking: boolean }
  | { type: 'error'; message: string }
  | { type: 'closed' }

type Protocol = 'orch' | 'shadow'

function pcm16FromFloat32(input: Float32Array): ArrayBuffer {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out.buffer
}

function float32FromPcm16(buf: ArrayBuffer): Float32Array {
  const view = new Int16Array(buf)
  const out = new Float32Array(view.length)
  for (let i = 0; i < view.length; i++) out[i] = view[i] / (view[i] < 0 ? 0x8000 : 0x7fff)
  return out
}

const RECORD_SAMPLE_RATE = 16000

export class VoiceSession {
  private ws: WebSocket | null = null
  private recordCtx: AudioContext | null = null
  private stream: MediaStream | null = null
  private processor: ScriptProcessorNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private playCtx: AudioContext | null = null
  private ttsChunks: ArrayBuffer[] = []
  private ttsSampleRate = 22050
  private ready: Promise<VoiceCapabilities>
  private resolveReady!: (c: VoiceCapabilities) => void
  private rejectReady!: (e: Error) => void

  constructor(
    private wsUrl: string,
    private protocol: Protocol,
    private onEvent: (e: VoiceEvent) => void,
  ) {
    this.ready = new Promise((resolve, reject) => {
      this.resolveReady = resolve
      this.rejectReady = reject
    })
  }

  connect(): Promise<VoiceCapabilities> {
    const ws = new WebSocket(`${this.wsUrl}?protocol=${this.protocol}`)
    ws.binaryType = 'arraybuffer'
    this.ws = ws

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'ready') {
          this.resolveReady(msg.capabilities)
          this.onEvent({ type: 'ready', capabilities: msg.capabilities })
        } else if (msg.type === 'processing') {
          this.onEvent({ type: 'processing' })
        } else if (msg.type === 'transcription') {
          this.onEvent({ type: 'transcription', text: msg.text })
        } else if (msg.type === 'audio_start') {
          this.ttsSampleRate = msg.sample_rate
          this.ttsChunks = []
          this.onEvent({ type: 'speaking', speaking: true })
        } else if (msg.type === 'audio_end') {
          this._playBuffered()
        } else if (msg.type === 'error') {
          this.onEvent({ type: 'error', message: msg.message })
        }
      } else {
        this.ttsChunks.push(ev.data as ArrayBuffer)
      }
    }
    ws.onerror = () => this.rejectReady(new Error('Voice connection failed'))
    ws.onclose = () => this.onEvent({ type: 'closed' })

    return this.ready
  }

  /** Requests the mic and starts streaming PCM16 frames. Throws if the browser/user denies it. */
  async startRecording(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
    // Safari/older browsers ignore a requested sampleRate on AudioContext; resampling to
    // exactly 16kHz across all browsers needs an AudioWorklet + resampler, which is more
    // machinery than a push-to-talk button warrants here — most engines honor it, and the
    // server-side Whisper/VAD path tolerates some drift in practice.
    this.recordCtx = new AudioContext({ sampleRate: RECORD_SAMPLE_RATE })
    this.source = this.recordCtx.createMediaStreamSource(this.stream)
    this.processor = this.recordCtx.createScriptProcessor(4096, 1, 1)
    this.processor.onaudioprocess = (e) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(pcm16FromFloat32(e.inputBuffer.getChannelData(0)))
      }
    }
    this.source.connect(this.processor)
    // a ScriptProcessorNode must be connected to a destination to fire — route to a
    // silent gain node instead of speakers so recording doesn't echo back
    const sink = this.recordCtx.createGain()
    sink.gain.value = 0
    this.processor.connect(sink)
    sink.connect(this.recordCtx.destination)
  }

  /** Stops the mic and tells the server to finalize the turn — a `transcription` event follows. */
  stopRecording(): void {
    this.processor?.disconnect()
    this.source?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.recordCtx?.close()
    this.processor = null
    this.source = null
    this.stream = null
    this.recordCtx = null
    this.ws?.send(JSON.stringify({ type: 'commit' }))
  }

  speak(text: string, protocol: Protocol = this.protocol): void {
    this.ws?.send(JSON.stringify({ type: 'synthesize', text, protocol }))
  }

  private async _playBuffered(): Promise<void> {
    const total = this.ttsChunks.reduce((n, c) => n + c.byteLength, 0)
    this.onEvent({ type: 'speaking', speaking: false })
    if (total === 0) return
    const merged = new Uint8Array(total)
    let offset = 0
    for (const chunk of this.ttsChunks) {
      merged.set(new Uint8Array(chunk), offset)
      offset += chunk.byteLength
    }
    this.ttsChunks = []

    this.playCtx ??= new AudioContext()
    const floats = float32FromPcm16(merged.buffer)
    const buffer = this.playCtx.createBuffer(1, floats.length, this.ttsSampleRate)
    // `floats` is always backed by a plain ArrayBuffer we allocated ourselves (never a
    // SharedArrayBuffer) — TS 5.7's stricter typed-array generics just can't prove that
    // through the Uint8Array(total)/.buffer round trip above.
    buffer.copyToChannel(floats as Float32Array<ArrayBuffer>, 0)
    const src = this.playCtx.createBufferSource()
    src.buffer = buffer
    src.connect(this.playCtx.destination)
    src.start()
  }

  close(): void {
    this.stopRecording()
    this.ws?.close()
    this.ws = null
    this.playCtx?.close()
    this.playCtx = null
  }
}
