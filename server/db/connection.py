import logging
from pathlib import Path
from psycopg_pool import AsyncConnectionPool
from config import settings

log = logging.getLogger("dexter.db")

_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool | None:
    global _pool
    if _pool is None:
        try:
            _pool = AsyncConnectionPool(
                conninfo=settings.database_url,
                min_size=2,
                max_size=10,
                open=False,
            )
            await _pool.open()
            log.info("Database pool opened")
        except Exception as e:
            log.error("Failed to create database pool: %s", e)
            _pool = None
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("Database pool closed")


async def init_db() -> None:
    pool = await get_pool()
    if pool is None:
        log.warning("No database connection — skipping schema init")
        return

    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()

    try:
        async with pool.connection() as conn:
            await conn.execute(sql)
            log.info("Database schema initialized")
    except Exception as e:
        log.error("Schema init failed: %s", e)
