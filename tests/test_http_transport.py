"""Servers also speak Streamable HTTP: spawn one on a free port and talk to it with mcp.Client."""

import os
import socket
import subprocess
import sys
import time

from mcp import Client

from dev_radar.hub import McpHub, result_data


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_git_server_over_streamable_http(repo):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "dev_radar.servers.git_insights", "--transport", "streamable-http", "--port", str(port)],
        env=os.environ | {"DEV_RADAR_REPO": str(repo)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while True:  # wait for uvicorn to accept connections
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                assert time.monotonic() < deadline and proc.poll() is None, "HTTP server did not start"
                time.sleep(0.2)
        async with Client(f"http://127.0.0.1:{port}/mcp") as c:
            names = {t.name for t in (await c.list_tools()).tools}
            r = await c.call_tool("top_authors", {})
        assert {"recent_commits", "churn_hotspots", "top_authors"} <= names
        assert r.structured_content["result"][0] == {"author": "Ada", "commits": 3}
        # the host can mix transports: this "git" entry is a URL, not a module to spawn
        async with McpHub(str(repo), {"git": f"http://127.0.0.1:{port}/mcp"}) as hub:
            assert result_data(await hub.call("git__top_authors"))[1] == {"author": "Grace", "commits": 1}
    finally:
        proc.terminate()
        proc.wait(timeout=10)
