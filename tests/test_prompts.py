"""Server-side prompt templates are listed and render with and without arguments."""

from mcp import Client

from dev_radar.servers import deps_watch, git_insights, github_activity


async def test_standup_prompt_embeds_commits(repo, monkeypatch):
    monkeypatch.setenv("DEV_RADAR_REPO", str(repo))
    async with Client(git_insights.mcp) as c:
        prompts = {p.name: p for p in (await c.list_prompts()).prompts}
        r = await c.get_prompt("standup", {"days": "7"})
        bad = await c.get_prompt("standup", {"days": "lots"})  # falls back to 1 day
    assert [a.name for a in prompts["standup"].arguments] == ["days"]
    text = r.messages[0].content.text
    assert r.messages[0].role == "user" and "feat: app v2 (Ada" in text and "last 7 day(s)" in text
    assert "last 1 day(s)" in bad.messages[0].content.text


async def test_review_and_dependency_prompts():
    async with Client(github_activity.mcp) as c:
        r = await c.get_prompt("review_queue", {"repos": "o/r"})
        default = await c.get_prompt("review_queue", {})
    assert "o/r" in r.messages[0].content.text and "prs_awaiting_review" in r.messages[0].content.text
    assert "DEV_RADAR_GITHUB_REPOS" in default.messages[0].content.text
    async with Client(deps_watch.mcp) as c:
        names = [p.name for p in (await c.list_prompts()).prompts]
        d = await c.get_prompt("triage_dependencies", {"project": "/srv/app"})
    assert names == ["triage_dependencies"]
    assert "/srv/app" in d.messages[0].content.text
