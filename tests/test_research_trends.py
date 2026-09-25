from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mcp import Client

from dev_radar.servers import research_trends
from dev_radar.servers.research_trends import mcp

NOW = datetime.now(UTC)
iso = lambda d: (NOW - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
rfc822 = lambda d: (NOW - timedelta(days=d)).strftime("%a, %d %b %Y %H:%M:%S +0000")  # noqa: E731

ARXIV = f"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/2609.00001v1</id><title>Agents that
    fix flaky tests</title><published>{iso(1)}</published><summary>We use an LLM to repair CI.</summary>
    <category term="cs.SE"/><category term="cs.AI"/><author><name>Ada</name></author><author><name>Grace</name></author></entry>
  <entry><id>http://arxiv.org/abs/2609.00002v1</id><title>Type inference for Rust macros</title>
    <published>{iso(2)}</published><summary>Static analysis.</summary><category term="cs.PL"/><author><name>Linus</name></author></entry>
  <entry><id>http://arxiv.org/abs/2608.00003v2</id><title>An old LLM paper</title>
    <published>{iso(20)}</published><summary>Too old.</summary><author><name>X</name></author></entry>
</feed>""".encode()

RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Eng blog</title>
  <item><title>Postgres 19 is out</title><link>https://blog.example/pg19</link><pubDate>{rfc822(1)}</pubDate></item>
  <item><title>Ancient history</title><link>https://blog.example/old</link><pubDate>{rfc822(60)}</pubDate></item>
  <item><title>Undated AI notes</title></item>
</channel></rss>""".encode()

ATOM = f"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Release notes</title>
  <entry><title>Rust 1.99</title><link rel="alternate" href="https://rel.example/rust"/><updated>{iso(0)}</updated></entry>
</feed>""".encode()

BODIES = {"https://export.arxiv.org/api/query": ARXIV, "https://blog.example/feed": RSS,
          "https://rel.example/atom": ATOM, "https://html.example/": b"<html><body>hi</body></html>"}


@pytest.fixture
def fake_http(monkeypatch):
    seen = []

    async def fake_get(client, url, params=None):
        seen.append((url, params))
        if url not in BODIES:
            raise httpx.ConnectError("down")
        return BODIES[url]
    monkeypatch.setattr(research_trends, "_get", fake_get)
    return seen


async def call(tool, **args):
    async with Client(mcp) as c:
        return await c.call_tool(tool, args)


async def test_arxiv_papers_window_keywords_and_query(fake_http, monkeypatch):
    monkeypatch.delenv("DEV_RADAR_ARXIV_CATEGORIES", raising=False)
    papers = (await call("arxiv_papers")).structured_content["result"]
    assert [p["id"] for p in papers] == ["2609.00001v1", "2609.00002v1"]  # 20-day-old one is outside days=3
    assert papers[0]["title"] == "Agents that fix flaky tests" and papers[0]["authors"] == ["Ada", "Grace"]
    assert papers[0]["url"] == "https://arxiv.org/abs/2609.00001v1"
    assert fake_http[0][1]["search_query"] == "cat:cs.SE OR cat:cs.AI"
    llm = (await call("arxiv_papers", keywords=["llm"], categories=["cs.SE"], days=30)).structured_content["result"]
    assert [p["id"] for p in llm] == ["2609.00001v1", "2608.00003v2"]  # abstract match counts too
    assert fake_http[-1][1]["search_query"] == "cat:cs.SE"
    assert (await call("arxiv_papers", categories=["cs.SE; drop"])).is_error


async def test_arxiv_down_is_tool_error(monkeypatch):
    async def boom(client, url, params=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(research_trends, "_get", boom)
    r = await call("arxiv_papers")
    assert r.is_error and "arXiv API unavailable" in r.content[0].text


async def test_feed_items_merges_rss_and_atom_and_reports_bad_feeds(fake_http, monkeypatch):
    monkeypatch.setenv("DEV_RADAR_FEEDS", "https://blog.example/feed, https://rel.example/atom,https://html.example/,https://gone.example/")
    r = (await call("feed_items")).structured_content
    assert [(i["feed"], i["title"]) for i in r["items"]] == [
        ("Release notes", "Rust 1.99"), ("Eng blog", "Postgres 19 is out"), ("Eng blog", "Undated AI notes")]
    assert r["items"][0]["url"] == "https://rel.example/rust"
    assert [e.split(":")[0] + ":" + e.split(":")[1] for e in r["errors"]] == ["https://html.example/", "https://gone.example/"]
    kw = (await call("feed_items", keywords=["ai", "POSTGRES"])).structured_content["items"]
    assert [i["title"] for i in kw] == ["Postgres 19 is out", "Undated AI notes"]


async def test_feed_items_needs_configuration(monkeypatch):
    monkeypatch.delenv("DEV_RADAR_FEEDS", raising=False)
    r = await call("feed_items")
    assert r.is_error and "DEV_RADAR_FEEDS" in r.content[0].text


def test_entity_bomb_is_refused():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa">'
            + b"".join(f'<!ENTITY {n} "{("&" + p + ";") * 10}">'.encode() for p, n in zip("abcdefg", "bcdefgh"))
            + b"]><rss>&h;</rss>")
    with pytest.raises(Exception):
        research_trends.parse_feed(bomb, "x")
