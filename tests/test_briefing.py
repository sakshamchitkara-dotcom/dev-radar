"""render_fallback with populated GitHub/deps sections and per-source failures (pure function, no servers)."""

from types import SimpleNamespace

import pytest

from dev_radar import briefing
from dev_radar.briefing import render_fallback

DATA = {
    "commits": [{"sha": "abc1234", "subject": "feat: x", "author": "Ada", "date": "2026-09-24T10:00:00+00:00"}],
    "authors": [{"author": "Ada", "commits": 3}, {"author": "Grace", "commits": 1}],
    "hotspots": [{"path": "app.py", "commits": 3, "lines_added": 10, "lines_deleted": 2}],
    "stories": [{"id": 1, "title": "Rust 2.0", "url": None, "hn_url": "https://news.ycombinator.com/item?id=1",
                 "score": 300, "comments": 120}],
    "system": {"cpu_percent": 12.0, "cpu_count": 8, "load_avg_1m": 1.5, "memory_percent": 93.0,
               "memory_used_gib": 15.0, "memory_total_gib": 16.0, "disk_path": "/", "disk_percent": 40.0,
               "disk_free_gib": 200.0, "warnings": ["memory at 93%"]},
    "processes": [{"name": "python", "memory_mib": 512.0}],
    "prs": {"items": [{"repo": "o/r", "number": 7, "url": "https://gh/pr/7", "title": "Add cache", "author": "bob",
                       "age_days": 4.2, "requested_reviewers": ["ada"]},
                      {"repo": "o/r", "number": 9, "url": "https://gh/pr/9", "title": "Docs", "author": "eve",
                       "age_days": 0.5, "requested_reviewers": []}], "errors": []},
    "ci": {"items": [{"repo": "o/r", "branch": "main", "sha": "abc1234", "state": "failure",
                      "runs": [{"workflow": "CI", "url": "https://gh/run/1", "conclusion": "failure", "status": "completed"}]},
                     {"repo": "o/empty", "branch": "trunk", "sha": None, "state": "none", "runs": []}],
           "errors": [{"repo": "o/gone", "error": "GET /repos/o/gone -> 404: Not Found"}]},
    "releases": {"items": [{"repo": "o/r", "tag": "v1.2", "url": "https://gh/rel", "published_at": "2026-09-23T00:00:00Z"}],
                 "errors": []},
    "vulns": {"checked": 40, "vulnerabilities": [{"id": "GHSA-1", "url": "https://osv.dev/GHSA-1", "package": "jinja2",
                                                  "version": "3.1.2", "severity": "HIGH", "summary": "XSS",
                                                  "fixed_in": ["3.1.3"]}]},
    "outdated": {"checked": 4, "outdated": [{"name": "httpx", "current": "0.27.0", "latest": "0.28.1"}], "errors": []},
}


def test_full_data_renders_every_section():
    md = render_fallback(DATA, "/x/app", ["rust"], 7)
    assert "_Repo `app` · last 7d · deterministic mode_" in md
    assert "- 4 commit(s) in the last 7 days by 2 author(s)" in md
    assert "- …and 3 more" in md
    assert "- CI failing on o/r" in md
    assert "- 1 known vulnerabilit(ies) in 1 package(s)" in md
    assert "- Machine warnings: memory at 93%" in md
    assert "- CI `o/r` main@abc1234: **failure** · [CI](https://gh/run/1) failure" in md
    assert "- CI `o/empty` trunk: no workflow runs" in md
    assert "- PR [o/r#7](https://gh/pr/7) Add cache — bob, 4d old, waiting on ada" in md
    assert "- PR [o/r#9](https://gh/pr/9) Docs — eve, 0d old, no reviews yet" in md
    assert "- Released [o/r v1.2](https://gh/rel) 2026-09-23" in md
    assert "- _o/gone: GET /repos/o/gone -> 404: Not Found_" in md
    assert "  - [GHSA-1](https://osv.dev/GHSA-1) `jinja2` 3.1.2 (HIGH): XSS — fixed in 3.1.3" in md
    assert "- 1 of 4 direct dependencies behind latest: `httpx` 0.27.0 → 0.28.1" in md
    assert "- [Rust 2.0](https://news.ycombinator.com/item?id=1) — 300 pts" in md  # no url: falls back to HN link
    assert "- Heaviest processes: python (512 MiB)" in md
    focus = md.split("## Suggested focus today\n")[1]
    assert focus.splitlines()[:3] == [
        "- Fix the red default branch on o/r before merging anything else.",
        "- Upgrade `jinja2` past 3.1.2 (GHSA-1).",
        "- Review o/r#7 — oldest PR waiting (4d).",
    ]


