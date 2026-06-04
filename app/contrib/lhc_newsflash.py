"""lhc_newsflash — City of LHC "News Flash" CivicPlus RSS (source-expansion #1).

Road closures (with dates + streets), PD/city press releases. ~daily cadence.
Feed verified live 2026-06-04. Inert build-only module: fetch + parse only,
no DB writes, not registered in any orchestrator.

Proposed store (PR decision): a ``news_items`` table keyed on the article URL,
or routing through the contribution queue with ``entity_type="news"``. See
app/contrib/news_item.py.
"""

from __future__ import annotations

import httpx

from app.contrib.civicplus_rss import fetch_civicplus_items
from app.contrib.news_item import NewsItem

SOURCE = "lhc_newsflash"
FEED_URL = "https://www.lhcaz.gov/RSSFeed.aspx?ModID=1&CID=All-newsflash.xml"


def fetch_newsflash(*, client: httpx.Client | None = None) -> list[NewsItem]:
    return fetch_civicplus_items(FEED_URL, source=SOURCE, client=client)
