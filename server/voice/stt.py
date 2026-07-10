import asyncio
import io
import logging
import struct
import wave

log = logging.getLogger("dexter.voice.stt")

_ENGINE = None

try:
    from faster_whisper import WhisperModel as FasterWhisperModel

    _ENGINE = "faster_whisper"
    log.info("faster-whisper available")
except ImportError:
    pass

if _ENGINE is None:
    try:
        import whisper as openai_whisper

        _ENGINE = "openai_whisper"
        log.info("openai-whisper available (slower fallback)")
    except ImportError:
        pass


def _pcm16_to_wav(audio_data: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)
    return buf.getvalue()


def _pcm16_to_float32(audio_data: bytes):
    import numpy as np

    samples = struct.unpack(f"<{len(audio_data) // 2}h", audio_data)
    return np.array(samples, dtype=np.float32) / 32768.0


class SpeechToText:
    def __init__(self, model_name: str = "base"):
        self._model_name = model_name
        self._model = None
        self._engine = _ENGINE

        if self._engine == "faster_whisper":
            self._model = FasterWhisperModel(model_name, device="cpu", compute_type="int8")
            log.info("Faster-Whisper model '%s' loaded", model_name)
        elif self._engine == "openai_whisper":
            self._model = openai_whisper.load_model(model_name)
            log.info("OpenAI-Whisper model '%s' loaded", model_name)
        else:
            raise RuntimeError("No whisper engine available — install faster-whisper or openai-whisper")

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> dict:
        if self._engine == "faster_whisper":
            return await self._transcribe_faster(audio_data, sample_rate)
        return await self._transcribe_openai(audio_data, sample_rate)

    async def _transcribe_faster(self, audio_data: bytes, sample_rate: int) -> dict:
        def _run():
            float_audio = _pcm16_to_float32(audio_data)
            segments_iter, info = self._model.transcribe(float_audio, beam_size=5)
            segments = []
            full_text_parts = []
            for seg in segments_iter:
                segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
                full_text_parts.append(seg.text.strip())
            return {
                "text": " ".join(full_text_parts),
                "language": info.language,
                "confidence": round(info.language_probability, 3),
                "segments": segments,
            }

        return await asyncio.to_thread(_run)

    async def _transcribe_openai(self, audio_data: bytes, sample_rate: int) -> dict:
        def _run():
            float_audio = _pcm16_to_float32(audio_data)
            result = self._model.transcribe(float_audio, fp16=False)
            segments = [
                {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                for s in result.get("segments", [])
            ]
            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", "en"),
                "confidence": 0.0,
                "segments": segments,
            }

        return await asyncio.to_thread(_run)


class DummySTT:
    def __init__(self, **_kwargs):
        log.warning("No STT engine available — install faster-whisper or openai-whisper")

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> dict:
        return {
            "text": "[STT unavailable — install faster-whisper]",
            "language": "en",
            "confidence": 0.0,
            "segments": [],
        }


def get_stt(model_name: str = "base") -> SpeechToText | DummySTT:
    try:
        return SpeechToText(model_name=model_name)
    except RuntimeError:
        return DummySTT()
