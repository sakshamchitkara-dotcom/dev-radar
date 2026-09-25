import json

from dev_radar.render import slack_payload, to_html, to_slack

MD = """# Dev Radar - 2026-09-25

_Repo `x` · last 7d_

## TL;DR
- 3 commit(s)
  - nested [link](https://e.com/?a=1&b=2)
- **bold** and `a<b` and [bad](javascript:alert(1))

| File | Commits |
|---|---:|
| `app.py` | 3 |
"""


def test_html_is_self_contained_and_escaped():
    h = to_html(MD, title="Dev Radar - 2026-09-25")
    assert h.startswith("<!doctype html>") and "<title>Dev Radar - 2026-09-25</title>" in h
    assert "<script" not in h and "http" not in h.split("<body>")[0]  # no external assets
    assert '<a href="https://e.com/?a=1&amp;b=2">link</a>' in h
    assert "javascript:" not in h.replace("[bad](javascript:alert(1))", "")  # left as text, never an href
    assert 'href="javascript' not in h
    assert "<code>a&lt;b</code>" in h and "<strong>bold</strong>" in h
    assert "<em>Repo <code>x</code> · last 7d</em>" in h
    assert '<td class="n">3</td>' in h
    assert h.count("<ul>") == h.count("</ul>") == 2


def test_slack_mrkdwn_and_payload():
    s = to_slack(MD)
    assert s.startswith("*Dev Radar - 2026-09-25*")
    assert "• 3 commit(s)\n    ◦ nested <https://e.com/?a=1&amp;b=2|link>" in s
    assert "• *bold* and `a&lt;b`" in s
    assert "• `app.py` — Commits 3" in s
    assert json.loads(slack_payload(MD))["text"] == s
