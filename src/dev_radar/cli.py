"""dev-radar CLI: launch the MCP servers and print a briefing."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import anthropic

from dev_radar.briefing import claude_briefing, fallback_briefing
from dev_radar.hub import McpHub

DEFAULT_KEYWORDS = "ai,llm,llms,python,rust,postgres,security,mcp"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def run(args: argparse.Namespace) -> str:
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    mode = args.mode
    if mode == "auto":
        mode = "claude" if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") else "fallback"
    async with McpHub(args.repo) as hub:
        _log(f"connected {len(hub.tools)} tools: {', '.join(sorted(hub.tools))}")
        if args.list_tools:
            return "\n".join(f"{t['name']}: {t['description']}" for t in hub.anthropic_tools()) + "\n"
        if mode == "fallback":
            _log("mode: fallback (deterministic)")
            return await fallback_briefing(hub, keywords, args.days)
        _log("mode: claude")
        try:
            return await claude_briefing(hub, keywords, args.days, log=_log)
        except (anthropic.APIError, RuntimeError) as e:
            if args.mode == "claude":
                raise
            _log(f"claude mode failed ({type(e).__name__}: {e}); falling back")
            return await fallback_briefing(hub, keywords, args.days)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dev-radar", description=__doc__)
    p.add_argument("--repo", default=".", help="git repo to brief on (default: cwd)")
    p.add_argument("--days", type=int, default=7, help="look-back window in days (1-365)")
    p.add_argument("--keywords", default=DEFAULT_KEYWORDS, help="comma-separated HN keywords")
    p.add_argument("--mode", choices=["auto", "claude", "fallback"], default="auto",
                   help="auto = claude if ANTHROPIC_API_KEY is set, else fallback")
    p.add_argument("--out", type=Path, help="also write the briefing to this file")
    p.add_argument("--list-tools", action="store_true", help="list discovered MCP tools and exit")
    args = p.parse_args(argv)
    if not 1 <= args.days <= 365:
        p.error("--days must be between 1 and 365")
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
    sys.stdout.write(text)
    if args.out:
        args.out.write_text(text)
        _log(f"wrote {args.out}")


if __name__ == "__main__":
    main()
