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

import anthropic

from dev_radar.hub import McpHub, result_data, result_text

MODEL = "claude-opus-5-5"
MAX_TURNS = 10

SYSTEM_PROMPT = """You are Dev Radar, writing a concise daily engineering briefing for the team that owns one git repository.

You have tools from five MCP servers: git (repo history), github (PRs awaiting review, CI status, releases for the configured repos), deps (outdated packages and OSV.dev vulnerabilities in the repo's lockfiles), hn (Hacker News front page) and system (this machine's health). Gather what you need, then write the briefing in GitHub-flavored markdown with these sections:

# Dev Radar - <date>
## TL;DR  (3 bullets max)
## Repo activity  (commits, who is active, notable subjects)
## Churn hotspots  (files changing most; say why that may matter)
## GitHub  (CI state per repo, PRs waiting for review oldest first, new releases)
## Dependencies  (known vulnerabilities with fixed versions first, then notable outdated packages)
## Industry radar  (HN stories relevant to the team's keywords, with links)
## Machine health  (only call out what is notable)
## Suggested focus today  (2-4 concrete actions tied to the data above)

Every number and link must come from a tool result. If a tool fails, say so in the relevant section instead of guessing. Output only the briefing."""


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- fallback


async def gather(hub: McpHub, keywords: list[str], days: int) -> dict[str, Any]:
    """Call the fixed tool set concurrently; failed calls come back as {"error": text}."""
    calls = {
        "commits": ("git__recent_commits", {"days": days, "limit": 15}),
        "hotspots": ("git__churn_hotspots", {"days": max(days, 30), "limit": 5}),
        "authors": ("git__top_authors", {"days": days, "limit": 200}),  # full list: TL;DR sums it
        "stories": ("hn__top_stories", {"keywords": keywords, "limit": 6, "scan": 100}),
        "system": ("system__snapshot", {}),
        "processes": ("system__top_processes", {"sort_by": "memory", "limit": 3}),
        "prs": ("github__prs_awaiting_review", {}),
        "ci": ("github__ci_status", {}),
        "releases": ("github__recent_releases", {"days": days}),
        "vulns": ("deps__vulnerabilities", {}),
        "outdated": ("deps__outdated", {"limit": 50}),
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
    prs, ci, releases = data["prs"], data["ci"], data["releases"]
    vulns, outdated = data["vulns"], data["outdated"]

    tldr = []
    if not _err(authors):
        # commits is capped for display, so count from the uncapped author totals
        tldr.append(f"{sum(a['commits'] for a in authors)} commit(s) in the last {days} days by {len(authors)} author(s)")
    if not _err(hotspots) and hotspots:
        tldr.append(f"Hottest file: `{hotspots[0]['path']}` ({hotspots[0]['commits']} commits)")
    if not _err(ci) and (red := [c["repo"] for c in ci["items"] if c["state"] == "failure"]):
        tldr.append(f"CI failing on {', '.join(red)}")
    elif not _err(ci) and ci["items"]:
        tldr.append(f"CI green or pending on all {len(ci['items'])} watched repo(s)")
    if not _err(vulns) and vulns["vulnerabilities"]:
        pkgs = {v["package"] for v in vulns["vulnerabilities"]}
        tldr.append(f"{len(vulns['vulnerabilities'])} known vulnerabilit(ies) in {len(pkgs)} package(s)")
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
        if not _err(authors) and (total := sum(a["commits"] for a in authors)) > len(commits):
            out.append(f"- …and {total - len(commits)} more")
    if not _err(authors) and authors:
        out += ["", "Active authors: " + ", ".join(f"{a['author']} ({a['commits']})" for a in authors[:5])]
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

    out += ["## GitHub"]
    if (e := _err(ci) or _err(prs)) and "No repos given" in e:
        out.append("_No repos configured: pass --github-repos owner/name,... or set DEV_RADAR_GITHUB_REPOS._")
    elif e:
        out.append(f"_github-activity failed: {e}_")
    else:
        out += [f"- CI `{c['repo']}` {c['branch']}"
                + (f"@{c['sha']}: **{c['state']}**" if c["sha"] else ": no workflow runs")
                + "".join(f" · [{r['workflow']}]({r['url']}) {r['conclusion'] or r['status']}" for r in c["runs"] if c["state"] == "failure")
                for c in ci["items"]]
        if prs["items"]:
            out += [f"- PR [{p['repo']}#{p['number']}]({p['url']}) {p['title']} — {p['author']}, {p['age_days']:.0f}d old"
                    + (f", waiting on {', '.join(p['requested_reviewers'])}" if p["requested_reviewers"] else ", no reviews yet")
                    for p in prs["items"][:10]]
        else:
            out.append(f"- No PRs awaiting review across {len(ci['items'])} repo(s)")
        if not _err(releases):
            out += [f"- Released [{r['repo']} {r['tag']}]({r['url']}) {r['published_at'][:10]}" for r in releases["items"][:5]]
            if not releases["items"]:
                out.append(f"- No releases in the last {days} days")
        out += [f"- _{x['repo']}: {x['error']}_" for x in ci["errors"]]
    out.append("")

    out += ["## Dependencies"]
    if e := _err(vulns):
        out.append(f"_deps-watch failed: {e}_")
    elif not vulns["checked"]:
        out.append("No lockfile found (uv.lock, poetry.lock, requirements*.txt, package-lock.json).")
    else:
        vs = vulns["vulnerabilities"]
        out.append(f"- {len(vs)} known vulnerabilit(ies) across {vulns['checked']} pinned package(s) (OSV.dev)")
        out += [f"  - [{v['id']}]({v['url']}) `{v['package']}` {v['version']} ({v['severity'] or 'unrated'}): {v['summary']}"
                + (f" — fixed in {', '.join(v['fixed_in'])}" if v["fixed_in"] else "") for v in vs[:10]]
    if e := _err(outdated):
        out.append(f"_deps-watch outdated check failed: {e}_")
    elif outdated["checked"]:
        rows = outdated["outdated"]
        out.append(f"- {len(rows)} of {outdated['checked']} direct dependencies behind latest"
                   + (": " + ", ".join(f"`{o['name']}` {o['current']} → {o['latest']}" for o in rows[:10]) if rows else ""))
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
    if not _err(ci) and (red := [c["repo"] for c in ci["items"] if c["state"] == "failure"]):
        focus.append(f"Fix the red default branch on {', '.join(red)} before merging anything else.")
    if not _err(vulns) and vulns["vulnerabilities"]:
        v = vulns["vulnerabilities"][0]
        focus.append(f"Upgrade `{v['package']}` past {v['version']} ({v['id']}).")
    if not _err(prs) and prs["items"]:
        p = prs["items"][0]
        focus.append(f"Review {p['repo']}#{p['number']} — oldest PR waiting ({p['age_days']:.0f}d).")
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


# ---------------------------------------------------------------- claude


async def _run_tool(hub: McpHub, block: Any) -> dict[str, Any]:
    try:
        res = await hub.call(block.name, block.input)
        content, is_error = result_text(res), bool(res.is_error)
    except Exception as e:  # unknown tool, transport failure: report to Claude, don't crash the loop
        content, is_error = f"{type(e).__name__}: {e}", True
    return {"type": "tool_result", "tool_use_id": block.id, "content": content or "(empty)", "is_error": is_error}


async def claude_briefing(
    hub: McpHub,
    keywords: list[str],
    days: int,
    client: anthropic.AsyncAnthropic | None = None,
    log: Any = None,
) -> str:
    """Agentic loop: Claude calls MCP tools until it writes the briefing."""
    client = client or anthropic.AsyncAnthropic()
    tools = hub.anthropic_tools()
    messages: list[dict[str, Any]] = [{
        "role": "user",
        "content": (
            f"Today is {_today()}. Write today's briefing for the repo at {Path(hub.repo).resolve()} "
            f"covering the last {days} days. Team interest keywords for Hacker News: {json.dumps(keywords)}."
        ),
    }]
    for _ in range(MAX_TURNS):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "medium"},
            tools=tools,
            messages=messages,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined the request: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Claude hit max_tokens before finishing the briefing")
        # Append the full content (thinking blocks included) so the next turn sees it unchanged.
        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            return "".join(b.text for b in response.content if b.type == "text").strip() + "\n"
        if log:
            for b in tool_uses:
                log(f"-> {b.name}({json.dumps(b.input)})")
        # Run parallel calls concurrently and return every result in one user message.
        results = await asyncio.gather(*(_run_tool(hub, b) for b in tool_uses))
        messages.append({"role": "user", "content": list(results)})
    raise RuntimeError(f"Claude did not finish within {MAX_TURNS} turns")
