"""Dev Radar MCP servers. Each module exposes `mcp` and a `main()` console entry point."""

from __future__ import annotations

import argparse

from mcp.server import MCPServer


def serve(mcp: MCPServer, argv: list[str] | None = None) -> None:
    """Run `mcp` over stdio (default) or Streamable HTTP, chosen on the command line."""
    p = argparse.ArgumentParser(prog=mcp.name, description=f"{mcp.name} MCP server")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1", help="HTTP bind address (streamable-http only)")
    p.add_argument("--port", type=int, default=8000, help="HTTP port (streamable-http only)")
    args = p.parse_args(argv)
    if args.transport == "stdio":
        mcp.run()
    else:
        # Passing host lets the SDK enable DNS-rebinding protection for loopback binds.
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
