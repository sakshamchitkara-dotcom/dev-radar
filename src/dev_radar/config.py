"""Optional TOML config: CLI defaults plus per-section enable/disable.

    keywords = ["ai", "postgres"]
    github_repos = ["me/api", "me/web"]
    calendars = ["~/calendars/work.ics"]
    days = 7

    [sections]
    industry_radar = false   # also skips the Hacker News calls
    machine_health = false

Command-line flags win over the file. Section keys are the "## " headings in snake_case.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

# section key -> gather() keys whose tool calls it needs (none: the section is built from other data)
SECTIONS: dict[str, tuple[str, ...]] = {
    "todays_meetings": ("meetings",),
    "repo_activity": (),
    "churn_hotspots": (),
    "github": ("prs", "ci", "releases"),
    "dependencies": ("vulns", "outdated"),
    "industry_radar": ("stories",),
    "machine_health": ("system", "processes"),
    "suggested_focus_today": (),
}
LIST_KEYS = {"keywords", "github_repos", "calendars"}  # joined into the CLI's comma/pathsep strings
SCALAR_KEYS = {"days": int, "mode": str, "format": str, "keep": int, "repo": str}
CHOICES = {"mode": ("auto", "claude", "fallback"), "format": ("md", "html", "slack")}  # set_defaults skips argparse's check


def default_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "dev-radar" / "config.toml"


def load(path: Path) -> tuple[dict[str, Any], set[str]]:
    """(argparse defaults, disabled section keys). Raises ValueError with a readable message."""
    try:
        raw = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ValueError(f"{path}: {e}") from e
    defaults: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "sections":
            continue
        if key in LIST_KEYS:
            if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
                raise ValueError(f"{path}: {key} must be a list of strings")
            defaults[key] = (os.pathsep if key == "calendars" else ",").join(value)
        elif key in SCALAR_KEYS:
            if not isinstance(value, SCALAR_KEYS[key]) or isinstance(value, bool):
                raise ValueError(f"{path}: {key} must be a {SCALAR_KEYS[key].__name__}")
            if key in CHOICES and value not in CHOICES[key]:
                raise ValueError(f"{path}: {key} must be one of {CHOICES[key]}")
            defaults[key] = value
        else:
            raise ValueError(f"{path}: unknown key {key!r}; use {sorted(LIST_KEYS | set(SCALAR_KEYS) | {'sections'})}")
    sections = raw.get("sections", {})
    if not isinstance(sections, dict) or not all(isinstance(v, bool) for v in sections.values()):
        raise ValueError(f"{path}: [sections] maps section names to true/false")
    if unknown := set(sections) - set(SECTIONS):
        raise ValueError(f"{path}: unknown section(s) {sorted(unknown)}; use {sorted(SECTIONS)}")
    return defaults, {k for k, on in sections.items() if not on}


def section_key(heading: str) -> str:
    """'## Industry radar (ai, rust)' -> 'industry_radar'; "## Today's meetings" -> 'todays_meetings'."""
    title = re.sub(r"\(.*\)", "", heading.lstrip("#")).replace("'", "")
    return "_".join(re.findall(r"[a-z0-9]+", title.lower()))


def drop_sections(markdown: str, disabled: set[str]) -> str:
    """Remove every '## ' section whose key is disabled (works on Claude's output as well as the template's)."""
    if not disabled:
        return markdown
    kept: list[str] = []
    skipping = False
    for line in markdown.splitlines(keepends=True):
        if line.startswith("## "):
            skipping = section_key(line) in disabled
        elif line.startswith("# "):
            skipping = False
        if not skipping:
            kept.append(line)
    return "".join(kept)
