"""calendar MCP server: today's meetings from local iCalendar (.ics) files.

Calendars come from $DEV_RADAR_CALENDARS: .ics files or directories of them, separated
by os.pathsep (":" on macOS/Linux). Export a calendar from Google/Outlook/Apple Calendar,
or point it at a synced .ics file. Parsing is stdlib only: line unfolding, TZID/UTC/floating
and all-day times (IANA or Windows zone names), DURATION, CANCELLED events, EXDATE, RDATE, moved or cancelled instances (RECURRENCE-ID),
and HOURLY/DAILY/WEEKLY/MONTHLY/YEARLY recurrence (INTERVAL, COUNT, UNTIL, BYDAY incl. 2TU/-1FR,
BYMONTHDAY, BYMONTH, BYSETPOS, BYYEARDAY, BYWEEKNO).
"""

from __future__ import annotations

import calendar
import functools
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
# Windows time zone names (Outlook/Exchange exports) -> IANA, from CLDR windowZones.xml (territory "001").
# ponytail: the common zones only; add a row when an export uses another one.
WINDOWS_TZ = {
    "Dateline Standard Time": "Etc/GMT+12", "Hawaiian Standard Time": "Pacific/Honolulu",
    "Alaskan Standard Time": "America/Anchorage", "Pacific Standard Time": "America/Los_Angeles",
    "US Mountain Standard Time": "America/Phoenix", "Mountain Standard Time": "America/Denver",
    "Central Standard Time": "America/Chicago", "Central America Standard Time": "America/Guatemala",
    "Canada Central Standard Time": "America/Regina", "Central Standard Time (Mexico)": "America/Mexico_City",
    "Eastern Standard Time": "America/New_York", "US Eastern Standard Time": "America/Indianapolis",
    "Atlantic Standard Time": "America/Halifax", "Newfoundland Standard Time": "America/St_Johns",
    "E. South America Standard Time": "America/Sao_Paulo", "Argentina Standard Time": "America/Buenos_Aires",
    "SA Pacific Standard Time": "America/Bogota", "UTC": "Etc/UTC", "Coordinated Universal Time": "Etc/UTC",
    "GMT Standard Time": "Europe/London", "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin", "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest", "Central European Standard Time": "Europe/Warsaw",
    "E. Europe Standard Time": "Europe/Chisinau", "FLE Standard Time": "Europe/Kiev",
    "GTB Standard Time": "Europe/Bucharest", "Israel Standard Time": "Asia/Jerusalem",
    "South Africa Standard Time": "Africa/Johannesburg", "Egypt Standard Time": "Africa/Cairo",
    "Turkey Standard Time": "Europe/Istanbul", "Russian Standard Time": "Europe/Moscow",
    "Arabian Standard Time": "Asia/Dubai", "Arab Standard Time": "Asia/Riyadh", "Iran Standard Time": "Asia/Tehran",
    "Pakistan Standard Time": "Asia/Karachi", "India Standard Time": "Asia/Calcutta",
    "Nepal Standard Time": "Asia/Katmandu", "Bangladesh Standard Time": "Asia/Dhaka",
    "SE Asia Standard Time": "Asia/Bangkok", "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore", "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo", "Korea Standard Time": "Asia/Seoul",
    "AUS Eastern Standard Time": "Australia/Sydney", "E. Australia Standard Time": "Australia/Brisbane",
    "Cen. Australia Standard Time": "Australia/Adelaide", "W. Australia Standard Time": "Australia/Perth",
    "New Zealand Standard Time": "Pacific/Auckland",
}
MAX_PERIODS = 5000  # ponytail: COUNT series walk from DTSTART; open-ended ones jump to the window first


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
    """The machine's time zone with its DST rules ($TZ, else /etc/localtime), not just today's UTC offset."""
    return _local_zone(os.environ.get("TZ", "").lstrip(":"))


@functools.lru_cache(maxsize=8)
def _local_zone(tz_env: str) -> tzinfo:
    try:
        if tz_env:
            return ZoneInfo(tz_env)
        with open("/etc/localtime", "rb") as f:
            return ZoneInfo.from_file(f)
    except (OSError, ValueError, ZoneInfoNotFoundError):
        # ponytail: fixed offset (Windows, odd setups); times on the other side of a DST switch are off by an hour
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
    return dt.replace(tzinfo=_zone(params["TZID"]) if "TZID" in params else _local()), False


