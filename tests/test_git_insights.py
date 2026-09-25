from mcp import Client

from dev_radar.servers.git_insights import mcp


async def test_recent_commits_newest_first(repo):
    async with Client(mcp) as c:
        r = await c.call_tool("recent_commits", {"repo": str(repo), "days": 7})
    commits = r.structured_content["result"]
    assert not r.is_error
    assert [x["subject"] for x in commits] == ["docs: readme", "feat: app v2", "feat: app v1", "feat: app v0"]
    assert commits[0]["author"] == "Grace"


async def test_churn_hotspots_ranks_and_skips_lockfiles(repo):
    async with Client(mcp) as c:
        r = await c.call_tool("churn_hotspots", {"repo": str(repo)})
        with_locks = await c.call_tool("churn_hotspots", {"repo": str(repo), "include_lockfiles": True})
    paths = [h["path"] for h in r.structured_content["result"]]
    assert paths == ["app.py", "README.md"]
    assert r.structured_content["result"][0]["commits"] == 3
    assert "uv.lock" in [h["path"] for h in with_locks.structured_content["result"]]


async def test_top_authors(repo):
    async with Client(mcp) as c:
        r = await c.call_tool("top_authors", {"repo": str(repo)})
    assert r.structured_content["result"] == [{"author": "Ada", "commits": 3}, {"author": "Grace", "commits": 1}]


async def test_rejects_out_of_range_days(repo):
    async with Client(mcp) as c:
        r = await c.call_tool("recent_commits", {"repo": str(repo), "days": 0})
    assert r.is_error


async def test_rejects_non_repo(tmp_path):
    async with Client(mcp) as c:
        r = await c.call_tool("recent_commits", {"repo": str(tmp_path)})
    assert r.is_error and "Not a git repository" in r.content[0].text


async def test_summary_resource(repo, monkeypatch):
    monkeypatch.setenv("DEV_RADAR_REPO", str(repo))
    async with Client(mcp) as c:
        r = await c.read_resource("git://summary")
    text = r.contents[0].text
    assert "branch: `main`" in text and "commits (7d): 4" in text
