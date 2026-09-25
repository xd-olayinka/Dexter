from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
import logging
import traceback

from models import ToolCall, ToolResult

log = logging.getLogger("dexter.tools.registry")


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Coroutine[Any, Any, str]]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get_schema(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": t.parameters,
                        "required": [
                            k for k, v in t.parameters.items()
                            if "default" not in v
                        ],
                    },
                },
            }
            for t in self._tools.values()
        ]

    async def execute(self, tool_call: ToolCall, task_id: str | None = None) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if not tool:
            await self._log_call(task_id, tool_call.name, success=False)
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Unknown tool: {tool_call.name}",
                success=False,
            )
        try:
            result = await tool.handler(**tool_call.arguments)
            await self._log_call(task_id, tool_call.name, success=True)
            return ToolResult(
                tool_call_id=tool_call.id,
                content=result,
                success=True,
            )
        except Exception as e:
            await self._log_call(task_id, tool_call.name, success=False)
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                success=False,
            )

    async def _log_call(self, task_id: str | None, tool_name: str, success: bool) -> None:
        """Real agent→tool edges for the Dependency map (docs/PHASE_3_4_PLAN.md §7) —
        best-effort, never blocks or fails a tool call if logging itself fails."""
        if task_id is None:
            return
        try:
            from db.connection import get_pool
            pool = await get_pool()
            if pool is None:
                return
            async with pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO agent_tool_calls (task_id, tool_name, success) VALUES (%s, %s, %s)",
                    (task_id, tool_name, success),
                )
        except Exception as e:
            log.warning("Could not log tool call %s for task %s: %s", tool_name, task_id, e)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


registry = ToolRegistry()
