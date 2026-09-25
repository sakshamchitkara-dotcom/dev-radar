"""calendar MCP server: today's meetings from local iCalendar (.ics) files.

Calendars come from $DEV_RADAR_CALENDARS: .ics files or directories of them, separated
by os.pathsep (":" on macOS/Linux). Export a calendar from Google/Outlook/Apple Calendar,
or point it at a synced .ics file. Parsing is stdlib only: line unfolding, TZID/UTC/floating
and all-day times, DURATION, CANCELLED events, EXDATE, and DAILY/WEEKLY recurrence
(INTERVAL, COUNT, UNTIL, BYDAY).
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dev_radar.servers import serve

mcp = MCPServer("calendar")

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MAX_OCCURRENCES = 5000  # ponytail: linear walk from DTSTART per rule; a daily event since 2012 is ~5k steps


class Event(BaseModel):
    title: str
    start: str  # ISO-8601, local time
    end: str
    all_day: bool
    location: str | None
    calendar: str  # file name it came from


class Agenda(BaseModel):
    day: str
    days: int
    events: list[Event]
    calendars: list[str]
    errors: list[str]


def _local() -> tzinfo:
    return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _unescape(v: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m[1] in "nN" else m[1], v)


def _prop(line: str) -> tuple[str, dict[str, str], str]:
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    return name.upper(), dict(p.split("=", 1) for p in params if "=" in p), value


def _when(value: str, params: dict[str, str]) -> tuple[datetime, bool]:
    """(aware datetime, all_day) for a DATE or DATE-TIME value."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.combine(datetime.strptime(value, "%Y%m%d").date(), time(), _local()), True
    utc = value.endswith("Z")
    dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if utc:
        return dt.replace(tzinfo=ZoneInfo("UTC")), False
    try:
        tz: tzinfo = ZoneInfo(params["TZID"].strip('"')) if "TZID" in params else _local()
    except (ZoneInfoNotFoundError, ValueError):
        tz = _local()  # Windows-style TZID names ("Pacific Standard Time"): best effort
    return dt.replace(tzinfo=tz), False


def _duration(value: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m:
        raise ValueError(f"bad DURATION {value!r}")
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    delta = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
    return -delta if m[1] == "-" else delta


def _occurrences(start: datetime, rule: str, exdates: set[datetime], lo: datetime, hi: datetime) -> list[datetime]:
    """Starts of a DAILY/WEEKLY series that fall before `hi` (callers filter by overlap with `lo`)."""
    parts = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        # ponytail: MONTHLY/YEARLY rules only show their first occurrence; add them when a real calendar needs it
        return [start]
    interval = int(parts.get("INTERVAL", 1))
    count = int(parts["COUNT"]) if "COUNT" in parts else None
    until = _when(parts["UNTIL"], {})[0] if "UNTIL" in parts else None
    if freq == "WEEKLY":
        days = sorted(WEEKDAYS.index(d[-2:]) for d in parts.get("BYDAY", WEEKDAYS[start.weekday()]).split(","))
        week0 = start - timedelta(days=start.weekday())
        candidates = (week0 + timedelta(weeks=n * interval, days=d) for n in range(MAX_OCCURRENCES) for d in days)
    else:
        candidates = (start + timedelta(days=n * interval) for n in range(MAX_OCCURRENCES))
    out, seen = [], 0
    for c in candidates:
        if c < start:
            continue  # BYDAY days earlier in DTSTART's week
        if c >= hi or (until and c > until) or (count is not None and seen >= count):
            break
        seen += 1
        if c not in exdates and c >= lo - timedelta(days=31):  # only keep ones that could overlap the window
            out.append(c)
    return out


def parse_ics(text: str, name: str, lo: datetime, hi: datetime) -> list[Event]:
    """Events from one calendar file overlapping [lo, hi)."""
    events: list[Event] = []
    props: dict[str, Any] | None = None
    for line in _unfold(text):
        key, params, value = _prop(line)
        if key == "BEGIN" and value.upper() == "VEVENT":
            props = {"EXDATE": set()}
        elif key == "END" and value.upper() == "VEVENT" and props is not None:
            events += _expand(props, name, lo, hi)
            props = None
        elif props is not None and key == "EXDATE":
            props["EXDATE"] |= {_when(v, params)[0] for v in value.split(",")}
        elif props is not None and key not in props:
            props[key] = (value, params)
    return events


def _expand(props: dict[str, Any], name: str, lo: datetime, hi: datetime) -> list[Event]:
    if "DTSTART" not in props or props.get("STATUS", ("",))[0].upper() == "CANCELLED" or "RECURRENCE-ID" in props:
        return []  # ponytail: moved single instances (RECURRENCE-ID) are dropped; the series keeps its usual slot
    start, all_day = _when(*props["DTSTART"])
    if "DTEND" in props:
        length = _when(*props["DTEND"])[0] - start
    elif "DURATION" in props:
        length = _duration(props["DURATION"][0])
    else:
        length = timedelta(days=1) if all_day else timedelta(0)
    starts = _occurrences(start, props["RRULE"][0], props["EXDATE"], lo, hi) if "RRULE" in props else [start]
    title = _unescape(props.get("SUMMARY", ("(no title)",))[0])
    location = _unescape(props["LOCATION"][0]) if props.get("LOCATION", ("",))[0] else None
    tz = _local()
    return [
        Event(title=title, start=s.astimezone(tz).isoformat(), end=(s + length).astimezone(tz).isoformat(),
              all_day=all_day, location=location, calendar=name)
        for s in starts
        if s < hi and (s + length > lo or (length == timedelta(0) and s >= lo))
    ]


def _calendar_files() -> list[Path]:
    files: list[Path] = []
    for entry in filter(None, os.environ.get("DEV_RADAR_CALENDARS", "").split(os.pathsep)):
        path = Path(entry).expanduser()
        files += sorted(path.glob("*.ics")) if path.is_dir() else [path]
    return files


@mcp.tool()
def events(
    day: Annotated[date | None, Field(description="First day (YYYY-MM-DD, local time); defaults to today")] = None,
    days: Annotated[int, Field(ge=1, le=14, description="How many days to cover")] = 1,
) -> Agenda:
    """Meetings and events from the local .ics calendars ($DEV_RADAR_CALENDARS), in start order."""
    files = _calendar_files()
    if not files:
        raise ToolError("No calendars configured: set DEV_RADAR_CALENDARS to .ics files or directories")
    first = day or date.today()
    lo = datetime.combine(first, time(), _local())
    hi = lo + timedelta(days=days)
    found: list[Event] = []
    errors: list[str] = []
    for f in files:
        try:
            found += parse_ics(f.read_text(encoding="utf-8", errors="replace"), f.name, lo, hi)
        except (OSError, ValueError, KeyError) as e:  # one bad file must not hide the others
            errors.append(f"{f}: {type(e).__name__}: {e}")
    found.sort(key=lambda e: (not e.all_day, e.start, e.title))
    return Agenda(day=first.isoformat(), days=days, events=found, calendars=[f.name for f in files], errors=errors)


@mcp.resource("calendar://today", mime_type="application/json")
def today() -> str:
    """Today's events from the configured calendars as JSON."""
    return events().model_dump_json()


def main() -> None:
    serve(mcp)


if __name__ == "__main__":
    main()
