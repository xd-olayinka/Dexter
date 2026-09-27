import importlib.util
import logging

import httpx
from fastapi import APIRouter, Header, Request

from config import settings
from tools.prometheus_tools import get_client as get_prometheus_client

log = logging.getLogger("dexter.status")

router = APIRouter(prefix="/api/status", tags=["status"])


def _lib_installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


async def _check_searxng() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(settings.searxng_url)
            return resp.status_code < 500
    except Exception:
        return False


async def _check_database() -> bool:
    try:
        from db import get_pool
        pool = await get_pool()
        if pool is None:
            return False
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@router.get("")
async def system_status(request: Request, authorization: str | None = Header(default=None)):
    # The status page is public (the app polls it before sign-in), but the push topic is a
    # secret: anyone who knows it can read gate alerts. Only a signed-in caller sees it.
    signed_in = not settings.require_auth
    if not signed_in and authorization and authorization.lower().startswith("bearer "):
        from auth import _resolve_session
        signed_in = await _resolve_session(authorization[7:].strip()) is not None
    ollama = request.app.state.ollama
    ollama_ok = await ollama.health()
    ollama_models = await ollama.list_models() if ollama_ok else []

    providers = getattr(request.app.state, "escalation_providers", {})
    provider_status = {}
    for name, provider in providers.items():
        provider_status[name] = await provider.available()

    brain = getattr(request.app.state, "brain", None)
    brain_info = await brain.describe() if brain else {"provider": "none", "model": "—", "ready": False}

    return {
        "backend": {"ok": True, "version": "0.1.0"},
        "brain": brain_info,
        "ollama": {
            "ok": ollama_ok,
            "url": settings.ollama_base_url,
            "model": settings.ollama_model,
            "models": ollama_models,
        },
        "database": {
            "ok": await _check_database(),
            "url": settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
        },
        "searxng": {"ok": await _check_searxng(), "url": settings.searxng_url},
        "voice": {
            "torch": _lib_installed("torch"),
            "stt": _lib_installed("faster_whisper") or _lib_installed("whisper"),
            "tts": _lib_installed("piper"),
        },
        "browser": {"playwright": _lib_installed("playwright")},
        "notifications": {
            "configured": bool(settings.ntfy_topic),
            "topic": settings.ntfy_topic if signed_in else None,
            "server": settings.ntfy_server,
        },
        "providers": provider_status,
        "prometheus": await _check_prometheus(),
    }


async def _check_prometheus() -> dict:
    client = get_prometheus_client()
    if client is None:
        return {"configured": False, "connected": False, "url": None}
    return {"configured": True, "connected": await client.health(timeout=3.0), "url": client.url}
