"""Guard configuration (docs/BACKEND_TASKS.md P6) — runtime-editable caps and rules,
so raising/lowering them is a Settings-panel action instead of an .env edit + restart.

The in-memory singleton is the source of truth executor.py reads from on every spawn —
a config change takes effect immediately, without a restart. Postgres, when reachable,
is a best-effort persistence layer on top of that (survives a restart); when it isn't,
the config still works for the life of the process, same graceful-degradation contract
as everything else here.
"""
from __future__ import annotations

import json
import uuid
import logging

from pydantic import BaseModel, Field

from config import settings
from db.connection import get_pool

log = logging.getLogger("dexter.shadow.guard_config")


class CustomRule(BaseModel):
    id: str = Field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:8]}")
    name: str
    keyword: str = ""            # empty = applies to every task, matched case-insensitively against the title
    max_spend: float | None = None
    require_approval: bool = False
    enabled: bool = True


class GuardConfig(BaseModel):
    daily_budget: float = settings.daily_cloud_budget
    per_task_budget_default: float = settings.per_task_budget_default
    high_cost_multiplier: float = 2.0
    long_running_minutes: int = 30
    custom_rules: list[CustomRule] = []


class GuardConfigStore:
    _instance: "GuardConfigStore | None" = None
    _config: GuardConfig

    def __new__(cls) -> "GuardConfigStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = GuardConfig()
            cls._instance._loaded = False
        return cls._instance

    async def get(self) -> GuardConfig:
        if not self._loaded:
            await self._load_from_db()
        return self._config

    async def _load_from_db(self) -> None:
        self._loaded = True  # only ever try once per process — a slow/down DB shouldn't be retried every call
        pool = await get_pool()
        if pool is None:
            return
        try:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """SELECT daily_budget, per_task_budget_default, high_cost_multiplier,
                              long_running_minutes, custom_rules FROM guard_config WHERE id = 1"""
                )
                row = await cur.fetchone()
            if row:
                self._config = GuardConfig(
                    daily_budget=float(row[0]), per_task_budget_default=float(row[1]),
                    high_cost_multiplier=float(row[2]), long_running_minutes=row[3],
                    custom_rules=[CustomRule(**r) for r in (row[4] or [])],
                )
        except Exception as e:
            log.warning("Could not load guard config from database, using defaults: %s", e)

    async def _persist(self) -> None:
        pool = await get_pool()
        if pool is None:
            return
        try:
            async with pool.connection() as conn:
                await conn.execute(
                    """INSERT INTO guard_config (id, daily_budget, per_task_budget_default,
                            high_cost_multiplier, long_running_minutes, custom_rules)
                       VALUES (1, %s, %s, %s, %s, %s::jsonb)
                       ON CONFLICT (id) DO UPDATE SET
                            daily_budget = EXCLUDED.daily_budget,
                            per_task_budget_default = EXCLUDED.per_task_budget_default,
                            high_cost_multiplier = EXCLUDED.high_cost_multiplier,
                            long_running_minutes = EXCLUDED.long_running_minutes,
                            custom_rules = EXCLUDED.custom_rules,
                            updated_at = now()""",
                    (
                        self._config.daily_budget, self._config.per_task_budget_default,
                        self._config.high_cost_multiplier, self._config.long_running_minutes,
                        json.dumps([r.model_dump() for r in self._config.custom_rules]),
                    ),
                )
        except Exception as e:
            log.warning("Could not persist guard config to database (kept in memory): %s", e)

    async def update(self, patch: dict) -> GuardConfig:
        await self.get()  # ensure loaded first, so a patch doesn't clobber a DB-loaded value with defaults
        self._config = self._config.model_copy(update={k: v for k, v in patch.items() if v is not None})
        await self._persist()
        return self._config

    async def add_rule(self, name: str, keyword: str = "", max_spend: float | None = None, require_approval: bool = False) -> GuardConfig:
        await self.get()
        rule = CustomRule(name=name, keyword=keyword, max_spend=max_spend, require_approval=require_approval)
        self._config = self._config.model_copy(update={"custom_rules": [*self._config.custom_rules, rule]})
        await self._persist()
        return self._config

    async def remove_rule(self, rule_id: str) -> GuardConfig:
        await self.get()
        self._config = self._config.model_copy(
            update={"custom_rules": [r for r in self._config.custom_rules if r.id != rule_id]}
        )
        await self._persist()
        return self._config


guard_config_store = GuardConfigStore()
