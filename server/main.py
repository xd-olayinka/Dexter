import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from ollama_client import OllamaClient
from chat import router as chat_router, websocket_chat
from shadow import shadow_router
from status import router as status_router
from voice import voice_router
from escalation import (
    escalation_router,
    TaskClassifier,
    ModelRouter,
    SpendTracker,
    AnthropicProvider,
    OpenAIProvider,
    GroqProvider,
    DeepSeekProvider,
)
from brain import Brain
from memory.store import ConversationStore
from memory.semantic import SemanticMemory
from memory.facts import FactStore
from memory.embeddings import make_embed_fn
from db.connection import init_db, close_pool
from projects import router as projects_router
from briefing import router as briefing_router
from files import router as files_router
from auth import router as auth_router
from metrics import router as metrics_router
from dependencies import router as dependencies_router
from ledger import router as ledger_router
from archive import router as archive_router
from ops import router as ops_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("dexter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        fast_model=settings.ollama_fast_model,
        embed_model=settings.ollama_embed_model,
    )
    app.state.ollama = ollama

    healthy = await ollama.health()
    if healthy:
        models = await ollama.list_models()
        log.info("Ollama connected — model: %s, available: %s", settings.ollama_model, models)
    else:
        log.warning("Ollama not reachable at %s — chat will return stub responses", settings.ollama_base_url)

    deepseek = DeepSeekProvider()
    providers = {
        "deepseek": deepseek,
        "anthropic": AnthropicProvider(),
        "openai": OpenAIProvider(),
        "groq": GroqProvider(),
    }
    tracker = SpendTracker()
    classifier = TaskClassifier()
    model_router = ModelRouter(
        classifier=classifier,
        providers=providers,
        ollama_client=ollama,
        tracker=tracker,
    )
    app.state.escalation_providers = providers
    app.state.spend_tracker = tracker
    app.state.model_router = model_router

    brain = Brain(ollama=ollama, deepseek=deepseek, tracker=tracker)
    app.state.brain = brain
    # Selector Core's execution path: any provider (Ollama included) behind one chat()
    from shadow.selector import ModelGateway
    app.state.gateway = ModelGateway(ollama, providers)
    active = await brain.describe()
    if active["ready"]:
        log.info("Brain online — %s · %s", active["provider"], active["model"])
    else:
        log.warning("Brain has no provider — install Ollama or set DEXTER_DEEPSEEK_API_KEY")

    # Memory (P2). init_db() no-ops (logs + returns) when Postgres isn't reachable —
    # every store below then just returns empty/raises RuntimeError per-call, which
    # chat.py and files.py already catch, so startup never fails on a missing DB.
    await init_db()
    embed_fn = make_embed_fn(ollama)
    app.state.embed_fn = embed_fn
    app.state.conversation_store = ConversationStore()
    app.state.semantic_memory = SemanticMemory(embed_fn=embed_fn)
    app.state.fact_store = FactStore()

    # Executors are in-memory: anything in flight when the last process stopped is marked
    # 'interrupted' and re-run (DEXTER_RESUME_INTERRUPTED=false to only mark them).
    from shadow.agents_store import resume_interrupted
    resumed = await resume_interrupted(app)
    if resumed:
        log.info("Recovered %d interrupted task(s)", resumed)

    import asyncio
    import gate_voter
    voter = asyncio.create_task(gate_voter.run_forever(app))

    yield

    voter.cancel()
    log.info("Shutting down Dexter")
    await close_pool()


app = FastAPI(title="Dexter", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(shadow_router)
app.include_router(voice_router)
app.include_router(escalation_router)
app.include_router(status_router)
app.include_router(projects_router)
app.include_router(briefing_router)
app.include_router(files_router)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(dependencies_router)
app.include_router(ledger_router)
app.include_router(archive_router)
app.include_router(ops_router)


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "version": "0.1.0"}


if not settings.static_dir:
    @app.get("/")
    async def health():
        return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket, token: str | None = None):
    await websocket_chat(ws, app.state, token)


if settings.static_dir:
    # Combined image: serve the built app; unknown non-API paths fall back to index.html.
    from pathlib import Path
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    _static = Path(settings.static_dir).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404)
        target = (_static / path).resolve()
        if path and target.is_file() and _static in target.parents:
            return FileResponse(target)
        return FileResponse(_static / "index.html")
