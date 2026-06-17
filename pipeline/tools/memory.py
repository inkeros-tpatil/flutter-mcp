"""Project episodic memory tools — save and recall decisions, bugs, patterns, and features."""

from opentelemetry import trace

from _db import _execute, _fetch, _fetchrow
from tools import tool

_EPISODE_TYPES = {"decision", "bug", "pattern", "feature", "refactor"}

_schema_ready = False


async def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    await _execute("""
        CREATE TABLE IF NOT EXISTS project_episodes (
            id             SERIAL      PRIMARY KEY,
            type           TEXT        NOT NULL,
            title          TEXT        NOT NULL,
            body           TEXT        NOT NULL,
            tags           TEXT[]      NOT NULL DEFAULT '{}',
            affected_files TEXT[]      NOT NULL DEFAULT '{}',
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await _execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_type ON project_episodes(type)"
    )
    await _execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_fts ON project_episodes "
        "USING GIN(to_tsvector('english', title || ' ' || body))"
    )
    await _execute(
        "CREATE INDEX IF NOT EXISTS idx_episodes_files ON project_episodes USING GIN(affected_files)"
    )
    _schema_ready = True


@tool
async def project_remember(
    type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    affected_files: list[str] | None = None,
) -> dict:
    """Save a project episode — a decision, bug, pattern, feature note, or refactor record.

    - type: one of "decision" | "bug" | "pattern" | "feature" | "refactor"
    - title: short one-line summary
    - body: full explanation — the WHY, not just the what
    - tags: optional keywords e.g. ["auth", "bloc", "token"]
    - affected_files: optional class names or file paths this episode relates to

    Returns the saved episode id and timestamp.
    """
    await _ensure_schema()
    span = trace.get_current_span()
    span.set_attribute("episode.type", type)
    span.set_attribute("episode.title", title)

    if type not in _EPISODE_TYPES:
        raise ValueError(f"type must be one of: {', '.join(sorted(_EPISODE_TYPES))}")

    row = await _fetchrow(
        """
        INSERT INTO project_episodes (type, title, body, tags, affected_files)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, created_at
        """,
        type,
        title,
        body,
        tags or [],
        affected_files or [],
    )
    span.set_attribute("episode.id", row["id"])
    return {
        "id": row["id"],
        "created_at": str(row["created_at"]),
        "type": type,
        "title": title,
    }


@tool
async def project_recall(
    query: str,
    type: str | None = None,
    affected_files: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Full-text search project episodes — call this before coding to surface past decisions and known bugs.

    - query: natural language string e.g. "auth token refresh" or "BLoC stream error"
    - type: optional filter — "decision" | "bug" | "pattern" | "feature" | "refactor"
    - affected_files: optional class/file names to narrow results
    - limit: max results (default 10)

    Returns episodes ranked by relevance, most relevant first.
    """
    await _ensure_schema()
    span = trace.get_current_span()
    span.set_attribute("recall.query", query)
    limit = min(limit, 50)

    params: list = [query]
    filters = [
        "to_tsvector('english', title || ' ' || body) @@ plainto_tsquery('english', $1)"
    ]

    if type:
        params.append(type)
        filters.append(f"type = ${len(params)}")

    if affected_files:
        params.append(affected_files)
        filters.append(f"affected_files && ${len(params)}")

    params.append(limit)
    where = " AND ".join(filters)
    sql = f"""
        SELECT
            id, type, title, body, tags, affected_files, created_at,
            ts_rank(
                to_tsvector('english', title || ' ' || body),
                plainto_tsquery('english', $1)
            ) AS rank
        FROM project_episodes
        WHERE {where}
        ORDER BY rank DESC
        LIMIT ${len(params)}
    """
    rows = await _fetch(sql, *params)
    span.set_attribute("recall.result_count", len(rows))
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "title": r["title"],
            "body": r["body"],
            "tags": list(r["tags"]),
            "affected_files": list(r["affected_files"]),
            "created_at": str(r["created_at"]),
            "relevance": round(float(r["rank"]), 4),
        }
        for r in rows
    ]


@tool
async def project_episodes(
    type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Browse recent project episodes — decisions, bugs, patterns, features, and refactors.

    - type: optional filter — "decision" | "bug" | "pattern" | "feature" | "refactor"
    - tags: optional list of tags; episodes must contain ALL given tags
    - limit: max results (default 20)

    Returns episodes newest-first with the first 300 chars of body as a summary.
    """
    await _ensure_schema()
    span = trace.get_current_span()
    limit = min(limit, 100)

    params: list = []
    filters: list[str] = []

    if type:
        params.append(type)
        filters.append(f"type = ${len(params)}")

    if tags:
        params.append(tags)
        filters.append(f"tags @> ${len(params)}")

    params.append(limit)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"""
        SELECT
            id, type, title,
            LEFT(body, 300) AS summary,
            tags, affected_files, created_at
        FROM project_episodes
        {where}
        ORDER BY created_at DESC
        LIMIT ${len(params)}
    """
    rows = await _fetch(sql, *params)
    span.set_attribute("episodes.result_count", len(rows))
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "title": r["title"],
            "summary": r["summary"],
            "tags": list(r["tags"]),
            "affected_files": list(r["affected_files"]),
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]
