"""reddit_havasu — r/LakeHavasu community signal via public JSON.

source-expansion #21. Community voice: "best mechanic?", openings/closings
chatter. Public JSON endpoints, descriptive UA, <= 10 req/min:

    https://www.reddit.com/r/LakeHavasu/new.json
    https://www.reddit.com/r/LakeHavasu/search.json?q=<business>&restrict_sr=1

ToS gray zone: we store ONLY the permalink + a short snippet and attribute/link
out at display time — never the full body, never used for training. Business
mentions are piped toward the existing mention_scanner flow.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: reddit.com is often blocked from datacenter
IPs — re-verify from prod (or via the proxy env pattern).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.contrib.mention_scanner import scan_tier3_response
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "reddit_havasu"
SUBREDDIT = "LakeHavasu"
NEW_URL = f"https://www.reddit.com/r/{SUBREDDIT}/new.json"
SEARCH_URL = f"https://www.reddit.com/r/{SUBREDDIT}/search.json"
# Descriptive UA per reddit API etiquette.
USER_AGENT = "havasu-chat/1.0 (by /u/havasuchat; +https://havasu-chat-production.up.railway.app)"
_SNIPPET_CHARS = 280
# <= 10 req/min -> ~0.16 qps.
_LIMITER = SourceLimiter("reddit_havasu", qps=0.15)


@dataclass
class RedditPost:
    post_id: str
    title: str
    permalink: str
    snippet: str | None
    author: str | None
    created_at: datetime | None
    mentions: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _permalink(data: dict) -> str:
    pl = data.get("permalink") or ""
    if pl.startswith("http"):
        return pl
    return f"https://www.reddit.com{pl}" if pl else (data.get("url") or "")


def parse_listing(payload: Any) -> list[RedditPost]:
    """Parse a reddit listing JSON into RedditPost records (snippet only)."""
    children = ((payload.get("data") or {}).get("children")) if isinstance(payload, dict) else None
    if not isinstance(children, list):
        return []
    posts: list[RedditPost] = []
    for child in children:
        data = child.get("data") if isinstance(child, dict) else None
        if not isinstance(data, dict):
            continue
        title = (data.get("title") or "").strip()
        if not title:
            continue
        selftext = (data.get("selftext") or "").strip()
        snippet = (selftext[:_SNIPPET_CHARS] or None) if selftext else None
        created = data.get("created_utc")
        created_at = (
            datetime.fromtimestamp(float(created), tz=UTC).replace(tzinfo=None)
            if isinstance(created, (int, float))
            else None
        )
        # Pipe business mentions toward the existing mention_scanner flow.
        mention_text = f"{title}. {selftext}"
        mentions = [m.mentioned_name for m in scan_tier3_response(mention_text)]
        posts.append(
            RedditPost(
                post_id=str(data.get("id") or ""),
                title=title,
                permalink=_permalink(data),
                snippet=snippet,
                author=data.get("author"),
                created_at=created_at,
                mentions=mentions,
                raw={"id": data.get("id")},
            )
        )
    return posts


def _get_json(url: str, params: dict | None, client: httpx.Client) -> Any:
    resp = _LIMITER.call_with_retry(lambda: client.get(url, params=params, timeout=30.0))
    if resp is None:
        raise RuntimeError(f"reddit fetch failed: {url}")
    resp.raise_for_status()
    return resp.json()


def fetch_new(*, limit: int = 25, client: httpx.Client | None = None) -> list[RedditPost]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        return parse_listing(_get_json(NEW_URL, {"limit": str(limit)}, c))
    finally:
        if owns:
            c.close()


def search_business(name: str, *, client: httpx.Client | None = None) -> list[RedditPost]:
    """Weekly sweep: search the subreddit for a business name."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    params = {"q": name, "restrict_sr": "1", "sort": "new", "limit": "10"}
    try:
        return parse_listing(_get_json(SEARCH_URL, params, c))
    finally:
        if owns:
            c.close()


def post_sample(p: RedditPost) -> dict:
    return {
        "title": p.title,
        "permalink": p.permalink,
        "snippet": p.snippet,
        "mentions": p.mentions[:6],
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
