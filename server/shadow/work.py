import logging

from models import Task
from shadow.budget import BudgetTracker
from tools import registry, run_with_tools

log = logging.getLogger("dexter.shadow.work")

EXECUTOR_SYSTEM = (
    "You are an executor sub-agent spawned by ANTHONY, the autonomous ops layer of "
    "the Dexter system. Complete the assigned task using the available tools when "
    "they help. Be efficient — minimal rounds, no filler. When done, reply with a "
    "concise report of what you did and the outcome. If the task cannot be completed "
    "with your tools, say exactly what is missing instead of inventing a result. If a Prometheus "
    "change comes back with \"proposed\": true, it is held for the Commander's approval in "
    "Prometheus — report it as held for approval, never as done."
)


class _TrackedBrain:
    """Wraps the Brain so every LLM call inside a task records real spend
    against that task's BudgetTracker (which is what trips the guards)."""

    def __init__(self, brain, task: Task, budget: BudgetTracker):
        self._brain = brain
        self._task = task
        self._budget = budget

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs):
        # Hard caps are checked before every model call, not just before/after the task —
        # a tripped task/daily budget stops the loop here and the executor logs why.
        status = self._budget.check_budget()
        if not status["ok"]:
            from shadow.selector import CapReached
            raise CapReached(status["trip_reason"])
        response = await self._brain.chat(
            messages, tools=tools, task_id=self._task.id, **kwargs
        )
        cost = response.get("cost_usd") if isinstance(response, dict) else None
        if cost:
            self._budget.record_spend(cost, label="llm_call")
        return response


def make_llm_work_fn(brain):
    async def work_fn(task: Task, budget: BudgetTracker) -> str:
        tracked = _TrackedBrain(brain, task, budget)
        from shadow.agents_store import save_checkpoint

        objective = task.title if not task.description else f"{task.title}\n\n{task.description}"
        checkpoint = task.metadata.pop("checkpoint", None)  # set when resuming after a restart
        if checkpoint:
            messages = list(checkpoint) + [{
                "role": "user",
                "content": "The server restarted mid-task. Your work so far is above — continue from where you "
                           "stopped; don't repeat steps that already succeeded.",
            }]
        else:
            messages = [
                {"role": "system", "content": EXECUTOR_SYSTEM},
                {"role": "user", "content": objective},
            ]

        async def checkpoint_step(msgs: list[dict]) -> None:
            await save_checkpoint(task.id, msgs)

        log.info("Executor %s running via brain (tools: %s)", task.id, registry.list_tools())
        result, _ = await run_with_tools(tracked, messages, registry, max_rounds=6, task_id=task.id, on_step=checkpoint_step)
        return result or "Executor finished without a final report."

    return work_fn
