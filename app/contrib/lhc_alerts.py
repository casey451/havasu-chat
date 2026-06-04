"""lhc_alerts — City of LHC "Alert Center" CivicPlus RSS (source-expansion #2).

Emergency alerts. This feed is USUALLY EMPTY (0 items) — that is the expected
steady state, not a failure. Designed for poll-until-nonempty: a run that
returns 0 items is healthy, and any nonempty result is the signal worth
surfacing fast. Inert build-only module: fetch + parse only, no DB writes.
"""

from __future__ import annotations

import httpx

from app.contrib.civicplus_rss import fetch_civicplus_items
from app.contrib.news_item import NewsItem

SOURCE = "lhc_alerts"
FEED_URL = "https://www.lhcaz.gov/RSSFeed.aspx?ModID=63&CID=All-0"


def fetch_alerts(*, client: httpx.Client | None = None) -> list[NewsItem]:
    """Fetch the Alert Center feed. An empty list is the expected normal state."""
    return fetch_civicplus_items(FEED_URL, source=SOURCE, client=client)
