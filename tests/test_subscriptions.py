"""Resource subscriptions over subscriptions/listen: tools publish updates for their report resources."""

import json

import anyio
import httpx
from mcp import Client

from dev_radar.servers import deps_watch, github_activity
from tests.test_github_activity import handler as github_handler


async def _next_event(sub):
    with anyio.fail_after(5):
        return await sub.__anext__()


async def test_ci_status_notifies_github_ci_subscribers(monkeypatch):
    monkeypatch.setattr(github_activity, "_client", lambda: httpx.AsyncClient(
        base_url="https://api.test", transport=httpx.MockTransport(github_handler)))
    github_activity._ci_states.clear()
    async with Client(github_activity.mcp) as c:
        async with c.listen(resource_subscriptions=["github://ci"]) as sub:
            assert sub.honored.resource_subscriptions == ["github://ci"]
            await c.call_tool("ci_status", {"repos": ["o/r"]})
            event = await _next_event(sub)
        state = json.loads((await c.read_resource("github://ci")).contents[0].text)
    assert event.uri == "github://ci"
    assert state == {"o/r": {"sha": "abcdef1", "state": "failure"}}


async def test_vulnerabilities_notifies_only_on_change(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("jinja2==2.10\n")
    results = iter([[{"id": "GHSA-1"}], [{"id": "GHSA-1"}]])

    async def fake_check(deps):
        return [deps_watch.Vulnerability(id=v["id"], package="jinja2", version="2.10", ecosystem="PyPI",
                                         summary="", severity=None, fixed_in=[], url="") for v in next(results)]
    monkeypatch.setattr(deps_watch, "check_vulns", fake_check)
    deps_watch._last_report.clear()
    published = []
    async with Client(deps_watch.mcp) as c:
        async with c.listen(resource_subscriptions=["deps://vulnerabilities"]) as sub:
            await c.call_tool("vulnerabilities", {"project": str(tmp_path)})
            published.append(await _next_event(sub))
            await c.call_tool("vulnerabilities", {"project": str(tmp_path)})  # same IDs: no event
            with anyio.move_on_after(0.3):
                published.append(await sub.__anext__())
        report = json.loads((await c.read_resource("deps://vulnerabilities")).contents[0].text)
    assert [e.uri for e in published] == ["deps://vulnerabilities"]
    assert report[str(tmp_path.resolve())]["vulnerabilities"][0]["id"] == "GHSA-1"
