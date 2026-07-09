"""GET /events.ics — whole-calendar iCalendar (VEVENT) feed (WP-3).

Emits every live event as a VEVENT so users can subscribe to the lake's calendar
in Apple/Google/Outlook. Hand-rolled iCalendar (RFC 5545) so we add no new
dependency: each line is CRLF-terminated, text fields are escaped, and recurring
events carry their ``RRULE`` through verbatim.

The footer link (``/events.ics`` in the shared footer partial) belongs to WP-1's
footer partial, so it is noted as a PR follow-up rather than wired here.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter, public_api_rate_limit
from app.db.database import get_db
from app.db.models import Event
from app.events.activity_taxonomy import activity_bucket, resolve_activity
from app.events.title_clean import clean_event_title
from app.home.event_buckets import GROUP_DEFS
from app.seo.urls import base_url as _canonical_base_url

router = APIRouter(tags=["events"])

_PRODID = "-//Ask Hava//Lake Havasu Events//EN"
# Bound the feed so a runaway event table can never produce a multi-megabyte
# response; the lake's real calendar is comfortably under this.
_MAX_EVENTS = 2000

# Every timed event is Lake Havasu local time. Arizona keeps MST (UTC-7) all
# year — no DST — so the VTIMEZONE has a single STANDARD component. Emitting a
# TZID (instead of the old floating local time) is the B5 fix: a floating
# DTSTART is interpreted in the *viewer's* zone, so an out-of-state subscriber
# saw camp/showtime events at the wrong hour.
_TZID = "America/Phoenix"
_VTIMEZONE: tuple[str, ...] = (
    "BEGIN:VTIMEZONE",
    f"TZID:{_TZID}",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:-0700",
    "TZOFFSETTO:-0700",
    "TZNAME:MST",
    "END:STANDARD",
    "END:VTIMEZONE",
)

# Bucket key -> human label for the CATEGORIES line (calendar reorg 2026-06-25).
_BUCKET_LABEL: dict[str, str] = {k: label for k, label, _icon in GROUP_DEFS}
# Coarse tag -> category label, so non-activity rows (markets, civic, music)
# still categorize when no activity:<slug> resolves. First match wins.
_COARSE_TAG_LABEL: tuple[tuple[str, str], ...] = (
    ("civic", "City & Government"),
    ("music", "Music & Nightlife"),
    ("lake-boating", "Lake & Boating"),
    ("automotive", "Auto & Motor"),
    ("festival", "Festivals & Events"),
    ("market", "Markets & Shopping"),
    ("food-drink", "Food & Drink"),
    ("family", "Kids & Family"),
)


def _event_categories(event: Event) -> list[str]:
    """iCalendar CATEGORIES for an event: the top-level bucket label + the
    canonical activity slug (read from the activity:<slug> tag stamped at ingest,
    or derived by the shared classifier), with a coarse-tag fallback so a
    market/civic/music row is still categorized. Empty when nothing classifies."""
    tags = [str(t) for t in (event.tags or [])]
    slug = resolve_activity(event.title or "", event.location_name, tags)
    cats: list[str] = []
    bkt = activity_bucket(slug)
    if bkt and bkt in _BUCKET_LABEL:
        cats.append(_BUCKET_LABEL[bkt])
    if slug:
        cats.append(slug)
    if not cats:
        tagset = {t.strip().lower() for t in tags}
        for tag, label in _COARSE_TAG_LABEL:
            if tag in tagset:
                cats.append(label)
                break
    return cats


def _escape_text(value: str | None) -> str:
    """Escape an iCalendar TEXT value (RFC 5545 §3.3.11)."""
    if not value:
        return ""
    out = (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )
    return out


def _fold_line(line: str) -> str:
    """Fold a content line at 75 octets per RFC 5545 §3.1 (continuation = space)."""
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    rest = line[75:]
    while rest:
        chunks.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(chunks)


def _fmt_dt(dt: datetime) -> str:
    """Floating local datetime (no Z) — events are in Lake Havasu local time."""
    return dt.strftime("%Y%m%dT%H%M%S")


def _fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def _vevent(event: Event, *, dtstamp: str, base_url: str) -> list[str]:
    lines: list[str] = ["BEGIN:VEVENT"]
    lines.append(f"UID:{event.id}@ask-hava")
    lines.append(f"DTSTAMP:{dtstamp}")

    start_at = datetime.combine(event.date, event.start_time)
    is_all_day = event.start_time == time(0, 0) and event.end_time is None
    recurs = bool(event.is_recurring and event.rrule)
    if is_all_day:
        lines.append(f"DTSTART;VALUE=DATE:{_fmt_date(event.date)}")
        lines.append(f"DTEND;VALUE=DATE:{_fmt_date(event.date + timedelta(days=1))}")
    else:
        lines.append(f"DTSTART;TZID={_TZID}:{_fmt_dt(start_at)}")
        if event.end_time is not None:
            # For a recurring event ``end_date`` is the SERIES end — the RRULE's
            # UNTIL covers it — so each occurrence's DTEND is SAME-DAY, never a
            # single multi-day block repeated daily. A non-recurring row keeps its
            # genuine (possibly multi-day) span.
            end_day = event.date if recurs else (event.end_date or event.date)
            end_at = datetime.combine(end_day, event.end_time)
            if end_at > start_at:
                lines.append(f"DTEND;TZID={_TZID}:{_fmt_dt(end_at)}")

    if event.is_recurring and event.rrule:
        rule = event.rrule.strip()
        if rule.upper().startswith("RRULE:"):
            rule = rule.split(":", 1)[1].strip()
        lines.append(f"RRULE:{rule}")

    lines.append(
        f"SUMMARY:{_escape_text(clean_event_title(event.title, location_name=event.location_name))}"
    )
    if event.location_name:
        lines.append(f"LOCATION:{_escape_text(event.location_name)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape_text(event.description)}")
    url = event.event_url or f"{base_url}/events/{event.id}"
    lines.append(f"URL:{_escape_text(url)}")
    # CATEGORIES (calendar reorg 2026-06-25): one line, comma-separated values
    # (bucket label + activity slug). Each value is escaped individually so the
    # separating commas stay category delimiters, not escaped text.
    cats = _event_categories(event)
    if cats:
        lines.append("CATEGORIES:" + ",".join(_escape_text(c) for c in cats))
    lines.append("END:VEVENT")
    return lines


@router.get("/events.ics")
@limiter.limit(public_api_rate_limit)
def events_ics_feed(request: Request, db: Session = Depends(get_db)) -> Response:
    """Return the whole live-event calendar as an iCalendar feed."""
    from app.core.timezone import now_lake_havasu

    # P1.0: route the iCal event URLs through the one canonical origin (BASE_URL)
    # instead of a hardcoded Railway host, so the Phase-0 domain swap is one env.
    base_url = _canonical_base_url()
    dtstamp = _fmt_dt(now_lake_havasu().replace(tzinfo=None))

    rows = (
        db.query(Event)
        .filter(Event.status == "live")
        .order_by(Event.date.asc(), Event.start_time.asc())
        .limit(_MAX_EVENTS)
        .all()
    )

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Lake Havasu Events",
    ]
    lines.extend(_VTIMEZONE)
    for ev in rows:
        lines.extend(_vevent(ev, dtstamp=dtstamp, base_url=base_url))
    lines.append("END:VCALENDAR")

    body = "\r\n".join(_fold_line(line) for line in lines) + "\r\n"
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="lake-havasu-events.ics"'},
    )


def build_single_event_ics(event: Event) -> str:
    """A complete single-event iCalendar document (one VEVENT) for the per-event
    "Add to calendar" download (UX-4). Reuses the same VEVENT builder + line
    folding as the sitewide feed so the two never drift."""
    from app.core.timezone import now_lake_havasu

    base_url = _canonical_base_url()
    dtstamp = _fmt_dt(now_lake_havasu().replace(tzinfo=None))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    lines.extend(_VTIMEZONE)
    lines.extend(_vevent(event, dtstamp=dtstamp, base_url=base_url))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_line(line) for line in lines) + "\r\n"
