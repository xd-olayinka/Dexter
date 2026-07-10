import logging
from typing import Callable, Awaitable
from db.connection import get_pool

log = logging.getLogger("dexter.memory.semantic")


class SemanticMemory:
    def __init__(self, embed_fn: Callable[[str], Awaitable[list[float]]]):
        self._embed = embed_fn

    async def index_message(self, conversation_id: str, message_id: str, content: str) -> None:
        vec = await self._embed(content)
        if not vec:
            log.warning("Empty embedding for message %s — skipping index", message_id)
            return

        pool = await get_pool()
        if pool is None:
            return

        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE messages SET embedding = %s::vector WHERE id = %s",
                (str(vec), message_id),
            )

    async def recall(
        self,
        query: str,
        limit: int = 5,
        conversation_id: str | None = None,
    ) -> list[dict]:
        vec = await self._embed(query)
        if not vec:
            return []

        pool = await get_pool()
        if pool is None:
            return []

        if conversation_id:
            sql = """SELECT id, content, role, conversation_id,
                        1 - (embedding <=> %s::vector) AS similarity
                    FROM messages
                    WHERE embedding IS NOT NULL AND conversation_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s"""
            params = (str(vec), conversation_id, str(vec), limit)
        else:
            sql = """SELECT id, content, role, conversation_id,
                        1 - (embedding <=> %s::vector) AS similarity
                    FROM messages
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s"""
            params = (str(vec), str(vec), limit)

        async with pool.connection() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()

        return [
            {
                "message_id": r[0],
                "content": r[1],
                "role": r[2],
                "conversation_id": str(r[3]),
                "similarity": float(r[4]),
            }
            for r in rows
        ]
