from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from config import settings

log = logging.getLogger("dexter.shadow.gates")


@dataclass
class ApprovalGate:
    task_id: str
    reason: str
    task_title: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"
    resolved_at: datetime | None = None


class GateManager:
    def __init__(self) -> None:
        self._gates: dict[str, ApprovalGate] = {}

    async def create_gate(self, task_id: str, reason: str, task_title: str = "") -> ApprovalGate:
        gate = ApprovalGate(task_id=task_id, reason=reason, task_title=task_title)
        self._gates[task_id] = gate
        log.warning("Gate created: task=%s reason=%s", task_id, reason)
        await self._notify(gate)
        return gate

    async def approve(self, task_id: str) -> bool:
        gate = self._gates.get(task_id)
        if gate is None or gate.status != "pending":
            return False
        gate.status = "approved"
        gate.resolved_at = datetime.now(timezone.utc)
        log.info("Gate approved: task=%s", task_id)
        return True

    async def reject(self, task_id: str, reason: str = "") -> bool:
        gate = self._gates.get(task_id)
        if gate is None or gate.status != "pending":
            return False
        gate.status = "rejected"
        gate.resolved_at = datetime.now(timezone.utc)
        if reason:
            gate.reason = f"{gate.reason} — rejected: {reason}"
        log.info("Gate rejected: task=%s reason=%s", task_id, reason)
        return True

    def list_pending(self) -> list[ApprovalGate]:
        return [g for g in self._gates.values() if g.status == "pending"]

    def get(self, task_id: str) -> ApprovalGate | None:
        return self._gates.get(task_id)

    async def _notify(self, gate: ApprovalGate) -> None:
        url = f"{settings.ntfy_server}/{settings.ntfy_topic}"
        title = f"Dexter Gate: {gate.task_title or gate.task_id}"
        body = f"{gate.reason}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    url,
                    content=body,
                    headers={
                        "Title": title,
                        "Priority": "high",
                        "Tags": "warning",
                    },
                )
            log.info("Gate notification sent to %s", url)
        except Exception as exc:
            log.warning("Failed to send gate notification: %s", exc)
