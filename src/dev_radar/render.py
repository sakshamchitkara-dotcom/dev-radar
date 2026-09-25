"""Render a briefing's markdown as self-contained HTML or a Slack incoming-webhook payload.

Both converters handle the markdown subset briefings use: #/## headings, "- " bullets
(one nesting level), pipe tables, paragraphs, **bold**, _italic_, `code` and [links](url).
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable

LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(r"(?<![\w*])_(.+?)_(?!\w)")


def _html_link(m: re.Match[str]) -> str:
    # text and URL are already HTML-escaped; only web links become anchors (no javascript: from feeds)
    if not m[2].startswith(("http://", "https://")):
        return m[0]
    return f'<a href="{m[2].replace(chr(34), "&quot;")}">{m[1]}</a>'


def _inline(text: str, code: Callable[[str], str], rest: Callable[[str], str]) -> str:
    """Apply `rest` outside `code spans` and `code` inside them (spans are placeholders meanwhile)."""
    spans: list[str] = []

    def stash(m: re.Match[str]) -> str:
        spans.append(code(m[1]))
        return f"\x00{len(spans) - 1}\x00"

    out = rest(re.sub(r"`([^`]*)`", stash, text))
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m[1])], out)


def _inline_html(text: str) -> str:
    def rest(t: str) -> str:
        t = LINK.sub(_html_link, html.escape(t, quote=False))
        return ITALIC.sub(r"<em>\1</em>", BOLD.sub(r"<strong>\1</strong>", t))
    return _inline(text, lambda c: f"<code>{html.escape(c)}</code>", rest)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?", line.strip()))


CSS = """
:root{--bg:#fff;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--code:#f6f8fa;--link:#0969da}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--line:#3d444d;--code:#151b23;--link:#4493f8}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-size:1.6em;margin:.2em 0}h2{font-size:1.2em;border-bottom:1px solid var(--line);padding-bottom:.25em;margin-top:1.6em}
a{color:var(--link)}code{background:var(--code);padding:.1em .35em;border-radius:4px;font-size:.9em}
em{color:var(--muted)}ul{padding-left:1.4em}li{margin:.2em 0}
.table{overflow-x:auto}table{border-collapse:collapse}th,td{border:1px solid var(--line);padding:4px 10px;text-align:left}
td.n,th.n{text-align:right}
""".strip()


def to_html(md: str, title: str = "Dev Radar") -> str:
    lines = md.splitlines()
    body: list[str] = []
    depth = 0  # open <ul> levels
    i = 0

    def close_lists(to: int = 0) -> None:
        nonlocal depth
        while depth > to:
            body.append("</li></ul>")
            depth -= 1

    while i < len(lines):
        line = lines[i]
        if m := re.match(r"^(\s*)- (.*)", line):
            level = 2 if len(m[1]) >= 2 else 1
            if level > depth:
                while depth < level:  # open (and nest) lists up to this level
                    body.append("<ul><li>")
                    depth += 1
            else:
                close_lists(level)
                body.append("</li><li>")
            body.append(_inline_html(m[2]))
        elif line.startswith("|") and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            close_lists()
            head = _cells(line)
            numeric = [c.strip().endswith(":") for c in _cells(lines[i + 1])]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            cls = lambda j: ' class="n"' if j < len(numeric) and numeric[j] else ""  # noqa: E731
            body.append('<div class="table"><table><thead><tr>'
                        + "".join(f"<th{cls(j)}>{_inline_html(c)}</th>" for j, c in enumerate(head)) + "</tr></thead><tbody>"
                        + "".join("<tr>" + "".join(f"<td{cls(j)}>{_inline_html(c)}</td>" for j, c in enumerate(r)) + "</tr>"
                                  for r in rows)
                        + "</tbody></table></div>")
            continue
        else:
            close_lists()
            if m := re.match(r"^(#{1,3}) (.*)", line):
                n = len(m[1])
                body.append(f"<h{n}>{_inline_html(m[2])}</h{n}>")
            elif line.strip():
                body.append(f"<p>{_inline_html(line)}</p>")
        i += 1
    close_lists()
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>\n<body>\n"
        + "\n".join(body) + "\n</body></html>\n"
    )


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline_slack(text: str) -> str:
    def rest(t: str) -> str:
        return BOLD.sub(r"*\1*", LINK.sub(lambda m: f"<{m[2]}|{m[1]}>", _slack_escape(t)))
    return _inline(text, lambda c: f"`{_slack_escape(c)}`", rest)


def to_slack(md: str) -> str:
    """Slack mrkdwn text: headings bold, bullets as •/◦, table rows flattened to bullets."""
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            head = _cells(line)
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = _cells(lines[i])
                rest = ", ".join(f"{h} {c}" for h, c in zip(head[1:], cells[1:]))
                out.append(f"• {_inline_slack(cells[0])} — {_inline_slack(rest)}")
                i += 1
            continue
        if m := re.match(r"^(#{1,3}) (.*)", line):
            if out and out[-1]:
                out.append("")
            plain = BOLD.sub(r"\1", m[2])  # the whole heading is bolded already
            out.append(f"*{_inline_slack(plain)}*")
        elif m := re.match(r"^(\s*)- (.*)", line):
            out.append(("    ◦ " if len(m[1]) >= 2 else "• ") + _inline_slack(m[2]))
        else:
            out.append(_inline_slack(line))
        i += 1
    return "\n".join(out).strip() + "\n"


def slack_payload(md: str) -> str:
    """JSON body for a Slack incoming webhook: `curl -d @briefing.json -H 'content-type: application/json' $URL`."""
    return json.dumps({"text": to_slack(md), "unfurl_links": False, "unfurl_media": False}, ensure_ascii=False, indent=2) + "\n"
