"""MCP host side: connect to every Dev Radar server (stdio subprocess or Streamable HTTP URL) and route tool calls."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, TextContent, Tool

# server name -> python module spawned over stdio, or an http(s) URL of a running Streamable HTTP server
SERVERS = {
    "git": "dev_radar.servers.git_insights",
    "hn": "dev_radar.servers.hn_trends",
    "system": "dev_radar.servers.system_health",
    "github": "dev_radar.servers.github_activity",
    "deps": "dev_radar.servers.deps_watch",
}
# The stdio transport only forwards a minimal default environment; pass these through too.
PASSTHROUGH_ENV = (
    "HN_API_BASE", "GITHUB_TOKEN", "GITHUB_API_BASE", "DEV_RADAR_GITHUB_REPOS",
    "OSV_API_BASE", "PYPI_API_BASE", "NPM_API_BASE",
)
SEP = "__"  # qualified tool name: "<server>__<tool>" (Claude tool names allow [a-zA-Z0-9_-])


class McpHub:
    """Async context manager holding one MCP session per server."""

    def __init__(self, repo: str, servers: dict[str, str] = SERVERS) -> None:
        self.repo = repo
        self.servers = servers
        self.tools: dict[str, tuple[Client, Tool]] = {}
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> McpHub:
        try:
            for name, target in self.servers.items():
                if target.startswith(("http://", "https://")):
                    server: str | StdioServerParameters = target
                else:
                    server = StdioServerParameters(
                        command=sys.executable,
                        args=["-m", target],
                        env={"DEV_RADAR_REPO": self.repo} | {k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ},
                    )
                client = await self._stack.enter_async_context(Client(server))
                for tool in (await client.list_tools()).tools:
                    self.tools[f"{name}{SEP}{tool.name}"] = (client, tool)
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    def anthropic_tools(self) -> list[dict[str, Any]]:
        """MCP tool definitions translated to Claude Messages API tool dicts."""
        return [
            {
                "name": qualified,
                "description": f"[{qualified.split(SEP)[0]} server] {tool.description or ''}".strip(),
                "input_schema": tool.input_schema,
            }
            for qualified, (_, tool) in self.tools.items()
        ]

    async def call(self, qualified: str, arguments: dict[str, Any] | None = None) -> CallToolResult:
        if qualified not in self.tools:
            raise KeyError(f"Unknown tool {qualified!r}; known: {sorted(self.tools)}")
        client, tool = self.tools[qualified]
        return await client.call_tool(tool.name, arguments or {})


def result_text(result: CallToolResult) -> str:
    """Compact text for a tool result: structured JSON if present, else text blocks."""
    if result.structured_content is not None and not result.is_error:
        return json.dumps(result.structured_content, separators=(",", ":"))
    return "\n".join(b.text for b in result.content if isinstance(b, TextContent))


def result_data(result: CallToolResult) -> Any:
    """Structured payload with MCPServer's {"result": ...} wrapper for non-object returns removed."""
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data
