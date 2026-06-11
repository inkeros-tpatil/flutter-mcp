"""PostgreSQL tools — introspection, query, and write operations."""

from opentelemetry import trace

from _db import _execute, _fetch, _fetchrow, _fetchval, get_pool
from _tracing import mark_span_error, tracer
from tools import tool


@tool
async def list_tables(schema: str = "public") -> list[dict]:
    """List all tables in the given schema."""
    trace.get_current_span().set_attribute("schema", schema)
    rows = await _fetch(
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = $1
        ORDER BY table_name
        """,
        schema,
    )
    return [dict(r) for r in rows]


@tool
async def describe_table(table_name: str, schema: str = "public") -> list[dict]:
    """Describe columns of a table: name, type, nullable, default."""
    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)
    rows = await _fetch(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """,
        schema,
        table_name,
    )
    return [dict(r) for r in rows]


@tool
async def query(sql: str, params: list | None = None) -> list[dict]:
    """Run a read-only SELECT query and return rows as a list of dicts."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
        raise ValueError(
            "Only SELECT / WITH queries are allowed via this tool. Use execute() for writes."
        )
    trace.get_current_span().set_attribute("db.statement", sql)
    rows = await _fetch(sql, *(params or []))
    return [dict(r) for r in rows]


@tool
async def execute(sql: str, params: list | None = None) -> dict:
    """Execute an INSERT, UPDATE, DELETE, or DDL statement. Returns status string and row count."""
    if sql.strip().upper().startswith("SELECT"):
        raise ValueError("Use query() for SELECT statements.")
    trace.get_current_span().set_attribute("db.statement", sql)
    result = await _execute(sql, *(params or []))
    parts = result.split()
    row_count = int(parts[-1]) if parts and parts[-1].isdigit() else 0
    trace.get_current_span().set_attribute("db.rows_affected", row_count)
    return {"status": result, "row_count": row_count}


@tool
async def list_databases() -> list[str]:
    """List all databases on the PostgreSQL server."""
    rows = await _fetch(
        "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
    )
    return [r["datname"] for r in rows]


@tool
async def get_table_indexes(table_name: str, schema: str = "public") -> list[dict]:
    """List indexes on a table."""
    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)
    rows = await _fetch(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = $1 AND tablename = $2
        ORDER BY indexname
        """,
        schema,
        table_name,
    )
    return [dict(r) for r in rows]


@tool
async def get_row_count(table_name: str, schema: str = "public") -> dict:
    """Return the approximate and exact row count for a table."""
    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)
    approx = await _fetchval(
        """
        SELECT reltuples::bigint
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = $1 AND c.relname = $2
        """,
        schema,
        table_name,
    )
    exact = await _fetchval(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
    span.set_attribute("row_count.exact", exact)
    return {"approximate": approx, "exact": exact}


@tool
async def create_table(
    table_name: str,
    columns: list[dict],
    schema: str = "public",
    if_not_exists: bool = True,
) -> dict:
    """Create a table with the given column definitions.

    Each column dict must have:
      - name: str
      - type: str  (e.g. "TEXT", "INTEGER", "BOOLEAN", "TIMESTAMPTZ")
    Optional keys per column:
      - primary_key: bool
      - not_null: bool
      - unique: bool
      - default: str  (raw SQL default expression)

    Example columns:
      [{"name": "id", "type": "SERIAL", "primary_key": true},
       {"name": "email", "type": "TEXT", "not_null": true, "unique": true},
       {"name": "created_at", "type": "TIMESTAMPTZ", "default": "NOW()"}]
    """
    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)
    span.set_attribute("column_count", len(columns))

    col_defs = []
    for col in columns:
        parts = [f'"{col["name"]}"', col["type"]]
        if col.get("primary_key"):
            parts.append("PRIMARY KEY")
        if col.get("not_null") and not col.get("primary_key"):
            parts.append("NOT NULL")
        if col.get("unique") and not col.get("primary_key"):
            parts.append("UNIQUE")
        if col.get("default") is not None:
            parts.append(f'DEFAULT {col["default"]}')
        col_defs.append(" ".join(parts))

    exists_clause = "IF NOT EXISTS " if if_not_exists else ""
    ddl = f'CREATE TABLE {exists_clause}"{schema}"."{table_name}" (\n  {",  ".join(col_defs)}\n)'
    await _execute(ddl)
    return {"created": table_name, "schema": schema, "ddl": ddl}


