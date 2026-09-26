import uuid
import json
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel

from models import Message, Protocol, Role
from brain import Brain
from memory.store import ConversationStore
from memory.semantic import SemanticMemory
from files import document_store
from auth import CurrentContext, current_context, context_from_token

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

RECALL_LIMIT = 3
RECALL_MIN_SIMILARITY = 0.5

# The in-memory dict is the source of truth for building live context — chat must
# keep working turn-to-turn even if Postgres is down or never configured. Persistence
# (ConversationStore) and recall (SemanticMemory) are a best-effort layer on top: every
# call into them is wrapped so a DB hiccup degrades to "no memory this turn," never a
# broken chat. See docs/BACKEND_TASKS.md P2 — this is a deliberate reading of "replace
# the in-memory sessions dict with ConversationStore" that keeps the whole-backend
# graceful-degradation contract every other module here already follows.
sessions: dict[str, list[Message]] = {}
session_conversation_id: dict[str, str] = {}


class ChatRequest(BaseModel):
    message: str
    protocol: Protocol = Protocol.ORCH
    session_id: str | None = None


def _get_brain(request: Request) -> Brain:
    return request.app.state.brain


def _get_store(request: Request) -> ConversationStore:
    return request.app.state.conversation_store


def _get_semantic(request: Request) -> SemanticMemory:
    return request.app.state.semantic_memory


async def _document_note(embed_fn, query: str, business_id: str) -> dict | None:
    """A synthetic system message carrying the top matching ingested documents
    (server/files.py — P5). Same "nothing found → None" contract as _recall_note."""
    try:
        hits = await document_store.search(query, embed_fn, business_id, limit=2)
    except Exception as e:
        log.warning("Document search failed (continuing without it): %s", e)
        return None
    hits = [h for h in hits if h["similarity"] >= RECALL_MIN_SIMILARITY]
    if not hits:
        return None
    lines = "\n".join(f"- \"{h['title']}\": {h['content'][:400]}" for h in hits)
    return {
        "role": "system",
        "content": f"Relevant material from ingested documents (may or may not be relevant):\n{lines}",
    }


async def _ensure_session(store: ConversationStore, session_id: str | None, protocol: Protocol, ctx: CurrentContext) -> str:
    sid = session_id or uuid.uuid4().hex[:12]
    if sid not in sessions:
        sessions[sid] = []
        try:
            conv_id = await store.create_conversation(protocol, user_id=ctx.user_id, business_id=ctx.business_id)
            session_conversation_id[sid] = conv_id
        except Exception as e:
            log.warning("Could not open a persisted conversation for session %s: %s", sid, e)
    return sid


async def _persist(store: ConversationStore, semantic: SemanticMemory, sid: str, message: Message) -> None:
    conv_id = session_conversation_id.get(sid)
    if conv_id is None:
        return
    try:
        await store.save_message(conv_id, message)
        await semantic.index_message(conv_id, message.id, message.content)
    except Exception as e:
        log.warning("Memory write failed for session %s (continuing without it): %s", sid, e)


async def _recall_note(semantic: SemanticMemory, sid: str, query: str, business_id: str) -> dict | None:
    """A synthetic system message carrying relevant snippets from OTHER conversations —
    the live session's own history already covers same-conversation context. Returns
    None (nothing to prepend) when memory is unavailable or nothing scores above the
    similarity floor, so an empty/irrelevant recall never dilutes the prompt."""
    conv_id = session_conversation_id.get(sid)
    try:
        hits = await semantic.recall(query, limit=RECALL_LIMIT + 3, business_id=business_id)
    except Exception as e:
        log.warning("Semantic recall failed (continuing without it): %s", e)
        return None
    hits = [h for h in hits if h["conversation_id"] != conv_id and h["similarity"] >= RECALL_MIN_SIMILARITY]
    if not hits:
        return None
    lines = "\n".join(f"- {h['content'][:280]}" for h in hits[:RECALL_LIMIT])
    return {
        "role": "system",
        "content": f"Relevant context from earlier conversations (may or may not be relevant — use your judgement):\n{lines}",
    }


