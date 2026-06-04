"""senior_center — Lake Havasu Senior Center classes/activities (HTML scrape).

source-expansion #13. Small HTML scrape of lakehavasuseniorcenter.com's
current-events page (classes, activities — many recurring weekly with no fixed
calendar date). RELEVANCE GATE: the dry-run surfaces samples so Casey can judge
whether the content is useful; the module is trivially removable.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: selectors parsed defensively against a fixture
(sandbox could not reach the site); confirm vs live markup before wiring.
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from app.contrib.event_record import EventRecord
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "senior_center"
CURRENT_EVENTS_URL = "https://lakehavasuseniorcenter.com/current-events"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("senior_center", qps=0.5)
_TITLE_TAGS = ("h2", "h3", "h4", "strong", "b")


def parse_activities(html: str) -> list[EventRecord]:
    """Parse activity blocks into recurring EventRecords (no fixed date)."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select(".activity, .event, .event-item, article, li.activity")
    records: list[EventRecord] = []
    for block in blocks:
        title_el = None
        for tag in _TITLE_TAGS:
            title_el = block.find(tag)
            if title_el:
                break
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        if not title:
            continue
        # Detail = the rest of the block's text minus the title.
        detail = block.get_text(" ", strip=True)
        if detail.startswith(title):
            detail = detail[len(title):].strip(" -–—:")
        records.append(
            EventRecord(
                source=SOURCE,
                title=title,
                start_date=None,  # recurring schedule; no fixed calendar date
                description=detail or None,
                tags=["senior-center", "class"],
            )
        )
    return records


def fetch_activities(*, client: httpx.Client | None = None) -> list[EventRecord]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(CURRENT_EVENTS_URL, timeout=30.0))
        if resp is None:
            raise RuntimeError("senior_center fetch failed")
        resp.raise_for_status()
        return parse_activities(resp.text)
    finally:
        if owns:
            c.close()


def activity_sample(rec: EventRecord) -> dict:
    return {"title": rec.title, "detail": (rec.description or "")[:160], "tags": rec.tags}
