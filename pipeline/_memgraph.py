"""Memgraph (Bolt) connection management.

Mirrors the pattern in _db.py: lazy singleton driver, single cypher() helper.
The driver is created on first use and reused across tool calls.
"""
import os

from neo4j import AsyncGraphDatabase

from _tracing import mark_span_error, tracer

MEMGRAPH_URI = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")

_driver = None


async def get_driver():
    global _driver
    if _driver is None:
        # Memgraph ships with auth disabled by default; ("", "") satisfies
        # the neo4j driver's requirement for credentials.
        _driver = AsyncGraphDatabase.driver(MEMGRAPH_URI, auth=("", ""))
    return _driver


async def cypher_query(query: str, params: dict | None = None) -> list[dict]:
    """Execute a Cypher query and return all rows as a list of dicts."""
    with tracer.start_as_current_span("memgraph.query") as span:
        span.set_attribute("db.system", "memgraph")
        span.set_attribute("db.statement", query)
        try:
            driver = await get_driver()
            async with driver.session() as session:
                result = await session.run(query, parameters=params or {})
                data = await result.data()
                span.set_attribute("db.rows_returned", len(data))
                return data
        except Exception as exc:
            mark_span_error(span, exc)
            raise