def _zone(tzid: str) -> tzinfo:
    """IANA or Windows ("Pacific Standard Time") zone name; unknown names fall back to local time."""
    tzid = tzid.strip('"')
    try:
        return ZoneInfo(WINDOWS_TZ.get(tzid, tzid))
    except (ZoneInfoNotFoundError, ValueError):
        return _local()


def _duration(value: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m:
        raise ValueError(f"bad DURATION {value!r}")
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    delta = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
    return -delta if m[1] == "-" else delta


def _month_days(year: int, month: int, parts: dict[str, str], start: datetime) -> list[int]:
    """Days of one month matched by BYMONTHDAY / BYDAY (e.g. 2TU, -1FR, MO) / BYSETPOS, else DTSTART's day."""
    last = calendar.monthrange(year, month)[1]
    if "BYMONTHDAY" in parts:
        days = [d if d > 0 else last + d + 1 for d in map(int, parts["BYMONTHDAY"].split(","))]
    elif "BYDAY" in parts:
        days = []
        for spec in parts["BYDAY"].split(","):
            wd = WEEKDAYS.index(spec[-2:])
            matching = [d for d in range(1, last + 1) if date(year, month, d).weekday() == wd]
            nth = int(spec[:-2] or 0)  # 0 = every such weekday; 2 = second; -1 = last
            if nth == 0:
                days += matching
            elif -len(matching) <= nth <= len(matching):
                days.append(matching[nth - 1 if nth > 0 else nth])
    else:
        days = [start.day]
    days = sorted({d for d in days if 1 <= d <= last})  # RFC 5545: invalid dates (Feb 30) are skipped
    if "BYSETPOS" in parts:
        pos = [int(i) for i in parts["BYSETPOS"].split(",")]
        days = sorted({days[i - 1 if i > 0 else i] for i in pos if i and -len(days) <= i <= len(days)})
    return days


def _year_days(year: int, parts: dict[str, str], start: datetime) -> list[date]:
    """Days of one year matched by BYYEARDAY (1, -1 = Dec 31) or BYWEEKNO (ISO weeks, WKST=MO) with BYDAY."""
    if "BYYEARDAY" in parts:
        n = 366 if calendar.isleap(year) else 365
        days = [date(year, 1, 1) + timedelta(days=(d if d > 0 else n + d + 1) - 1)
                for d in map(int, parts["BYYEARDAY"].split(",")) if 1 <= abs(d) <= n]
    else:
        weeks = date(year, 12, 28).isocalendar().week  # 52 or 53
        wds = [WEEKDAYS.index(s[-2:]) for s in parts.get("BYDAY", WEEKDAYS[start.weekday()]).split(",")]
        days = [date.fromisocalendar(year, w if w > 0 else weeks + w + 1, wd + 1)
                for w in map(int, parts["BYWEEKNO"].split(",")) if 1 <= abs(w) <= weeks for wd in wds]
    if "BYMONTH" in parts:
        days = [d for d in days if d.month in {int(m) for m in parts["BYMONTH"].split(",")}]
    return sorted(set(days))


def _occurrences(start: datetime, rule: str, exdates: set[datetime], lo: datetime, hi: datetime) -> list[datetime]:
    """Starts of an HOURLY/DAILY/WEEKLY/MONTHLY/YEARLY series that fall before `hi` (callers filter by overlap with `lo`)."""
    parts = dict(p.split("=", 1) for p in rule.upper().split(";") if "=" in p)
    freq = parts.get("FREQ")
    if freq not in ("HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return [start]
    interval = int(parts.get("INTERVAL", 1))
    count = int(parts["COUNT"]) if "COUNT" in parts else None
    until = _when(parts["UNTIL"], {})[0] if "UNTIL" in parts else None
    week0 = start - timedelta(days=start.weekday())
    weekdays = sorted(WEEKDAYS.index(d[-2:]) for d in parts.get("BYDAY", WEEKDAYS[start.weekday()]).split(","))
    months = [int(m) for m in parts["BYMONTH"].split(",")] if "BYMONTH" in parts else [start.month]

    def period(n: int) -> list[datetime]:
        if freq == "HOURLY":
            return [start + timedelta(hours=n * interval)]
        if freq == "DAILY":
            return [start + timedelta(days=n * interval)]
        if freq == "WEEKLY":
            return [week0 + timedelta(weeks=n * interval, days=d) for d in weekdays]
        if freq == "MONTHLY":
            y, m = divmod(start.month - 1 + n * interval, 12)
            ym = [(start.year + y, m + 1)]
        elif "BYYEARDAY" in parts or "BYWEEKNO" in parts:
            return [start.replace(year=d.year, month=d.month, day=d.day) for d in _year_days(start.year + n * interval, parts, start)]
        else:
            ym = [(start.year + n * interval, m) for m in sorted(months)]
        return [start.replace(year=y, month=m, day=d) for y, m in ym for d in _month_days(y, m, parts, start)]

    first = 0
    if count is None:  # skip whole periods before the window instead of walking from DTSTART
        span = {"HOURLY": 1 / 24, "DAILY": 1, "WEEKLY": 7, "MONTHLY": 31, "YEARLY": 366}[freq] * interval * 86400
        first = max(0, int((lo - start).total_seconds() // span) - 2)
    out, seen = [], 0
    for n in range(first, first + MAX_PERIODS):
        for c in period(n):
            if c < start:
                continue  # BYDAY days earlier in DTSTART's week/month
            if c >= hi or (until and c > until) or (count is not None and seen >= count):
                return out
            seen += 1
            if c not in exdates and c >= lo - timedelta(days=31):  # only keep ones that could overlap the window
                out.append(c)
    return out


def parse_ics(text: str, name: str, lo: datetime, hi: datetime) -> list[Event]:
    """Events from one calendar file overlapping [lo, hi)."""
    vevents: list[dict[str, Any]] = []
    props: dict[str, Any] | None = None
    nested = 0  # inside VALARM etc.: those properties are not the event's
    for line in _unfold(text):
        key, params, value = _prop(line)
        if key == "BEGIN" and value.upper() == "VEVENT":
            props, nested = {"EXDATE": set(), "RDATE": set()}, 0
        elif props is None:
            continue
        elif key == "BEGIN":
            nested += 1
        elif key == "END" and nested:
            nested -= 1
        elif key == "END" and value.upper() == "VEVENT":
            vevents.append(props)
            props = None
        elif nested:
            continue
        elif key in ("EXDATE", "RDATE"):  # RDATE;VALUE=PERIOD start/end: the start is what counts
            props[key] |= {_when(v.split("/")[0], params)[0] for v in value.split(",")}
        elif key not in props:
            props[key] = (value, params)
    # A RECURRENCE-ID event replaces (or, if cancelled, removes) one instance of the series with the same UID.
    moved: dict[str, set[datetime]] = {}
    for ev in vevents:
        if "RECURRENCE-ID" in ev and "UID" in ev:
            moved.setdefault(ev["UID"][0], set()).add(_when(*ev["RECURRENCE-ID"])[0])
    events: list[Event] = []
    for ev in vevents:
        if "RECURRENCE-ID" not in ev and ev.get("UID", ("",))[0] in moved:
            ev["EXDATE"] |= moved[ev["UID"][0]]
        events += _expand(ev, name, lo, hi)
    return events


def _expand(props: dict[str, Any], name: str, lo: datetime, hi: datetime) -> list[Event]:
    if "DTSTART" not in props or props.get("STATUS", ("",))[0].upper() == "CANCELLED":
        return []
    start, all_day = _when(*props["DTSTART"])
    if "DTEND" in props:
        length = _when(*props["DTEND"])[0] - start
    elif "DURATION" in props:
        length = _duration(props["DURATION"][0])
    else:
        length = timedelta(days=1) if all_day else timedelta(0)
    starts = [start]
    if "RECURRENCE-ID" not in props:
        if "RRULE" in props:
            starts = _occurrences(start, props["RRULE"][0], props["EXDATE"], lo, hi)
        starts = sorted(set(starts) | (props["RDATE"] - props["EXDATE"]))
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
