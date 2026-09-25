"""Projects / Tasks persistence (docs/BACKEND_TASKS.md P3), scoped per business since
Phase 4 (docs/PHASE_3_4_PLAN.md §1) — every read/write is confined to the caller's
`business_id` (resolved from `current_context`; the default context when auth is off),
so once real accounts exist, one business can never see or touch another's projects.

Real Postgres-backed CRUD behind `/api/projects` and `/api/tasks`, replacing the
`PROJECTS` / `TASKS_TODAY` / `TASKS_UPCOMING` mocks in `src/data.ts`. Shape mirrors
those mocks closely so the frontend swap (Build Plan 2.3) is a data-source change,
not a markup change.

Like every other persistence-backed module here, a missing/unreachable Postgres
raises a clear 503 rather than a stack trace — the frontend's existing online/offline
handling already knows how to fall back to demo data when a call fails.
"""
from __future__ import annotations

import uuid
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.connection import get_pool
from auth import CurrentContext, current_context

log = logging.getLogger("dexter.projects")

router = APIRouter(prefix="/api", tags=["projects"])

DB_UNAVAILABLE = "Database not configured — install PostgreSQL (see Settings) to persist projects and tasks."


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------- models

class ProjectIn(BaseModel):
    name: str
    category: str = ""
    status: str = "Ongoing"
    priority: str = "Medium"
    due_date: date | None = None
    people: list[str] = []
    agents_note: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: date | None = None
    people: list[str] | None = None
    agents_note: str | None = None


class ProjectOut(ProjectIn):
    id: str
    tasks_total: int = 0
    tasks_done: int = 0
    created_at: datetime
    updated_at: datetime


class TaskIn(BaseModel):
    title: str
    project_id: str | None = None
    meta: str = ""
    when_bucket: str = "today"  # 'today' | 'upcoming'
    status: str = "open"        # 'open' | 'done' | 'blocked'


class TaskPatch(BaseModel):
    title: str | None = None
    project_id: str | None = None
    meta: str | None = None
    when_bucket: str | None = None
    status: str | None = None
    delegated_task_id: str | None = None


class TaskOut(BaseModel):
    id: str
    project_id: str | None
    title: str
    meta: str
    when_bucket: str
    status: str
    delegated_task_id: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- stores

class ProjectStore:
    async def list(self, business_id: str) -> list[dict]:
        pool = await get_pool()
        if pool is None:
            return []
        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT p.id, p.name, p.category, p.status, p.priority, p.due_date, p.people,
                          p.agents_note, p.created_at, p.updated_at,
                          COUNT(t.id) AS tasks_total,
                          COUNT(t.id) FILTER (WHERE t.status = 'done') AS tasks_done
                   FROM projects p LEFT JOIN tasks t ON t.project_id = p.id
                   WHERE p.business_id = %s
                   GROUP BY p.id ORDER BY p.updated_at DESC""",
                (business_id,),
            )
            rows = await cur.fetchall()
        return [_project_row(r) for r in rows]

    async def create(self, data: ProjectIn, business_id: str) -> dict:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        pid = _new_id("proj")
        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO projects (id, name, category, status, priority, due_date, people, agents_note, business_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
                (pid, data.name, data.category, data.status, data.priority, data.due_date,
                 _json(data.people), data.agents_note, business_id),
            )
        return await self.get(pid, business_id)

    async def get(self, project_id: str, business_id: str) -> dict | None:
        pool = await get_pool()
        if pool is None:
            return None
        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT p.id, p.name, p.category, p.status, p.priority, p.due_date, p.people,
                          p.agents_note, p.created_at, p.updated_at,
                          COUNT(t.id) AS tasks_total,
                          COUNT(t.id) FILTER (WHERE t.status = 'done') AS tasks_done
                   FROM projects p LEFT JOIN tasks t ON t.project_id = p.id
                   WHERE p.id = %s AND p.business_id = %s GROUP BY p.id""",
                (project_id, business_id),
            )
            row = await cur.fetchone()
        return _project_row(row) if row else None

    async def update(self, project_id: str, patch: ProjectPatch, business_id: str) -> dict | None:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        fields = patch.model_dump(exclude_unset=True)
        if not fields:
            return await self.get(project_id, business_id)
        set_parts, params = [], []
        for key, value in fields.items():
            if key == "people":
                set_parts.append("people = %s::jsonb")
                params.append(_json(value))
            else:
                set_parts.append(f"{key} = %s")
                params.append(value)
        set_parts.append("updated_at = now()")
        params.extend([project_id, business_id])
        async with pool.connection() as conn:
            await conn.execute(f"UPDATE projects SET {', '.join(set_parts)} WHERE id = %s AND business_id = %s", params)
        return await self.get(project_id, business_id)

    async def delete(self, project_id: str, business_id: str) -> bool:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        async with pool.connection() as conn:
            cur = await conn.execute("DELETE FROM projects WHERE id = %s AND business_id = %s", (project_id, business_id))
            return cur.rowcount > 0


