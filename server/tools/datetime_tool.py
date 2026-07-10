from datetime import datetime, timezone

from tools.registry import Tool, registry


async def current_datetime() -> str:
    now = datetime.now(timezone.utc)
    local = datetime.now().astimezone()
    return (
        f"UTC:   {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"Local: {local.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )


async def time_until(target: str) -> str:
    try:
        t = datetime.fromisoformat(target)
    except ValueError:
        return f"Could not parse datetime: {target}"

    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = t - now

    if delta.total_seconds() < 0:
        delta = -delta
        prefix = "was"
        suffix = "ago"
    else:
        prefix = "is"
        suffix = "from now"

    total_seconds = int(delta.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")

    return f"{target} {prefix} {' '.join(parts)} {suffix}"


registry.register(
    Tool(
        name="current_datetime",
        description="Get the current date, time, and timezone",
        parameters={},
        handler=current_datetime,
    )
)

registry.register(
    Tool(
        name="time_until",
        description="Calculate time remaining until a target datetime",
        parameters={
            "target": {
                "type": "string",
                "description": "Target datetime in ISO 8601 format (e.g. 2025-12-31T23:59:59)",
            },
        },
        handler=time_until,
    )
)
