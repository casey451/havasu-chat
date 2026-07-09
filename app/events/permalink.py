"""Public event permalink feature, extracted from app/main.py (audit 2026-07-01
decomposition): the ``/events`` redirect, the per-event ``.ics`` download, and
the ``/events/{id}`` HTML detail page + all their render helpers.

Pure move: routes, paths, route-registration order (``.ics`` before the
``{event_id}`` catch-all), and rendered output are unchanged. The router is
mounted from ``app.main``; ``app.main`` re-exports the tested helpers
(``_display_date`` / ``_format_event_datetime`` / ``_event_is_past`` /
``_truncate_for_og``) under their historical names. Imports only leaf modules
(none import ``main``), so no cycle.
"""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.admin.url_safety import safe_href
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu, occurrence_end_dt, to_lake_naive
from app.db.database import get_db
from app.db.models import Event, Provider
from app.events.directions import directions_url as event_directions_url
from app.events.event_type_tags import event_type_label
from app.events.recurrence import _event_is_recurring, next_occurrence
from app.events.tag_display import public_event_tags
from app.events.time_labels import is_time_tbd
from app.events.title_clean import clean_event_title
from app.seo.urls import base_url as _base_url

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter()


def _display_date(event: Event) -> date:
    """The date to SHOW on the detail page. For a recurring series ``event.date``
    is just the RRULE anchor (often a 2024 "Monday, January 1" seed), so show the
    next upcoming occurrence instead — matching the live day/index listing and
    killing the N1 "January 1 / This event has passed" contradiction. One-offs
    keep their own date."""
    if _event_is_recurring(event):
        nxt = next_occurrence(event, on_or_after=now_lake_havasu().date())
        if nxt is not None:
            return nxt
    return event.date


def _format_event_datetime(event: Event) -> str:
    display = _display_date(event)
    weekday = display.strftime("%A")
    month = display.strftime("%B")
    day = display.day
    # 2026-07-01 master audit §5.4: a next-calendar-year date rendered as
    # "Thursday, January 14" reads as PAST in July. Show the year whenever the
    # displayed date isn't in the current calendar year.
    year_suffix = (
        f", {display.year}" if display.year != now_lake_havasu().year else ""
    )
    if is_time_tbd(event.start_time, event.end_time):
        # WP-4 allows NULL times at ingest (never fabricate noon), and a bare
        # 00:00 start with no real end is the aggregator-ingest "no time given"
        # fallback, not a real midnight event — show the date only. The single
        # definition of that contract lives in app/events/time_labels.py.
        return f"{weekday}, {month} {day}{year_suffix}"
    hour_24 = event.start_time.hour
    minute = event.start_time.minute
    suffix = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12 or 12
    return f"{weekday}, {month} {day}{year_suffix}, {hour_12}:{minute:02d} {suffix}"


def _event_is_past(event: Event) -> bool:
    # Drives the "This event has passed" banner on the detail page. A recurring
    # series is "passed" only when it has NO future occurrence left (e.g. an
    # RRULE whose UNTIL is in the past) -- never while it still recurs. The old
    # guard only checked ``event.rdate``, so RRULE-only series (the senior-center
    # rows: rrule set, rdate NULL, anchored at 2024-01-01) fell through and wore
    # a false "passed" banner while listed live all week (N1). Compare against
    # Lake Havasu local time. A date-only one-off (NULL time) is past only once
    # the whole day is over -- never mid-day -- so a same-day all-day event is
    # not prematurely buried.
    if _event_is_recurring(event):
        return next_occurrence(event, on_or_after=now_lake_havasu().date()) is None
    now = now_lake_havasu()
    end_d = event.end_date or event.date
    if end_d < now.date():
        return True
    if end_d > now.date():
        return False
    if event.end_time is not None:
        # Shared end-moment resolution: an end_time of 00:00 (or any time at/
        # before the start) means the event runs PAST midnight, so it is not
        # "passed" earlier the same day (live bug: 1 PM "Motor Madness" stored
        # with a 00:00 end read as passed at 08:54 AM). Compare in Phoenix
        # wall-clock, consistent with the feed and /events-ui.
        end_dt = occurrence_end_dt(end_d, event.start_time, event.end_time)
        if end_dt is not None:
            return to_lake_naive(now) > end_dt
    # No end time on file (whether or not a start time is known): a same-day
    # event is NOT "passed" until the local day is over. The old 3-hour-run
    # assumption flipped a morning event to "passed" mid-morning (live bug: the
    # 9:00 AM Board of Adjustment meeting wore "This event has passed" at 9:07
    # AM). end_d == now.date() here (the earlier date checks handled past/future
    # days), so the event still has the rest of the day to run.
    return False


