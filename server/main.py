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
)

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

    providers = {
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

    yield

    log.info("Shutting down Dexter")


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


@app.get("/")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await websocket_chat(ws, app.state)
