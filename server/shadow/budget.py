from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from models import BudgetSnapshot
from config import settings

log = logging.getLogger("dexter.shadow.budget")


class DailyBudgetLedger:
    _instance: DailyBudgetLedger | None = None
    _entries: list[dict]
    _date: date

    def __new__(cls) -> DailyBudgetLedger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._entries = []
            cls._instance._date = datetime.now(timezone.utc).date()
        return cls._instance

    def reset_if_new_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._date:
            log.info("Daily budget ledger reset (was %s, now %s)", self._date, today)
            self._entries.clear()
            self._date = today

    def record(self, amount: float, task_id: str, label: str = "") -> None:
        self.reset_if_new_day()
        self._entries.append({
            "amount": amount,
            "task_id": task_id,
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def total_today(self) -> float:
        self.reset_if_new_day()
        return sum(e["amount"] for e in self._entries)

    def get_log(self, limit: int = 50) -> list[dict]:
        self.reset_if_new_day()
        return list(reversed(self._entries[-limit:]))


_daily_ledger = DailyBudgetLedger()


class BudgetTracker:
    def __init__(self, task_id: str, task_budget: float, daily_budget: float | None = None):
        self._task_id = task_id
        self._task_budget = task_budget
        self._daily_budget = daily_budget or settings.daily_cloud_budget
        self._task_spend: float = 0.0

    @property
    def task_spend(self) -> float:
        return self._task_spend

    def record_spend(self, amount: float, label: str = "") -> None:
        self._task_spend += amount
        _daily_ledger.record(amount, self._task_id, label)
        log.info(
            "Spend recorded: $%.4f (%s) task=%s total=$%.4f",
            amount, label or "-", self._task_id, self._task_spend,
        )

    def check_budget(self) -> dict:
        task_remaining = self._task_budget - self._task_spend
        daily_remaining = self._daily_budget - _daily_ledger.total_today()
        trip_reason = None

        if self._task_spend > self._task_budget:
            trip_reason = f"Task budget exceeded (${self._task_spend:.2f} / ${self._task_budget:.2f})"
        elif _daily_ledger.total_today() > self._daily_budget:
            trip_reason = f"Daily budget exceeded (${_daily_ledger.total_today():.2f} / ${self._daily_budget:.2f})"

        return {
            "ok": trip_reason is None,
            "task_remaining": max(task_remaining, 0.0),
            "daily_remaining": max(daily_remaining, 0.0),
            "trip_reason": trip_reason,
        }

    def get_snapshot(self, active_tasks: int = 0, total_tasks_today: int = 0) -> BudgetSnapshot:
        return BudgetSnapshot(
            daily_limit=self._daily_budget,
            daily_spent=_daily_ledger.total_today(),
            daily_remaining=max(self._daily_budget - _daily_ledger.total_today(), 0.0),
            active_tasks=active_tasks,
            total_tasks_today=total_tasks_today,
        )