def test_every_source_failing_still_renders_a_briefing():
    broken = {k: {"error": f"{k} down"} for k in DATA}
    md = render_fallback(broken, "/x/app", [], 7, since="2026-09-24T00:00:00+00:00")
    assert "since 2026-09-24T00:00:00+00:00" in md
    assert "## TL;DR\n- No data gathered" in md
    assert "_git-insights failed: commits down_" in md
    assert "_github-activity failed: ci down_" in md
    assert "_deps-watch failed: vulns down_" in md and "_deps-watch outdated check failed: outdated down_" in md
    assert "## Industry radar (all topics)\n_hn-trends failed: stories down_" in md
    assert "_system-health failed: system down_" in md
    assert md.rstrip().endswith("- Nothing urgent. Ship something.")


def test_green_ci_and_empty_results():
    data = DATA | {
        "ci": {"items": [{"repo": "o/r", "branch": "main", "sha": "a", "state": "success", "runs": []}], "errors": []},
        "prs": {"items": [], "errors": []}, "releases": {"items": [], "errors": []},
        "vulns": {"checked": 0, "vulnerabilities": []}, "commits": [], "hotspots": [], "stories": [],
    }
    md = render_fallback(data, "/x/app", ["ai"], 3)
    assert "- CI green or pending on all 1 watched repo(s)" in md
    assert "- No PRs awaiting review across 1 repo(s)" in md
    assert "- No releases in the last 3 days" in md
    assert "No lockfile found" in md
    assert "No commits in the window." in md and "No file changes in the window." in md
    assert "Nothing on the HN front page matches today." in md


# ---------------------------------------------------------------- claude loop stop conditions

class FakeHub:
    repo = "/x/app"

    def anthropic_tools(self):
        return [{"name": "git__top_authors", "description": "", "input_schema": {"type": "object"}}]

    async def call(self, name, args):
        return SimpleNamespace(is_error=False, structured_content={"result": []}, content=[])


def scripted(*responses):
    it = iter(responses)

    async def create(**kw):
        return next(it)
    return SimpleNamespace(messages=SimpleNamespace(create=create))


TOOL_TURN = SimpleNamespace(stop_reason="tool_use", stop_details=None,
                            content=[SimpleNamespace(type="tool_use", id="t", name="git__top_authors", input={})])


@pytest.mark.parametrize("response,error", [
    (SimpleNamespace(stop_reason="refusal", stop_details={"category": "x"}, content=[]), "declined"),
    (SimpleNamespace(stop_reason="max_tokens", stop_details=None, content=[]), "max_tokens"),
])
async def test_claude_loop_raises_on_refusal_and_max_tokens(response, error):
    with pytest.raises(RuntimeError, match=error):
        await briefing.claude_briefing(FakeHub(), [], 7, client=scripted(response))


async def test_claude_loop_gives_up_after_max_turns():
    client = scripted(*[TOOL_TURN] * briefing.MAX_TURNS)
    logged = []
    with pytest.raises(RuntimeError, match=f"within {briefing.MAX_TURNS} turns"):
        await briefing.claude_briefing(FakeHub(), ["ai"], 7, client=client, since="2026-09-24", log=logged.append)
    assert logged[0] == "-> git__top_authors({})" and len(logged) == briefing.MAX_TURNS
