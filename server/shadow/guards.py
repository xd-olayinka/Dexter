from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from models import Task
from shadow.budget import BudgetTracker
from shadow.guard_config import GuardConfig


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


def _make_high_cost_task(config: GuardConfig) -> Callable[[Task, BudgetTracker], str | None]:
    def check(task: Task, budget: BudgetTracker) -> str | None:
        cap = task.budget_cap or config.per_task_budget_default
        threshold = config.high_cost_multiplier * config.per_task_budget_default
        if cap > threshold:
            return f"High-cost task: budget cap ${cap:.2f} > {config.high_cost_multiplier:.1f}x default ${config.per_task_budget_default:.2f}"
        return None
    return check


def _make_long_running(config: GuardConfig) -> Callable[[Task, BudgetTracker], str | None]:
    def check(task: Task, budget: BudgetTracker) -> str | None:
        if task.status.value == "running" and task.created_at:
            elapsed = (datetime.now(timezone.utc) - task.created_at).total_seconds()
            limit_s = config.long_running_minutes * 60
            if elapsed > limit_s:
                return f"Task running for {elapsed / 60:.0f} minutes (limit: {config.long_running_minutes})"
        return None
    return check


def _make_custom_rule(rule) -> Callable[[Task, BudgetTracker], str | None]:
    def check(task: Task, budget: BudgetTracker) -> str | None:
        if rule.keyword and rule.keyword.lower() not in task.title.lower():
            return None
        if rule.max_spend is not None and budget.task_spend > rule.max_spend:
            return f"Guard \"{rule.name}\": spend ${budget.task_spend:.2f} > ${rule.max_spend:.2f}"
        if rule.require_approval:
            return f"Guard \"{rule.name}\": always requires approval"
        return None
    return check


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
    def from_config(config: GuardConfig) -> GuardChain:
        chain = GuardChain()
        chain.add_rule(GuardRule(name="budget_exceeded", check=_budget_exceeded))
        chain.add_rule(GuardRule(name="daily_budget_exceeded", check=_daily_budget_exceeded))
        chain.add_rule(GuardRule(name="high_cost_task", check=_make_high_cost_task(config)))
        chain.add_rule(GuardRule(name="long_running", check=_make_long_running(config)))
        for rule in config.custom_rules:
            if rule.enabled:
                chain.add_rule(GuardRule(name=f"custom:{rule.id}", check=_make_custom_rule(rule)))
        return chain
