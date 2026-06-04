"""mcso_press — Mohave County Sheriff's Office press releases (HTML scrape).

source-expansion #5. ~2-3 releases/week covering river/desert incidents outside
city limits (often the gap golakehavasu/lhcaz miss). Source is an HTML listing:

    https://www.mohave.gov/departments/sheriff/press-release/

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: the page markup is parsed defensively (the
sandbox could not reach mohave.gov); confirm the selectors against live HTML
before wiring. Produces NewsItem records.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.news_item import NewsItem
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "mcso_press"
LISTING_URL = "https://www.mohave.gov/departments/sheriff/press-release/"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("mcso_press", qps=0.5)


def _parse_date(text: str | None) -> "object | None":
    if not text:
        return None
    try:
        return dateutil_parser.parse(text, fuzzy=True)
    except (ValueError, OverflowError):
        return None


def parse_press_releases(html: str, *, base_url: str = LISTING_URL) -> list[NewsItem]:
    """Parse the MCSO press-release listing into NewsItem records.

    Defensive: iterates ``<article>`` blocks (falling back to list items) and
    pulls the first link as title+url, a ``<time>``/date-ish element as the
    publish date, and the first paragraph as the lede.
    """
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("article") or soup.select("li.news-item, .news-item, .press-release-item")
    items: list[NewsItem] = []
    for block in blocks:
        link = block.find("a", href=True)
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link["href"].strip()
        if not title or not href:
            continue
        time_el = block.find("time")
        date_text = None
        if time_el is not None:
            date_text = time_el.get("datetime") or time_el.get_text(strip=True)
        published = _parse_date(date_text)
        para = block.find("p")
        summary = para.get_text(" ", strip=True) if para else None
        items.append(
            NewsItem(
                source=SOURCE,
                title=title,
                url=urljoin(base_url, href),
                published_at=published,  # type: ignore[arg-type]
                summary=summary or None,
            )
        )
    return items


def fetch_press_releases(*, client: httpx.Client | None = None) -> list[NewsItem]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(LISTING_URL, timeout=30.0))
        if resp is None:
            raise RuntimeError("mcso_press fetch failed")
        resp.raise_for_status()
        html = resp.text
    finally:
        if owns:
            c.close()
    return parse_press_releases(html)


def press_sample(item: NewsItem) -> dict:
    return {
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "summary": item.summary[:200] if item.summary else None,
    }
