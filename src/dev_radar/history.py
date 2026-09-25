"""Briefing history: one JSON file per run, and a "what changed" diff against an earlier run.

Each record keeps the structured tool data behind the briefing, so the diff compares
facts (commit SHAs, CI states, PRs, vulnerability IDs...) rather than prose.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def default_dir(repo: str) -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "dev-radar" / "history"
    resolved = Path(repo).resolve()
    return root / f"{resolved.name}-{hashlib.sha1(str(resolved).encode()).hexdigest()[:8]}"


def save(directory: Path, data: dict[str, Any], markdown: str, now: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{now.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps({"created_at": now.isoformat(), "data": data, "markdown": markdown}, indent=1))
    return path


def load_all(directory: Path) -> list[dict[str, Any]]:
    """Every readable record, oldest first; corrupt files are skipped, not fatal."""
    records = []
    for p in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            rec = json.loads(p.read_text())
            datetime.fromisoformat(rec["created_at"])
            records.append(rec | {"path": str(p)})
        except (ValueError, KeyError, TypeError, OSError):
            continue
    return records


def baseline(records: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The latest run from before today (i.e. "yesterday" or older); else the latest earlier run today."""
    earlier = [r for r in records if datetime.fromisoformat(r["created_at"]) < now]
    before_today = [r for r in earlier if datetime.fromisoformat(r["created_at"]).date() < now.date()]
    return (before_today or earlier or [None])[-1]


def _ok(data: dict[str, Any], key: str) -> Any:
    value = data.get(key)
    return None if value is None or (isinstance(value, dict) and "error" in value) else value


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Human-readable changes between two gathered data sets; sources that errored on either side are skipped."""
    out: list[str] = []

    def both(key: str) -> tuple[Any, Any]:
        a, b = _ok(old, key), _ok(new, key)
        return (a, b) if a is not None and b is not None else (None, None)

    a, b = both("commits")
    if b is not None:
        fresh = [c for c in b if c["sha"] not in {c["sha"] for c in a}]
        if fresh:
            out.append(f"{len(fresh)} new commit(s): " + ", ".join(f"`{c['sha']}` {c['subject']}" for c in fresh[:5])
                       + (" …" if len(fresh) > 5 else ""))

    a, b = both("ci")
    if b is not None:
        before = {c["repo"]: c["state"] for c in a["items"]}
        out += [f"CI `{c['repo']}`: {before[c['repo']]} → **{c['state']}**"
                for c in b["items"] if c["repo"] in before and before[c["repo"]] != c["state"]]

    a, b = both("prs")
    if b is not None:
        key = lambda p: f"{p['repo']}#{p['number']}"  # noqa: E731
        was, now = {key(p) for p in a["items"]}, {key(p) for p in b["items"]}
        out += [f"New PR awaiting review: [{key(p)}]({p['url']}) {p['title']}" for p in b["items"] if key(p) not in was]
        if gone := sorted(was - now):
            out.append(f"No longer waiting for review: {', '.join(gone)}")

    a, b = both("releases")
    if b is not None:
        seen = {(r["repo"], r["tag"]) for r in a["items"]}
        out += [f"New release: [{r['repo']} {r['tag']}]({r['url']})" for r in b["items"] if (r["repo"], r["tag"]) not in seen]

    a, b = both("vulns")
    if b is not None:
        was = {v["id"]: v for v in a["vulnerabilities"]}
        now = {v["id"]: v for v in b["vulnerabilities"]}
        out += [f"New vulnerability: [{i}]({v['url']}) in `{v['package']}` {v['version']}" for i, v in now.items() if i not in was]
        if fixed := sorted(set(was) - set(now)):
            out.append(f"Resolved vulnerabilities: {', '.join(fixed)}")

    a, b = both("outdated")
    if b is not None:
        was = {o["name"] for o in a["outdated"]}
        now = {o["name"]: o for o in b["outdated"]}
        out += [f"Newly outdated: `{n}` {o['current']} → {o['latest']}" for n, o in now.items() if n not in was]
        if caught_up := sorted(was - set(now)):
            out.append(f"Now up to date: {', '.join(f'`{n}`' for n in caught_up)}")

    a, b = both("hotspots")
    if b and a and a[0]["path"] != b[0]["path"]:
        out.append(f"Hottest file moved: `{a[0]['path']}` → `{b[0]['path']}`")

    a, b = both("stories")
    if b is not None:
        fresh = [s for s in b if s["id"] not in {s["id"] for s in a}]
        if fresh:
            out.append(f"{len(fresh)} new matching HN stor(ies), e.g. [{fresh[0]['title']}]({fresh[0]['hn_url']})")

    a, b = both("system")
    if b is not None:
        for label, field in (("Memory", "memory_percent"), ("Disk", "disk_percent")):
            if abs(b[field] - a[field]) >= 5:
                out.append(f"{label} {a[field]:.0f}% → {b[field]:.0f}%")
    return out


def changes_section(prev: dict[str, Any] | None, data: dict[str, Any], now: datetime) -> str:
    if prev is None:
        return "## What changed\n- First recorded briefing for this repo; tomorrow's will show a diff.\n"
    when = datetime.fromisoformat(prev["created_at"])
    label = "yesterday" if (now.date() - when.date()).days == 1 else when.strftime("%Y-%m-%d %H:%M")
    lines = diff(prev["data"], data) or ["Nothing material changed."]
    return f"## What changed since {label}\n" + "".join(f"- {line}\n" for line in lines)


def insert_section(markdown: str, section: str) -> str:
    """Place `section` right after the TL;DR (or at the end when there is none)."""
    start = markdown.find("## TL;DR")
    nxt = markdown.find("\n## ", start + 1) if start != -1 else -1
    if nxt == -1:
        return markdown.rstrip("\n") + "\n\n" + section
    return markdown[:nxt + 1] + section + "\n" + markdown[nxt + 1:]
