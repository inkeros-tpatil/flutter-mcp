# MCP API Specification — postgres-mcp

**Protocol:** Model Context Protocol (MCP) over JSON-RPC 2.0  
**Framework:** FastMCP `fastmcp-slim[server]>=3.4.2`

| Module | Responsibility |
|--------|---------------|
| `postgres_mcp.py` | Entry point — creates `FastMCP`, calls `tools.load_all(mcp)`, runs transport |
| `_tracing.py` | `TracerProvider` setup, `tracer`, alert hooks (`SlackAlertHook`, `PagerDutyAlertHook`), `mark_span_error`, `trigger_alerts` |
| `_db.py` | asyncpg connection pool, `_fetch` / `_fetchval` / `_fetchrow` / `_execute` helpers |
| `tools/__init__.py` | `@tool` decorator, `_registry`, `load_all(mcp)` auto-discovery |
| `tools/db.py` | 12 PostgreSQL tool implementations |
| `tools/graph_rag.py` | Graph RAG stub (raises `NotImplementedError` — implement to activate) |

---

## Transport

The server supports two transports selected at startup via `MCP_TRANSPORT`.

| Transport | When | Endpoint |
|-----------|------|----------|
| SSE | `MCP_TRANSPORT=sse` | `http://<host>:<MCP_PORT>/sse` |
| stdio | default (unset) | stdin / stdout |

The project `.mcp.json` points Claude Code at the SSE endpoint:

```json
{
  "mcpServers": {
    "postgres": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

Relevant environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_TRANSPORT` | `stdio` | `sse` to run as HTTP server |
| `MCP_PORT` | `8000` | HTTP port for SSE transport |
| `DATABASE_URL` | `postgresql://devuser:devpassword@localhost:5432/devdb` | asyncpg connection string |

---

## Tool Registration

### Architecture

Tools are organised as a plugin system. Adding a new tool set requires no changes to existing files.

```
pipeline/
  postgres_mcp.py      # Entry point — 10 lines
  _tracing.py          # TracerProvider, alert hooks, span error helpers
  _db.py               # asyncpg pool + db.fetch / fetchval / fetchrow / execute
  tools/
    __init__.py        # @tool decorator + load_all(mcp)
    db.py              # 12 PostgreSQL tools
    graph_rag.py       # Graph RAG tools (stub — add implementation to activate)
    <any>.py           # Drop a new file here; it is discovered automatically
```

### `@tool` decorator

Defined in `tools/__init__.py`. Wraps every tool call in a `tool.<fn_name>` span and centralises error recording and alert firing — tool functions contain no span boilerplate.

```python
# tools/my_tools.py  — a complete new tool module
from opentelemetry import trace
from tools import tool

@tool
async def my_tool(arg: str) -> dict:
    """One-line description shown in the MCP manifest."""
    trace.get_current_span().set_attribute("arg", arg)
    ...
```

FastMCP derives the manifest from the decorated function:

| Manifest field | Source |
|----------------|--------|
| `name` | Function name (snake_case) |
| `description` | First line of the docstring |
| `inputSchema` | Python type annotations → JSON Schema |
| `outputSchema` | Return type annotation → JSON Schema |

`functools.wraps` preserves `__name__`, `__doc__`, and `__annotations__` on the wrapper, so FastMCP sees the original function's metadata. `inspect.signature` follows `__wrapped__` to the original for parameter introspection.

### `load_all(mcp)`

Called once at startup in `postgres_mcp.py`. Uses `pkgutil.iter_modules` to discover every non-private module in `tools/` (any file not starting with `_`), imports it (which fires the `@tool` decorators), then calls `mcp.tool()(fn)` for each collected function.

```python
# postgres_mcp.py
mcp = FastMCP("PostgreSQL")
tools.load_all(mcp)
```

### Adding a new tool set

1. Create `pipeline/tools/<name>.py`
2. Decorate async functions with `@tool`
3. Restart the server — the module is discovered automatically

No changes to `postgres_mcp.py`, `tools/__init__.py`, or any existing file.

