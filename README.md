# development-pipeline

A local development environment for the **Recruitment Tool** Flutter application. It provides:

- A **Flutter demo app** (recruitment tool, Clean Architecture + BLoC)
- A **postgres-mcp server** — MCP tools for PostgreSQL, Memgraph AST graph, pub.dev intelligence, and project episodic memory
- Supporting infrastructure: PostgreSQL, Memgraph (graph DB), Arize Phoenix (tracing/observability)

Claude Code connects to the MCP server over SSE to use all tools during development.

---

## Repository layout

```
development-pipeline/
├── demo_app/           # Flutter application (the codebase Claude works on)
├── pipeline/           # MCP server source code
│   ├── postgres_mcp.py # Entry point
│   ├── tools/          # Tool modules (auto-discovered)
│   │   ├── ast.py      # Cypher queries against the Memgraph AST graph
│   │   ├── db.py       # PostgreSQL tools (query, insert, describe, …)
│   │   ├── graph_rag.py# Graph RAG tools
│   │   └── memory.py   # Project episodic memory (decisions, bugs, patterns)
│   ├── flutter_pub_tools.py  # pub.dev intelligence tools
│   ├── ingest_ast.py   # Parses demo_app Dart files → Memgraph graph
│   ├── Dockerfile
│   └── requirements.txt
├── monitoring/
│   └── health.py       # CLI health report (latency / volume / error rate)
├── docker-compose.yml
├── .mcp.json           # Points Claude Code at http://localhost:8000/sse
├── CLAUDE.md           # Coding instructions for Claude
└── SKILLS.md
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker + Docker Compose | 24+ | For all infrastructure services |
| Flutter SDK | 3.32+ | For the demo app |
| Python | 3.12+ | Only needed for running `ingest_ast.py` outside Docker or local pipeline dev |
| Claude Code | latest | Connects to MCP server via `.mcp.json` |

---

## Quick start

### 1. Start all infrastructure

```bash
docker compose up -d
```

This starts five services:

| Service | Container | Purpose | Port(s) |
|---------|-----------|---------|---------|
| PostgreSQL 16 | `dev_postgres` | Primary database | `5434` (host) → `5432` |
| Arize Phoenix | `dev_phoenix` | Tracing UI + OTLP receiver | `6006` (UI), `4317` (gRPC), `4318` (HTTP) |
| Memgraph MAGE | `dev_memgraph` | AST code graph (Bolt) | `7687` (Bolt), `7444` (monitoring) |
| Memgraph Lab | `dev_memgraph_lab` | Graph browser UI | `3000` |
| MCP server | `dev_mcp` | postgres-mcp SSE server | `8000` |

Wait for all services to be healthy:

```bash
docker compose ps
```

All containers should show `healthy` or `running` before proceeding.

### 2. Ingest the AST graph

The MCP `ast_*` tools query a code graph built from `demo_app/lib`. Populate it once (and re-run after code changes):

```bash
cd pipeline
pip install -r requirements.txt   # one-time; skip if already installed
python ingest_ast.py
```

The script connects to Memgraph at `bolt://localhost:7687` and parses all `.dart` files in `../demo_app/lib`. Re-running is safe — it uses `MERGE` throughout.

To use a different path:

```bash
python ingest_ast.py --demo-app-path /path/to/your/flutter/lib --memgraph-uri bolt://localhost:7687
```

### 3. Verify the MCP server is reachable

```bash
curl -s http://localhost:8000/sse
```

You should see an SSE stream start. Press `Ctrl+C` to cancel.

### 4. Open Claude Code

The project root contains `.mcp.json` which points Claude Code at the MCP server:

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

Open Claude Code from the `development-pipeline/` directory and all MCP tools will be available automatically.

---

## Running the demo app

The demo app is a Flutter recruitment tool. Run it on your preferred target:

```bash
cd demo_app
flutter pub get
flutter run                    # pick a device interactively
flutter run -d linux           # Linux desktop
flutter run -d chrome          # web
flutter run -d android         # connected Android device/emulator
```

To run tests:

```bash
cd demo_app
flutter test
```

