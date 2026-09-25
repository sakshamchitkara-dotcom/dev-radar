"""Servers also speak Streamable HTTP: spawn one on a free port and talk to it with mcp.Client."""

import os
import socket
import subprocess
import sys
import time

import httpx

from mcp import Client

from dev_radar.hub import McpHub, result_data


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_git_server(repo, **env: str) -> tuple[subprocess.Popen, int]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "dev_radar.servers.git_insights", "--transport", "streamable-http", "--port", str(port)],
        env=os.environ | {"DEV_RADAR_REPO": str(repo)} | env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 20
    while True:  # wait for uvicorn to accept connections
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return proc, port
        except OSError:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                raise AssertionError("HTTP server did not start")
            time.sleep(0.2)


async def test_git_server_over_streamable_http(repo, monkeypatch):
    monkeypatch.delenv("DEV_RADAR_HTTP_TOKEN", raising=False)
    proc, port = _start_git_server(repo)
    try:
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


async def test_bearer_token_guards_the_http_server(repo, monkeypatch):
    proc, port = _start_git_server(repo, DEV_RADAR_HTTP_TOKEN="s3cret")
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            r = httpx.post(url, json={}, headers=headers)
            assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Bearer")
        monkeypatch.setenv("DEV_RADAR_HTTP_TOKEN", "wrong")
        async with McpHub(str(repo), {"git": url}) as hub:
            assert "git" in hub.failed and not hub.tools
        monkeypatch.setenv("DEV_RADAR_HTTP_TOKEN", "s3cret")  # the host sends it as a bearer token
        async with McpHub(str(repo), {"git": url}) as hub:
            assert result_data(await hub.call("git__top_authors"))[0] == {"author": "Ada", "commits": 3}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_public_bind_without_token_is_refused(monkeypatch):
    monkeypatch.delenv("DEV_RADAR_HTTP_TOKEN", raising=False)
    proc = subprocess.run([sys.executable, "-m", "dev_radar.servers.git_insights", "--transport", "streamable-http",
                           "--host", "0.0.0.0"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2 and "set DEV_RADAR_HTTP_TOKEN" in proc.stderr
