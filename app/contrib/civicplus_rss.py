"""CivicPlus RSS parsing helper (shared by lhc_newsflash + lhc_alerts).

The City of Lake Havasu City runs CivicPlus, which exposes module feeds at
``https://www.lhcaz.gov/RSSFeed.aspx?ModID=<id>&CID=...``. News Flash (ModID=1)
carries road closures and city/PD press releases; the Alert Center (ModID=63)
carries emergency alerts (usually empty — design for poll-until-nonempty).

Both feeds are plain RSS, so this helper fetches with a descriptive User-Agent +
polite rate limiting (rule 7) and normalises entries to :class:`NewsItem`. No
DB writes — the caller (a dry-run CLI) decides what to do with the records.
"""

from __future__ import annotations

import logging
from datetime import datetime
from time import struct_time
from typing import Any

import feedparser
import httpx

from app.contrib.news_item import NewsItem
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("civicplus_rss", qps=0.5)


def _struct_to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime(*value[:6])
    except (TypeError, ValueError):
        return None


def fetch_feed_text(url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> str:
    """GET an RSS feed as text with a descriptive UA + polite pacing."""
    owns = client is None
    c = client or httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(url, timeout=timeout))
        if resp is None:
            raise RuntimeError(f"civicplus rss fetch failed: {url}")
        resp.raise_for_status()
        return resp.text
    finally:
        if owns:
            c.close()


def parse_feed(text: str, *, source: str) -> list[NewsItem]:
    """Parse RSS text into NewsItem records (newest first as served)."""
    feed = feedparser.parse(text)
    items: list[NewsItem] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = _struct_to_datetime(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        summary = (entry.get("summary") or entry.get("description") or "").strip() or None
        tags = [t.get("term") for t in entry.get("tags", []) if isinstance(t, dict) and t.get("term")]
        items.append(
            NewsItem(
                source=source,
                title=title,
                url=link,
                published_at=published,
                summary=summary,
                categories=tags,
                raw={"id": entry.get("id")},
            )
        )
    return items


def fetch_civicplus_items(
    url: str,
    *,
    source: str,
    client: httpx.Client | None = None,
) -> list[NewsItem]:
    """Fetch + parse one CivicPlus RSS feed into NewsItem records."""
    text = fetch_feed_text(url, client=client)
    return parse_feed(text, source=source)


def feed_sample(item: NewsItem) -> dict[str, Any]:
    """Compact sample projection for dry-run output."""
    return {
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "categories": item.categories,
        "summary": (item.summary[:200] + "…") if item.summary and len(item.summary) > 200 else item.summary,
    }
