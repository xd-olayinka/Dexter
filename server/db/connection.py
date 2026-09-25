import logging
import time
from pathlib import Path
from psycopg_pool import AsyncConnectionPool, PoolTimeout
from config import settings

log = logging.getLogger("dexter.db")

_pool: AsyncConnectionPool | None = None
_last_failure_at: float = 0.0

# psycopg_pool's default open() timeout is 30s, and it's genuinely reachable when
# Postgres just isn't there (this backend runs with zero external services by
# design). Without a short connect timeout AND a failure cooldown, every single
# request that touches persistence would stall for up to 30s, and would keep
# retrying on every subsequent call — the opposite of the "degrades gracefully"
# contract every other module here follows. CONNECT_TIMEOUT_S bounds one attempt;
# FAILURE_COOLDOWN_S stops us from retrying that attempt on every request in between.
CONNECT_TIMEOUT_S = 2.0
FAILURE_COOLDOWN_S = 15.0


async def get_pool() -> AsyncConnectionPool | None:
    global _pool, _last_failure_at
    if _pool is not None:
        return _pool

    if time.monotonic() - _last_failure_at < FAILURE_COOLDOWN_S:
        return None

    try:
        pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            open=False,
        )
        await pool.open(wait=True, timeout=CONNECT_TIMEOUT_S)
        _pool = pool
        log.info("Database pool opened")
        return _pool
    except (PoolTimeout, Exception) as e:
        log.warning("Database unavailable (retrying in %.0fs): %s", FAILURE_COOLDOWN_S, e)
        _last_failure_at = time.monotonic()
        return None


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
