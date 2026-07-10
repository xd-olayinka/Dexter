import asyncio
import io
import logging
import wave
from collections.abc import AsyncIterator

log = logging.getLogger("dexter.voice.tts")

try:
    from piper import PiperVoice
    from piper.download import ensure_voice_exists, find_voice, get_voices

    _PIPER_AVAILABLE = True
except ImportError:
    _PIPER_AVAILABLE = False

try:
    from models import Protocol
except ImportError:
    from server.models import Protocol

try:
    from config import settings
except ImportError:
    from server.config import settings


class TextToSpeech:
    def __init__(self, voice_id: str):
        if not _PIPER_AVAILABLE:
            raise RuntimeError("piper-tts not installed")
        self._voice_id = voice_id
        self._voice = None
        self._sample_rate_val = 22050
        self._load_voice()

    def _load_voice(self):
        try:
            data_dir = None
            try:
                from pathlib import Path

                data_dir = Path.home() / ".local" / "share" / "piper_voices"
                data_dir.mkdir(parents=True, exist_ok=True)
                voices_info = get_voices(str(data_dir))
                ensure_voice_exists(self._voice_id, [str(data_dir)], str(data_dir), voices_info)
                onnx_path, config_path = find_voice(self._voice_id, [str(data_dir)])
            except Exception:
                from pathlib import Path

                onnx_path = Path(self._voice_id)
                config_path = Path(f"{self._voice_id}.json")
                if not onnx_path.exists():
                    raise

            self._voice = PiperVoice.load(str(onnx_path), config_path=str(config_path))
            if hasattr(self._voice, "config") and hasattr(self._voice.config, "sample_rate"):
                self._sample_rate_val = self._voice.config.sample_rate
            log.info("Piper voice '%s' loaded (sample_rate=%d)", self._voice_id, self._sample_rate_val)
        except Exception as e:
            log.error("Failed to load Piper voice '%s': %s", self._voice_id, e)
            raise

    @property
    def sample_rate(self) -> int:
        return self._sample_rate_val

    async def synthesize(self, text: str) -> bytes:
        def _run():
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate_val)
                self._voice.synthesize(text, wf)
            buf.seek(0)
            with wave.open(buf, "rb") as wf:
                return wf.readframes(wf.getnframes())

        return await asyncio.to_thread(_run)

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        def _run():
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate_val)
                self._voice.synthesize(text, wf)
            return buf.getvalue()

        wav_bytes = await asyncio.to_thread(_run)
        with io.BytesIO(wav_bytes) as buf:
            with wave.open(buf, "rb") as wf:
                chunk_size = self._sample_rate_val * 2 * 100 // 1000
                while True:
                    frames = wf.readframes(chunk_size // 2)
                    if not frames:
                        break
                    yield frames


class DummyTTS:
    def __init__(self, voice_id: str = "dummy"):
        self._voice_id = voice_id
        self._sample_rate_val = 22050
        log.warning("TTS unavailable for voice '%s' — install piper-tts", voice_id)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate_val

    async def synthesize(self, text: str) -> bytes:
        return b""

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        return
        yield


def get_tts(protocol: Protocol) -> TextToSpeech | DummyTTS:
    voice_id = settings.piper_voice_orch if protocol == Protocol.ORCH else settings.piper_voice_shadow
    if not _PIPER_AVAILABLE:
        return DummyTTS(voice_id=voice_id)
    try:
        return TextToSpeech(voice_id=voice_id)
    except Exception:
        return DummyTTS(voice_id=voice_id)
