from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from config import settings
from models import Task
from shadow.budget import BudgetTracker


@dataclass
class GuardRule:
    name: str
    check: Callable[[Task, BudgetTracker], str | None]


def _budget_exceeded(task: Task, budget: BudgetTracker) -> str | None:
    status = budget.check_budget()
    if not status["ok"] and "Task budget" in (status["trip_reason"] or ""):
        return status["trip_reason"]
    return None


def _daily_budget_exceeded(task: Task, budget: BudgetTracker) -> str | None:
    status = budget.check_budget()
    if not status["ok"] and "Daily budget" in (status["trip_reason"] or ""):
        return status["trip_reason"]
    return None


def _high_cost_task(task: Task, budget: BudgetTracker) -> str | None:
    cap = task.budget_cap or settings.per_task_budget_default
    if cap > 2 * settings.per_task_budget_default:
        return f"High-cost task: budget cap ${cap:.2f} > 2× default ${settings.per_task_budget_default:.2f}"
    return None


def _long_running(task: Task, budget: BudgetTracker) -> str | None:
    if task.status.value == "running" and task.created_at:
        elapsed = (datetime.now(timezone.utc) - task.created_at).total_seconds()
        if elapsed > 1800:
            return f"Task running for {elapsed / 60:.0f} minutes (limit: 30)"
    return None


BUILTIN_RULES = [
    GuardRule(name="budget_exceeded", check=_budget_exceeded),
    GuardRule(name="daily_budget_exceeded", check=_daily_budget_exceeded),
    GuardRule(name="high_cost_task", check=_high_cost_task),
    GuardRule(name="long_running", check=_long_running),
]


class GuardChain:
    def __init__(self) -> None:
        self._rules: list[GuardRule] = []

    def add_rule(self, rule: GuardRule) -> None:
        self._rules.append(rule)

    def check(self, task: Task, budget: BudgetTracker) -> str | None:
        for rule in self._rules:
            result = rule.check(task, budget)
            if result is not None:
                return result
        return None

    @staticmethod
    def default_chain() -> GuardChain:
        chain = GuardChain()
        for rule in BUILTIN_RULES:
            chain.add_rule(rule)
        return chain
