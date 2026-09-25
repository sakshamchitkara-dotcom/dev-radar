"""dev-radar CLI: launch the MCP servers and print a briefing."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from anthropic.lib.credentials import default_credentials

from dev_radar import config, history
from dev_radar.briefing import claude_briefing, gather, render_fallback
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


def claude_credentials_problem() -> str | None:
    """None when the SDK can authenticate (env key/token, `ant auth login` profile, federation); else why not."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None
    try:
        found = default_credentials()
    except anthropic.AnthropicError as e:  # an explicitly selected profile that is missing or broken
        return str(e)
    return None if found else "no ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or `ant auth login` profile found"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def run(args: argparse.Namespace) -> str:
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    mode = args.mode
    if mode == "auto":
        mode = "claude" if claude_credentials_problem() is None else "fallback"
    async with McpHub(args.repo, SERVERS | args.connect) as hub:
        _log(f"connected {len(hub.tools)} tools: {', '.join(sorted(hub.tools))}")
        for name, why in hub.failed.items():
            _log(f"warning: {name} server unavailable, its sections will say so ({why})")
        if args.list_tools:
            return "\n".join(f"{t['name']}: {t['description']}" for t in hub.anthropic_tools()) + "\n"
        # The fixed tool set feeds the fallback template and the history diff in both modes.
        skip = frozenset(k for s in args.disabled for k in config.SECTIONS[s])
        data = await gather(hub, keywords, args.days, args.since, skip)
        md = None
        if mode == "claude":
            _log("mode: claude")
            try:
                md = await claude_briefing(hub, keywords, args.days, log=_log, since=args.since)
            except (anthropic.APIError, RuntimeError) as e:
                if args.mode == "claude":
                    raise
                _log(f"claude mode failed ({type(e).__name__}: {e}); falling back")
        else:
            _log("mode: fallback (deterministic)")
        md = md or render_fallback(data, hub.repo, keywords, args.days, args.since)
        md = config.drop_sections(md, args.disabled)
        if args.timings:
            _log(hub.timing_report())
    if args.history_dir is None:
        return md
    now = datetime.now().astimezone()
    prev = history.baseline(history.load_all(args.history_dir), now)
    md = history.insert_section(md, history.changes_section(prev, data, now))
    _log(f"saved history {history.save(args.history_dir, data, md, now)}")
    if removed := history.prune(args.history_dir, args.keep):
        _log(f"pruned {len(removed)} old briefing(s) (--keep {args.keep})")
    return md


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dev-radar", description=__doc__)
    p.add_argument("--repo", default=".", help="git repo to brief on (default: cwd)")
    window = p.add_mutually_exclusive_group()
    window.add_argument("--days", type=int, default=7, help="look-back window in days (1-365)")
    window.add_argument("--since", help="window start: 36h, 3d, 2w, yesterday, or an ISO date/datetime")
    p.add_argument("--keywords", default=DEFAULT_KEYWORDS, help="comma-separated HN keywords")
    p.add_argument("--mode", choices=["auto", "claude", "fallback"], default="auto",
                   help="auto = claude if credentials are found (API key, auth token or `ant auth login` profile), else fallback")
    p.add_argument("--format", choices=["md", "html", "slack"], default="md",
                   help="md, self-contained html, or slack (incoming-webhook JSON payload with mrkdwn text)")
    p.add_argument("--out", type=Path, help="also write the briefing to this file")
    p.add_argument("--list-tools", action="store_true", help="list discovered MCP tools and exit")
    p.add_argument("--timings", action="store_true", help="print per-tool call latency to stderr after the run")
    p.add_argument("--github-repos", help="comma-separated owner/name repos for github-activity "
                   "(default: $DEV_RADAR_GITHUB_REPOS)")
    p.add_argument("--calendars", help=f".ics files or directories for today's meetings, separated by {os.pathsep!r} "
                   "(default: $DEV_RADAR_CALENDARS)")
    p.add_argument("--history-dir", type=Path, help="where past briefings are kept (default: "
                   "$XDG_STATE_HOME/dev-radar/history/<repo>-<hash>, i.e. ~/.local/state/...)")
    p.add_argument("--no-history", action="store_true", help="don't save this briefing or diff against earlier ones")
    p.add_argument("--keep", type=int, default=90, metavar="N",
                   help="keep only the newest N saved briefings (default 90; 0 keeps everything)")
    p.add_argument("--list-history", action="store_true", help="list saved briefings for --repo and exit")
    p.add_argument("--connect", action="append", default=[], metavar="NAME=URL",
                   help=f"use a running Streamable HTTP server instead of spawning one; NAME in {sorted(SERVERS)}")
    p.add_argument("--config", type=Path, help="TOML file with defaults for these flags and [sections] on/off "
                   f"(default: {config.default_path()} if it exists)")
    pre, _ = p.parse_known_args(argv)
    cfg_path = pre.config or (config.default_path() if config.default_path().is_file() else None)
    disabled: set[str] = set()
    if cfg_path:
        try:
            defaults, disabled = config.load(cfg_path)
        except ValueError as e:
            p.error(f"--config: {e}")
        p.set_defaults(**defaults)
    args = p.parse_args(argv)
    args.disabled = disabled
    connect = dict(c.partition("=")[::2] for c in args.connect)
    if unknown := set(connect) - set(SERVERS):
        p.error(f"--connect: unknown server(s) {sorted(unknown)}; choose from {sorted(SERVERS)}")
    if bad := [u for u in connect.values() if not u.startswith(("http://", "https://"))]:
        p.error(f"--connect needs NAME=http(s)://host:port/mcp, got {bad}")
    args.connect = connect
    if args.github_repos is not None:
        os.environ["DEV_RADAR_GITHUB_REPOS"] = args.github_repos  # forwarded to the spawned server
    if args.calendars is not None:
        os.environ["DEV_RADAR_CALENDARS"] = args.calendars
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
    if args.keep < 0:
        p.error("--keep must be 0 (keep everything) or a positive count")
    if not Path(args.repo).is_dir():
        p.error(f"--repo {args.repo!r} is not a directory")
    args.repo = str(Path(args.repo).resolve())
    args.history_dir = None if args.no_history else (args.history_dir or history.default_dir(args.repo))
    if args.list_history:
        records = history.load_all(args.history_dir) if args.history_dir else []
        for r in records:
            print(f"{r['created_at']}  {r['path']}")
        _log(f"{len(records)} saved briefing(s) in {args.history_dir}")
        return
    if args.mode == "claude" and (problem := claude_credentials_problem()):
        p.error(f"--mode claude needs Claude credentials: {problem} (or use --mode fallback)")

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
