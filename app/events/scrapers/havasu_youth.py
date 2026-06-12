"""Recurring youth/family fixtures with no scrapeable calendar feed.

These venues publish a FIXED weekly schedule rather than an events feed:
Havasu Lanes' "Rock & Bowl" glow nights, and Altitude Trampoline Park's
"Junior Jump Time" and "Glow in the Park". We emit concrete dated occurrences
across a rolling window so the youth/family calendar always shows the next
several weeks. Re-running extends the horizon; ``find_duplicate``
(venue + date + normalized title) keeps it idempotent, and each occurrence gets
a distinct ``?occ=`` URL so it lands as its own contribution
(``normalize_submission_url`` preserves query strings).

Schedules verified 2026-06-12 from havasulanesaz.com/SPECIALS and
altitudetrampolinepark.com (Lake Havasu City). When a venue changes its weekly
schedule, edit ``FIXTURES`` — that is the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

HORIZON_DAYS = 56  # ~8 weeks of rolling occurrences

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


def _toptracer(
    slug: str,
    *,
    weekdays: tuple[int, ...],
    start: time,
    end: time,
    price: str,
) -> Fixture:
    """Build a Toptracer-at-Iron-Wolf family range fixture for one day group."""
    return Fixture(
        slug=slug,
        title="Toptracer Range — Family Night Golf",
        weekdays=weekdays,
        start=start,
        end=end,
        venue="Iron Wolf Golf & Country Club — Toptracer Range",
        address="3275 N Latrobe Dr, Lake Havasu City, AZ 86404",
        url="https://ironwolfgcc.com/toptracer/",
        description=(
            "Topgolf-style target games on a climate-controlled range — "
            "affordable fun for the whole family, plus night golf and fire "
            f"pits. Hours & rate: {price} (per bay, groups of 1–6). "
            "Reserve a bay: (928) 764-1404 ext 2."
        ),
        tags=("family", "kids", "all ages", "toptracer", "golf"),
    )


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
    # Toptracer driving range at Iron Wolf — Topgolf-style target games, "night
    # golf", and "affordable fun for the entire family" (per the venue's own
    # flyer). Transcribed from the SUMMER 2026 rates image on
    # ironwolfgcc.com/toptracer/ (verified 2026-06-12; the flyer is authoritative
    # per Casey). Closed Tuesday. One fixture per operating day; per-bay hourly
    # price is in the blurb.
    _toptracer(
        "toptracer-mon", weekdays=(0,), start=time(17, 0), end=time(21, 0),
        price="$30 per hour, 5–9 PM",
    ),
    _toptracer(
        "toptracer-wed-thu", weekdays=(2, 3), start=time(17, 0), end=time(21, 0),
        price="$35 per hour, 5–9 PM",
    ),
    _toptracer(
        "toptracer-fri-sat", weekdays=(4, 5), start=time(14, 0), end=time(22, 0),
        price="$49/hr 2–5 PM, then $59/hr 5–10 PM",
    ),
    _toptracer(
        "toptracer-sun", weekdays=(6,), start=time(11, 0), end=time(19, 0),
        price="$35 per hour, 11 AM–7 PM",
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
