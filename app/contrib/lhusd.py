"""lhusd — Lake Havasu Unified School District via Apptegy Thrillshare.

source-expansion #4. Apptegy Thrillshare exposes the district's CMS over JSON +
iCal, no auth:

* live feed  (announcements/news): ``/api/v2/s/322922/live_feeds?page=1``
* events     (school calendar):     ``/api/v2/s/322924/events?start_date=..&end_date=..``
* district iCal:                    ``/api/v4/o/19160/cms/events/generate_ical``

We ingest the live feed as NewsItem records and the calendar via the iCal feed
(reusing app.events.scrapers.ical_parse). Month-long all-day academic spans
(e.g. "Summer School", "Spring Break") are noise for an event feed, so they are
filtered out — see :func:`is_academic_span_noise`.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. NEEDS_PROD_VERIFY: the live_feeds JSON field names are parsed
defensively (sandbox could not reach Thrillshare); confirm against a live
payload before wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import httpx
from bs4 import BeautifulSoup

from app.contrib.news_item import NewsItem
from app.contrib.rate_limiter import SourceLimiter
from app.events.scrapers.ical_parse import ICalEvent, parse_ical_events

if TYPE_CHECKING:
    from app.contrib.event_record import EventRecord

logger = logging.getLogger(__name__)

SOURCE = "lhusd"
_THRILLSHARE = "https://thrillshare-cmsv2.services.thrillshare.com"
LIVE_FEEDS_URL = f"{_THRILLSHARE}/api/v2/s/322922/live_feeds"
EVENTS_URL = f"{_THRILLSHARE}/api/v2/s/322924/events"
ICAL_URL = f"{_THRILLSHARE}/api/v4/o/19160/cms/events/generate_ical"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"

# All-day events spanning at least this many days are treated as academic-term
# noise (Summer School, Spring Break) rather than discrete calendar events.
ACADEMIC_SPAN_MIN_DAYS = 7

_LIMITER = SourceLimiter("lhusd", qps=0.5)


@dataclass
class LhusdEvent:
    summary: str
    start: datetime
    end: datetime | None
    location: str | None
    all_day: bool
    url: str | None = None
    raw: dict = field(default_factory=dict)

    def dedupe_key(self) -> str:
        return f"lhusd:{self.summary.lower()}:{self.start.date().isoformat()}"


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _strip_html(value: Any) -> str | None:
    if not value:
        return None
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return text or None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_live_feeds(payload: Any) -> list[NewsItem]:
    """Map a Thrillshare live_feeds JSON payload to NewsItem records.

    Defensive about the container + field names since the exact schema is
    NEEDS_PROD_VERIFY; supports ``data``/``live_feeds``/top-level list and the
    common title/url/description/published key variants.
    """
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("live_feeds") or payload.get("items") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []

    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _first(row, ("title", "headline", "name"))
        url = _first(row, ("url", "permalink", "public_url", "link"))
        if not title or not url:
            continue
        published = _parse_dt(_first(row, ("published_at", "created_at", "date", "updated_at")))
        summary = _strip_html(_first(row, ("description", "summary", "content", "body")))
        items.append(
            NewsItem(
                source=SOURCE,
                title=str(title).strip(),
                url=str(url).strip(),
                published_at=published,
                summary=summary,
                raw={"id": row.get("id")},
            )
        )
    return items


def _is_all_day(ev: ICalEvent) -> bool:
    raw = ev.raw or {}
    dtstart = raw.get("DTSTART", "")
    return "T" not in dtstart  # date-only DTSTART => all-day


def is_academic_span_noise(ev: LhusdEvent, *, min_days: int = ACADEMIC_SPAN_MIN_DAYS) -> bool:
    """True for month-long all-day academic spans we don't want as events."""
    if not ev.all_day or ev.end is None:
        return False
    span_days = (ev.end.date() - ev.start.date()).days
    return span_days >= min_days


def parse_ical(text: str) -> list[LhusdEvent]:
    """Parse the district iCal, dropping academic-span noise."""
    events: list[LhusdEvent] = []
    for ical in parse_ical_events(text):
        ev = LhusdEvent(
            summary=ical.summary,
            start=ical.start,
            end=ical.end,
            location=ical.location or None,
            all_day=_is_all_day(ical),
            url=ical.url,
            raw={"uid": ical.uid},
        )
        if is_academic_span_noise(ev):
            continue
        events.append(ev)
    return events


def _fetch_text(url: str, *, params: dict | None = None, client: httpx.Client | None = None) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/calendar"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(url, params=params, timeout=30.0))
        if resp is None:
            raise RuntimeError(f"lhusd fetch failed: {url}")
        resp.raise_for_status()
        return resp.text
    finally:
        if owns:
            c.close()


def fetch_live_feeds(*, page: int = 1, client: httpx.Client | None = None) -> list[NewsItem]:
    import json

    text = _fetch_text(LIVE_FEEDS_URL, params={"page": str(page)}, client=client)
    return parse_live_feeds(json.loads(text))


def fetch_events(*, client: httpx.Client | None = None) -> list[LhusdEvent]:
    text = _fetch_text(ICAL_URL, client=client)
    return parse_ical(text)


def event_sample(ev: LhusdEvent) -> dict[str, Any]:
    return {
        "summary": ev.summary,
        "start": ev.start.isoformat(),
        "end": ev.end.isoformat() if ev.end else None,
        "all_day": ev.all_day,
        "location": ev.location,
    }


def _unescape_ical_text(value: str | None) -> str | None:
    """Undo RFC 5545 TEXT escaping (\\, \\; \\n \\\\) left on iCal property values."""
    if not value:
        return None
    out = (
        value.replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\\\", "\\")
    )
    return out.strip() or None


def to_event_records(
    events: list[LhusdEvent], *, today: date | None = None
) -> list["EventRecord"]:
    """Map LHUSD calendar events to EventRecords for ingestion (upcoming only)."""
    from app.contrib.event_record import EventRecord

    today = today or date.today()
    records: list[EventRecord] = []
    for ev in events:
        start_date = ev.start.date()
        if start_date < today:
            continue
        end_date = ev.end.date() if ev.end else None
        title = (ev.summary or "").strip()
        if not title:
            # Defensive: an upstream iCal event without SUMMARY must not abort
            # the whole apply run — skip just that row.
            continue
        records.append(
            EventRecord(
                source=SOURCE,
                title=title,
                start_date=start_date,
                start_time=None if ev.all_day else ev.start.time().replace(tzinfo=None),
                end_date=end_date if (end_date and end_date > start_date) else None,
                end_time=None if (ev.all_day or ev.end is None) else ev.end.time().replace(tzinfo=None),
                venue_name=_unescape_ical_text(ev.location) or "Lake Havasu Unified School District",
                url=ev.url,
                tags=["school", "education", "lhusd"],
                raw={"uid": (ev.raw or {}).get("uid")},
            )
        )
    return records


def news_sample(item: NewsItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "summary": item.summary[:200] if item.summary else None,
    }
