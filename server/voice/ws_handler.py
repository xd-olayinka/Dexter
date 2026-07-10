import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

try:
    from models import Protocol
except ImportError:
    from server.models import Protocol

from voice.pipeline import create_pipeline, VoicePipeline

log = logging.getLogger("dexter.voice.ws")

router = APIRouter()

_pipeline: VoicePipeline | None = None


def _get_pipeline() -> VoicePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = create_pipeline()
    return _pipeline


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket, protocol: str = "orch"):
    await websocket.accept()

    proto = Protocol.SHADOW if protocol == "shadow" else Protocol.ORCH
    pipeline = _get_pipeline()
    caps = pipeline.capabilities()

    await websocket.send_text(json.dumps({
        "type": "ready",
        "protocol": proto.value,
        "capabilities": caps,
    }))

    log.info("Voice WS connected (protocol=%s)", proto.value)

    audio_buffer: list[bytes] = []
    pipeline.vad.reset()

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                chunk = message["bytes"]
                audio_buffer.append(chunk)

                vad_result = pipeline.vad.process_chunk(chunk)

                if vad_result["speech_ended"] and audio_buffer:
                    await websocket.send_text(json.dumps({"type": "processing"}))

                    text, _ = await pipeline.process_audio_turn(audio_buffer, proto)

                    await websocket.send_text(json.dumps({
                        "type": "transcription",
                        "text": text,
                        "protocol": proto.value,
                    }))

                    audio_buffer = []
                    pipeline.vad.reset()

            elif "text" in message and message["text"]:
                data = json.loads(message["text"])

                if data.get("type") == "synthesize":
                    response_text = data.get("text", "")
                    speak_protocol = Protocol(data.get("protocol", proto.value))

                    sample_rate = pipeline.get_tts_sample_rate(speak_protocol)
                    await websocket.send_text(json.dumps({
                        "type": "audio_start",
                        "sample_rate": sample_rate,
                    }))

                    async for audio_chunk in pipeline.text_to_speech_stream(response_text, speak_protocol):
                        await websocket.send_bytes(audio_chunk)

                    await websocket.send_text(json.dumps({"type": "audio_end"}))

                elif data.get("type") == "reset":
                    audio_buffer = []
                    pipeline.vad.reset()
                    await websocket.send_text(json.dumps({"type": "reset_ack"}))

                elif data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        log.info("Voice WS disconnected (protocol=%s)", proto.value)
    except Exception as e:
        log.exception("Voice WS error: %s", e)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
