"""allevents — AllEvents.in Lake Havasu events via schema.org JSON-LD.

source-expansion #9. ~130 rolling events including bar/nightlife events no other
source has (Flying X Saloon, Sky Lounge, The Office). The city + this-weekend
pages carry schema.org Event JSON-LD.

High overlap with golakehavasu/RiverScene on marquee events, so records are
deduped on the normalised (title, start date, venue) key WITHIN the batch here,
and at ingestion route through the event contribution flow + events.dedup
(cross-source guard). Inert build-only module: fetch + parse only, no DB writes,
no orchestrator registration.
"""

from __future__ import annotations

import logging

import httpx

from app.contrib.event_record import EventRecord, dedupe_within, parse_jsonld_events
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "allevents"
CITY_URL = "https://allevents.in/lake-havasu-city"
WEEKEND_URL = "https://allevents.in/lake-havasu-city/this-weekend"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("allevents", qps=0.5)


def _fetch_html(url: str, client: httpx.Client) -> str:
    resp = _LIMITER.call_with_retry(lambda: client.get(url, timeout=30.0))
    if resp is None:
        raise RuntimeError(f"allevents fetch failed: {url}")
    resp.raise_for_status()
    return resp.text


def fetch_events(*, include_weekend: bool = True, client: httpx.Client | None = None) -> list[EventRecord]:
    """Fetch the city (+ this-weekend) pages and parse their JSON-LD events."""
    owns = client is None
    c = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, follow_redirects=True
    )
    try:
        records = parse_jsonld_events(_fetch_html(CITY_URL, c), source=SOURCE)
        if include_weekend:
            records += parse_jsonld_events(_fetch_html(WEEKEND_URL, c), source=SOURCE)
    finally:
        if owns:
            c.close()
    return dedupe_within(records)
