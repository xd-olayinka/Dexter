import logging
import struct

log = logging.getLogger("dexter.voice.vad")

try:
    import torch
    import numpy as np

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

_silero_model = None


def _load_silero():
    global _silero_model
    if _silero_model is not None:
        return _silero_model
    try:
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad", onnx=False, trust_repo=True
        )
        _silero_model = model
        log.info("Silero VAD model loaded")
        return model
    except Exception as e:
        log.warning("Failed to load Silero VAD: %s", e)
        return None


class VoiceActivityDetector:
    def __init__(self, threshold: float = 0.5, min_silence_ms: int = 700):
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self._model = _load_silero() if _TORCH_AVAILABLE else None
        self._speech_active = False
        self._silence_samples = 0
        self._chunk_count = 0

    def process_chunk(self, audio_chunk: bytes, sample_rate: int = 16000) -> dict:
        if self._model is None:
            self._chunk_count += 1
            return {"speech_detected": False, "speech_ended": self._chunk_count >= 1, "confidence": 0.0}

        samples = struct.unpack(f"<{len(audio_chunk) // 2}h", audio_chunk)
        tensor = torch.FloatTensor(samples) / 32768.0

        window_size = 512 if sample_rate == 16000 else 256
        if len(tensor) < window_size:
            tensor = torch.nn.functional.pad(tensor, (0, window_size - len(tensor)))

        confidence = float(self._model(tensor[:window_size], sample_rate).item())
        is_speech = confidence >= self.threshold

        min_silence_samples = int(sample_rate * self.min_silence_ms / 1000)

        if is_speech:
            self._speech_active = True
            self._silence_samples = 0
        elif self._speech_active:
            self._silence_samples += len(samples)

        speech_ended = self._speech_active and self._silence_samples >= min_silence_samples

        if speech_ended:
            self._speech_active = False
            self._silence_samples = 0

        return {"speech_detected": is_speech, "speech_ended": speech_ended, "confidence": confidence}

    def reset(self):
        self._speech_active = False
        self._silence_samples = 0
        self._chunk_count = 0
        if self._model is not None:
            self._model.reset_states()


class DummyVAD:
    def __init__(self, **_kwargs):
        self._received = False

    def process_chunk(self, audio_chunk: bytes, sample_rate: int = 16000) -> dict:
        self._received = True
        return {"speech_detected": False, "speech_ended": True, "confidence": 0.0}

    def reset(self):
        self._received = False


def get_vad(**kwargs) -> VoiceActivityDetector | DummyVAD:
    if _TORCH_AVAILABLE:
        try:
            return VoiceActivityDetector(**kwargs)
        except Exception as e:
            log.warning("VAD init failed, using dummy: %s", e)
    else:
        log.info("torch not installed — VAD running in passthrough mode")
    return DummyVAD(**kwargs)
