"""research-trends MCP server: recent arXiv papers and posts from RSS/Atom feeds.

arXiv categories come from each call or $DEV_RADAR_ARXIV_CATEGORIES (comma-separated,
default cs.SE,cs.AI). Feeds are only the ones configured in $DEV_RADAR_FEEDS (comma-separated
URLs): the tool takes no URLs from the caller, so a model cannot point it at arbitrary hosts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import xml.etree.ElementTree as ET  # expat >= 2.4.1: no external entities, entity bombs refused
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Annotated

import httpx
from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from dev_radar.servers import serve

ARXIV_API = os.environ.get("ARXIV_API_BASE", "https://export.arxiv.org/api")
ATOM = "{http://www.w3.org/2005/Atom}"
DEFAULT_CATEGORIES = "cs.SE,cs.AI"

mcp = MCPServer("research-trends")
logging.getLogger("httpx").setLevel(logging.WARNING)

Keywords = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=50)]],
    Field(max_length=20, description="Case-insensitive whole-word filter on title and abstract; empty = no filter"),
]
Category = Annotated[str, Field(pattern=r"^[a-z-]+(\.[A-Za-z-]+)?$", description="arXiv category, e.g. cs.SE")]


class Paper(BaseModel):
    id: str
    title: str
    authors: list[str]
    published: str
    categories: list[str]
    url: str
    summary: str  # first 300 characters of the abstract


class Post(BaseModel):
    feed: str  # the feed's own title, else its URL
    title: str
    url: str | None
    published: str | None


class FeedReport(BaseModel):
    items: list[Post]
    feeds: list[str]
    errors: list[str]


def _matcher(keywords: list[str]) -> re.Pattern[str] | None:
    return re.compile(r"\b(" + "|".join(map(re.escape, keywords)) + r")\b", re.I) if keywords else None


def _text(el: ET.Element | None) -> str:
    return " ".join((el.text or "").split()) if el is not None else ""


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, str | int] | None = None) -> bytes:
    resp = await client.get(url, params=params, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def parse_arxiv(xml: bytes) -> list[Paper]:
    papers = []
    for e in ET.fromstring(xml).iter(f"{ATOM}entry"):
        url = _text(e.find(f"{ATOM}id"))
        papers.append(Paper(
            id=url.rsplit("/abs/", 1)[-1],
            title=_text(e.find(f"{ATOM}title")),
            authors=[_text(a.find(f"{ATOM}name")) for a in e.findall(f"{ATOM}author")],
            published=_text(e.find(f"{ATOM}published")),
            categories=[c.get("term", "") for c in e.findall(f"{ATOM}category")],
            url=url.replace("http://", "https://", 1),
            summary=_text(e.find(f"{ATOM}summary"))[:300],
        ))
    return papers


def _date(text: str) -> datetime | None:
    """RSS (RFC 822) or Atom (ISO 8601) timestamp, as aware UTC; None if missing or unparseable."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text) if text[:4].isdigit() else parsedate_to_datetime(text)
    except (ValueError, TypeError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def parse_feed(xml: bytes, url: str) -> list[Post]:
    """Items of an RSS 2.0 or Atom feed."""
    root = ET.fromstring(xml)
    if root.tag == f"{ATOM}feed":
        name = _text(root.find(f"{ATOM}title")) or url
        out = []
        for e in root.iter(f"{ATOM}entry"):
            links = e.findall(f"{ATOM}link")
            link = next((ln.get("href") for ln in links if ln.get("rel", "alternate") == "alternate"), None)
            when = _date(_text(e.find(f"{ATOM}published")) or _text(e.find(f"{ATOM}updated")))
            out.append(Post(feed=name, title=_text(e.find(f"{ATOM}title")), url=link,
                            published=when.isoformat() if when else None))
        return out
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise ValueError(f"not an RSS 2.0 or Atom feed (root <{root.tag}>)")
    name = _text(channel.find("title")) or url
    out = []
    for it in channel.iter("item"):
        when = _date(_text(it.find("pubDate")))
        out.append(Post(feed=name, title=_text(it.find("title")), url=_text(it.find("link")) or None,
                        published=when.isoformat() if when else None))
    return out


@mcp.tool()
async def arxiv_papers(
    categories: Annotated[list[Category] | None, Field(max_length=10, description="Defaults to $DEV_RADAR_ARXIV_CATEGORIES or cs.SE,cs.AI")] = None,
    keywords: Keywords = [],
    days: Annotated[int, Field(ge=1, le=30, description="Only papers submitted in the last N days")] = 3,
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum papers to return")] = 10,
    scan: Annotated[int, Field(ge=1, le=300, description="How many of the newest submissions to scan")] = 150,
) -> list[Paper]:
    """Newest arXiv submissions in the given categories, optionally filtered by keyword, newest first."""
    cats = categories or [c.strip() for c in os.environ.get("DEV_RADAR_ARXIV_CATEGORIES", DEFAULT_CATEGORIES).split(",") if c.strip()]
    params: dict[str, str | int] = {"search_query": " OR ".join(f"cat:{c}" for c in cats), "sortBy": "submittedDate",
                                    "sortOrder": "descending", "max_results": scan}
    try:
        async with httpx.AsyncClient() as client:
            papers = parse_arxiv(await _get(client, f"{ARXIV_API}/query", params))
    except (httpx.HTTPError, ET.ParseError) as e:
        raise ToolError(f"arXiv API unavailable: {e}") from e
    cutoff = datetime.now(UTC) - timedelta(days=days)
    pattern = _matcher(keywords)
    return [p for p in papers
            if (_date(p.published) or cutoff) >= cutoff and (not pattern or pattern.search(f"{p.title} {p.summary}"))][:limit]


@mcp.tool()
async def feed_items(
    keywords: Keywords = [],
    days: Annotated[int, Field(ge=1, le=90, description="Only items published in the last N days (undated items are kept)")] = 7,
    limit: Annotated[int, Field(ge=1, le=100, description="Maximum items to return")] = 15,
) -> FeedReport:
    """Recent posts from the RSS/Atom feeds in $DEV_RADAR_FEEDS, newest first; a broken feed is reported, not fatal."""
    feeds = [f.strip() for f in os.environ.get("DEV_RADAR_FEEDS", "").split(",") if f.strip()]
    if not feeds:
        raise ToolError("No feeds configured: set DEV_RADAR_FEEDS to comma-separated RSS/Atom URLs")
    async with httpx.AsyncClient(headers={"user-agent": "dev-radar (+https://github.com/sakshamchitkara-dotcom/dev-radar)"}) as client:
        bodies = await asyncio.gather(*(_get(client, f) for f in feeds), return_exceptions=True)
    items: list[Post] = []
    errors: list[str] = []
    for url, body in zip(feeds, bodies):
        try:
            if isinstance(body, BaseException):
                raise body
            items += parse_feed(body, url)
        except (httpx.HTTPError, ET.ParseError, ValueError) as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    cutoff = datetime.now(UTC) - timedelta(days=days)
    pattern = _matcher(keywords)
    items = [p for p in items
             if (not p.published or datetime.fromisoformat(p.published) >= cutoff) and (not pattern or pattern.search(p.title))]
    items.sort(key=lambda p: p.published or "", reverse=True)
    return FeedReport(items=items[:limit], feeds=feeds, errors=errors)


def main() -> None:
    serve(mcp)


if __name__ == "__main__":
    main()
