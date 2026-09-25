"""dev-radar CLI: launch the MCP servers and print a briefing."""

from __future__ import annotations

import argparse
import asyncio
import os
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic

from dev_radar.briefing import claude_briefing, fallback_briefing
from dev_radar.hub import SERVERS, McpHub
from dev_radar.render import slack_payload, to_html

DEFAULT_KEYWORDS = "ai,llm,llms,python,rust,postgres,security,mcp"


def parse_since(text: str, now: datetime | None = None) -> datetime:
    """'36h', '3d', '2w', 'yesterday' (local midnight) or an ISO date/datetime -> aware datetime."""
    now = (now or datetime.now().astimezone()).replace(microsecond=0)
    if m := re.fullmatch(r"(\d+)([hdw])", text.strip()):
        unit = {"h": "hours", "d": "days", "w": "weeks"}[m[2]]
        return now - timedelta(**{unit: int(m[1])})
    if text.strip() == "yesterday":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    parsed = datetime.fromisoformat(text.strip())  # ValueError on garbage
    return parsed if parsed.tzinfo else parsed.astimezone()


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def run(args: argparse.Namespace) -> str:
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    mode = args.mode
    if mode == "auto":
        mode = "claude" if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") else "fallback"
    async with McpHub(args.repo, SERVERS | args.connect) as hub:
        _log(f"connected {len(hub.tools)} tools: {', '.join(sorted(hub.tools))}")
        if args.list_tools:
            return "\n".join(f"{t['name']}: {t['description']}" for t in hub.anthropic_tools()) + "\n"
        if mode == "fallback":
            _log("mode: fallback (deterministic)")
            return await fallback_briefing(hub, keywords, args.days, args.since)
        _log("mode: claude")
        try:
            return await claude_briefing(hub, keywords, args.days, log=_log, since=args.since)
        except (anthropic.APIError, RuntimeError) as e:
            if args.mode == "claude":
                raise
            _log(f"claude mode failed ({type(e).__name__}: {e}); falling back")
            return await fallback_briefing(hub, keywords, args.days, args.since)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dev-radar", description=__doc__)
    p.add_argument("--repo", default=".", help="git repo to brief on (default: cwd)")
    window = p.add_mutually_exclusive_group()
    window.add_argument("--days", type=int, default=7, help="look-back window in days (1-365)")
    window.add_argument("--since", help="window start: 36h, 3d, 2w, yesterday, or an ISO date/datetime")
    p.add_argument("--keywords", default=DEFAULT_KEYWORDS, help="comma-separated HN keywords")
    p.add_argument("--mode", choices=["auto", "claude", "fallback"], default="auto",
                   help="auto = claude if ANTHROPIC_API_KEY is set, else fallback")
    p.add_argument("--format", choices=["md", "html", "slack"], default="md",
                   help="md, self-contained html, or slack (incoming-webhook JSON payload with mrkdwn text)")
    p.add_argument("--out", type=Path, help="also write the briefing to this file")
    p.add_argument("--list-tools", action="store_true", help="list discovered MCP tools and exit")
    p.add_argument("--github-repos", help="comma-separated owner/name repos for github-activity "
                   "(default: $DEV_RADAR_GITHUB_REPOS)")
    p.add_argument("--connect", action="append", default=[], metavar="NAME=URL",
                   help=f"use a running Streamable HTTP server instead of spawning one; NAME in {sorted(SERVERS)}")
    args = p.parse_args(argv)
    connect = dict(c.partition("=")[::2] for c in args.connect)
    if unknown := set(connect) - set(SERVERS):
        p.error(f"--connect: unknown server(s) {sorted(unknown)}; choose from {sorted(SERVERS)}")
    if bad := [u for u in connect.values() if not u.startswith(("http://", "https://"))]:
        p.error(f"--connect needs NAME=http(s)://host:port/mcp, got {bad}")
    args.connect = connect
    if args.github_repos is not None:
        os.environ["DEV_RADAR_GITHUB_REPOS"] = args.github_repos  # forwarded to the spawned server
    if args.since:
        try:
            start = parse_since(args.since)
        except ValueError:
            p.error(f"--since {args.since!r}: use 36h, 3d, 2w, yesterday or an ISO date like 2026-09-20")
        args.since = start.isoformat()
        # Day-granular tools (churn, releases) get the smallest whole-day window covering it.
        args.days = max(1, math.ceil((datetime.now().astimezone() - start).total_seconds() / 86400))
    if not 1 <= args.days <= 365:
        p.error("--days/--since must span between 1 and 365 days")
    if not Path(args.repo).is_dir():
        p.error(f"--repo {args.repo!r} is not a directory")
    args.repo = str(Path(args.repo).resolve())
    # ponytail: env-only check; users on an `ant auth login` profile need ANTHROPIC_API_KEY or --mode auto won't pick Claude
    if args.mode == "claude" and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        p.error("--mode claude needs ANTHROPIC_API_KEY (or use --mode fallback)")

    try:
        text = asyncio.run(run(args))
    except (anthropic.APIError, RuntimeError) as e:
        sys.exit(f"dev-radar: {type(e).__name__}: {e}")
    if not args.list_tools and args.format == "html":
        text = to_html(text, title=text.splitlines()[0].lstrip("# ") if text.strip() else "Dev Radar")
    elif not args.list_tools and args.format == "slack":
        text = slack_payload(text)
    sys.stdout.write(text)
    if args.out:
        args.out.write_text(text)
        _log(f"wrote {args.out}")


if __name__ == "__main__":
    main()
