import httpx

from config import settings
from tools.registry import Tool, registry


async def web_search(query: str, num_results: int = 5) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.searxng_url}/search",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return "Web search unavailable — SearXNG is not running"
    except httpx.HTTPStatusError as e:
        return f"Search request failed: {e.response.status_code}"

    data = resp.json()
    results = data.get("results", [])[:num_results]
    if not results:
        return "No results found."

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r.get('title', 'Untitled')}\n"
            f"   {r.get('url', '')}\n"
            f"   {r.get('content', 'No snippet')}"
        )
    return "\n\n".join(lines)


registry.register(
    Tool(
        name="web_search",
        description="Search the web for current information",
        parameters={
            "query": {"type": "string", "description": "Search query"},
            "num_results": {
                "type": "integer",
                "description": "Number of results",
                "default": 5,
            },
        },
        handler=web_search,
    )
)
