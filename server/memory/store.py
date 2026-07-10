import json
import logging
from models import Message, Role, Protocol
from db.connection import get_pool

log = logging.getLogger("dexter.memory.store")


class ConversationStore:
    async def create_conversation(self, protocol: Protocol) -> str:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError("Database unavailable")

        async with pool.connection() as conn:
            row = await conn.execute(
                "INSERT INTO conversations (protocol) VALUES (%s) RETURNING id",
                (protocol.value,),
            )
            result = await row.fetchone()
            return str(result[0])

    async def save_message(self, conversation_id: str, message: Message) -> None:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError("Database unavailable")

        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, protocol, timestamp, tool_calls, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)""",
                (
                    message.id,
                    conversation_id,
                    message.role.value,
                    message.content,
                    message.protocol.value,
                    message.timestamp,
                    json.dumps([tc.model_dump() for tc in message.tool_calls]),
                    json.dumps(message.metadata),
                ),
            )

    async def get_messages(self, conversation_id: str, limit: int = 50) -> list[Message]:
        pool = await get_pool()
        if pool is None:
            return []

        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT id, role, content, protocol, timestamp, tool_calls, metadata
                FROM messages WHERE conversation_id = %s
                ORDER BY timestamp ASC LIMIT %s""",
                (conversation_id, limit),
            )
            rows = await cur.fetchall()

        return [
            Message(
                id=r[0],
                role=Role(r[1]),
                content=r[2],
                protocol=Protocol(r[3]),
                timestamp=r[4],
                tool_calls=r[5] if r[5] else [],
                metadata=r[6] if r[6] else {},
            )
            for r in rows
        ]

    async def list_conversations(self, limit: int = 20) -> list[dict]:
        pool = await get_pool()
        if pool is None:
            return []

        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT c.id, c.protocol, c.created_at, c.updated_at, c.title, c.metadata,
                    (SELECT content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.timestamp DESC LIMIT 1) AS last_message
                FROM conversations c
                ORDER BY c.updated_at DESC LIMIT %s""",
                (limit,),
            )
            rows = await cur.fetchall()

        return [
            {
                "id": str(r[0]),
                "protocol": r[1],
                "created_at": r[2].isoformat(),
                "updated_at": r[3].isoformat(),
                "title": r[4],
                "metadata": r[5],
                "last_message": r[6],
            }
            for r in rows
        ]
