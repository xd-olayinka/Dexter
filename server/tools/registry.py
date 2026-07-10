from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
import traceback

from models import ToolCall, ToolResult


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

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Unknown tool: {tool_call.name}",
                success=False,
            )
        try:
            result = await tool.handler(**tool_call.arguments)
            return ToolResult(
                tool_call_id=tool_call.id,
                content=result,
                success=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                success=False,
            )

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


registry = ToolRegistry()
