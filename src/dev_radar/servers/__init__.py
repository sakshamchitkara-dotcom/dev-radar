"""Dev Radar MCP servers. Each module exposes `mcp` and a `main()` console entry point."""

from __future__ import annotations

import argparse
import hmac
import os
from typing import Any

from mcp.server import MCPServer

TOKEN_ENV = "DEV_RADAR_HTTP_TOKEN"
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def require_bearer(app: Any, token: str) -> Any:
    """ASGI wrapper: HTTP requests need `Authorization: Bearer <token>` (constant-time compare), else 401."""
    expected = f"Bearer {token}".encode()

    async def guarded(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and not hmac.compare_digest(dict(scope["headers"]).get(b"authorization", b""), expected):
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"), (b"www-authenticate", b'Bearer realm="dev-radar"')]})
            await send({"type": "http.response.body", "body": b'{"error":"invalid_token"}'})
            return
        await app(scope, receive, send)

    return guarded


def serve(mcp: MCPServer, argv: list[str] | None = None) -> None:
    """Run `mcp` over stdio (default) or Streamable HTTP, chosen on the command line."""
    p = argparse.ArgumentParser(prog=mcp.name, description=f"{mcp.name} MCP server")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1", help="HTTP bind address (streamable-http only)")
    p.add_argument("--port", type=int, default=8000, help="HTTP port (streamable-http only)")
    args = p.parse_args(argv)
    if args.transport == "stdio":
        mcp.run()
        return
    token = os.environ.get(TOKEN_ENV)
    if args.host not in LOOPBACK and not token:
        p.error(f"--host {args.host} exposes the server beyond this machine; set {TOKEN_ENV} to require a bearer token")
    import uvicorn

    # Passing host lets the SDK enable DNS-rebinding protection for loopback binds.
    app = mcp.streamable_http_app(host=args.host)
    uvicorn.run(require_bearer(app, token) if token else app, host=args.host, port=args.port, log_level="warning")
