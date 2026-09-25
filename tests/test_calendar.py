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
