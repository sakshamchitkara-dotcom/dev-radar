from datetime import datetime, timedelta, timezone

from dev_radar import history

TZ = timezone.utc
NOW = datetime(2026, 9, 25, 9, 0, tzinfo=TZ)

OLD = {
    "commits": [{"sha": "a1", "subject": "old"}],
    "ci": {"items": [{"repo": "o/r", "state": "success"}], "errors": []},
    "prs": {"items": [{"repo": "o/r", "number": 1, "url": "u1", "title": "one"}], "errors": []},
    "releases": {"items": [], "errors": []},
    "vulns": {"checked": 2, "vulnerabilities": [{"id": "GHSA-old", "package": "p", "version": "1", "url": "v"}]},
    "outdated": {"checked": 2, "outdated": [{"name": "p", "current": "1", "latest": "2"}], "errors": []},
    "hotspots": [{"path": "a.py"}],
    "stories": [{"id": 1, "title": "t1", "hn_url": "h1"}],
    "system": {"memory_percent": 50.0, "disk_percent": 40.0},
}
NEW = {
    "commits": [{"sha": "b2", "subject": "fix: thing"}, {"sha": "a1", "subject": "old"}],
    "ci": {"items": [{"repo": "o/r", "state": "failure"}], "errors": []},
    "prs": {"items": [{"repo": "o/r", "number": 2, "url": "u2", "title": "two"}], "errors": []},
    "releases": {"items": [{"repo": "o/r", "tag": "v1", "url": "r"}], "errors": []},
    "vulns": {"checked": 2, "vulnerabilities": [{"id": "GHSA-new", "package": "q", "version": "3", "url": "v2"}]},
    "outdated": {"checked": 2, "outdated": [], "errors": []},
    "hotspots": [{"path": "b.py"}],
    "stories": {"error": "HN down"},
    "system": {"memory_percent": 58.0, "disk_percent": 41.0},
}


def test_diff_reports_each_kind_of_change_and_skips_errored_sources():
    assert history.diff(OLD, NEW) == [
        "1 new commit(s): `b2` fix: thing",
        "CI `o/r`: success → **failure**",
        "New PR awaiting review: [o/r#2](u2) two",
        "No longer waiting for review: o/r#1",
        "New release: [o/r v1](r)",
        "New vulnerability: [GHSA-new](v2) in `q` 3",
        "Resolved vulnerabilities: GHSA-old",
        "Now up to date: `p`",
        "Hottest file moved: `a.py` → `b.py`",
        "Memory 50% → 58%",
    ]
    assert history.diff(OLD, OLD) == []


def test_save_load_and_baseline_prefers_yesterday(tmp_path):
    history.save(tmp_path, OLD, "# old", NOW - timedelta(days=1, hours=2))
    history.save(tmp_path, OLD, "# earlier today", NOW - timedelta(hours=1))
    (tmp_path / "garbage.json").write_text("{not json")
    records = history.load_all(tmp_path)
    assert [r["markdown"] for r in records] == ["# old", "# earlier today"]
    assert history.baseline(records, NOW)["markdown"] == "# old"
    assert history.baseline(records[1:], NOW)["markdown"] == "# earlier today"
    assert history.baseline([], NOW) is None
    section = history.changes_section(records[0], NEW, NOW)
    assert section.startswith("## What changed since yesterday\n- 1 new commit(s)")


def test_insert_section_after_tldr():
    md = "# T\n\n## TL;DR\n- x\n\n## Repo activity\n- y\n"
    out = history.insert_section(md, "## What changed\n- z\n")
    assert out == "# T\n\n## TL;DR\n- x\n\n## What changed\n- z\n\n## Repo activity\n- y\n"
    assert history.insert_section("# T\nno sections\n", "## W\n").endswith("no sections\n\n## W\n")


def test_default_dir_is_per_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    a, b = history.default_dir("/x/app"), history.default_dir("/y/app")
    assert a.parent == tmp_path / "dev-radar" / "history" and a != b and a.name.startswith("app-")
