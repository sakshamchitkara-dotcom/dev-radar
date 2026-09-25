import time as _time

import pytest
from mcp import Client

from dev_radar.servers.calendar_ics import _duration, mcp

ICS = r"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:standup
SUMMARY:Team standup
DTSTART;TZID=America/Los_Angeles:20260901T093000
DTEND;TZID=America/Los_Angeles:20260901T094500
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
EXDATE;TZID=America/Los_Angeles:20260924T093000
END:VEVENT
BEGIN:VEVENT
UID:review
SUMMARY:Design review: caching\, rollout
  plan
LOCATION:Room 4\; 2nd floor
DTSTART:20260925T210000Z
DURATION:PT1H30M
END:VEVENT
BEGIN:VEVENT
UID:offsite
SUMMARY:Offsite
DTSTART;VALUE=DATE:20260925
DTEND;VALUE=DATE:20260926
END:VEVENT
BEGIN:VEVENT
UID:cancelled
SUMMARY:Cancelled sync
STATUS:CANCELLED
DTSTART:20260925T170000Z
DTEND:20260925T180000Z
END:VEVENT
BEGIN:VEVENT
UID:onboarding
SUMMARY:Onboarding
DTSTART:20260922T160000Z
DTEND:20260922T170000Z
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
BEGIN:VEVENT
UID:tomorrow
SUMMARY:Tomorrow only
DTSTART:20260926T170000Z
DTEND:20260926T180000Z
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture(autouse=True)
def pacific(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    _time.tzset()
    yield
    monkeypatch.undo()
    _time.tzset()


async def call(**args):
    async with Client(mcp) as c:
        return await c.call_tool("events", args)


async def test_events_for_one_day(tmp_path, monkeypatch):
    (tmp_path / "work.ics").write_text(ICS)
    (tmp_path / "broken.ics").write_text("BEGIN:VEVENT\nDTSTART:not-a-date\nEND:VEVENT\n")
    monkeypatch.setenv("DEV_RADAR_CALENDARS", str(tmp_path))
    r = (await call(day="2026-09-25")).structured_content
    got = [(e["title"], e["start"][11:16], e["end"][11:16], e["all_day"]) for e in r["events"]]
    assert got == [
        ("Offsite", "00:00", "00:00", True),  # all-day first
        ("Team standup", "09:30", "09:45", False),  # weekly BYDAY series, TZID
        ("Design review: caching, rollout plan", "14:00", "15:30", False),  # UTC + DURATION, folded + escaped
    ]
    assert r["events"][2]["location"] == "Room 4; 2nd floor" and r["events"][2]["calendar"] == "work.ics"
    assert r["calendars"] == ["broken.ics", "work.ics"]
    assert len(r["errors"]) == 1 and r["errors"][0].startswith(str(tmp_path / "broken.ics"))


async def test_recurrence_exdate_count_and_weekends(tmp_path, monkeypatch):
    (tmp_path / "work.ics").write_text(ICS)
    monkeypatch.setenv("DEV_RADAR_CALENDARS", str(tmp_path / "work.ics"))
    r = (await call(day="2026-09-21", days=7)).structured_content
    standups = [e["start"][:10] for e in r["events"] if e["title"] == "Team standup"]
    assert standups == ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-25"]  # 24th excluded, no weekend
    onboarding = [e["start"][:10] for e in r["events"] if e["title"] == "Onboarding"]
    assert onboarding == ["2026-09-22", "2026-09-23", "2026-09-24"]  # COUNT=3
    assert "Tomorrow only" in {e["title"] for e in r["events"]}
    assert "Cancelled sync" not in {e["title"] for e in r["events"]}


async def test_unconfigured_and_validation(monkeypatch):
    monkeypatch.delenv("DEV_RADAR_CALENDARS", raising=False)
    r = await call()
    assert r.is_error and "DEV_RADAR_CALENDARS" in r.content[0].text
    assert (await call(days=99)).is_error


def test_duration():
    assert _duration("PT1H30M").total_seconds() == 5400
    assert _duration("P1W2D").days == 9 and _duration("-PT15M").total_seconds() == -900
    with pytest.raises(ValueError):
        _duration("1 hour")


def _starts(body: str, first: str, days: int) -> dict[str, list[str]]:
    from datetime import date, datetime, time, timedelta

    from dev_radar.servers.calendar_ics import _local, parse_ics
    lo = datetime.combine(date.fromisoformat(first), time(), _local())
    out: dict[str, list[str]] = {}
    for e in parse_ics(f"BEGIN:VCALENDAR\n{body}END:VCALENDAR\n", "t.ics", lo, lo + timedelta(days=days)):
        out.setdefault(e.title, []).append(e.start[:16])
    return out


def _ev(uid: str, title: str, start: str, rule: str = "", extra: str = "") -> str:
    return (f"BEGIN:VEVENT\nUID:{uid}\nSUMMARY:{title}\nDTSTART;TZID=America/Los_Angeles:{start}\nDURATION:PT1H\n"
            + (f"RRULE:{rule}\n" if rule else "") + extra + "END:VEVENT\n")


def test_monthly_and_yearly_rules():
    got = _starts(
        _ev("a", "2nd Tue", "20260113T100000", "FREQ=MONTHLY;BYDAY=2TU")
        + _ev("b", "Month end", "20260131T160000", "FREQ=MONTHLY;BYMONTHDAY=-1")
        + _ev("c", "31st", "20260131T090000", "FREQ=MONTHLY")  # skips 30-day months (RFC 5545)
        + _ev("d", "Last weekday", "20260130T170000", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1")
        + _ev("e", "Planning", "20250310T090000", "FREQ=YEARLY;BYMONTH=3,9;BYMONTHDAY=10")
        + _ev("f", "Quarterly", "20260105T110000", "FREQ=MONTHLY;INTERVAL=3;BYDAY=1MO;COUNT=4"),
        "2026-08-01", 92)
    assert got["2nd Tue"] == ["2026-08-11T10:00", "2026-09-08T10:00", "2026-10-13T10:00"]
    assert got["Month end"] == ["2026-08-31T16:00", "2026-09-30T16:00", "2026-10-31T16:00"]
    assert got["31st"] == ["2026-08-31T09:00", "2026-10-31T09:00"]
    assert got["Last weekday"] == ["2026-08-31T17:00", "2026-09-30T17:00", "2026-10-30T17:00"]
    assert got["Planning"] == ["2026-09-10T09:00"]
    assert got["Quarterly"] == ["2026-10-05T11:00"]  # Jan 5, Apr 6, Jul 6, Oct 5 = COUNT 4
    assert "Quarterly" not in _starts(_ev("f", "Quarterly", "20260105T110000", "FREQ=MONTHLY;INTERVAL=3;BYDAY=1MO;COUNT=3"),
                                      "2026-08-01", 92)


def test_old_open_ended_series_still_reaches_today():
    got = _starts(_ev("x", "Daily since 2001", "20010102T090000", "FREQ=DAILY"), "2026-09-25", 1)
    assert got == {"Daily since 2001": ["2026-09-25T09:00"]}  # ~9,400 days: past the old 5,000-step walk


def test_recurrence_id_moves_or_cancels_one_instance_and_valarm_is_ignored():
    series = _ev("s", "Standup", "20260901T093000", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
                 "BEGIN:VALARM\nACTION:DISPLAY\nSUMMARY:Reminder\nLOCATION:nowhere\nTRIGGER:-PT10M\nEND:VALARM\n")
    moved = ("BEGIN:VEVENT\nUID:s\nSUMMARY:Standup (moved)\nRECURRENCE-ID;TZID=America/Los_Angeles:20260922T093000\n"
             "DTSTART;TZID=America/Los_Angeles:20260922T140000\nDURATION:PT15M\nEND:VEVENT\n")
    cancelled = ("BEGIN:VEVENT\nUID:s\nSUMMARY:Standup\nSTATUS:CANCELLED\n"
                 "RECURRENCE-ID;TZID=America/Los_Angeles:20260923T093000\nDTSTART;TZID=America/Los_Angeles:20260923T093000\nEND:VEVENT\n")
    got = _starts(series + moved + cancelled, "2026-09-21", 5)
    assert got == {"Standup": ["2026-09-21T09:30", "2026-09-24T09:30", "2026-09-25T09:30"],
                   "Standup (moved)": ["2026-09-22T14:00"]}


def test_windows_tzid_names_map_to_iana():
    from dev_radar.servers.calendar_ics import _when
    pst = _when("20260925T093000", {"TZID": '"Pacific Standard Time"'})[0]
    ist = _when("20260925T093000", {"TZID": "India Standard Time"})[0]
    assert pst.utcoffset().total_seconds() == -7 * 3600  # PDT in September
    assert ist.utcoffset().total_seconds() == 5.5 * 3600
    assert _when("20260925T093000", {"TZID": "Nowhere/Made_Up"})[0].tzinfo is not None  # local fallback
