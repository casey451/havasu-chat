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

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Event
from app.events.title_clean import clean_event_title
from app.seo.urls import base_url as _canonical_base_url

router = APIRouter(tags=["events"])

_PRODID = "-//Ask Hava//Lake Havasu Events//EN"
# Bound the feed so a runaway event table can never produce a multi-megabyte
# response; the lake's real calendar is comfortably under this.
_MAX_EVENTS = 2000


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
    if is_all_day:
        lines.append(f"DTSTART;VALUE=DATE:{_fmt_date(event.date)}")
        lines.append(f"DTEND;VALUE=DATE:{_fmt_date(event.date + timedelta(days=1))}")
    else:
        lines.append(f"DTSTART:{_fmt_dt(start_at)}")
        if event.end_time is not None:
            end_at = datetime.combine(event.end_date or event.date, event.end_time)
            if end_at > start_at:
                lines.append(f"DTEND:{_fmt_dt(end_at)}")

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
    lines.append("END:VEVENT")
    return lines


@router.get("/events.ics")
def events_ics_feed(db: Session = Depends(get_db)) -> Response:
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
    lines.extend(_vevent(event, dtstamp=dtstamp, base_url=base_url))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_line(line) for line in lines) + "\r\n"
