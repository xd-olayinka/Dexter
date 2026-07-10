import importlib.util
import logging

import httpx
from fastapi import APIRouter, Request

from config import settings

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
async def system_status(request: Request):
    ollama = request.app.state.ollama
    ollama_ok = await ollama.health()
    ollama_models = await ollama.list_models() if ollama_ok else []

    providers = getattr(request.app.state, "escalation_providers", {})
    provider_status = {}
    for name, provider in providers.items():
        provider_status[name] = await provider.available()

    return {
        "backend": {"ok": True, "version": "0.1.0"},
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
            "topic": settings.ntfy_topic,
            "server": settings.ntfy_server,
        },
        "providers": provider_status,
    }
