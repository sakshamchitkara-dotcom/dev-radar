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


def test_claude_credentials_from_env_profile_or_nothing(tmp_path, monkeypatch):
    from dev_radar.cli import claude_credentials_problem
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_CONFIG_DIR",
                "ANTHROPIC_FEDERATION_RULE_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # no ~/.config/anthropic profile
    assert "no ANTHROPIC_API_KEY" in claude_credentials_problem()
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_PROFILE", "dev")  # explicitly selected but missing: say why
    assert "Config file not found" in claude_credentials_problem()
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "dev.json").write_text('{"authentication": {"type": "user_oauth"}}')
    assert claude_credentials_problem() is None
    monkeypatch.delenv("ANTHROPIC_PROFILE")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert claude_credentials_problem() is None
