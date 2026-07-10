from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date
from collections import defaultdict

from config import settings


@dataclass
class SpendEntry:
    timestamp: datetime
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_id: str | None = None


class SpendTracker:
    def __init__(self):
        self._entries: list[SpendEntry] = []

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        task_id: str | None = None,
    ):
        self._entries.append(SpendEntry(
            timestamp=datetime.now(timezone.utc),
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            task_id=task_id,
        ))

    def _today_entries(self) -> list[SpendEntry]:
        today = datetime.now(timezone.utc).date()
        return [e for e in self._entries if e.timestamp.date() == today]

    def total_today(self) -> float:
        return sum(e.cost_usd for e in self._today_entries())

    def total_by_provider(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for e in self._today_entries():
            totals[e.provider] += e.cost_usd
        return dict(totals)

    def total_by_model(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for e in self._today_entries():
            totals[e.model] += e.cost_usd
        return dict(totals)

    def recent(self, limit: int = 50) -> list[dict]:
        entries = self._entries[-limit:] if limit < len(self._entries) else self._entries
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "provider": e.provider,
                "model": e.model,
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "cost_usd": e.cost_usd,
                "task_id": e.task_id,
            }
            for e in reversed(entries)
        ]

    def budget_remaining(self) -> float:
        return max(0.0, settings.daily_cloud_budget - self.total_today())
