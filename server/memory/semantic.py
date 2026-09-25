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
        business_id: str | None = None,
    ) -> list[dict]:
        vec = await self._embed(query)
        if not vec:
            return []

        pool = await get_pool()
        if pool is None:
            return []

        # business_id is enforced via a join, not a denormalized column on messages —
        # keeps this table's shape stable regardless of how Phase 4's scoping evolves.
        clauses = ["m.embedding IS NOT NULL"]
        params: list = [str(vec)]
        if conversation_id:
            clauses.append("m.conversation_id = %s")
            params.append(conversation_id)
        if business_id:
            clauses.append("c.business_id = %s")
            params.append(business_id)
        params.extend([str(vec), limit])

        sql = f"""SELECT m.id, m.content, m.role, m.conversation_id,
                    1 - (m.embedding <=> %s::vector) AS similarity
                FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE {' AND '.join(clauses)}
                ORDER BY m.embedding <=> %s::vector
                LIMIT %s"""

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
