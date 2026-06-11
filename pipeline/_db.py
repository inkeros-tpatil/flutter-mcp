import os

import asyncpg

from _tracing import mark_span_error, tracer

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://devuser:devpassword@localhost:5432/devdb",
)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def _fetch(sql: str, *params) -> list:
    pool = await get_pool()
    with tracer.start_as_current_span("db.fetch") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", sql)
        try:
            rows = await pool.fetch(sql, *params)
            span.set_attribute("db.rows_returned", len(rows))
            return rows
        except Exception as exc:
            mark_span_error(span, exc)
            raise


async def _fetchval(sql: str, *params):
    pool = await get_pool()
    with tracer.start_as_current_span("db.fetchval") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", sql)
        try:
            return await pool.fetchval(sql, *params)
        except Exception as exc:
            mark_span_error(span, exc)
            raise


async def _fetchrow(sql: str, *params):
    pool = await get_pool()
    with tracer.start_as_current_span("db.fetchrow") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", sql)
        try:
            return await pool.fetchrow(sql, *params)
        except Exception as exc:
            mark_span_error(span, exc)
            raise


async def _execute(sql: str, *params) -> str:
    pool = await get_pool()
    with tracer.start_as_current_span("db.execute") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", sql)
        try:
            return await pool.execute(sql, *params)
        except Exception as exc:
            mark_span_error(span, exc)
            raise