@tool
async def insert_row(
    table_name: str,
    data: dict,
    schema: str = "public",
    returning: list[str] | None = None,
) -> dict:
    """Insert a single row into a table.

    - data: column-to-value mapping, e.g. {"name": "Alice", "age": 30}
    - returning: optional list of column names to return after insert, e.g. ["id", "created_at"]
    """
    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)

    cols = list(data.keys())
    vals = list(data.values())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    col_list = ", ".join(f'"{c}"' for c in cols)
    sql = f'INSERT INTO "{schema}"."{table_name}" ({col_list}) VALUES ({placeholders})'

    if returning:
        sql += " RETURNING " + ", ".join(f'"{c}"' for c in returning)
        row = await _fetchrow(sql, *vals)
        return dict(row)
    else:
        status = await _execute(sql, *vals)
        return {"status": status}


@tool
async def insert_rows(
    table_name: str,
    rows: list[dict],
    schema: str = "public",
) -> dict:
    """Bulk-insert multiple rows into a table.

    All dicts in rows must share the same keys (columns).
    Returns the number of rows inserted.
    """
    if not rows:
        return {"inserted": 0}

    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)
    span.set_attribute("row_count", len(rows))

    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    n_cols = len(cols)
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            with tracer.start_as_current_span("db.bulk_insert") as db_span:
                db_span.set_attribute("db.system", "postgresql")
                db_span.set_attribute("db.rows_to_insert", len(rows))
                try:
                    inserted = 0
                    for row in rows:
                        vals = [row[c] for c in cols]
                        placeholders = ", ".join(f"${i + 1}" for i in range(n_cols))
                        sql = f'INSERT INTO "{schema}"."{table_name}" ({col_list}) VALUES ({placeholders})'
                        await conn.execute(sql, *vals)
                        inserted += 1
                    db_span.set_attribute("db.rows_inserted", inserted)
                except Exception as exc:
                    mark_span_error(db_span, exc)
                    raise

    return {"inserted": inserted, "table": table_name}


@tool
async def get_rows(
    table_name: str,
    schema: str = "public",
    columns: list[str] | None = None,
    where: dict | None = None,
    order_by: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Retrieve rows from a table without writing raw SQL.

    - columns: list of column names to select (None = all)
    - where: equality filters, e.g. {"status": "active", "role": "admin"}
    - order_by: column name, optionally with " ASC" or " DESC"
    - limit: max rows to return (default 100, max 1000)
    - offset: rows to skip for pagination
    """
    limit = min(limit, 1000)
    span = trace.get_current_span()
    span.set_attribute("table_name", table_name)
    span.set_attribute("schema", schema)
    span.set_attribute("limit", limit)
    span.set_attribute("offset", offset)

    col_clause = "*" if not columns else ", ".join(f'"{c}"' for c in columns)
    sql = f'SELECT {col_clause} FROM "{schema}"."{table_name}"'

    params: list = []
    if where:
        conditions = []
        for col, val in where.items():
            params.append(val)
            conditions.append(f'"{col}" = ${len(params)}')
        sql += " WHERE " + " AND ".join(conditions)

    if order_by:
        sql += f" ORDER BY {order_by}"

    params.append(limit)
    sql += f" LIMIT ${len(params)}"
    params.append(offset)
    sql += f" OFFSET ${len(params)}"

    rows = await _fetch(sql, *params)
    return [dict(r) for r in rows]
