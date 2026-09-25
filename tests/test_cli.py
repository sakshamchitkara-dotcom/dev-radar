from datetime import datetime, timedelta, timezone

import pytest

from dev_radar.cli import parse_since

NOW = datetime(2026, 9, 25, 15, 30, tzinfo=timezone(timedelta(hours=-7)))


@pytest.mark.parametrize("text,expected", [
    ("36h", NOW - timedelta(hours=36)),
    ("3d", NOW - timedelta(days=3)),
    ("2w", NOW - timedelta(weeks=2)),
    ("yesterday", datetime(2026, 9, 24, tzinfo=NOW.tzinfo)),
    ("2026-09-20T08:00:00+00:00", datetime(2026, 9, 20, 8, tzinfo=timezone.utc)),
])
def test_parse_since(text, expected):
    assert parse_since(text, NOW) == expected


def test_parse_since_naive_date_gets_local_tz_and_garbage_raises():
    assert parse_since("2026-09-20").tzinfo is not None
    with pytest.raises(ValueError):
        parse_since("last tuesday")