def _truncate_for_og(value: str, limit: int = 160) -> str:
    # og:description should never cut a word in half ("...Lake Hav"). Collapse
    # whitespace, then if we're over the limit trim back to the last word
    # boundary inside the budget and append an ellipsis. Falls back to a hard
    # slice only when a single token is longer than the limit.
    clean = " ".join(value.split()).strip()
    if len(clean) <= limit:
        return clean
    head = clean[:limit].rstrip()
    cut = head.rfind(" ")
    if cut > 0:
        head = head[:cut].rstrip()
    return head + "..."


def _link_domain(url: str | None) -> str:
    """Bare hostname for a URL (no leading ``www.``), or ``""`` when unparseable."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _link_label(url: str | None) -> str:
    """Friendly link text — the site's domain, else a generic fallback."""
    return _link_domain(url) or "Visit event page"


def _event_link_html(event_url: str | None, source_url: str | None) -> str:
    """The 'Event Link' block for the detail page.

    Shows a friendly domain label rather than the raw URL string. Falls back to
    ``source_url`` as the primary link when no ``event_url`` is stored, so a
    source-only event still links somewhere. ``safe_href`` strips dangerous
    schemes (the URLs are scraped/unvalidated and this is a public page; audit
    M2).

    Provenance byline (§3A, 2026-07-04): a quiet "Source: <aggregator>" line is
    shown ONLY when the aggregator is all we have. When ``event_url`` is a real
    organizer URL on a different domain than ``source_url`` (e.g. the Farmers
    Market's own site found via River Scene), that organizer link is the primary
    and the aggregator label is noise, so it is SUPPRESSED. When the only link is
    the aggregator (no ``event_url``, or ``event_url`` on the same domain as the
    source), the aggregator is already the primary "Event Link" — the byline
    would just duplicate it, so it stays hidden there too.
    """
    primary = (event_url or source_url or "").strip()
    if not primary:
        return ""
    safe_url = html.escape(safe_href(primary))
    label = html.escape(_link_label(primary))
    out = (
        f"<p><strong>Event Link:</strong> "
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{label}</a></p>'
    )
    src = (source_url or "").strip()
    ev = (event_url or "").strip()
    # A distinct organizer URL = a non-empty event_url on a different domain than
    # the source. When present it IS the primary link above, so drop the byline.
    has_organizer_url = bool(ev) and bool(_link_domain(ev)) and _link_domain(ev) != _link_domain(src)
    if (
        src
        and _link_domain(src)
        and _link_domain(src) != _link_domain(primary)
        and not has_organizer_url
    ):
        src_safe = html.escape(safe_href(src))
        src_label = html.escape(_link_domain(src))
        out += (
            f'<p class="ev-source"><small>Source: '
            f'<a href="{src_safe}" target="_blank" rel="noopener noreferrer">{src_label}</a>'
            f"</small></p>"
        )
    return out


def _render_not_found_response(request: Request, *, gone: bool = False) -> HTMLResponse:
    """Render the event error page. ``gone=True`` → 410 (the event was removed:
    status ``deleted``); otherwise 404 (missing or not-yet-public)."""
    return templates.TemplateResponse(
        request=request,
        name="event_not_found_lake.html",
        context={"gone": gone},
        status_code=410 if gone else 404,
    )


def _venue_profile_url(db: Session, event: Event) -> str | None:
    """Internal ``/provider/<slug>`` link for the event's venue, when that venue
    has a live directory page — so the event detail links back to the place
    (site review §1). Returns None when the venue has no published profile.
    """
    prov: Provider | None = None
    if event.provider_id:
        prov = db.query(Provider).filter(Provider.id == event.provider_id).first()
    if prov is None and event.entity_id:
        prov = db.query(Provider).filter(Provider.entity_id == event.entity_id).first()
    if prov is None or not prov.slug or prov.draft or prov.is_active is False:
        return None
    return f"/provider/{prov.slug}"


