"""Recurring youth/family fixtures with no scrapeable calendar feed.

These venues publish a FIXED weekly schedule rather than an events feed:
Havasu Lanes' "Rock & Bowl" glow nights, and Altitude Trampoline Park's
"Junior Jump Time" and "Glow in the Park" (the two client-named Altitude gaps
this WS12 slice closes). We emit concrete dated occurrences across a rolling
window so the youth/family calendar always shows the next several weeks.
Re-running extends the horizon; the runner's ``find_duplicate``
(venue + date + normalized title + time) keeps it idempotent, and each
occurrence gets a distinct ``?occ=`` URL so it lands as its own contribution
(``normalize_submission_url`` preserves query strings).

Salvage note (WS12, from closed PR #302):
  * KEPT: Rock & Bowl + the two Altitude fixtures — the client-named coverage
    gaps, and there is no live feed for them (FB/venue-watcher is the eventual
    durable path; a hand-maintained fixture is the honest stopgap).
  * DROPPED: the four "Toptracer — Family Night Golf" fixtures from #302. A
    driving-range's per-bay hourly rate is venue *hours*, not a dated event
    (WS6 §14.3 moves "Golf Course — Open daily" to the places-open rail), and
    "Family Night Golf" is itself a WS6 AM/PM lint fixture. Publishing it as a
    nightly kids event is exactly the padding WS6 removes.
  * ROLLOUT: NOT auto-approved. Every occurrence lands PENDING in the review
    queue (training wheels) — which is also the checkpoint where Casey
    re-verifies these hand-maintained schedules are still current before any
    row goes live. When a venue changes its weekly schedule, edit ``FIXTURES``;
    that tuple is the single source of truth.

Schedules verified 2026-06-12 from havasulanesaz.com/SPECIALS and
altitudetrampolinepark.com (Lake Havasu City). Re-confirm at review time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

# ~6 weeks of rolling occurrences. Shorter than #302's 8 weeks to keep the
# first training-wheels review batch smaller; re-runs roll the window forward.
HORIZON_DAYS = 42

_ALTITUDE_URL = (
    "https://www.altitudetrampolinepark.com/locations/arizona/"
    "lake-havasu-city/5601-highway-95-n/"
)
_ALTITUDE_ADDR = "5601 Highway 95 N Unit 404-D, Lake Havasu City, AZ 86404"


@dataclass(frozen=True)
class Fixture:
    slug: str
    title: str
    weekdays: tuple[int, ...]  # Monday=0 .. Sunday=6
    start: time
    venue: str
    url: str
    end: time | None = None
    address: str | None = None
    description: str = ""
    tags: tuple[str, ...] = ()


FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        slug="rock-and-bowl",
        title="Rock & Bowl — Family Glow Bowling",
        weekdays=(4, 5),  # Friday, Saturday
        start=time(18, 0),
        end=time(23, 0),
        venue="Havasu Lanes",
        address="2128 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        url="https://www.havasulanesaz.com/SPECIALS",
        description=(
            "Lights down, fun up — black-lights, party lights and all your "
            "favorite music. $18 / $22 / $26 per person includes shoes plus "
            "1 / 2 / 3 hours of unlimited bowling. Bumper bowling for the kids."
        ),
        tags=("family", "kids", "all ages", "bowling", "glow"),
    ),
    Fixture(
        slug="altitude-junior-jump",
        title="Junior Jump Time (Ages 6 & Under)",
        weekdays=(1, 3),  # Tuesday, Thursday
        start=time(10, 0),
        end=time(12, 0),
        venue="Altitude Trampoline Park",
        address=_ALTITUDE_ADDR,
        url=_ALTITUDE_URL,
        description=(
            "Our biggest jump time for our littlest jumpers — designed for "
            "highflyers ages 6 & under. Open sight lines and comfy seating so "
            "grown-ups can 'sittervise'. $9."
        ),
        tags=("toddler", "kids", "family"),
    ),
    Fixture(
        slug="altitude-glow-wed",
        title="Glow in the Park — All Ages",
        weekdays=(2,),  # Wednesday
        start=time(17, 0),
        end=time(19, 0),
        venue="Altitude Trampoline Park",
        address=_ALTITUDE_ADDR,
        url=_ALTITUDE_URL,
        description="Jump under the blacklights with DJ Des — all ages invited.",
        tags=("family", "kids", "all ages", "glow"),
    ),
    Fixture(
        slug="altitude-glow-sat",
        title="Glow in the Park — All Ages",
        weekdays=(5,),  # Saturday
        start=time(19, 0),
        end=time(21, 0),
        venue="Altitude Trampoline Park",
        address=_ALTITUDE_ADDR,
        url=_ALTITUDE_URL,
        description="Footloose free play under the weekend lights with DJ Des. $20.",
        tags=("family", "kids", "all ages", "glow"),
    ),
)

_BY_SLUG = {fx.slug: fx for fx in FIXTURES}


class HavasuYouthClient(EventIngestClient):
    source_name = "havasu_youth"
    scrape_source = "havasu_youth"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today = query.get("today") or date.today()
        horizon = today + timedelta(days=HORIZON_DAYS)
        hits: list[RawHit] = []
        for fx in FIXTURES:
            d = today
            while d <= horizon:
                if d.weekday() in fx.weekdays:
                    # Distinct per-occurrence URL so each lands as its own
                    # contribution (normalize_submission_url keeps the query).
                    occ_url = f"{fx.url}?occ={fx.slug}-{d.isoformat()}"
                    hits.append(
                        RawHit(
                            source=self.source_name,
                            source_stable_id=occ_url,
                            name=fx.title,
                            raw={"slug": fx.slug, "date": d.isoformat()},
                        )
                    )
                d += timedelta(days=1)
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        fx = _BY_SLUG[str(raw["slug"])]
        d = date.fromisoformat(str(raw["date"]))
        return EventPayload(
            name=fx.title,
            entity_type="event",
            source=self.scrape_source,
            start_date=d,
            start_time=fx.start,
            end_time=fx.end,
            venue_name=fx.venue,
            address=fx.address,
            description=fx.description,
            event_url=hit.raw_hit.source_stable_id,
            source_stable_url=hit.raw_hit.source_stable_id,
            category_slug="events",
            tags=list(fx.tags),
        )
