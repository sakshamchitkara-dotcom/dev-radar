"""hn-trends MCP server: Hacker News top stories via the public Firebase API."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError

from dev_radar.servers import serve

HN_API = os.environ.get("HN_API_BASE", "https://hacker-news.firebaseio.com/v0")

mcp = MCPServer("hn-trends")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request is noise

Keyword = Annotated[str, Field(min_length=1, max_length=50)]


class Story(BaseModel):
    id: int
    title: str
    url: str | None
    score: int
    comments: int
    by: str
    hn_url: str


async def _get_json(client: httpx.AsyncClient, path: str) -> Any:
    resp = await client.get(f"{HN_API}/{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _to_story(item: dict[str, Any]) -> Story:
    return Story(
        id=item["id"],
        title=item.get("title", ""),
        url=item.get("url"),
        score=item.get("score", 0),
        comments=item.get("descendants", 0),
        by=item.get("by", "?"),
        hn_url=f"https://news.ycombinator.com/item?id={item['id']}",
    )


@mcp.tool()
async def top_stories(
    keywords: Annotated[list[Keyword], Field(max_length=20, description="Case-insensitive title filter; empty = no filter")] = [],
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum stories to return")] = 10,
    scan: Annotated[int, Field(ge=1, le=200, description="How many front-page stories to scan")] = 60,
) -> list[Story]:
    """Top Hacker News stories, optionally filtered to titles containing any keyword."""
    # Word-boundary match so "ai" hits "AI agents" but not "Rails".
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, keywords)) + r")\b", re.I) if keywords else None
    try:
        # Connection cap keeps the fan-out polite to the public API.
        async with httpx.AsyncClient(limits=httpx.Limits(max_connections=16)) as client:
            ids = (await _get_json(client, "topstories.json"))[:scan]
            items = await asyncio.gather(*(_get_json(client, f"item/{i}.json") for i in ids))
    except httpx.HTTPError as e:
        raise ToolError(f"Hacker News API unavailable: {e}") from e
    stories = [
        _to_story(it) for it in items
        if it and it.get("type") == "story" and not it.get("dead") and not it.get("deleted")
    ]
    if pattern:
        stories = [s for s in stories if pattern.search(s.title)]
    return stories[:limit]


@mcp.resource("hn://item/{item_id}", mime_type="application/json")
async def item(item_id: str) -> str:
    """A single Hacker News item as JSON."""
    if not item_id.isdigit():
        raise ResourceNotFoundError(f"Invalid item id: {item_id!r}")
    try:
        async with httpx.AsyncClient() as client:
            data = await _get_json(client, f"item/{item_id}.json")
    except httpx.HTTPError as e:
        raise ResourceNotFoundError(f"Hacker News API unavailable: {e}") from e
    if data is None:
        raise ResourceNotFoundError(f"No such item: {item_id}")
    return _to_story(data).model_dump_json()


def main() -> None:
    serve(mcp)


if __name__ == "__main__":
    main()