def _render_permalink_response(
    request: Request, *, event: Event, permalink_url: str, venue_url: str | None = None
) -> HTMLResponse:
    contact_html = ""
    if event.contact_name or event.contact_phone:
        parts = [html.escape(p) for p in [event.contact_name, event.contact_phone] if p]
        contact_html = f"<p><strong>Contact:</strong> {' | '.join(parts)}</p>"

    event_link_html = _event_link_html(event.event_url, event.source_url)

    tags_html = ""
    display_tags = public_event_tags(event.tags)
    if display_tags:
        tag_nodes = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in display_tags)
        tags_html = f'<div class="tags"><h2>Tags</h2><div class="tag-wrap">{tag_nodes}</div></div>'

    # Event JSON-LD (SEO audit §2.7: zero Event schema on a hyperlocal events
    # product — a free rich-results win). Built as a dict here so missing
    # fields are OMITTED, never emitted as ``"key": null``. Arizona ignores
    # DST: the offset is -07:00 year-round.
    # Schema.org wants the upcoming date, so a recurring series advertises its
    # next occurrence (not the 2024 RRULE anchor) — same source as the visible
    # date, keeping the rich result and the page in agreement.
    disp_date = _display_date(event)
    if is_time_tbd(event.start_time, event.end_time):
        start_iso = disp_date.isoformat()
    else:
        start_iso = (
            f"{disp_date.isoformat()}T{event.start_time.strftime('%H:%M')}:00-07:00"
        )
    event_jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.title,
        "startDate": start_iso,
        "url": permalink_url,
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@type": "Place",
            "name": event.location_name or "Lake Havasu City",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Lake Havasu City",
                "addressRegion": "AZ",
                "addressCountry": "US",
            },
        },
    }
    if event.end_time is not None and not is_time_tbd(event.start_time, event.end_time):
        end_d = disp_date if _event_is_recurring(event) else (event.end_date or event.date)
        event_jsonld["endDate"] = (
            f"{end_d.isoformat()}T{event.end_time.strftime('%H:%M')}:00-07:00"
        )
    if event.description:
        event_jsonld["description"] = _truncate_for_og(event.description, limit=300)
    if event.image_url and str(event.image_url).startswith("http"):
        event_jsonld["image"] = [event.image_url]

    return templates.TemplateResponse(
        request=request,
        name="event_permalink_lake.html",
        context={
            "event_title": clean_event_title(event.title, location_name=event.location_name),
            "og_description": _truncate_for_og(event.description),
            "og_url": permalink_url,
            "image_url": event.image_url,
            "formatted_datetime": _format_event_datetime(event),
            "is_past": _event_is_past(event),
            # P2: the type folded into the detail eyebrow ("Live Music"/"Comedy").
            "type_label": event_type_label(event.title, event.tags, event.location_name),
            "location_name": event.location_name,
            "venue_url": venue_url,
            "directions_url": event_directions_url(event.location_name),
            "description": event.description,
            "cost": getattr(event, "cost", None),
            "cost_description": getattr(event, "cost_description", None),
            "host": getattr(event, "host", None),
            "contact_html": contact_html,
            "event_link_html": event_link_html,
            "tags_html": tags_html,
            "event_jsonld": event_jsonld,
            "ics_url": f"/events/{event.id}.ics",
        },
    )


@router.get("/events")
def events_redirect() -> RedirectResponse:
    # /events used to serve the raw EventRead JSON dump (leaking embedding,
    # source, and internal columns to any caller). The public JSON contract now
    # lives at /api/events (app/v1/routes/events.py, scrubbed serializer); the
    # human-facing list is /events-ui. 301 so the old JSON path folds into the
    # browsable UI for crawlers.
    return RedirectResponse(url="/events-ui", status_code=301)


@router.get("/events/{event_id}.ics", include_in_schema=False)
def event_ics(event_id: str, db: Session = Depends(get_db)) -> Response:
    """Per-event iCalendar download (UX-4 "Add to calendar"). Registered before
    the HTML permalink so ``/events/{id}.ics`` matches this route, not the
    ``{event_id}`` catch-all."""
    from app.api.routes.calendar_feed import build_single_event_ics

    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        raise HTTPException(status_code=404, detail="event_not_found")
    return Response(
        content=build_single_event_ics(event),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="event-{event.id}.ics"'},
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
def event_permalink(event_id: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        return _render_not_found_response(request)
    # SEO: a removed event (status "deleted") is permanently gone — return 410,
    # not the full page (a soft-404/served-removed-content bug). Only the literal
    # "deleted" status takes this path, so a live event is never mistakenly gone.
    if event.status == "deleted":
        return _render_not_found_response(request, gone=True)
    # ED-5: build a canonical https URL from the configured base (request.url is
    # http behind Railway's proxy when X-Forwarded-Proto isn't honored).
    permalink_url = f"{_base_url()}/events/{event.id}"
    venue_url = _venue_profile_url(db, event)
    return _render_permalink_response(
        request, event=event, permalink_url=permalink_url, venue_url=venue_url
    )
