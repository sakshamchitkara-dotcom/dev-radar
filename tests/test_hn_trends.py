import httpx
import pytest
from mcp import Client

from dev_radar.servers import hn_trends
from dev_radar.servers.hn_trends import mcp

ITEMS = {
    1: {"id": 1, "type": "story", "title": "Show HN: An MCP server in Rust", "url": "https://a.example", "score": 300, "descendants": 40, "by": "x"},
    2: {"id": 2, "type": "story", "title": "Rails 9 released", "url": "https://b.example", "score": 200, "descendants": 10, "by": "y"},
    3: {"id": 3, "type": "job", "title": "We're hiring AI engineers", "by": "z"},
    4: {"id": 4, "type": "story", "title": "AI agents in production", "score": 100, "descendants": 5, "by": "w", "dead": True},
    5: {"id": 5, "type": "story", "title": "New AI chip", "score": 50, "by": "v"},
}


@pytest.fixture
def fake_hn(monkeypatch):
    async def fake_get_json(client, path):
        if path == "topstories.json":
            return list(ITEMS)
        return ITEMS.get(int(path.split("/")[1].split(".")[0]))
    monkeypatch.setattr(hn_trends, "_get_json", fake_get_json)


async def test_top_stories_unfiltered_skips_jobs_and_dead(fake_hn):
    async with Client(mcp) as c:
        r = await c.call_tool("top_stories", {})
    assert [s["id"] for s in r.structured_content["result"]] == [1, 2, 5]


async def test_keyword_filter_is_whole_word_case_insensitive(fake_hn):
    async with Client(mcp) as c:
        r = await c.call_tool("top_stories", {"keywords": ["ai", "RUST"]})
    stories = r.structured_content["result"]
    # "ai" must not match "Rails"; the dead story and the job are excluded
    assert [s["id"] for s in stories] == [1, 5]
    assert stories[0]["hn_url"] == "https://news.ycombinator.com/item?id=1"
    assert stories[1]["url"] is None and stories[1]["comments"] == 0


async def test_limit_and_validation(fake_hn):
    async with Client(mcp) as c:
        r = await c.call_tool("top_stories", {"limit": 1})
        bad = await c.call_tool("top_stories", {"limit": 0})
        empty_kw = await c.call_tool("top_stories", {"keywords": [""]})
    assert len(r.structured_content["result"]) == 1
    assert bad.is_error and empty_kw.is_error


async def test_api_failure_is_tool_error(monkeypatch):
    async def boom(client, path):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(hn_trends, "_get_json", boom)
    async with Client(mcp) as c:
        r = await c.call_tool("top_stories", {})
    assert r.is_error and "unavailable" in r.content[0].text


async def test_item_resource(fake_hn):
    async with Client(mcp) as c:
        r = await c.read_resource("hn://item/1")
        with pytest.raises(Exception):
            await c.read_resource("hn://item/abc")
    assert '"title":"Show HN: An MCP server in Rust"' in r.contents[0].text
