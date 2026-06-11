#!/usr/bin/env python3
"""postgres-mcp daily health monitor.

Three saved views:
  1. latency    — p50 / p95 / p99 per tool span
  2. volume     — data rows and LLM token usage per component (tool span)
  3. error_rate — per-span error counts + hourly trend with ! flag on >5 %

Usage:
  python health.py                          # all three views, last 24 h
  python health.py --view latency           # single view
  python health.py --window 1              # last 1 h
  PHOENIX_ENDPOINT=http://host:6006 python health.py

Scheduling (cron):
  0 9 * * * cd /path/to/monitoring && python health.py >> /var/log/mcp-health.log 2>&1
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

PHOENIX_ENDPOINT = os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006")
PROJECT_NAME = os.environ.get("PHOENIX_PROJECT", "default")


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def _import_deps():
    try:
        import pandas as pd  # noqa: F401
    except ImportError:
        sys.exit("pandas not installed — run: pip install -r requirements.txt")
    try:
        import phoenix as px  # noqa: F401
    except ImportError:
        sys.exit("arize-phoenix not installed — run: pip install -r requirements.txt")


def fetch_spans(window_hours: int):
    import phoenix as px

    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    client = px.Client(endpoint=PHOENIX_ENDPOINT)
    df = client.get_spans_dataframe(project_name=PROJECT_NAME, start_time=since)
    return df


# ---------------------------------------------------------------------------
# View 1 — Latency p50 / p95 / p99
# ---------------------------------------------------------------------------

def view_latency(df):
    """Span duration percentiles for every tool.* span, sorted by p95 desc."""
    tool = df[df["name"].str.startswith("tool.", na=False)].copy()
    if tool.empty:
        print("  (no tool.* spans in window)\n")
        return

    tool["latency_ms"] = (
        (tool["end_time"] - tool["start_time"]).dt.total_seconds() * 1000
    )

    stats = (
        tool.groupby("name")["latency_ms"]
        .agg(
            count="count",
            p50=lambda x: x.quantile(0.50),
            p95=lambda x: x.quantile(0.95),
            p99=lambda x: x.quantile(0.99),
        )
        .reset_index()
        .sort_values("p95", ascending=False)
    )

    print(f"  {'Span':<32} {'N':>6} {'p50 ms':>10} {'p95 ms':>10} {'p99 ms':>10}")
    print("  " + "-" * 72)
    for _, row in stats.iterrows():
        p95_flag = " !" if row["p95"] > 1000 else "  "
        print(
            f"  {row['name']:<32} {int(row['count']):>6}"
            f" {row['p50']:>10.1f} {row['p95']:>10.1f}{p95_flag} {row['p99']:>10.1f}"
        )
    print()


# ---------------------------------------------------------------------------
# View 2 — Data volume / token usage by component
# ---------------------------------------------------------------------------

# OpenTelemetry GenAI semantic convention attributes for LLM token counts.
# These are present when the LLM client (e.g. Claude via opentelemetry-instrumentation-anthropic)
# is also instrumented and its spans are visible in the same Phoenix project.
_TOKEN_IN_COL = "attributes.llm.token_count.prompt"
_TOKEN_OUT_COL = "attributes.llm.token_count.completion"

# DB-side row counts (tracked by this MCP server today).
_ROWS_RETURNED_COL = "attributes.db.rows_returned"
_ROWS_INSERTED_COL = "attributes.db.rows_inserted"
_ROWS_AFFECTED_COL = "attributes.db.rows_affected"


def _col(df, name):
    """Return column values or a zero Series if the column doesn't exist."""
    import pandas as pd
    return df[name].fillna(0) if name in df.columns else pd.Series(0, index=df.index)


