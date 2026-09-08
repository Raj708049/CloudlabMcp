"""Quick local test: launch the MCP server and call a tool.

It reads the CLOUDLAB_* settings from .cursor/mcp.json (the same config Cline /
Cursor use), starts server.py over stdio, lists the tools, and runs the safe
`config_check` tool.

Usage:
    python test_client.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent


def load_env_from_mcp_json() -> dict:
    """Pull the cloudlabMcp 'env' block out of .cursor/mcp.json if present."""
    cfg = HERE / ".cursor" / "mcp.json"
    if not cfg.exists():
        print("WARNING: .cursor/mcp.json not found — using current environment.")
        return dict(os.environ)
    data = json.loads(cfg.read_text())
    env = data["mcpServers"]["cloudlabMcp"].get("env", {})
    return {**os.environ, **env}


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "server.py")],
        env=load_env_from_mcp_json(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("CONNECTED. Tools:", [t.name for t in tools.tools])

            result = await session.call_tool("config_check", {})
            print("config_check ->", result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
