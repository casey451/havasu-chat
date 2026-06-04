"""abc15_havasu — ABC15 (Scripps) Lake Havasu section RSS.

source-expansion #8. Sporadic but free full-text coverage of major Havasu
incidents (paywall-free, unlike News-Herald):

    https://www.abc15.com/news/region-northern-az/lake-havasu.rss

Standard RSS, so this reuses the generic RSS helpers in civicplus_rss. Inert
build-only module: fetch + parse only, no DB writes, no orchestrator
registration. Produces NewsItem records.
"""

from __future__ import annotations

import httpx

from app.contrib.civicplus_rss import fetch_feed_text, parse_feed
from app.contrib.news_item import NewsItem

SOURCE = "abc15_havasu"
FEED_URL = "https://www.abc15.com/news/region-northern-az/lake-havasu.rss"


def fetch_articles(*, client: httpx.Client | None = None) -> list[NewsItem]:
    text = fetch_feed_text(FEED_URL, client=client)
    return parse_feed(text, source=SOURCE)
