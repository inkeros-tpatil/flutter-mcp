# Tracing Standards

Distributed tracing for this project uses **OpenTelemetry** with traces exported via OTLP/gRPC to [Arize Phoenix](https://phoenix.arize.com/) for visualization.

- **Service name:** `postgres-mcp`
- **Exporter:** OTLP gRPC — endpoint set via `PHOENIX_ENDPOINT` env var (default: `http://localhost:4317`)
- **Span processor:** `BatchSpanProcessor`

---

## Span Naming

Spans use a `<category>.<operation>` format. Two categories exist:

| Prefix | Scope |
|--------|-------|
| `db.*` | Low-level database driver calls |
| `tool.*` | MCP tool entry points (one per exposed tool) |

`tool.*` spans are the outer span; they call into `db.*` spans which are the inner spans. Never create a `db.*` span without a `tool.*` parent already on the context stack — consumers rely on this hierarchy for attribution.

### Defined span names

**Database layer**

| Span | Description |
|------|-------------|
| `db.fetch` | `fetchrow` returning multiple rows |
| `db.fetchval` | Fetch a single scalar value |
| `db.fetchrow` | Fetch a single row |
| `db.execute` | Non-query statement (INSERT / UPDATE / DELETE / DDL) |
| `db.bulk_insert` | Multi-row INSERT used by `tool.insert_rows` |

**Tool layer**

| Span | Description |
|------|-------------|
| `tool.list_tables` | List all tables in a schema |
| `tool.describe_table` | Describe columns of a table |
| `tool.query` | Arbitrary read-only SQL query |
| `tool.execute` | Arbitrary write SQL statement |
| `tool.list_databases` | List available databases |
| `tool.get_table_indexes` | Get indexes for a table |
| `tool.get_row_count` | Count rows in a table |
| `tool.create_table` | CREATE TABLE statement |
| `tool.insert_row` | Single-row INSERT |
| `tool.insert_rows` | Multi-row INSERT (batched) |
| `tool.get_rows` | Paginated row fetch with optional filtering |

---

## Required Attributes

### All `db.*` spans

| Attribute | Type | Value |
|-----------|------|-------|
| `db.system` | string | `"postgresql"` — always |
| `db.statement` | string | The full SQL string being executed |

### `db.fetch`

| Attribute | Type | Notes |
|-----------|------|-------|
| `db.rows_returned` | int | Set *after* the query completes |

### `db.execute`

| Attribute | Type | Notes |
|-----------|------|-------|
| `db.rows_affected` | int | Set *after* the statement completes |

### `db.bulk_insert`

| Attribute | Type | Notes |
|-----------|------|-------|
| `db.rows_to_insert` | int | Set at span start, before execution |
| `db.rows_inserted` | int | Set *after* completion |

### All `tool.*` spans — schema-scoped operations

The following tools operate on a named schema and/or table. Set these attributes at span start:

| Attribute | Type | Required for |
|-----------|------|--------------|
| `schema` | string | `list_tables`, `describe_table`, `get_table_indexes`, `get_row_count`, `create_table`, `insert_row`, `insert_rows`, `get_rows` |
| `table_name` | string | `describe_table`, `get_table_indexes`, `get_row_count`, `create_table`, `insert_row`, `insert_rows`, `get_rows` |

### Additional tool-specific attributes

| Span | Attribute | Type | Notes |
|------|-----------|------|-------|
| `tool.create_table` | `column_count` | int | Number of columns in the schema definition |
| `tool.get_row_count` | `row.count.exact` | int | Set after the count query returns |
| `tool.get_rows` | `limit` | int | Max rows requested (cap: 1000) |
| `tool.get_rows` | `offset` | int | Pagination offset |

---

## Error Handling

Every span records errors via two helpers in `postgres_mcp.py`:

| Helper | Purpose | Call site |
|--------|---------|-----------|
| `_mark_span_error(span, exc)` | Sets `StatusCode.ERROR`, records the exception with stack trace, sets `error.type` attribute | Every error site (`db.*` and `tool.*` spans) |
| `_trigger_alerts(span, exc)` | Schedules registered alert hooks as a background `asyncio` task | `tool.*` spans only (once per user-visible failure) |

### `error.type` attribute

Set on every error span by `_mark_span_error`:

| Value | Meaning |
|-------|---------|
| `"timeout"` | `asyncio.TimeoutError` or `asyncpg.QueryCanceledError` (statement_timeout) |
| `<ExceptionClassName>` | Any other exception, named by its Python class |

### Pattern

```python
with tracer.start_as_current_span("tool.query") as span:
    span.set_attribute("db.statement", sql)
    try:
        rows = await _fetch(sql, *(params or []))
        return [dict(r) for r in rows]
    except Exception as exc:
        _mark_span_error(span, exc)   # always
        _trigger_alerts(span, exc)    # tool.* spans only
        raise                         # always re-raise
```

Rules:
- `db.*` spans call `_mark_span_error` only — alerts fire once at the tool boundary, not for every nested span.
- Never swallow exceptions inside a span.
- On successful completion no status call is needed — `StatusCode.UNSET` is treated as OK by Phoenix.

---

## Events That Must Always Be Traced

The following operations must have a span every time they execute, with no exceptions:

1. **Every SQL statement** sent to the database — wrapped in a `db.*` span with `db.statement` set.
2. **Every MCP tool invocation** — the tool function body must be wrapped in the corresponding `tool.*` span before any logic executes.
3. **Every bulk insert batch** — `db.bulk_insert` must always nest inside `tool.insert_rows`, even for a single-row degenerate case.
4. **Every exception** from a traced operation — recorded via `record_exception` on the active span before propagating.

Operations that do **not** require their own spans (handled by the parent):
- Connection pool acquisition/release
- Row serialization / type coercion
- JSON encoding of tool responses

---

## Span Lifecycle Rules

- Use `tracer.start_as_current_span()` as a context manager — do not manually call `span.end()`.
- Set attributes that are known at entry time (e.g., `db.statement`, `schema`, `table_name`) **immediately after span creation**, before any `await`.
- Set result attributes (e.g., `db.rows_returned`, `db.rows_inserted`) **before the `with` block exits**, while the span is still open.
- Do not pass `Span` objects between functions. Child functions should call `trace.get_current_span()` if they need the active span.

---

## Health Monitor — Saved Views

The three canonical views live in `monitoring/health.py` and query Phoenix via `px.Client`.

### Running

```bash
# install deps once
pip install -r monitoring/requirements.txt

# all three views, last 24 h
python monitoring/health.py

# single view
python monitoring/health.py --view latency
python monitoring/health.py --view volume
python monitoring/health.py --view error_rate

# custom window
python monitoring/health.py --window 1        # last hour

# against a remote Phoenix
PHOENIX_ENDPOINT=http://host:6006 python monitoring/health.py
```

Via Docker Compose (starts once daily, logs to container stdout):

```bash
docker compose --profile monitor up monitor
```

### View 1 — Latency p50 / p95 / p99

Shows span duration percentiles for every `tool.*` span, sorted by p95 descending. Rows with p95 > 1 s are flagged with `!`.

Spans to watch:
- `tool.insert_rows` — single transaction, should be < 200 ms for typical batch sizes
- `tool.query` / `tool.execute` — driven by SQL complexity; p95 > 500 ms warrants index review

### View 2 — Data Volume by Component

Shows call count and total rows read/written per `tool.*` span. This is the data-throughput proxy available today from `db.rows_returned`, `db.rows_inserted`, and `db.rows_affected` attributes.

**LLM token counts** (`gen_ai.usage.input_tokens` / `gen_ai.usage.completion_tokens`) appear in this view automatically when the Claude/LLM client is instrumented with `openinference-instrumentation-anthropic` and its spans land in the same Phoenix project. Until then, the view prints a setup note instead.

### View 3 — Error Rate over Time

Per-span error count and percentage for the window, followed by an hourly breakdown of the last 24 hours. Rows above 5 % are flagged with `!`.

`error.type = "timeout"` spans count as errors here. To distinguish timeouts from other failures, filter on the `error.type` attribute in Phoenix's UI or run:

```bash
python monitoring/health.py --view error_rate
```

then cross-reference with Phoenix → Traces → filter `error.type = timeout`.

---

## Alert Hooks

Error and timeout spans fire registered `AlertHook` implementations as background tasks. Hooks are wired in entirely via environment variables — no code changes required.

### Built-in hooks

| Hook class | Activating env var | Notes |
|------------|-------------------|-------|
| `SlackAlertHook` | `SLACK_WEBHOOK_URL` | Posts to a Slack incoming webhook |
| `PagerDutyAlertHook` | `PAGERDUTY_ROUTING_KEY` | Triggers via PagerDuty Events API v2 |

Both hooks use stdlib `urllib` in a thread executor so they never block the event loop. Network failures in a hook are logged as warnings and do not propagate.

### Adding a custom hook

Implement the `AlertHook` protocol and call `register_alert_hook()` at startup:

```python
from postgres_mcp import AlertEvent, AlertHook, register_alert_hook

class MyHook:
    async def fire(self, event: AlertEvent) -> None:
        # event.span_name, event.error_type, event.error_message, event.is_timeout
        ...

register_alert_hook(MyHook())
```

### `AlertEvent` fields

| Field | Type | Description |
|-------|------|-------------|
| `span_name` | `str` | e.g. `"tool.query"` |
| `error_type` | `str` | Exception class name or `"timeout"` |
| `error_message` | `str` | `str(exc)` |
| `is_timeout` | `bool` | True for `asyncio.TimeoutError` / `QueryCanceledError` |
| `attributes` | `dict` | Reserved for future span attribute forwarding |

---

## Exporter & Backend

| Setting | Value |
|---------|-------|
| Protocol | OTLP gRPC |
| Env var | `PHOENIX_ENDPOINT` |
| Default endpoint | `http://localhost:4317` |
| Docker Compose endpoint | `http://phoenix:4317` |
| Phoenix UI port | `6006` |
| Phoenix HTTP OTLP port | `4318` |

The Phoenix service is defined in `docker-compose.yml`. When running locally without Docker, set `PHOENIX_ENDPOINT=http://localhost:4317` and start Phoenix separately.