### Calling a tool (JSON-RPC)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_tables",
    "arguments": { "schema": "public" }
  }
}
```

Successful response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      { "type": "text", "text": "[{\"table_name\": \"users\", \"table_type\": \"BASE TABLE\"}]" }
    ],
    "isError": false
  }
}
```

Error response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      { "type": "text", "text": "column \"foo\" does not exist" }
    ],
    "isError": true
  }
}
```

---

## Error Model

The `@tool` decorator in `tools/__init__.py` is the single error boundary for all tool calls. It opens the `tool.*` span before invoking the function body, so **every exception — including input validation errors — is traced and triggers alerts**.

```
@tool wrapper opens tool.* span
        │
        ├─ fn() raises ValueError (input validation)
        │       mark_span_error(tool_span, exc)   ← StatusCode.ERROR + stack trace
        │       trigger_alerts(tool_span, exc)    ← Slack / PagerDuty (async)
        │       re-raise → FastMCP → isError: true
        │
        └─ fn() calls db helper → db.* span opens
                │
                └─ asyncpg raises
                        mark_span_error(db_span, exc)   ← StatusCode.ERROR on db span
                        re-raise → propagates to @tool wrapper
                        mark_span_error(tool_span, exc) ← StatusCode.ERROR on tool span
                        trigger_alerts(tool_span, exc)  ← alert fires once, at tool boundary
                        re-raise → FastMCP → isError: true
