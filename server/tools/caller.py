from models import ToolCall
from tools.registry import ToolRegistry


async def run_with_tools(
    ollama_client,
    messages: list[dict],
    tool_registry: ToolRegistry,
    max_rounds: int = 5,
) -> tuple[str, list[dict]]:
    tools = tool_registry.get_schema()

    for _ in range(max_rounds):
        response = await ollama_client.chat(
            messages=messages,
            tools=tools,
        )

        msg = response.get("message", {})
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content", ""), messages

        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_call = ToolCall(
                name=fn.get("name", ""),
                arguments=fn.get("arguments", {}),
            )
            result = await tool_registry.execute(tool_call)
            messages.append({
                "role": "tool",
                "content": result.content,
            })

    final = messages[-1]
    if isinstance(final, dict) and final.get("role") == "assistant":
        return final.get("content", ""), messages

    return "", messages
