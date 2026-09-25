"""git-insights MCP server: recent commits, churn hotspots and authors for a local repo.

The repo defaults to $DEV_RADAR_REPO (or the working directory); every tool also
accepts an explicit `repo` path. Git is invoked without a shell.
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dev_radar.servers import serve

mcp = MCPServer("git-insights")

Days = Annotated[int, Field(ge=1, le=365, description="Look-back window in days")]
Limit = Annotated[int, Field(ge=1, le=200, description="Maximum rows to return")]
RepoPath = Annotated[str | None, Field(description="Path inside a git repo; defaults to $DEV_RADAR_REPO or cwd")]


# Generated files churn constantly and drown out real hotspots.
LOCKFILES = {"uv.lock", "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock", "go.sum", "Gemfile.lock"}


class Commit(BaseModel):
    sha: str
    author: str
    date: str
    subject: str


class FileChurn(BaseModel):
    path: str
    commits: int
    lines_added: int
    lines_deleted: int


class AuthorStats(BaseModel):
    author: str
    commits: int


def _repo_root(repo: str | None) -> Path:
    path = Path(repo or os.environ.get("DEV_RADAR_REPO") or os.getcwd()).expanduser()
    if not path.is_dir():
        raise ToolError(f"Not a directory: {path}")
    out = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10,
    )
    if out.returncode != 0:
        raise ToolError(f"Not a git repository: {path}")
    return Path(out.stdout.strip())


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        # An empty repo has no HEAD; treat it as "no history" rather than an error.
        if "does not have any commits" in out.stderr:
            return ""
        raise ToolError(f"git {args[0]} failed: {out.stderr.strip()}")
    return out.stdout


@mcp.tool()
def recent_commits(days: Days = 7, limit: Limit = 20, repo: RepoPath = None) -> list[Commit]:
    """List the most recent commits in the look-back window, newest first."""
    root = _repo_root(repo)
    raw = _git(root, "log", f"--since={days} days ago", f"-n{limit}", "--format=%h%x1f%an%x1f%aI%x1f%s")
    return [Commit(**dict(zip(("sha", "author", "date", "subject"), line.split("\x1f"))))
            for line in raw.splitlines() if line]


@mcp.tool()
def churn_hotspots(
    days: Days = 30, limit: Limit = 10, repo: RepoPath = None, include_lockfiles: bool = False
) -> list[FileChurn]:
    """Files changed most often in the window (by commit count, then lines touched). Lockfiles skipped by default."""
    root = _repo_root(repo)
    raw = _git(root, "log", f"--since={days} days ago", "--numstat", "--format=")
    stats: dict[str, list[int]] = {}
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if not include_lockfiles and Path(path).name in LOCKFILES:
            continue
        s = stats.setdefault(path, [0, 0, 0])
        s[0] += 1
        # Binary files report "-" for line counts.
        s[1] += int(added) if added.isdigit() else 0
        s[2] += int(deleted) if deleted.isdigit() else 0
    ranked = sorted(stats.items(), key=lambda kv: (-kv[1][0], -(kv[1][1] + kv[1][2]), kv[0]))
    return [FileChurn(path=p, commits=c, lines_added=a, lines_deleted=d) for p, (c, a, d) in ranked[:limit]]


@mcp.tool()
def top_authors(days: Days = 30, limit: Limit = 10, repo: RepoPath = None) -> list[AuthorStats]:
    """Authors ranked by commit count in the window."""
    root = _repo_root(repo)
    raw = _git(root, "log", f"--since={days} days ago", "--format=%an")
    counts = Counter(line for line in raw.splitlines() if line)
    return [AuthorStats(author=a, commits=n) for a, n in counts.most_common(limit)]


@mcp.resource("git://summary", mime_type="text/markdown")
def repo_summary() -> str:
    """Markdown summary of the default repo: branch, HEAD and last-7-day activity."""
    root = _repo_root(None)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() if _git(root, "log", "-1", "--format=%h") else "(no commits)"
    commits = recent_commits(days=7, limit=200)
    authors = top_authors(days=7, limit=5)
    lines = [
        f"# {root.name}",
        f"- branch: `{branch}`",
        f"- commits (7d): {len(commits)}",
        f"- active authors (7d): {', '.join(a.author for a in authors) or 'none'}",
    ]
    return "\n".join(lines)


@mcp.prompt(title="Stand-up summary")
def standup(days: str = "1") -> str:
    """Draft a stand-up update from the default repo's recent commits (embedded in the prompt)."""
    n = int(days) if days.isdigit() and 1 <= int(days) <= 365 else 1
    commits = recent_commits(days=n, limit=50)
    log = "\n".join(f"- {c.sha} {c.subject} ({c.author}, {c.date[:10]})" for c in commits) or "(no commits)"
    return (
        f"Here are the commits from the last {n} day(s):\n\n{log}\n\n"
        "Write a short stand-up update grouped by theme: what shipped, what is in progress, and any risk "
        "(reverts, fixups, large churn). Use churn_hotspots if you need more context. Keep it under 8 bullets."
    )


def main() -> None:
    serve(mcp)


if __name__ == "__main__":
    main()
