import os

from fastmcp import FastMCP
import tools
from flutter_pub_tools import flutter_pub_mcp

mcp = FastMCP("PostgreSQL")
tools.load_all(mcp)
mcp.mount(flutter_pub_mcp, namespace="flutter_pub")

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "8000")))
    else:
        mcp.run()
