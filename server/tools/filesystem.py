from pathlib import Path

from tools.registry import Tool, registry

ALLOWED_DIRS: list[Path] = [Path.home()]


def _validate_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not any(p == allowed or allowed in p.parents for allowed in ALLOWED_DIRS):
        raise PermissionError(f"Access denied — path outside allowed directories: {p}")
    return p


async def read_file(path: str) -> str:
    p = _validate_path(path)
    if not p.is_file():
        return f"Not a file or does not exist: {p}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {e}"


async def write_file(path: str, content: str) -> str:
    p = _validate_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {p}"
    except Exception as e:
        return f"Error writing file: {e}"


async def list_directory(path: str) -> str:
    p = _validate_path(path)
    if not p.is_dir():
        return f"Not a directory or does not exist: {p}"
    entries: list[str] = []
    for child in sorted(p.iterdir()):
        kind = "dir" if child.is_dir() else "file"
        entries.append(f"[{kind}] {child.name}")
    if not entries:
        return "Directory is empty."
    return "\n".join(entries)


registry.register(
    Tool(
        name="read_file",
        description="Read the contents of a file",
        parameters={
            "path": {"type": "string", "description": "Absolute file path to read"},
        },
        handler=read_file,
    )
)

registry.register(
    Tool(
        name="write_file",
        description="Write content to a file",
        parameters={
            "path": {"type": "string", "description": "Absolute file path to write to"},
            "content": {"type": "string", "description": "Content to write"},
        },
        handler=write_file,
    )
)

registry.register(
    Tool(
        name="list_directory",
        description="List files and directories at a given path",
        parameters={
            "path": {"type": "string", "description": "Absolute directory path"},
        },
        handler=list_directory,
    )
)
