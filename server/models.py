from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
from typing import Any
import uuid


class Protocol(str, Enum):
    ORCH = "orch"
    SHADOW = "shadow"


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    role: Role
    content: str
    protocol: Protocol = Protocol.ORCH
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_calls: list["ToolCall"] = []
    metadata: dict[str, Any] = {}


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: f"tc_{uuid.uuid4().hex[:8]}")
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    success: bool = True


class TaskStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    GATED = "gated"
    DONE = "done"
    KILLED = "killed"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.DRAFT
    protocol: Protocol = Protocol.SHADOW
    executor_id: str | None = None
    budget_cap: float | None = None
    spend: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = {}


class EscalationLevel(str, Enum):
    LOCAL = "local"
    FAST = "fast"
    CLOUD = "cloud"


class ModelRoute(BaseModel):
    level: EscalationLevel
    provider: str
    model: str
    reason: str


class BudgetSnapshot(BaseModel):
    daily_limit: float
    daily_spent: float
    daily_remaining: float
    active_tasks: int
    total_tasks_today: int