class TaskStore:
    async def list(self, business_id: str, when_bucket: str | None = None, project_id: str | None = None) -> list[dict]:
        pool = await get_pool()
        if pool is None:
            return []
        clauses, params = ["business_id = %s"], [business_id]
        if when_bucket:
            clauses.append("when_bucket = %s")
            params.append(when_bucket)
        if project_id:
            clauses.append("project_id = %s")
            params.append(project_id)
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""SELECT id, project_id, title, meta, when_bucket, status, delegated_task_id, created_at, updated_at
                    FROM tasks WHERE {' AND '.join(clauses)} ORDER BY created_at ASC""",
                params,
            )
            rows = await cur.fetchall()
        return [_task_row(r) for r in rows]

    async def create(self, data: TaskIn, business_id: str) -> dict:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        tid = _new_id("todo")
        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO tasks (id, project_id, title, meta, when_bucket, status, business_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (tid, data.project_id, data.title, data.meta, data.when_bucket, data.status, business_id),
            )
        return await self.get(tid, business_id)

    async def get(self, task_id: str, business_id: str) -> dict | None:
        pool = await get_pool()
        if pool is None:
            return None
        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT id, project_id, title, meta, when_bucket, status, delegated_task_id, created_at, updated_at
                   FROM tasks WHERE id = %s AND business_id = %s""",
                (task_id, business_id),
            )
            row = await cur.fetchone()
        return _task_row(row) if row else None

    async def update(self, task_id: str, patch: TaskPatch, business_id: str) -> dict | None:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        fields = patch.model_dump(exclude_unset=True)
        if not fields:
            return await self.get(task_id, business_id)
        set_parts = [f"{k} = %s" for k in fields]
        set_parts.append("updated_at = now()")
        params = [*fields.values(), task_id, business_id]
        async with pool.connection() as conn:
            await conn.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = %s AND business_id = %s", params)
        return await self.get(task_id, business_id)

    async def delete(self, task_id: str, business_id: str) -> bool:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        async with pool.connection() as conn:
            cur = await conn.execute("DELETE FROM tasks WHERE id = %s AND business_id = %s", (task_id, business_id))
            return cur.rowcount > 0


def _json(value) -> str:
    import json
    return json.dumps(value)


def _project_row(r) -> dict:
    return {
        "id": r[0], "name": r[1], "category": r[2], "status": r[3], "priority": r[4],
        "due_date": r[5], "people": r[6] or [], "agents_note": r[7],
        "created_at": r[8], "updated_at": r[9],
        "tasks_total": r[10], "tasks_done": r[11],
    }


def _task_row(r) -> dict:
    return {
        "id": r[0], "project_id": r[1], "title": r[2], "meta": r[3], "when_bucket": r[4],
        "status": r[5], "delegated_task_id": r[6], "created_at": r[7], "updated_at": r[8],
    }


projects_store = ProjectStore()
tasks_store = TaskStore()


# ---------------------------------------------------------------- routes

@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(ctx: CurrentContext = Depends(current_context)):
    return await projects_store.list(ctx.business_id)


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, ctx: CurrentContext = Depends(current_context)):
    try:
        return await projects_store.create(body, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, body: ProjectPatch, ctx: CurrentContext = Depends(current_context)):
    try:
        result = await projects_store.update(project_id, body, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, ctx: CurrentContext = Depends(current_context)):
    try:
        deleted = await projects_store.delete(project_id, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(when: str | None = None, project_id: str | None = None, ctx: CurrentContext = Depends(current_context)):
    return await tasks_store.list(ctx.business_id, when_bucket=when, project_id=project_id)


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskIn, ctx: CurrentContext = Depends(current_context)):
    try:
        return await tasks_store.create(body, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, body: TaskPatch, ctx: CurrentContext = Depends(current_context)):
    try:
        result = await tasks_store.update(task_id, body, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, ctx: CurrentContext = Depends(current_context)):
    try:
        deleted = await tasks_store.delete(task_id, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