```

### Exception taxonomy

**Input validation** (`ValueError`)  
Raised inside the tool function before any DB call. The tool span is open and records the error. Alerts fire. Callers see `isError: true`.

Occurs in:
- `query`: SQL does not start with `SELECT` or `WITH`
- `execute`: SQL starts with `SELECT`

**Database errors** (`asyncpg.PostgresError` subclasses)  
Raised by asyncpg inside a `db.*` span. Both the `db.*` span and the enclosing `tool.*` span are marked as errors.

| asyncpg exception | SQLSTATE | Typical cause |
|-------------------|----------|---------------|
| `UndefinedTableError` | 42P01 | Table does not exist |
| `UndefinedColumnError` | 42703 | Column does not exist |
| `UniqueViolationError` | 23505 | Unique constraint |
| `NotNullViolationError` | 23502 | NOT NULL constraint |
| `ForeignKeyViolationError` | 23503 | FK constraint |
| `SyntaxOrAccessError` | 42xxx | Malformed SQL |
| `QueryCanceledError` | 57014 | `statement_timeout` hit |

**Timeout errors** (`asyncio.TimeoutError`, `asyncpg.QueryCanceledError`)  
Both are classified as timeouts. The span gets `error.type = "timeout"`. All other exceptions set `error.type` to the Python class name.

### What the caller receives

`isError: true` with the exception message as `content[0].text`. The full stack trace is in the OTel span (visible in Phoenix) and is never forwarded to the caller.

---

## Tools

### `list_tables`

List all tables in a schema.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `schema` | `string` | no | `"public"` | PostgreSQL schema name |

**Response** — `array of objects`

```json
[
  { "table_name": "users",   "table_type": "BASE TABLE" },
  { "table_name": "v_active", "table_type": "VIEW" }
]
```

| Field | Type | Values |
|-------|------|--------|
| `table_name` | string | |
| `table_type` | string | `"BASE TABLE"`, `"VIEW"`, `"FOREIGN"` |

**Errors**

| Condition | Type |
|-----------|------|
| Schema does not exist | returns empty array (no rows match) |
| DB connection failure | `asyncpg.PostgresConnectionError` |

---

### `describe_table`

Describe all columns in a table, in ordinal position order.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `table_name` | `string` | yes | — | |
| `schema` | `string` | no | `"public"` | |

**Response** — `array of objects`

```json
[
  {
    "column_name": "id",
    "data_type": "integer",
    "is_nullable": "NO",
    "column_default": "nextval('users_id_seq'::regclass)",
    "character_maximum_length": null
  },
  {
    "column_name": "email",
    "data_type": "character varying",
    "is_nullable": "NO",
    "column_default": null,
    "character_maximum_length": 255
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `column_name` | string | |
| `data_type` | string | PostgreSQL type name |
| `is_nullable` | string | `"YES"` or `"NO"` |
| `column_default` | string \| null | Raw SQL default expression |
| `character_maximum_length` | integer \| null | Set for `character varying` / `char` |

**Errors**

| Condition | Type |
|-----------|------|
| Table does not exist | returns empty array |

---

### `query`

Run a read-only `SELECT` or `WITH` query and return all rows.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `sql` | `string` | yes | — | Must start with `SELECT` or `WITH` (case-insensitive after trimming) |
| `params` | `array` | no | `null` | Positional bind parameters (`$1`, `$2`, …) |

**Response** — `array of objects`

One object per row; keys are column names.

```json
[
  { "id": 1, "email": "alice@example.com", "created_at": "2024-01-01T00:00:00+00:00" }
]
```

**Errors**

| Condition | Type | Traced |
|-----------|------|--------|
| SQL does not start with `SELECT` / `WITH` | `ValueError` — `"Only SELECT / WITH queries are allowed…"` | Yes |
| SQL syntax error | `asyncpg.PostgresSyntaxError` | Yes |
| Unknown column / table | `asyncpg.UndefinedColumnError` / `UndefinedTableError` | Yes |
| Timeout | `asyncpg.QueryCanceledError` → `error.type = "timeout"` | Yes |

---

### `execute`

Execute an `INSERT`, `UPDATE`, `DELETE`, or DDL statement.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `sql` | `string` | yes | — | Must not start with `SELECT` |
| `params` | `array` | no | `null` | Positional bind parameters |

**Response** — `object`

```json
{ "status": "UPDATE 3", "row_count": 3 }
```

| Field | Type | Notes |
|-------|------|-------|
| `status` | string | PostgreSQL command tag, e.g. `"INSERT 0 1"`, `"UPDATE 3"`, `"CREATE TABLE"` |
| `row_count` | integer | Last space-separated token of `status` parsed as int; `0` if not numeric |

**Errors**

| Condition | Type | Traced |
|-----------|------|--------|
| SQL starts with `SELECT` | `ValueError` — `"Use query() for SELECT statements."` | Yes |
| Constraint violation | `asyncpg.UniqueViolationError` / `NotNullViolationError` / etc. | Yes |
| DDL permission denied | `asyncpg.InsufficientPrivilegeError` | Yes |

---

### `list_databases`

List all non-template databases on the server.

**Parameters** — none

**Response** — `array of string`

```json
["devdb", "postgres"]
```

**Errors**

| Condition | Type |
|-----------|------|
| Insufficient privilege to query `pg_database` | `asyncpg.InsufficientPrivilegeError` |

---

### `get_table_indexes`

List all indexes defined on a table.

**Parameters**

| Name | Type | Required | Default |
|------|------|----------|---------|
| `table_name` | `string` | yes | — |
| `schema` | `string` | no | `"public"` |

**Response** — `array of objects`

```json
[
  {
    "indexname": "users_pkey",
    "indexdef": "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)"
  },
  {
    "indexname": "users_email_idx",
    "indexdef": "CREATE UNIQUE INDEX users_email_idx ON public.users USING btree (email)"
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `indexname` | string | Index name |
| `indexdef` | string | Full `CREATE INDEX` DDL |

**Errors**

| Condition | Type |
|-----------|------|
| Table does not exist | returns empty array |

---

### `get_row_count`

Return the approximate and exact row count for a table.

The approximate count reads `pg_class.reltuples` (updated by ANALYZE, cheap). The exact count issues `SELECT COUNT(*)` (full table scan, always accurate).

**Parameters**

| Name | Type | Required | Default |
|------|------|----------|---------|
| `table_name` | `string` | yes | — |
| `schema` | `string` | no | `"public"` |

**Response** — `object`

```json
{ "approximate": 9800, "exact": 9823 }
```

| Field | Type | Notes |
|-------|------|-------|
| `approximate` | integer | From `pg_class.reltuples`; may be `-1` if stats have never been collected |
| `exact` | integer | From `COUNT(*)` — accurate but potentially slow on large tables |

**Errors**

| Condition | Type |
|-----------|------|
| Table does not exist | `asyncpg.UndefinedTableError` on the `COUNT(*)` call |

---

### `create_table`

Build and execute a `CREATE TABLE` statement from a column definition list.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `table_name` | `string` | yes | — | |
| `columns` | `array of ColumnDef` | yes | — | See below |
| `schema` | `string` | no | `"public"` | |
| `if_not_exists` | `boolean` | no | `true` | Adds `IF NOT EXISTS` clause |

**ColumnDef object**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | `string` | yes | Column name |
| `type` | `string` | yes | SQL type: `TEXT`, `INTEGER`, `BOOLEAN`, `TIMESTAMPTZ`, `SERIAL`, etc. |
| `primary_key` | `boolean` | no | Adds `PRIMARY KEY`; implies NOT NULL and UNIQUE |
| `not_null` | `boolean` | no | Adds `NOT NULL`; ignored when `primary_key: true` |
| `unique` | `boolean` | no | Adds `UNIQUE`; ignored when `primary_key: true` |
| `default` | `string` | no | Raw SQL expression, e.g. `"NOW()"`, `"0"`, `"gen_random_uuid()"` |

**Request example**

```json
{
  "table_name": "users",
  "schema": "public",
  "columns": [
    { "name": "id",         "type": "SERIAL",      "primary_key": true },
    { "name": "email",      "type": "TEXT",         "not_null": true, "unique": true },
    { "name": "created_at", "type": "TIMESTAMPTZ",  "default": "NOW()" }
  ]
}
```

**Response** — `object`

```json
{
  "created": "users",
  "schema": "public",
  "ddl": "CREATE TABLE IF NOT EXISTS \"public\".\"users\" (\n  \"id\" SERIAL PRIMARY KEY,  \"email\" TEXT NOT NULL UNIQUE,  \"created_at\" TIMESTAMPTZ DEFAULT NOW()\n)"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `created` | string | Table name echoed back |
| `schema` | string | Schema echoed back |
| `ddl` | string | The exact DDL that was executed |

**Errors**

| Condition | Type |
|-----------|------|
| Table already exists and `if_not_exists: false` | `asyncpg.DuplicateTableError` |
| Invalid SQL type string | `asyncpg.PostgresSyntaxError` |
| Schema does not exist | `asyncpg.InvalidSchemaNameError` |

---

### `insert_row`

Insert a single row. Optionally return specified columns from the inserted row.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `table_name` | `string` | yes | — | |
| `data` | `object` | yes | — | Column-to-value map |
| `schema` | `string` | no | `"public"` | |
| `returning` | `array of string` | no | `null` | Column names to return via `RETURNING` |

**Request example**

```json
{
  "table_name": "users",
  "data": { "email": "bob@example.com" },
  "returning": ["id", "created_at"]
}
```

**Response** — shape depends on `returning`

Without `returning`:
```json
{ "status": "INSERT 0 1" }
```

With `returning`:
```json
{ "id": 42, "created_at": "2024-06-11T09:00:00+00:00" }
```

When `returning` is set, the response is a flat object with one key per requested column. When omitted, only the PostgreSQL command tag is returned.

**Errors**

| Condition | Type |
|-----------|------|
| Column does not exist | `asyncpg.UndefinedColumnError` |
| NOT NULL violation | `asyncpg.NotNullViolationError` |
| Unique constraint | `asyncpg.UniqueViolationError` |
| FK constraint | `asyncpg.ForeignKeyViolationError` |

---

### `insert_rows`

Bulk-insert multiple rows inside a single transaction. All rows must have identical keys.

Returns `{"inserted": 0}` immediately if `rows` is empty. The `tool.insert_rows` span is still opened — the early return occurs inside it.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `table_name` | `string` | yes | — | |
| `rows` | `array of object` | yes | — | All objects must share the same keys |
| `schema` | `string` | no | `"public"` | |

**Request example**

```json
{
  "table_name": "users",
  "rows": [
    { "email": "carol@example.com" },
    { "email": "dave@example.com" }
  ]
}
```

**Response** — `object`

```json
{ "inserted": 2, "table": "users" }
```

| Field | Type | Notes |
|-------|------|-------|
| `inserted` | integer | Number of rows successfully inserted |
| `table` | string | Table name echoed back |

**Transaction behaviour**  
All inserts run inside a single `asyncpg` transaction. Any row failing a constraint rolls back the entire batch. The `inserted` count reflects rows committed; on error it is not returned (the exception propagates).

**Errors**

| Condition | Type |
|-----------|------|
| Mismatched keys across rows | `KeyError` at Python level |
| Any constraint violation | rolls back full batch; raises corresponding `asyncpg` error |

---

### `get_rows`

Retrieve rows from a table without writing SQL. Supports column selection, equality filtering, ordering, and pagination.

**Parameters**

| Name | Type | Required | Default | Notes |
|------|------|----------|---------|-------|
| `table_name` | `string` | yes | — | |
| `schema` | `string` | no | `"public"` | |
| `columns` | `array of string` | no | `null` | Column names to select; `null` → `SELECT *` |
| `where` | `object` | no | `null` | Equality filters; keys are column names, values are exact match values |
| `order_by` | `string` | no | `null` | Column name, optionally followed by `" ASC"` or `" DESC"` |
| `limit` | `integer` | no | `100` | Max rows. Silently capped at `1000` server-side |
| `offset` | `integer` | no | `0` | Rows to skip for pagination |

**Request example**

```json
{
  "table_name": "users",
  "columns": ["id", "email"],
  "where": { "status": "active" },
  "order_by": "created_at DESC",
  "limit": 50,
  "offset": 0
}
```

**Response** — `array of objects`

```json
[
  { "id": 1, "email": "alice@example.com" },
  { "id": 2, "email": "bob@example.com" }
]
```

**Limit cap**  
`limit` values above `1000` are silently reduced to `1000` before the query runs. The capped value is recorded in the `limit` span attribute.

**`where` constraints**  
Only equality conditions (`col = $n`) are generated. For range filters, `IN`, or `LIKE`, use `query` with raw SQL instead.

**Errors**

| Condition | Type |
|-----------|------|
| Unknown column in `columns` or `where` | `asyncpg.UndefinedColumnError` |
| Table does not exist | `asyncpg.UndefinedTableError` |
| Invalid `order_by` expression | `asyncpg.PostgresSyntaxError` |

---

## Stub Tool Sets

### `graph_rag` — `tools/graph_rag.py`

Registered automatically by `load_all`. Both tools raise `NotImplementedError` until implemented; calls return `isError: true` and fire alerts.

| Tool | Parameters | Status |
|------|-----------|--------|
| `graph_search` | `query: str`, `top_k: int = 10` | stub |
| `graph_neighbors` | `node_id: str`, `depth: int = 1` | stub |

To implement: replace the `raise NotImplementedError(...)` bodies, add any required dependencies to `pipeline/requirements.txt`, and restart. No other files change.

---

## Connection Pool

A single `asyncpg.Pool` is shared across all tools and created lazily on the first tool call.

| Setting | Value |
|---------|-------|
| `min_size` | 1 |
| `max_size` | 5 |
| Connection string | `DATABASE_URL` env var |

`insert_rows` acquires a dedicated connection from the pool for its transaction (`pool.acquire()`). All other tools use `pool.fetch` / `pool.execute` which borrow a connection implicitly.

---

## Error Propagation Reference

| Exception | Spans marked | `error.type` | Alert fired | Caller sees |
|-----------|-------------|-------------|-------------|-------------|
| `ValueError` (input validation) | `tool.*` only | class name | Yes | `isError: true`, message |
| `asyncpg.PostgresError` subclass | `db.*` + `tool.*` | class name | Yes | `isError: true`, message |
| `asyncpg.QueryCanceledError` | `db.*` + `tool.*` | `"timeout"` | Yes | `isError: true`, message |
| `asyncio.TimeoutError` | `tool.*` only | `"timeout"` | Yes | `isError: true`, message |
| `NotImplementedError` (stub tools) | `tool.*` only | class name | Yes | `isError: true`, message |

Alerts fire once per tool call, at the `tool.*` span boundary (`trigger_alerts` in `_tracing.py`), regardless of how many nested `db.*` spans were involved. The full stack trace is attached via `span.record_exception()` and is visible in Phoenix; it is never forwarded to the MCP caller.
