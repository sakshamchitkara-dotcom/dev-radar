"""github-activity MCP server: PRs awaiting review, CI status and recent releases.

Read-only: it only ever issues GET requests to the GitHub REST API.
Repos come from each call's `repos` argument or $DEV_RADAR_GITHUB_REPOS
(comma-separated owner/name). The token is $GITHUB_TOKEN, else `gh auth token`,
else none (anonymous: public repos only, 60 requests/hour).
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, TypeVar

import httpx
from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from dev_radar.servers import serve

GITHUB_API = os.environ.get("GITHUB_API_BASE", "https://api.github.com")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

mcp = MCPServer("github-activity")
logging.getLogger("httpx").setLevel(logging.WARNING)

Repos = Annotated[
    list[Annotated[str, Field(pattern=REPO_RE.pattern)]] | None,
    Field(max_length=50, description="owner/name repos; defaults to $DEV_RADAR_GITHUB_REPOS"),
]
Days = Annotated[int, Field(ge=1, le=365, description="Look-back window in days")]


class PullRequest(BaseModel):
    repo: str
    number: int
    title: str
    author: str
    url: str
    age_days: float
    requested_reviewers: list[str]
    reviews: int


class WorkflowRun(BaseModel):
    workflow: str
    status: str
    conclusion: str | None
    url: str


class CiStatus(BaseModel):
    repo: str
    branch: str
    sha: str | None
    state: str  # success | failure | pending | none
    runs: list[WorkflowRun]


class Release(BaseModel):
    repo: str
    tag: str
    name: str
    published_at: str
    prerelease: bool
    url: str


class RepoError(BaseModel):
    repo: str
    error: str


class PullRequests(BaseModel):
    items: list[PullRequest]
    errors: list[RepoError]


class CiStatuses(BaseModel):
    items: list[CiStatus]
    errors: list[RepoError]


class Releases(BaseModel):
    items: list[Release]
    errors: list[RepoError]


@functools.cache
def _token() -> str | None:
    if tok := os.environ.get("GITHUB_TOKEN"):
        return tok
    if gh := shutil.which("gh"):
        out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    return None


def _repos(repos: list[str] | None) -> list[str]:
    chosen = repos or [r.strip() for r in os.environ.get("DEV_RADAR_GITHUB_REPOS", "").split(",") if r.strip()]
    if not chosen:
        raise ToolError("No repos given and $DEV_RADAR_GITHUB_REPOS is not set")
    bad = [r for r in chosen if not REPO_RE.match(r)]
    if bad:
        raise ToolError(f"Invalid repo name(s): {bad}; expected owner/name")
    return list(dict.fromkeys(chosen))


def _client() -> httpx.AsyncClient:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if tok := _token():
        headers["Authorization"] = f"Bearer {tok}"
    return httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=15, limits=httpx.Limits(max_connections=10))


def _check(resp: httpx.Response, path: str) -> Any:
    if resp.status_code >= 400:
        msg = resp.json().get("message", resp.text) if "json" in resp.headers.get("content-type", "") else resp.text
        raise ToolError(f"GET {path} -> {resp.status_code}: {msg}")
    return resp.json()


async def _get(client: httpx.AsyncClient, path: str, **params: Any) -> Any:
    return _check(await client.get(path, params=params), path)


async def _get_pages(client: httpx.AsyncClient, path: str, max_pages: int = 5, **params: Any) -> list[Any]:
    """A list endpoint followed through its Link rel="next" headers, up to `max_pages` pages."""
    items: list[Any] = []
    resp = await client.get(path, params=params)
    for page in range(1, max_pages + 1):
        items += _check(resp, path)
        if page == max_pages or not (url := resp.links.get("next", {}).get("url")):
            break
        resp = await client.get(url)  # the next URL carries the query (an explicit params={} would drop it)
    return items


T = TypeVar("T")


async def _per_repo(repos: list[str], fetch: Callable[[httpx.AsyncClient, str], Awaitable[list[T]]]) -> tuple[list[T], list[RepoError]]:
    """Run `fetch` for every repo concurrently; one bad repo becomes an error row, not a failed call."""
    async with _client() as client:
        results = await asyncio.gather(*(fetch(client, r) for r in repos), return_exceptions=True)
    items: list[T] = []
    errors: list[RepoError] = []
    for repo, res in zip(repos, results):
        if isinstance(res, BaseException):
            errors.append(RepoError(repo=repo, error=str(res) or type(res).__name__))
        else:
            items.extend(res)
    return items, errors


def _age_days(iso: str) -> float:
    return round((datetime.now(UTC) - datetime.fromisoformat(iso)).total_seconds() / 86400, 1)


@mcp.tool()
async def prs_awaiting_review(repos: Repos = None, include_reviewed: bool = False) -> PullRequests:
    """Open, non-draft PRs that still need a review (reviewers requested or no reviews yet), oldest first."""
    async def fetch(client: httpx.AsyncClient, repo: str) -> list[PullRequest]:
        pulls = await _get_pages(client, f"/repos/{repo}/pulls", state="open", per_page=100)  # up to 500 open PRs
        pulls = [p for p in pulls if not p.get("draft")]
        reviews = await asyncio.gather(*(_get(client, f"/repos/{repo}/pulls/{p['number']}/reviews", per_page=100) for p in pulls))
        out = []
        for p, revs in zip(pulls, reviews):
            requested = [u["login"] for u in p.get("requested_reviewers", [])] + [t["slug"] for t in p.get("requested_teams", [])]
            if include_reviewed or requested or not revs:
                out.append(PullRequest(
                    repo=repo, number=p["number"], title=p["title"], author=p["user"]["login"], url=p["html_url"],
                    age_days=_age_days(p["created_at"]), requested_reviewers=requested, reviews=len(revs),
                ))
        return out

    items, errors = await _per_repo(_repos(repos), fetch)
    return PullRequests(items=sorted(items, key=lambda p: -p.age_days), errors=errors)


@mcp.tool()
async def ci_status(ctx: Context, repos: Repos = None) -> CiStatuses:
    """GitHub Actions result for the latest commit on each repo's default branch.

    States are remembered as the `github://ci` resource; subscribers are notified when any repo's state changes.
    """
    async def fetch(client: httpx.AsyncClient, repo: str) -> list[CiStatus]:
        branch = (await _get(client, f"/repos/{repo}"))["default_branch"]
        runs = (await _get(client, f"/repos/{repo}/actions/runs", branch=branch, per_page=30))["workflow_runs"]
        if not runs:
            return [CiStatus(repo=repo, branch=branch, sha=None, state="none", runs=[])]
        sha = runs[0]["head_sha"]  # newest first
        latest: dict[str, dict[str, Any]] = {}
        for r in runs:  # keep the newest run of each workflow for that commit
            if r["head_sha"] == sha:
                latest.setdefault(r["name"], r)
        head = [WorkflowRun(workflow=n, status=r["status"], conclusion=r["conclusion"], url=r["html_url"]) for n, r in latest.items()]
        if any(r.conclusion in ("failure", "timed_out", "cancelled", "startup_failure") for r in head):
            state = "failure"
        elif any(r.status != "completed" for r in head):
            state = "pending"
        else:
            state = "success"
        return [CiStatus(repo=repo, branch=branch, sha=sha[:7], state=state, runs=head)]

    items, errors = await _per_repo(_repos(repos), fetch)
    changed = False
    for s in items:
        changed |= _ci_states.get(s.repo) != (s.sha, s.state)
        _ci_states[s.repo] = (s.sha, s.state)
    if changed:
        await ctx.notify_resource_updated(CI_URI)
    return CiStatuses(items=items, errors=errors)


CI_URI = "github://ci"
_ci_states: dict[str, tuple[str | None, str]] = {}  # repo -> (sha, state) from the last ci_status call


@mcp.resource(CI_URI, mime_type="application/json")
def last_ci_states() -> str:
    """Last known CI state per repo (refreshed by the `ci_status` tool). Subscribable."""
    return json.dumps({repo: {"sha": sha, "state": state} for repo, (sha, state) in _ci_states.items()})


@mcp.tool()
async def recent_releases(repos: Repos = None, days: Days = 30) -> Releases:
    """Published (non-draft) releases in the look-back window, newest first."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    async def fetch(client: httpx.AsyncClient, repo: str) -> list[Release]:
        return [
            Release(repo=repo, tag=r["tag_name"], name=r["name"] or r["tag_name"], published_at=r["published_at"],
                    prerelease=r["prerelease"], url=r["html_url"])
            for r in await _get(client, f"/repos/{repo}/releases", per_page=20)
            if not r["draft"] and r["published_at"] and datetime.fromisoformat(r["published_at"]) >= cutoff
        ]

    items, errors = await _per_repo(_repos(repos), fetch)
    return Releases(items=sorted(items, key=lambda r: r.published_at, reverse=True), errors=errors)


@mcp.resource("github://repos", mime_type="text/plain")
def configured_repos() -> str:
    """The repos this server watches by default ($DEV_RADAR_GITHUB_REPOS), one per line."""
    raw = os.environ.get("DEV_RADAR_GITHUB_REPOS", "")
    return "\n".join(dict.fromkeys(r.strip() for r in raw.split(",") if r.strip()))


@mcp.prompt(title="Review queue triage")
def review_queue(repos: str = "") -> str:
    """Ask the model to triage open PRs and CI health for the given (or configured) repos."""
    target = repos.strip() or "the configured repos ($DEV_RADAR_GITHUB_REPOS)"
    return (
        f"Triage the review queue for {target}.\n"
        "1. Call prs_awaiting_review and ci_status.\n"
        "2. List PRs oldest first with who is blocking each one.\n"
        "3. Flag any repo whose default branch CI is failing: a red main blocks every PR.\n"
        "4. End with the three reviews that would unblock the most work today."
    )


def main() -> None:
    serve(mcp)


if __name__ == "__main__":
    main()
