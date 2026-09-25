"""End-to-end: real server subprocesses over stdio, driven by McpHub and the CLI."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from dev_radar.briefing import claude_briefing, fallback_briefing
from dev_radar.hub import McpHub, result_data

DEAD_HN = "http://127.0.0.1:9"  # nothing listens on the discard port: forces the HN error path


@pytest.fixture(autouse=True)
def offline_hn(monkeypatch):
    monkeypatch.setenv("HN_API_BASE", DEAD_HN)
    monkeypatch.delenv("DEV_RADAR_GITHUB_REPOS", raising=False)


async def test_hub_discovers_all_servers_over_stdio(repo):
    async with McpHub(str(repo)) as hub:
        assert sorted(hub.tools) == [
            "deps__list_dependencies", "deps__outdated", "deps__vulnerabilities",
            "git__churn_hotspots", "git__recent_commits", "git__top_authors",
            "github__ci_status", "github__prs_awaiting_review", "github__recent_releases",
            "hn__top_stories", "system__snapshot", "system__top_processes",
        ]
        tools = hub.anthropic_tools()
        assert all(t["input_schema"]["type"] == "object" for t in tools)
        authors = result_data(await hub.call("git__top_authors"))
        assert authors[0] == {"author": "Ada", "commits": 3}
        bad = await hub.call("git__recent_commits", {"days": 9999})
        assert bad.is_error


async def test_fallback_briefing_over_stdio_degrades_when_hn_is_down(repo):
    async with McpHub(str(repo)) as hub:
        md = await fallback_briefing(hub, ["ai"], days=7)
    assert md.startswith("# Dev Radar - ")
    assert "4 commit(s) in the last 7 days by 2 author(s)" in md
    assert "| `app.py` | 3 |" in md
    assert "_hn-trends failed:" in md
    assert "_No repos configured: pass --github-repos" in md
    assert "_deps-watch failed:" in md and "Could not parse a lockfile" in md  # the fixture's uv.lock is not TOML
    assert "CPU" in md


class FakeMessages:
    """Scripted stand-in for AsyncAnthropic().messages: two tool calls, then the briefing."""

    def __init__(self):
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            return SimpleNamespace(stop_reason="tool_use", stop_details=None, content=[
                SimpleNamespace(type="tool_use", id="t1", name="git__top_authors", input={"days": 7}),
                SimpleNamespace(type="tool_use", id="t2", name="nope__missing", input={}),
            ])
        return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                               content=[SimpleNamespace(type="text", text="# Dev Radar - test\nAda leads.")])


async def test_claude_loop_routes_tool_calls_through_stdio_servers(repo):
    fake = SimpleNamespace(messages=FakeMessages())
    async with McpHub(str(repo)) as hub:
        md = await claude_briefing(hub, ["ai"], 7, client=fake)
    assert md == "# Dev Radar - test\nAda leads.\n"
    first, second = fake.messages.calls
    assert first["model"] == "claude-opus-5-5"
    assert {t["name"] for t in first["tools"]} >= {"git__top_authors", "hn__top_stories"}
    # messages is shared and mutated: [user prompt, assistant tool_use, user tool_results, final assistant]
    results = second["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]  # all results in one user turn
    assert json.loads(results[0]["content"])["result"][0]["author"] == "Ada"
    assert results[0]["is_error"] is False
    assert results[1]["is_error"] is True and "Unknown tool" in results[1]["content"]


def test_cli_fallback_end_to_end(repo, tmp_path):
    out = tmp_path / "briefing.md"
    proc = subprocess.run(
        [sys.executable, "-m", "dev_radar.cli", "--repo", str(repo), "--mode", "fallback", "--out", str(out)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "connected 12 tools" in proc.stderr
    assert "## Churn hotspots" in proc.stdout
    assert out.read_text() == proc.stdout
