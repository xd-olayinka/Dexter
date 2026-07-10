from fastapi import APIRouter, Request
from pydantic import BaseModel

from models import EscalationLevel

router = APIRouter(prefix="/api/escalation", tags=["escalation"])


class RouteRequest(BaseModel):
    message: str
    force_level: str | None = None


@router.get("/providers")
async def list_providers(request: Request):
    providers = request.app.state.escalation_providers
    result = []
    for name, provider in providers.items():
        result.append({
            "name": name,
            "available": await provider.available(),
            "default_model": getattr(provider, "DEFAULT_MODEL", "unknown"),
        })
    return {"providers": result}


@router.get("/spend")
async def get_spend(request: Request):
    tracker = request.app.state.spend_tracker
    return {
        "total_today": round(tracker.total_today(), 6),
        "by_provider": {k: round(v, 6) for k, v in tracker.total_by_provider().items()},
        "by_model": {k: round(v, 6) for k, v in tracker.total_by_model().items()},
        "budget_remaining": round(tracker.budget_remaining(), 6),
    }


@router.get("/spend/history")
async def spend_history(request: Request):
    tracker = request.app.state.spend_tracker
    return {"entries": tracker.recent()}


@router.post("/route")
async def dry_run_route(request: Request, body: RouteRequest):
    model_router = request.app.state.model_router
    force = EscalationLevel(body.force_level) if body.force_level else None
    route = await model_router.route(body.message, force_level=force)
    return route.model_dump()
