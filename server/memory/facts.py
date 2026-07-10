import logging
from db.connection import get_pool

log = logging.getLogger("dexter.memory.facts")


class FactStore:
    async def set_fact(self, category: str, key: str, value: str, metadata: dict | None = None) -> None:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError("Database unavailable")

        meta = metadata or {}

        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO facts (category, key, value, metadata)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (category, key) DO UPDATE
                SET value = EXCLUDED.value,
                    metadata = EXCLUDED.metadata,
                    updated_at = now(),
                    active = true""",
                (category, key, value, _json_dumps(meta)),
            )

    async def get_fact(self, category: str, key: str) -> str | None:
        pool = await get_pool()
        if pool is None:
            return None

        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT value FROM facts WHERE category = %s AND key = %s AND active = true",
                (category, key),
            )
            row = await cur.fetchone()
            return row[0] if row else None

    async def list_facts(self, category: str | None = None) -> list[dict]:
        pool = await get_pool()
        if pool is None:
            return []

        async with pool.connection() as conn:
            if category:
                cur = await conn.execute(
                    """SELECT id, category, key, value, created_at, updated_at, metadata
                    FROM facts WHERE active = true AND category = %s
                    ORDER BY updated_at DESC""",
                    (category,),
                )
            else:
                cur = await conn.execute(
                    """SELECT id, category, key, value, created_at, updated_at, metadata
                    FROM facts WHERE active = true
                    ORDER BY updated_at DESC"""
                )
            rows = await cur.fetchall()

        return [
            {
                "id": str(r[0]),
                "category": r[1],
                "key": r[2],
                "value": r[3],
                "created_at": r[4].isoformat(),
                "updated_at": r[5].isoformat(),
                "metadata": r[6],
            }
            for r in rows
        ]

    async def delete_fact(self, category: str, key: str) -> None:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError("Database unavailable")

        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE facts SET active = false, updated_at = now() WHERE category = %s AND key = %s",
                (category, key),
            )


def _json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj)
