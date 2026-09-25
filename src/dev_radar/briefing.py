"""Turn MCP tool output into a markdown engineering briefing.

Two modes share the same McpHub:
- fallback: call a fixed set of tools and fill a template (no API key needed)
- claude:   let Claude pick tools from every server and write the briefing
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dev_radar.hub import McpHub, result_data, result_text

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- fallback


async def gather(hub: McpHub, keywords: list[str], days: int) -> dict[str, Any]:
    """Call the fixed tool set concurrently; failed calls come back as {"error": text}."""
    calls = {
        "commits": ("git__recent_commits", {"days": days, "limit": 15}),
        "hotspots": ("git__churn_hotspots", {"days": max(days, 30), "limit": 5}),
        "authors": ("git__top_authors", {"days": days, "limit": 5}),
        "stories": ("hn__top_stories", {"keywords": keywords, "limit": 6, "scan": 100}),
        "system": ("system__snapshot", {}),
        "processes": ("system__top_processes", {"sort_by": "memory", "limit": 3}),
    }
    results = await asyncio.gather(*(hub.call(t, a) for t, a in calls.values()), return_exceptions=True)
    data: dict[str, Any] = {}
    for key, res in zip(calls, results):
        if isinstance(res, BaseException):
            data[key] = {"error": str(res)}
        elif res.is_error:
            data[key] = {"error": result_text(res)}
        else:
            data[key] = result_data(res)
    return data


def _err(value: Any) -> str | None:
    return value.get("error") if isinstance(value, dict) and "error" in value else None


def render_fallback(data: dict[str, Any], repo: str, keywords: list[str], days: int) -> str:
    out = [f"# Dev Radar - {_today()}", "", f"_Repo `{Path(repo).resolve().name}` · last {days}d · deterministic mode_", ""]
    commits, hotspots, authors = data["commits"], data["hotspots"], data["authors"]
    stories, system, procs = data["stories"], data["system"], data["processes"]

    tldr = []
    if not _err(commits):
        tldr.append(f"{len(commits)} commit(s) in the last {days} days" + (f" by {len(authors)} author(s)" if not _err(authors) else ""))
    if not _err(hotspots) and hotspots:
        tldr.append(f"Hottest file: `{hotspots[0]['path']}` ({hotspots[0]['commits']} commits)")
    if not _err(system):
        tldr.append("Machine warnings: " + ", ".join(system["warnings"]) if system["warnings"] else "Machine healthy (no metric over threshold)")
    out += ["## TL;DR", *(f"- {t}" for t in tldr or ["No data gathered"]), ""]

    out += ["## Repo activity"]
    if e := _err(commits):
        out.append(f"_git-insights failed: {e}_")
    elif not commits:
        out.append("No commits in the window.")
    else:
        out += [f"- `{c['sha']}` {c['subject']} — {c['author']}, {c['date'][:10]}" for c in commits]
    if not _err(authors) and authors:
        out += ["", "Active authors: " + ", ".join(f"{a['author']} ({a['commits']})" for a in authors)]
    out.append("")

    out += ["## Churn hotspots"]
    if e := _err(hotspots):
        out.append(f"_git-insights failed: {e}_")
    elif not hotspots:
        out.append("No file changes in the window.")
    else:
        out += ["| File | Commits | +lines | -lines |", "|---|---:|---:|---:|"]
        out += [f"| `{h['path']}` | {h['commits']} | {h['lines_added']} | {h['lines_deleted']} |" for h in hotspots]
    out.append("")

    out += [f"## Industry radar ({', '.join(keywords) or 'all topics'})"]
    if e := _err(stories):
        out.append(f"_hn-trends failed: {e}_")
    elif not stories:
        out.append("Nothing on the HN front page matches today.")
    else:
        out += [f"- [{s['title']}]({s['url'] or s['hn_url']}) — {s['score']} pts, [{s['comments']} comments]({s['hn_url']})" for s in stories]
    out.append("")

    out += ["## Machine health"]
    if e := _err(system):
        out.append(f"_system-health failed: {e}_")
    else:
        out += [
            f"- CPU {system['cpu_percent']:.0f}% across {system['cpu_count']} cores (load {system['load_avg_1m']})",
            f"- Memory {system['memory_percent']:.0f}% ({system['memory_used_gib']} / {system['memory_total_gib']} GiB)",
            f"- Disk `{system['disk_path']}` {system['disk_percent']:.0f}% used, {system['disk_free_gib']} GiB free",
        ]
        if not _err(procs) and procs:
            out.append("- Heaviest processes: " + ", ".join(f"{p['name']} ({p['memory_mib']:.0f} MiB)" for p in procs))
    out.append("")

    focus = []
    if not _err(hotspots) and hotspots:
        focus.append(f"Review test coverage for `{hotspots[0]['path']}` — it changes more than anything else.")
    if not _err(system) and system["warnings"]:
        focus.append("Investigate resource pressure: " + ", ".join(system["warnings"]) + ".")
    if not _err(stories) and stories:
        focus.append(f"Skim \"{stories[0]['title']}\" — top match for your keywords.")
    out += ["## Suggested focus today", *(f"- {f}" for f in focus or ["Nothing urgent. Ship something."])]
    return "\n".join(out) + "\n"


async def fallback_briefing(hub: McpHub, keywords: list[str], days: int) -> str:
    return render_fallback(await gather(hub, keywords, days), hub.repo, keywords, days)
