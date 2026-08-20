import uuid
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel

from models import Message, Protocol, Role
from brain import Brain

log = logging.getLogger("dexter.chat")

router = APIRouter(prefix="/api/chat")

SYSTEM_PROMPTS = {
    Protocol.ORCH: (
        "You are Dexter, a warm and sharp personal AI operative. "
        "You help the Commander plan, prioritize, and execute. "
        "Be concise, confident, and actionable."
    ),
    Protocol.SHADOW: (
        "You are Dexter operating in Shadow Protocol. "
        "You are the execution layer — cold, efficient, precise. "
        "Report status, await orders, execute without hesitation."
    ),
}

sessions: dict[str, list[Message]] = {}


class ChatRequest(BaseModel):
    message: str
    protocol: Protocol = Protocol.ORCH
    session_id: str | None = None


def _get_brain(request: Request) -> Brain:
    return request.app.state.brain


def _ensure_session(session_id: str | None) -> str:
    sid = session_id or uuid.uuid4().hex[:12]
    if sid not in sessions:
        sessions[sid] = []
    return sid


def _build_messages(session_id: str, protocol: Protocol) -> list[dict]:
    history = sessions[session_id]
    return [
        {"role": "system", "content": SYSTEM_PROMPTS[protocol]},
        *[{"role": m.role.value, "content": m.content} for m in history],
    ]


@router.post("/send")
async def send_message(body: ChatRequest, request: Request):
    brain = _get_brain(request)
    sid = _ensure_session(body.session_id)

    user_msg = Message(role=Role.USER, content=body.message, protocol=body.protocol)
    sessions[sid].append(user_msg)

    llm_messages = _build_messages(sid, body.protocol)
    response = await brain.chat(llm_messages)

    content = response["message"]["content"]
    assistant_msg = Message(role=Role.ASSISTANT, content=content, protocol=body.protocol)
    sessions[sid].append(assistant_msg)

    return {
        "session_id": sid,
        "message": assistant_msg.model_dump(mode="json"),
    }


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    history = sessions.get(session_id, [])
    return {
        "session_id": session_id,
        "messages": [m.model_dump(mode="json") for m in history],
    }


async def websocket_chat(ws: WebSocket, app_state):
    await ws.accept()
    brain: Brain = app_state.brain
    session_id = uuid.uuid4().hex[:12]
    sessions[session_id] = []

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)

            content = data.get("content", "")
            protocol = Protocol(data.get("protocol", "orch"))

            user_msg = Message(role=Role.USER, content=content, protocol=protocol)
            sessions[session_id].append(user_msg)

            llm_messages = _build_messages(session_id, protocol)
            stream = await brain.chat(llm_messages, stream=True)

            full_content = ""
            async for chunk in stream:
                token = chunk["message"]["content"]
                full_content += token
                await ws.send_json({"type": "chunk", "content": token})

            assistant_msg = Message(
                role=Role.ASSISTANT, content=full_content, protocol=protocol
            )
            sessions[session_id].append(assistant_msg)

            await ws.send_json({
                "type": "done",
                "message": assistant_msg.model_dump(mode="json"),
            })
    except WebSocketDisconnect:
        log.info("WebSocket disconnected: session %s", session_id)
    except Exception as e:
        log.error("WebSocket error: %s", e)
        try:
            await ws.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
