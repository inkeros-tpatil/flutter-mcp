"""Graph RAG tools — stub showing the plugin contract.

To activate: install dependencies, implement the functions below, and restart.
No changes to any other file are required — load_all() discovers this module
automatically because it lives in the tools/ package.
"""

from opentelemetry import trace

from tools import tool


@tool
async def graph_search(query: str, top_k: int = 10) -> list[dict]:
    """Search the knowledge graph and return the top-k relevant nodes."""
    span = trace.get_current_span()
    span.set_attribute("query.length", len(query))
    span.set_attribute("top_k", top_k)
    raise NotImplementedError("graph_search is not yet implemented")


@tool
async def graph_neighbors(node_id: str, depth: int = 1) -> list[dict]:
    """Return all neighbours of a node up to the given hop depth."""
    span = trace.get_current_span()
    span.set_attribute("node_id", node_id)
    span.set_attribute("depth", depth)
    raise NotImplementedError("graph_neighbors is not yet implemented")
