"""Tool registry for postgres-mcp.

Drop a .py file in this package and decorate async functions with @tool.
load_all(mcp) discovers every non-private module here, imports it (firing
the @tool decorators), then bulk-registers collected functions with FastMCP.
No existing file needs to change.

Adding a new tool set — e.g. Graph RAG:
    1. Create pipeline/tools/graph_rag.py
    2. Decorate tool functions with @tool
    3. Done — load_all picks it up automatically on next startup
"""

import functools
import importlib
import pkgutil
from pathlib import Path

from opentelemetry import trace

from _tracing import mark_span_error, tracer, trigger_alerts

_registry: list = []


def tool(fn):
    """Register an async function as an MCP tool.

    Wraps every call in a ``tool.<fn_name>`` span and centralises error
    recording and alert firing.  Tool functions retrieve the active span
    via ``trace.get_current_span()`` to set call-specific attributes.

    Example::

        @tool
        async def my_tool(x: int) -> dict:
            trace.get_current_span().set_attribute("x", x)
            ...
    """
    span_name = f"tool.{fn.__name__}"

    @functools.wraps(fn)
    async def _wrapper(*args, **kwargs):
        with tracer.start_as_current_span(span_name) as span:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                mark_span_error(span, exc)
                trigger_alerts(span, exc)
                raise

    _registry.append(_wrapper)
    return _wrapper


def load_all(mcp) -> None:
    """Discover every non-private module in tools/ and register its tools.

    Modules whose names start with ``_`` are skipped so internal helpers
    can live in this package without being treated as tool sets.
    """
    pkg_dir = str(Path(__file__).parent)
    for _, module_name, _ in pkgutil.iter_modules([pkg_dir]):
        if not module_name.startswith("_"):
            importlib.import_module(f".{module_name}", package=__name__)
    for fn in _registry:
        mcp.tool()(fn)