def view_volume(df):
    """Rows read/written and LLM tokens per tool span.

    Rows read/written is the data-throughput proxy tracked today.
    LLM token columns (llm.token_count.*) appear automatically when
    the Claude/LLM client is instrumented with openinference or the
    Anthropic OTel SDK and those spans share the same Phoenix project.
    """
    tool = df[df["name"].str.startswith("tool.", na=False)].copy()
    if tool.empty:
        print("  (no tool.* spans in window)\n")
        return

    tool["_rows"] = (
        _col(tool, _ROWS_RETURNED_COL)
        + _col(tool, _ROWS_INSERTED_COL)
        + _col(tool, _ROWS_AFFECTED_COL)
    )

    stats = (
        tool.groupby("name")
        .agg(calls=("name", "count"), rows=("_rows", "sum"))
        .reset_index()
        .sort_values("rows", ascending=False)
    )

    print(f"  {'Span':<32} {'Calls':>6} {'Rows (read+written)':>20}")
    print("  " + "-" * 62)
    for _, row in stats.iterrows():
        print(f"  {row['name']:<32} {int(row['calls']):>6} {int(row['rows']):>20,}")

    # LLM token summary — shows if genai instrumentation is present
    has_tokens = _TOKEN_IN_COL in tool.columns
    if has_tokens:
        t_in = int(_col(tool, _TOKEN_IN_COL).sum())
        t_out = int(_col(tool, _TOKEN_OUT_COL).sum())
        print(f"\n  LLM tokens  prompt: {t_in:,}   completion: {t_out:,}")
    else:
        print(
            "\n  LLM token columns not present."
            "\n  Instrument the Claude/LLM client with openinference-instrumentation-anthropic"
            "\n  and point it at the same Phoenix project to populate gen_ai.usage.* counts."
        )
    print()


# ---------------------------------------------------------------------------
# View 3 — Error rate over time
# ---------------------------------------------------------------------------

def view_error_rate(df):
    """Per-span error rate summary + hourly trend. Flags rows above 5 % with !."""
    tool = df[df["name"].str.startswith("tool.", na=False)].copy()
    if tool.empty:
        print("  (no tool.* spans in window)\n")
        return

    # Normalise status_code to a bool — Phoenix may return 'ERROR', 'OK', or 'UNSET'
    tool["is_error"] = tool["status_code"].astype(str).str.upper() == "ERROR"

    # Per-span summary
    stats = (
        tool.groupby("name")
        .agg(total=("is_error", "count"), errors=("is_error", "sum"))
        .reset_index()
    )
    stats["rate"] = stats["errors"] / stats["total"] * 100
    stats = stats.sort_values("rate", ascending=False)

    print(f"  {'Span':<32} {'Total':>7} {'Errors':>7} {'Rate':>8}")
    print("  " + "-" * 58)
    for _, row in stats.iterrows():
        flag = " !" if row["rate"] > 5 else "  "
        print(
            f"  {row['name']:<32} {int(row['total']):>7}"
            f" {int(row['errors']):>7} {row['rate']:>7.1f}%{flag}"
        )

    # Hourly trend
    print()
    print(f"  {'Hour (UTC)':<22} {'Calls':>6} {'Errors':>7} {'Rate':>8}")
    print("  " + "-" * 47)
    tool["hour"] = tool["start_time"].dt.floor("h")
    hourly = (
        tool.groupby("hour")
        .agg(total=("is_error", "count"), errors=("is_error", "sum"))
        .reset_index()
        .sort_values("hour")
    )
    hourly["rate"] = hourly["errors"] / hourly["total"] * 100
    for _, row in hourly.tail(24).iterrows():
        flag = " !" if row["rate"] > 5 else "  "
        print(
            f"  {str(row['hour']):<22} {int(row['total']):>6}"
            f" {int(row['errors']):>7} {row['rate']:>7.1f}%{flag}"
        )
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

VIEWS = {
    "latency": view_latency,
    "volume": view_volume,
    "error_rate": view_error_rate,
}


def main():
    parser = argparse.ArgumentParser(description="postgres-mcp health monitor")
    parser.add_argument(
        "--view",
        choices=list(VIEWS),
        default=None,
        help="Run a single view (default: all three)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=24,
        metavar="HOURS",
        help="Rolling lookback window in hours (default: 24)",
    )
    args = parser.parse_args()

    _import_deps()

    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"  postgres-mcp Health Report")
    print(f"  {now.strftime('%Y-%m-%d %H:%M UTC')}  |  last {args.window}h  |  {PHOENIX_ENDPOINT}")
    print(f"{'='*60}\n")

    df = fetch_spans(args.window)

    if df is None or df.empty:
        print("  No spans found. Is the MCP service running and sending traces?\n")
        sys.exit(0)

    active_views = {args.view: VIEWS[args.view]} if args.view else VIEWS

    for name, fn in active_views.items():
        label = name.replace("_", " ").title()
        print(f"── {label} {'─' * (54 - len(label))}\n")
        fn(df)


if __name__ == "__main__":
    main()
