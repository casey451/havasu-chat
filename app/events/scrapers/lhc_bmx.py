"""USA BMX microsites schedule — Lake Havasu City BMX (track 136).

Live source: the USA BMX "microsites" JSON API behind
``www.usabmx.com/tracks/az-lake-havasu-city-bmx/events``. The
``schedule/upcoming`` endpoint returns this week's + upcoming races/clinics as
structured JSON (date, race time, signup window, type), so no HTML parsing is
needed. Lake Havasu City BMX runs Tuesday & Thursday practice/race nights and
markets itself "IT'S FOR THE KIDS" — every occurrence is a youth/family event.

Verified 2026-06-12. Endpoint shape (both arrays share one item schema)::

    { "thisWeekEvent": [ {item} ], "upcomingEvent": [ {item} ] }
    item = { name, race_start_time ("ASAP" | "6:30 PM"), race_begins_on (ISO),
             signup_start_time ("6pm"), signup_end_time ("7pm"),
             series_race_type, description (HTML), status ("ACTIVE"|"RESULT"),
             track_id, race_id, ... }
"""

from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Any

from dateutil import parser as dateutil_parser

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

BMX_TRACK_ID = 136
UPCOMING_URL = (
    "https://www.usabmx.com/api/backend/microsites/schedule/upcoming"
    f"?bmx_track_id={BMX_TRACK_ID}&page=1&limit=60"
)
EVENT_DETAIL_BASE = "https://www.usabmx.com/events"
VENUE_NAME = "Lake Havasu City BMX"
# Operator-confirmed track address (Casey, 2026-06-12): the physical track is at
# SARA Park, NOT the McCulloch Blvd mailing address USA BMX lists.
VENUE_ADDRESS = "7269 Sara Park Ln, Lake Havasu City, AZ 86406"
# Operator-confirmed weekly rhythm: Tue & Thu practice/sign-ups 7 PM, racing
# 8 PM. The USA BMX feed reports "ASAP" race time + a 6–7 PM signup window for
# weekday locals; we prefer the operator times for those and keep the feed's
# explicit clock time when it gives one (clinics, weekend regional races).
DEFAULT_RACE_NIGHT_START = time(19, 0)  # 7 PM — the night "starts"

# Family signal baked into every payload so family_filter keeps these in
# family mode even though the raw race names ("Local Race", "Clinic") do not
# read as kid-specific.
_TAGS = ("youth", "kids", "family", "bmx")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str | None) -> str:
    return _HTML_TAG_RE.sub("", s or "").strip()


def _parse_time(raw_race_time: str | None) -> time:
    """The feed's explicit clock time, else the operator's 7 PM night start.

    ``race_start_time`` is "ASAP" for weekday locals (no clock time in the feed)
    but a real value for clinics ("6:30 PM") and weekend races ("9:00 AM"). When
    it parses we keep it; when it is "ASAP"/blank we fall back to the
    operator-confirmed 7 PM start (see ``DEFAULT_RACE_NIGHT_START``).
    """
    s = (raw_race_time or "").strip()
    if s and s.upper() != "ASAP":
        try:
            return dateutil_parser.parse(s).time().replace(tzinfo=None)
        except (ValueError, OverflowError):
            pass
    return DEFAULT_RACE_NIGHT_START


class LhcBmxClient(EventIngestClient):
    source_name = "lhc_bmx"
    scrape_source = "lhc_bmx"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today = query.get("today") or date.today()
        payload = json.loads(self.fetch_text(UPCOMING_URL, timeout=60.0))
        events = list(payload.get("thisWeekEvent") or []) + list(
            payload.get("upcomingEvent") or []
        )
        hits: list[RawHit] = []
        seen: set[str] = set()
        for ev in events:
            if str(ev.get("status") or "").upper() == "RESULT":
                continue  # past race with results already posted
            begins = ev.get("race_begins_on")
            if not begins:
                continue
            try:
                start_date = dateutil_parser.parse(str(begins)).date()
            except (ValueError, OverflowError):
                continue
            if start_date < today:
                continue
            race_id = ev.get("race_id")
            url = f"{EVENT_DETAIL_BASE}/{race_id}" if race_id else UPCOMING_URL
            if url in seen:
                continue
            seen.add(url)
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=url,
                    name=str(ev.get("name") or "BMX Race"),
                    raw=dict(ev, _start_date=start_date.isoformat(), _url=url),
                )
            )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        start_date = dateutil_parser.parse(str(raw["_start_date"])).date()
        start_time = _parse_time(raw.get("race_start_time"))
        raw_name = str(raw.get("name") or "Race").strip()
        # "Local Race" / "Clinic" -> "BMX Local Race" so both a reader and the
        # family filter (matches the "bmx" keyword) see this is the BMX track.
        title = raw_name if raw_name.lower().startswith("bmx") else f"BMX {raw_name}"

        body = _strip_html(raw.get("description"))
        race_time_raw = str(raw.get("race_start_time") or "")
        # Keep the feed's explicit clock time in the blurb when it gives one;
        # for weekday "ASAP" locals show the operator's 7 PM / 8 PM rhythm.
        time_line = (
            f"Race time: {race_time_raw}"
            if race_time_raw and race_time_raw.upper() != "ASAP"
            else "Practice & sign-ups 7 PM • Racing 8 PM"
        )
        desc_parts = [
            p
            for p in (
                body,
                time_line,
                "Lake Havasu City BMX at SARA Park — Tuesday & Thursday "
                "practice/race nights. New riders get a free one-day pass. "
                "Full schedule on the Lake Havasu City BMX Facebook page. "
                "It's for the kids!",
            )
            if p
        ]
        return EventPayload(
            name=title,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_date,
            start_time=start_time,
            venue_name=VENUE_NAME,
            address=VENUE_ADDRESS,
            description="\n\n".join(desc_parts),
            event_url=hit.raw_hit.source_stable_id,
            source_stable_url=hit.raw_hit.source_stable_id,
            category_slug="events",
            tags=list(_TAGS),
        )