---

## Docker services in detail

### PostgreSQL

Stores project episodic memory (decisions, bugs, patterns) and any application data.

```
Host:     localhost:5434
User:     devuser
Password: devpassword
DB:       devdb
```

Connect directly:

```bash
docker exec -it dev_postgres psql -U devuser -d devdb
```

Data persists in the `postgres_data` Docker volume across restarts.

### Arize Phoenix

Distributed tracing UI. Every MCP tool call is traced with OpenTelemetry and sent to Phoenix.

- **UI:** http://localhost:6006
- **OTLP gRPC (for instrumented clients):** `localhost:4317`

### Memgraph

Graph database storing the Dart AST — files, classes, relationships, and architecture layers.

- **Bolt endpoint:** `bolt://localhost:7687` (no auth required in dev)
- **Monitoring:** http://localhost:7444

Connect with `mgconsole` (inside the container):

```bash
docker exec -it dev_memgraph mgconsole
```

Example Cypher queries:

```cypher
-- All BLoC classes in the project
MATCH (c:Class {role: 'bloc'}) RETURN c.name, c.file_path;

-- Dependency chain from a specific class
MATCH (c:Class {name: 'AuthBloc'})-[:DEPENDS_ON*1..3]->(dep:Class)
RETURN dep.name, dep.role;
```

Graph data persists in `memgraph_data` and `memgraph_log` volumes.

### Memgraph Lab

Visual graph browser — useful for exploring the AST graph.

- **UI:** http://localhost:3000
- Connects automatically to Memgraph on startup

### MCP server (`dev_mcp`)

The postgres-mcp server runs in SSE mode and exposes all tools to Claude Code.

- **SSE endpoint:** http://localhost:8000/sse
- Rebuilt from `./pipeline/Dockerfile` on `docker compose up --build`

To rebuild after pipeline source changes:

```bash
docker compose up -d --build mcp
```

To tail logs:

```bash
docker compose logs -f mcp
```

---

## MCP tools reference

All tools are registered automatically — drop a `.py` file in `pipeline/tools/` and decorate async functions with `@tool`. No other files need to change.

### PostgreSQL tools (`tools/db.py`)

| Tool | Description |
|------|-------------|
| `list_tables` | List tables in a schema |
| `describe_table` | Describe columns of a table |
| `query` | Run a `SELECT`/`WITH` query |
| `execute` | Run `INSERT`/`UPDATE`/`DELETE`/DDL |
| `list_databases` | List all databases |
| `get_table_indexes` | List indexes on a table |
| `get_row_count` | Approximate + exact row count |
| `create_table` | Build and execute a `CREATE TABLE` |
| `insert_row` | Insert a single row |
| `insert_rows` | Bulk insert rows in a transaction |
| `get_rows` | Retrieve rows with filtering and pagination |

### AST graph tools (`tools/ast.py`)

Require `ingest_ast.py` to have been run first.

| Tool | Description |
|------|-------------|
| `ast_query` | Run a freeform Cypher query against the code graph |
| `ast_find` | Find a class or file by name (partial match) |
| `ast_dependencies` | Dependency subgraph for a class (upstream + downstream) |
| `ast_feature_map` | Files and classes organized by feature/layer |

### Episodic memory tools (`tools/memory.py`)

| Tool | Description |
|------|-------------|
| `project_remember` | Save a decision, bug, pattern, feature note, or refactor |
| `project_recall` | Full-text search past episodes |
| `project_episodes` | Browse all episodes, newest first |

### pub.dev intelligence tools (`flutter_pub_tools.py`)

These tools fetch live data from pub.dev — never use training-memory package versions.

| Tool | Description |
|------|-------------|
| `flutter_pub_get_latest` | Latest version + pubspec entry for any package |
| `flutter_pub_get_compatible_version` | Newest version matching your SDK constraints |
| `flutter_pub_check_compatibility` | Detect conflicts before running `flutter pub get` |
| `flutter_pub_get_firebase_matrix` | Full compatible Firebase version set |
| `flutter_pub_search` | Search pub.dev by keyword |
| `flutter_pub_remember_combo` | Store a verified working pubspec combo |
| `flutter_pub_recall_combos` | Query stored combos by package/tag/SDK |
| `flutter_pub_get_combo_pubspec` | Retrieve the full pubspec.yaml for a named combo |

