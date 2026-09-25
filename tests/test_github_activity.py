import httpx
import pytest
from mcp import Client

from dev_radar.servers import github_activity
from dev_radar.servers.github_activity import mcp

NOW = "2099-01-01T00:00:00Z"
PULLS = [
    {"number": 1, "title": "Needs review", "draft": False, "user": {"login": "ada"}, "html_url": "https://gh/pr/1",
     "created_at": "2020-01-01T00:00:00Z", "requested_reviewers": [{"login": "grace"}], "requested_teams": []},
    {"number": 2, "title": "Draft", "draft": True, "user": {"login": "ada"}, "html_url": "https://gh/pr/2",
     "created_at": NOW, "requested_reviewers": [], "requested_teams": []},
    {"number": 3, "title": "Already approved", "draft": False, "user": {"login": "bob"}, "html_url": "https://gh/pr/3",
     "created_at": NOW, "requested_reviewers": [], "requested_teams": []},
]
RUNS = [  # newest first; two workflows on the head commit, one older run
    {"name": "CI", "head_sha": "abcdef123", "status": "completed", "conclusion": "success", "html_url": "u1"},
    {"name": "Lint", "head_sha": "abcdef123", "status": "completed", "conclusion": "failure", "html_url": "u2"},
    {"name": "CI", "head_sha": "old", "status": "completed", "conclusion": "failure", "html_url": "u3"},
]
RELEASES = [
    {"tag_name": "v2", "name": "", "draft": False, "prerelease": False, "published_at": NOW, "html_url": "r2"},
    {"tag_name": "v1", "name": "One", "draft": False, "prerelease": False, "published_at": "2000-01-01T00:00:00Z", "html_url": "r1"},
    {"tag_name": "v3", "name": "Draft", "draft": True, "prerelease": False, "published_at": None, "html_url": "r3"},
]


def handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"  # the server is read-only
    path = request.url.path
    routes = {
        "/repos/o/r": {"default_branch": "main"},
        "/repos/o/r/pulls": PULLS,
        "/repos/o/r/pulls/1/reviews": [],
        "/repos/o/r/pulls/3/reviews": [{"state": "APPROVED"}],
        "/repos/o/r/actions/runs": {"workflow_runs": RUNS},
        "/repos/o/r/releases": RELEASES,
        "/repos/o/empty": {"default_branch": "trunk"},
        "/repos/o/empty/actions/runs": {"workflow_runs": []},
    }
    if path == "/repos/o/many/pulls":  # two pages of open PRs linked by rel="next"
        page = int(request.url.params.get("page", 1))
        nums = range(1, 101) if page == 1 else range(101, 106)
        link = {"link": '<https://api.test/repos/o/many/pulls?state=open&per_page=100&page=2>; rel="next"'} if page == 1 else {}
        return httpx.Response(200, headers=link, json=[
            {**PULLS[0], "number": n, "html_url": f"https://gh/pr/{n}", "created_at": NOW} for n in nums])
    if path.startswith("/repos/o/many/pulls/"):
        return httpx.Response(200, json=[])
    if path in routes:
        return httpx.Response(200, json=routes[path])
    return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture(autouse=True)
def fake_github(monkeypatch):
    monkeypatch.setattr(github_activity, "_client", lambda: httpx.AsyncClient(
        base_url="https://api.test", transport=httpx.MockTransport(handler)))
    monkeypatch.delenv("DEV_RADAR_GITHUB_REPOS", raising=False)


async def test_prs_awaiting_review_skips_drafts_and_reviewed():
    async with Client(mcp) as c:
        r = await c.call_tool("prs_awaiting_review", {"repos": ["o/r"]})
        everything = await c.call_tool("prs_awaiting_review", {"repos": ["o/r"], "include_reviewed": True})
    items = r.structured_content["items"]
    assert [p["number"] for p in items] == [1]
    assert items[0]["requested_reviewers"] == ["grace"] and items[0]["reviews"] == 0
    assert [p["number"] for p in everything.structured_content["items"]] == [1, 3]  # oldest first


async def test_prs_follow_pagination():
    async with Client(mcp) as c:
        r = await c.call_tool("prs_awaiting_review", {"repos": ["o/many"]})
    assert sorted(p["number"] for p in r.structured_content["items"]) == list(range(1, 106))


async def test_ci_status_uses_head_commit_and_reports_failure():
    async with Client(mcp) as c:
        r = await c.call_tool("ci_status", {"repos": ["o/r", "o/empty", "o/missing"]})
    by_repo = {s["repo"]: s for s in r.structured_content["items"]}
    assert by_repo["o/r"]["state"] == "failure" and by_repo["o/r"]["sha"] == "abcdef1"
    assert [w["workflow"] for w in by_repo["o/r"]["runs"]] == ["CI", "Lint"]
    assert by_repo["o/empty"] == {"repo": "o/empty", "branch": "trunk", "sha": None, "state": "none", "runs": []}
    assert r.structured_content["errors"] == [{"repo": "o/missing", "error": "GET /repos/o/missing -> 404: Not Found"}]


async def test_recent_releases_filters_window_and_drafts():
    async with Client(mcp) as c:
        r = await c.call_tool("recent_releases", {"repos": ["o/r"], "days": 30})
    assert [(x["tag"], x["name"]) for x in r.structured_content["items"]] == [("v2", "v2")]


async def test_repos_from_env_and_validation(monkeypatch):
    async with Client(mcp) as c:
        none = await c.call_tool("ci_status", {})
        bad = await c.call_tool("ci_status", {"repos": ["not a repo"]})
        monkeypatch.setenv("DEV_RADAR_GITHUB_REPOS", "o/r, o/r")
        ok = await c.call_tool("ci_status", {})
        res = await c.read_resource("github://repos")
    assert none.is_error and "DEV_RADAR_GITHUB_REPOS" in none.content[0].text
    assert bad.is_error
    assert [s["repo"] for s in ok.structured_content["items"]] == ["o/r"]  # deduplicated
    assert res.contents[0].text == "o/r"


def test_token_prefers_env(monkeypatch):
    github_activity._token.cache_clear()
    monkeypatch.setenv("GITHUB_TOKEN", "t0k")
    try:
        assert github_activity._token() == "t0k"
    finally:
        github_activity._token.cache_clear()
