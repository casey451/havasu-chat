"""river_scene_news — RiverScene Magazine news articles via WordPress REST.

source-expansion #7. RiverScene's events are already ingested by
app.contrib.river_scene (sitemap + HTML). This sibling adds the magazine's
*news* articles (community news, school stories, business spotlights) via the
WordPress REST API — full text, free, no auth, the cleanest news path found:

    https://riverscenemagazine.com/wp-json/wp/v2/posts

Supports ``?after=`` (ISO date), ``?categories=``, and pagination
(``per_page``/``page``). Reuses the existing river_scene client (descriptive UA
+ proxy env fallback) so it shares the events scraper's egress handling without
disturbing it.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. Produces NewsItem records.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.contrib.news_item import NewsItem
from app.contrib.river_scene import REQUEST_TIMEOUT, build_river_scene_client

logger = logging.getLogger(__name__)

SOURCE = "river_scene_news"
POSTS_URL = "https://riverscenemagazine.com/wp-json/wp/v2/posts"


def _html_to_text(value: Any) -> str | None:
    if not value:
        return None
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return text or None


def _rendered(field: Any) -> Any:
    """WP REST fields are ``{"rendered": "..."}`` objects."""
    if isinstance(field, dict):
        return field.get("rendered")
    return field


def parse_posts(payload: Any) -> list[NewsItem]:
    """Map a WP REST posts array to NewsItem records."""
    if not isinstance(payload, list):
        return []
    items: list[NewsItem] = []
    for post in payload:
        if not isinstance(post, dict):
            continue
        title = _html_to_text(_rendered(post.get("title")))
        link = (post.get("link") or "").strip()
        if not title or not link:
            continue
        published: datetime | None = None
        raw_date = post.get("date_gmt") or post.get("date")
        if raw_date:
            try:
                published = dateutil_parser.parse(str(raw_date)).replace(tzinfo=None)
            except (ValueError, OverflowError):
                published = None
        summary = _html_to_text(_rendered(post.get("excerpt")))
        categories = [str(c) for c in (post.get("categories") or []) if c is not None]
        items.append(
            NewsItem(
                source=SOURCE,
                title=title,
                url=link,
                published_at=published,
                summary=summary,
                categories=categories,
                raw={"id": post.get("id")},
            )
        )
    return items


def fetch_posts(
    *,
    after: str | None = None,
    categories: str | None = None,
    per_page: int = 20,
    page: int = 1,
    client: httpx.Client | None = None,
) -> list[NewsItem]:
    """Fetch one page of news posts. ``after`` is an ISO8601 datetime string."""
    if client is None:
        with build_river_scene_client(timeout=REQUEST_TIMEOUT) as c:
            return fetch_posts(
                after=after, categories=categories, per_page=per_page, page=page, client=c
            )

    params: dict[str, str] = {"per_page": str(per_page), "page": str(page)}
    if after:
        params["after"] = after
    if categories:
        params["categories"] = categories
    resp = client.get(POSTS_URL, params=params)
    resp.raise_for_status()
    return parse_posts(resp.json())


def post_sample(item: NewsItem) -> dict:
    return {
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "categories": item.categories,
        "summary": item.summary[:200] if item.summary else None,
    }