### Graph RAG tools (`tools/graph_rag.py`)

| Tool | Status |
|------|--------|
| `graph_search` | Stub — raises `NotImplementedError` until implemented |
| `graph_neighbors` | Stub — raises `NotImplementedError` until implemented |

---

## Adding a new MCP tool

1. Create `pipeline/tools/<name>.py`
2. Import and use the `@tool` decorator:

```python
from opentelemetry import trace
from tools import tool

@tool
async def my_tool(arg: str) -> dict:
    """One-line description shown in the MCP tool manifest."""
    trace.get_current_span().set_attribute("arg", arg)
    # ... implementation
    return {"result": arg}
```

3. Rebuild and restart the MCP container:

```bash
docker compose up -d --build mcp
```

No changes to `postgres_mcp.py` or any other file are needed — `load_all()` discovers the module automatically.

---

## Local pipeline development (without Docker)

To run the MCP server on the host for faster iteration:

```bash
cd pipeline
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL="postgresql://devuser:devpassword@localhost:5434/devdb"
export MEMGRAPH_URI="bolt://localhost:7687"
export MCP_TRANSPORT=sse
export MCP_PORT=8000
export PHOENIX_ENDPOINT="http://localhost:4317"
export EMBEDDING_PROVIDER=local

python postgres_mcp.py
```

PostgreSQL, Memgraph, and Phoenix still need to be running via Docker:

```bash
docker compose up -d postgres memgraph phoenix
```

Update `.mcp.json` if you change the port.

---

## Health monitoring

The `monitoring/` directory contains a CLI health report that reads traces from Phoenix.

```bash
cd monitoring
pip install -r requirements.txt

python health.py                      # all three views, last 24 h
python health.py --view latency       # p50 / p95 / p99 per tool
python health.py --view volume        # row counts and LLM token usage
python health.py --view error_rate    # per-tool error rates + hourly trend
python health.py --window 1           # narrow to last 1 hour
```

Phoenix must be running (`docker compose up -d phoenix`) and the MCP server must have received at least one tool call for spans to appear.

To schedule a daily report (cron):

```
0 9 * * * cd /path/to/monitoring && python health.py >> /var/log/mcp-health.log 2>&1
```

---

## Stopping and resetting

Stop all containers (data is preserved in volumes):

```bash
docker compose down
```

Stop and wipe all data volumes (full reset):

```bash
docker compose down -v
```

After a full reset, re-run `ingest_ast.py` to repopulate the graph.

---

## Environment variable reference

| Variable | Default | Service | Purpose |
|----------|---------|---------|---------|
| `DATABASE_URL` | `postgresql://devuser:devpassword@postgres:5432/devdb` | mcp | asyncpg connection string |
| `MCP_TRANSPORT` | `sse` | mcp | `sse` or `stdio` |
| `MCP_PORT` | `8000` | mcp | HTTP port for SSE |
| `PHOENIX_ENDPOINT` | `http://phoenix:4317` | mcp | OTLP gRPC endpoint |
| `MEMGRAPH_URI` | `bolt://memgraph:7687` | mcp | Memgraph Bolt connection |
| `EMBEDDING_PROVIDER` | `local` | mcp | `local` or `openai` |
| `OPENAI_API_KEY` | — | mcp | Required when `EMBEDDING_PROVIDER=openai` |
| `VECTOR_TOP_K` | `8` | mcp | Graph RAG vector retrieval limit |
| `TRAVERSAL_DEPTH` | `2` | mcp | Graph RAG traversal depth |
| `RESULT_TOP_N` | `6` | mcp | Graph RAG final result limit |
| `PHOENIX_ENDPOINT` | `http://localhost:6006` | monitoring | Phoenix UI for health.py |
| `DEMO_APP_PATH` | `../demo_app/lib` | ingest_ast | Path to Dart lib directory |
