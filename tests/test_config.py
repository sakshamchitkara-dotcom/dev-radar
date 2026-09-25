import os
import re

import pytest

from dev_radar import config

MD = """# Dev Radar - 2026-09-25

## TL;DR
- x

## Today's meetings
- 09:30 standup

## Industry radar (ai, rust)
- story

## Machine health
- CPU 3%

## Suggested focus today
- ship
"""


def test_drop_sections_by_snake_case_heading():
    out = config.drop_sections(MD, {"industry_radar", "todays_meetings"})
    assert out == "# Dev Radar - 2026-09-25\n\n## TL;DR\n- x\n\n## Machine health\n- CPU 3%\n\n## Suggested focus today\n- ship\n"
    assert config.drop_sections(MD, set()) == MD


def test_load_turns_lists_into_cli_strings(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('keywords = ["ai", "rust"]\ncalendars = ["a.ics", "b"]\ndays = 3\n[sections]\nmachine_health = false\ngithub = true\n')
    defaults, disabled = config.load(f)
    assert defaults == {"keywords": "ai,rust", "calendars": f"a.ics{os.pathsep}b", "days": 3}
    assert disabled == {"machine_health"}


@pytest.mark.parametrize("text,message", [
    ("nope = 1", "unknown key 'nope'"),
    ("days = \"7\"", "days must be a int"),
    ("keywords = \"ai\"", "keywords must be a list of strings"),
    ("[sections]\nweather = false", "unknown section(s) ['weather']"),
    ("[sections]\ngithub = \"off\"", "maps section names to true/false"),
    ("days = ", "Invalid value"),
    ('format = "pdf"', "format must be one of ('md', 'html', 'slack')"),
])
def test_load_rejects_bad_config(tmp_path, text, message):
    f = tmp_path / "c.toml"
    f.write_text(text)
    with pytest.raises(ValueError, match=re.escape(message)):
        config.load(f)


def test_every_template_heading_has_a_section_key():
    from dev_radar.briefing import render_fallback
    from tests.test_briefing import DATA
    headings = [line for line in render_fallback(DATA, "/x/a", ["ai"], 7).splitlines() if line.startswith("## ")]
    assert {config.section_key(h) for h in headings} - {"tl_dr"} == set(config.SECTIONS)
