from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from config import settings
from models import Task, TaskStatus
from shadow.budget import BudgetTracker
from shadow.gates import GateManager
from shadow.guards import GuardChain

log = logging.getLogger("dexter.shadow.executor")

WorkFn = Callable[[Task, BudgetTracker], Coroutine[Any, Any, str]]


class ExecutorProcess:
    def __init__(
        self,
        task: Task,
        budget: BudgetTracker,
        guard_chain: GuardChain,
        gate_manager: GateManager,
        on_update: Callable[[Task], Any],
    ) -> None:
        self.task = task
        self.budget = budget
        self.guard_chain = guard_chain
        self.gate_manager = gate_manager
        self.on_update = on_update
        self._gate_event = asyncio.Event()
        self._gate_event.set()
        self._asyncio_task: asyncio.Task | None = None

    async def run(self, work_fn: WorkFn) -> None:
        self.task.status = TaskStatus.RUNNING
        self.task.executor_id = f"exec_{self.task.id}"
        self._notify_update()
        log.info("Executor started: %s", self.task.id)

        try:
            trip = self.guard_chain.check(self.task, self.budget)
            if trip:
                await self._enter_gate(trip)

            result = await work_fn(self.task, self.budget)

            trip = self.guard_chain.check(self.task, self.budget)
            if trip:
                await self._enter_gate(trip)

            self.task.status = TaskStatus.DONE
            self.task.result = result
            self.task.spend = self.budget.task_spend
            self.task.completed_at = datetime.now(timezone.utc)
            log.info("Executor done: %s spend=$%.4f", self.task.id, self.task.spend)
        except asyncio.CancelledError:
            self.task.status = TaskStatus.KILLED
            self.task.error = self.task.error or "cancelled"
            self.task.completed_at = datetime.now(timezone.utc)
            log.info("Executor cancelled: %s", self.task.id)
        except Exception as exc:
            self.task.status = TaskStatus.KILLED
            self.task.error = str(exc)
            self.task.completed_at = datetime.now(timezone.utc)
            log.exception("Executor failed: %s", self.task.id)
        finally:
            self.task.spend = self.budget.task_spend
            self._notify_update()

    async def _enter_gate(self, reason: str) -> None:
        self.task.status = TaskStatus.GATED
        self._notify_update()
        self._gate_event.clear()

        gate = await self.gate_manager.create_gate(
            self.task.id, reason, task_title=self.task.title,
        )
        log.info("Executor gated: %s reason=%s", self.task.id, reason)

        await self._gate_event.wait()

        resolved = self.gate_manager.get(self.task.id)
        if resolved and resolved.status == "rejected":
            self.task.error = f"Gate rejected: {reason}"
            raise asyncio.CancelledError()

        self.task.status = TaskStatus.RUNNING
        self._notify_update()
        log.info("Executor resumed after gate: %s", self.task.id)

    def resume_gate(self) -> None:
        self._gate_event.set()

    def _notify_update(self) -> None:
        try:
            self.on_update(self.task)
        except Exception:
            log.exception("on_update callback failed for %s", self.task.id)


async def _default_work_fn(task: Task, budget: BudgetTracker) -> str:
    budget.record_spend(0.01, "simulated_llm_call")
    await asyncio.sleep(1)
    return f"Simulated completion of: {task.title}"


class ExecutorManager:
    def __init__(self, gate_manager: GateManager | None = None) -> None:
        self._executors: dict[str, ExecutorProcess] = {}
        self._tasks: dict[str, Task] = {}
        self._gate_manager = gate_manager or GateManager()
        self._guard_chain = GuardChain.default_chain()

    @property
    def gate_manager(self) -> GateManager:
        return self._gate_manager

    async def spawn(
        self,
        task: Task,
        on_update: Callable[[Task], Any] | None = None,
        work_fn: WorkFn | None = None,
    ) -> str:
        if task.budget_cap is None:
            task.budget_cap = settings.per_task_budget_default

        budget = BudgetTracker(
            task_id=task.id,
            task_budget=task.budget_cap,
            daily_budget=settings.daily_cloud_budget,
        )

        callback = on_update or (lambda t: None)
        executor = ExecutorProcess(
            task=task,
            budget=budget,
            guard_chain=self._guard_chain,
            gate_manager=self._gate_manager,
            on_update=callback,
        )

        self._executors[task.id] = executor
        self._tasks[task.id] = task
        task.status = TaskStatus.QUEUED
        fn = work_fn or _default_work_fn
        executor._asyncio_task = asyncio.create_task(executor.run(fn))
        log.info("Task spawned: %s '%s' budget=$%.2f", task.id, task.title, task.budget_cap)
        return task.id

    async def kill(self, task_id: str, reason: str = "manual") -> bool:
        executor = self._executors.get(task_id)
        if executor is None:
            return False
        task = executor.task
        if task.status in (TaskStatus.DONE, TaskStatus.KILLED):
            return False
        task.error = reason
        if executor._asyncio_task and not executor._asyncio_task.done():
            executor._asyncio_task.cancel()
        task.status = TaskStatus.KILLED
        task.completed_at = datetime.now(timezone.utc)
        log.info("Task killed: %s reason=%s", task_id, reason)
        return True

    async def get_status(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    async def list_active(self) -> list[Task]:
        return [
            t for t in self._tasks.values()
            if t.status not in (TaskStatus.DONE, TaskStatus.KILLED)
        ]

    def list_all(self) -> list[Task]:
        return list(self._tasks.values())

    async def approve_gate(self, task_id: str) -> bool:
        approved = await self._gate_manager.approve(task_id)
        if not approved:
            return False
        executor = self._executors.get(task_id)
        if executor:
            executor.resume_gate()
        return True

    async def reject_gate(self, task_id: str, reason: str = "") -> bool:
        rejected = await self._gate_manager.reject(task_id, reason)
        if not rejected:
            return False
        executor = self._executors.get(task_id)
        if executor:
            executor.resume_gate()
        return True
