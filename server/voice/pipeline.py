import logging
from collections.abc import AsyncIterator

try:
    from models import Protocol
except ImportError:
    from server.models import Protocol

try:
    from config import settings
except ImportError:
    from server.config import settings

from voice.vad import get_vad
from voice.stt import get_stt
from voice.tts import get_tts, DummyTTS, TextToSpeech

log = logging.getLogger("dexter.voice.pipeline")


class VoicePipeline:
    def __init__(self, vad, stt, tts_orch, tts_shadow):
        self.vad = vad
        self.stt = stt
        self.tts_orch = tts_orch
        self.tts_shadow = tts_shadow

    async def process_audio_turn(self, audio_chunks: list[bytes], protocol: Protocol) -> tuple[str, bytes]:
        audio_data = b"".join(audio_chunks)
        if not audio_data:
            return ("", b"")
        result = await self.stt.transcribe(audio_data)
        return (result["text"], b"")

    async def text_to_speech(self, text: str, protocol: Protocol) -> bytes:
        tts = self.tts_orch if protocol == Protocol.ORCH else self.tts_shadow
        return await tts.synthesize(text)

    async def text_to_speech_stream(self, text: str, protocol: Protocol) -> AsyncIterator[bytes]:
        tts = self.tts_orch if protocol == Protocol.ORCH else self.tts_shadow
        async for chunk in tts.synthesize_stream(text):
            yield chunk

    def get_tts_sample_rate(self, protocol: Protocol) -> int:
        tts = self.tts_orch if protocol == Protocol.ORCH else self.tts_shadow
        return tts.sample_rate

    def capabilities(self) -> dict:
        from voice.vad import DummyVAD
        from voice.stt import DummySTT

        return {
            "vad": not isinstance(self.vad, DummyVAD),
            "stt": not isinstance(self.stt, DummySTT),
            "tts_orch": not isinstance(self.tts_orch, DummyTTS),
            "tts_shadow": not isinstance(self.tts_shadow, DummyTTS),
        }


def create_pipeline() -> VoicePipeline:
    log.info("Initializing voice pipeline...")

    vad = get_vad()
    stt = get_stt(model_name=settings.whisper_model)
    tts_orch = get_tts(Protocol.ORCH)
    tts_shadow = get_tts(Protocol.SHADOW)

    pipeline = VoicePipeline(vad=vad, stt=stt, tts_orch=tts_orch, tts_shadow=tts_shadow)
    caps = pipeline.capabilities()

    available = [k for k, v in caps.items() if v]
    missing = [k for k, v in caps.items() if not v]

    if available:
        log.info("Voice components available: %s", ", ".join(available))
    if missing:
        log.warning("Voice components unavailable (using dummies): %s", ", ".join(missing))

    return pipeline