async def _standing(fact_store, business_id: str | None, text: str) -> tuple[dict | None, str | None]:
    """Save or drop a standing preference the Commander just stated, then return the
    preferences note for the prompt plus what changed (for the client to show)."""
    import ops

    changed = None
    stmt = ops.extract_standing_fact(text)
    if stmt and await ops.remember(fact_store, business_id, stmt):
        changed = f"Remembered: {stmt}"
    else:
        phrase = ops.extract_forget(text)
        if phrase:
            n = await ops.forget(fact_store, business_id, phrase)
            changed = f"Forgot {n} preference{'s' if n != 1 else ''} about \"{phrase}\"" if n else None
    return ops.standing_note(await ops.standing_facts(fact_store, business_id)), changed


def _build_messages(session_id: str, protocol: Protocol, notes: list[dict] = ()) -> list[dict]:
    history = sessions[session_id]
    messages = [{"role": "system", "content": SYSTEM_PROMPTS[protocol]}]
    messages.extend(n for n in notes if n)
    messages.extend({"role": m.role.value, "content": m.content} for m in history)
    return messages


@router.post("/send")
async def send_message(body: ChatRequest, request: Request, ctx: CurrentContext = Depends(current_context)):
    brain = _get_brain(request)
    store = _get_store(request)
    semantic = _get_semantic(request)
    sid = await _ensure_session(store, body.session_id, body.protocol, ctx)

    user_msg = Message(role=Role.USER, content=body.message, protocol=body.protocol)
    sessions[sid].append(user_msg)
    await _persist(store, semantic, sid, user_msg)

    standing, remembered = await _standing(request.app.state.fact_store, ctx.business_id, body.message)
    notes = [
        standing,
        await _recall_note(semantic, sid, body.message, ctx.business_id),
        await _document_note(request.app.state.embed_fn, body.message, ctx.business_id),
    ]
    llm_messages = _build_messages(sid, body.protocol, notes)
    response = await brain.chat(llm_messages, business_id=ctx.business_id)

    content = response["message"]["content"]
    assistant_msg = Message(role=Role.ASSISTANT, content=content, protocol=body.protocol)
    sessions[sid].append(assistant_msg)
    await _persist(store, semantic, sid, assistant_msg)

    return {
        "session_id": sid,
        "message": assistant_msg.model_dump(mode="json"),
        "remembered": remembered,
    }


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    history = sessions.get(session_id, [])
    return {
        "session_id": session_id,
        "messages": [m.model_dump(mode="json") for m in history],
    }


async def websocket_chat(ws: WebSocket, app_state, token: str | None = None):
    try:
        ctx = await context_from_token(token)
    except Exception as e:
        await ws.close(code=4401, reason=str(e))
        return
    await ws.accept()
    brain: Brain = app_state.brain
    store: ConversationStore = app_state.conversation_store
    semantic: SemanticMemory = app_state.semantic_memory
    session_id = uuid.uuid4().hex[:12]
    sessions[session_id] = []
    try:
        conv_id = await store.create_conversation(Protocol.ORCH, user_id=ctx.user_id, business_id=ctx.business_id)
        session_conversation_id[session_id] = conv_id
    except Exception as e:
        log.warning("Could not open a persisted conversation for session %s: %s", session_id, e)

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)

            content = data.get("content", "")
            protocol = Protocol(data.get("protocol", "orch"))

            user_msg = Message(role=Role.USER, content=content, protocol=protocol)
            sessions[session_id].append(user_msg)
            await _persist(store, semantic, session_id, user_msg)

            standing, remembered = await _standing(app_state.fact_store, ctx.business_id, content)
            if remembered:
                await ws.send_json({"type": "remembered", "content": remembered})
            notes = [
                standing,
                await _recall_note(semantic, session_id, content, ctx.business_id),
                await _document_note(app_state.embed_fn, content, ctx.business_id),
            ]
            llm_messages = _build_messages(session_id, protocol, notes)
            stream = await brain.chat(llm_messages, stream=True, business_id=ctx.business_id)

            full_content = ""
            async for chunk in stream:
                token = chunk["message"]["content"]
                full_content += token
                await ws.send_json({"type": "chunk", "content": token})

            assistant_msg = Message(
                role=Role.ASSISTANT, content=full_content, protocol=protocol
            )
            sessions[session_id].append(assistant_msg)
            await _persist(store, semantic, session_id, assistant_msg)

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
