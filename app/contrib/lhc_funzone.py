"""Lake Havasu bowling / billiards / family-fun venues: curated facility set +
hours-event specs + themed special sessions.

Mirrors :mod:`app.contrib.lhc_golf` in shape (pure helpers operate on curated
data with no network; the loader :mod:`scripts.lhc_funzone_load` owns
persistence + reconcile/approve). These family-entertainment venues already live
in the directory (``family-fun-and-arcades``, category id 56) but are **not on
the calendar** — this module publishes:

  * **Facilities** -> ``EntityPayload`` providers under the existing directory
    subcategory ``family-fun-and-arcades`` (Tier-1 ``things-to-do-and-attractions``).
  * **Regular hours** -> all-day ``Event`` occurrences on a rolling forward
    window (exactly how golf/pickleball venue hours are published), tagged
    ``activity:<bowling|billiards|trampoline|family-fun>`` + ``facet:hours`` —
    surfaced as the **Bowling, Billiards & Family Fun** section under Things to Do.
  * **Themed recurring sessions** (Cosmic Bowling, Glow in the Park) -> distinct
    **dated, timed** ``Event`` occurrences tagged ``activity:<slug>`` +
    ``facet:special`` so they render as destination events in their own
    **Special Sessions** section, NOT folded into the venue's hours line
    (the key distinction Casey called out: cosmic/glow nights ≠ regular hours).

The venue set is **curated from the 2026-06-25 research** (Appendix A of the
reorg plan): these venues' hours are static facts (or behind booking widgets /
Google Places), not a single scrapeable page, so there is no HTML parse helper.

Records map to ``source="lhc_funzone"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.contrib.ingest_base import EntityPayload

SOURCE_NAME = "lhc_funzone"
# Tier-1 catalog slug (resolved to Provider.category_id by the loader). The
# bowling/billiards/family-fun cluster mirrors the existing directory leaf
# (family-fun-and-arcades) under the things-to-do department.
DEFAULT_CATEGORY_SLUG = "things-to-do-and-attractions"
# Second-level Provider.subcategory (already exists in the directory taxonomy).
SUBCATEGORY = "family-fun-and-arcades"
LEGACY_CATEGORY = "family-fun-and-arcades"

# Hours (and the rolling specials window) are republished on a rolling forward
# window and pruned as they age (mirrors golf/pickleball).
HOURS_WINDOW_DAYS = 7

# Display label per activity slug (used in the all-day hours-row title).
_SLUG_LABEL: dict[str, str] = {
    "bowling": "Bowling",
    "billiards": "Billiards",
    "trampoline": "Trampoline Park",
    "family-fun": "Family Fun",
}


@dataclass(frozen=True)
class FunVenue:
    """One in-town bowling / billiards / family-fun venue (curated)."""

    name: str
    activity_slug: str  # "bowling" | "billiards" | "trampoline" | "family-fun"
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    hours_text: str | None = None  # human-readable hours for the description
    blurb: str | None = None
    # Family-appropriate venues (bowling, trampoline) additively overlay Kids &
    # Family; the pool-hall/pub billiards venues do not.
    family_friendly: bool = False


@dataclass(frozen=True)
class SpecialSession:
    """A recurring themed venue session that is a destination event in its own
    right (Cosmic Bowling, Glow in the Park) — published as distinct dated rows,
    NOT folded into the venue's hours line."""

    title: str
    venue: FunVenue
    weekday: int  # Monday=0 .. Sunday=6
    start_time: str  # "HH:MM"
    end_time: str | None  # "HH:MM" or None (late/open-ended sessions)
    description: str
    family_friendly: bool = False


@dataclass
class FunEventSpec:
    """A funzone hours or special-session occurrence. Hours rows are all-day (the
    description carries the real hours, ``facet:hours`` keeps them low-prominence);
    special sessions are timed and carry ``facet:special``."""

    title: str
    description: str
    date: date
    end_date: date | None
    location_name: str
    event_url: str
    source_anchor: str
    tags: list[str] = field(default_factory=list)
    all_day: bool = True
    start_time: str | None = None
    end_time: str | None = None


# The in-town venue set (Appendix A, 2026-06-25). Hours that are unconfirmed are
# omitted from ``hours_text`` (the description still anchors the venue); the
# loader publishes hours rows for every curated venue regardless.
IN_TOWN_VENUES: tuple[FunVenue, ...] = (
    FunVenue(
        name="Havasu Lanes & Keglers Pub",
        activity_slug="bowling",
        address="2128 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        phone="(928) 855-2235",
        website="https://havasulanesaz.com/",
        hours_text="Open daily — 32 lanes, full bar (Keglers Pub), arcade, and pool tables. "
                   "Cosmic Bowling Fri 6–9pm (family) and Sat 9pm–midnight.",
        blurb="Lake Havasu's bowling alley: 32 lanes, Keglers Pub, arcade, and billiards.",
        family_friendly=True,
    ),
    FunVenue(
        name="Altitude Trampoline Park",
        activity_slug="trampoline",
        address="5601 AZ-95 N, Lake Havasu City, AZ 86404",
        website="https://altitudetrampolinepark.com/location/lake-havasu-city/",
        hours_text="Mon 11am–7pm · Tue 10am–7pm · Wed 11am–7pm · Thu 10am–7pm · "
                   "Fri 11am–8pm · Sat 10am–9pm · Sun 11am–7pm. "
                   "Glow in the Park every Sat 6–9pm; summer camps.",
        blurb="Indoor trampoline park — open jump, dodgeball, foam pit, and Glow nights.",
        family_friendly=True,
    ),
    FunVenue(
        name="Mr. Lucky's Billiards & Pub",
        activity_slug="billiards",
        address="3313 Maricopa Ave, Lake Havasu City, AZ 86406",
        website="https://mrluckysbilliardsaz.com/",
        hours_text="Open daily 11am–11pm — 14 tables, $5/hr, full bar; leagues and tournaments.",
        blurb="Billiards hall and pub: 14 tables, full bar, league and tournament play.",
    ),
    FunVenue(
        name="In the Pocket Billiard",
        activity_slug="billiards",
        address="2871 Indian Pipe Dr, Lake Havasu City, AZ 86406",
        hours_text="Billiards hall — call or see Google for current hours.",
        blurb="Lake Havasu billiards hall.",
    ),
    FunVenue(
        name="Lady Lee's Billiards Hall",
        activity_slug="billiards",
        address="Lake Havasu City, AZ",
        hours_text="Billiards hall — call or see the venue's page for current hours.",
        blurb="Lake Havasu billiards hall (also hosts a Monday-night dance party).",
    ),
)


# Themed recurring sessions (Appendix A). Cosmic Bowling splits into the Friday
# family night and the late Saturday session; Glow in the Park is Altitude's
# Saturday glow event. Each is published as a distinct dated, timed event with
# ``facet:special`` so it never collapses into the venue's hours.
def _venue(name: str) -> FunVenue:
    return next(v for v in IN_TOWN_VENUES if v.name == name)


SPECIAL_SESSIONS: tuple[SpecialSession, ...] = (
    SpecialSession(
        title="Family Cosmic Bowling",
        venue=_venue("Havasu Lanes & Keglers Pub"),
        weekday=4,  # Friday
        start_time="18:00",
        end_time="21:00",
        description="Family Cosmic Bowling at Havasu Lanes — lights-down glow bowling with "
                    "music, every Friday 6–9pm. See havasulanesaz.com/SPECIALS.",
        family_friendly=True,
    ),
    SpecialSession(
        title="Cosmic Bowling",
        venue=_venue("Havasu Lanes & Keglers Pub"),
        weekday=5,  # Saturday
        start_time="21:00",
        end_time=None,  # 9pm–midnight (open-ended to avoid a 24:00 end)
        description="Late-night Cosmic Bowling at Havasu Lanes — glow bowling with music, "
                    "every Saturday 9pm–midnight. See havasulanesaz.com/SPECIALS.",
    ),
    SpecialSession(
        title="Glow in the Park",
        venue=_venue("Altitude Trampoline Park"),
        weekday=5,  # Saturday
        start_time="18:00",
        end_time="21:00",
        description="Glow in the Park at Altitude Trampoline Park — blacklight glow jump with "
                    "music, every Saturday 6–9pm.",
        family_friendly=True,
    ),
)


def _facility_description(v: FunVenue) -> str:
    bits: list[str] = []
    if v.blurb:
        bits.append(v.blurb)
    if v.hours_text:
        bits.append(f"Hours: {v.hours_text}")
    if v.website:
        bits.append(f"Details: {v.website}")
    return " ".join(bits)


def facility_to_entity_payload(
    v: FunVenue, *, category_slug: str = DEFAULT_CATEGORY_SLUG
) -> EntityPayload:
    """Map a :class:`FunVenue` to a source-agnostic :class:`EntityPayload`."""
    return EntityPayload(
        name=v.name,
        entity_type="place",
        lat=None,
        lng=None,
        address=v.address,
        phone=v.phone,
        website=v.website,
        description=_facility_description(v),
        category_slug=category_slug,
        legacy_category=LEGACY_CATEGORY,
        google_place_id=None,
        source=SOURCE_NAME,
    )


def _hours_tags(v: FunVenue) -> list[str]:
    """Canonical namespaced tags for a funzone hours occurrence: the cluster
    activity slug, the hours facet, and ``family`` on the kid-friendly venues so
    they additively overlay Kids & Family."""
    tags = [f"activity:{v.activity_slug}", "facet:hours"]
    if v.family_friendly:
        tags.append("family")
    return tags


def funzone_hours_event_specs(
    venues: tuple[FunVenue, ...] = IN_TOWN_VENUES,
    *,
    today: date | None = None,
    window_days: int = HOURS_WINDOW_DAYS,
) -> list[FunEventSpec]:
    """All-day funzone hours occurrences per venue across a rolling forward
    window (mirrors golf hours). The real hours live in the description;
    ``facet:hours`` keeps the row low-prominence under the funzone section."""
    today = today or date.today()
    specs: list[FunEventSpec] = []
    for v in venues:
        label = _SLUG_LABEL.get(v.activity_slug, "Family Fun")
        title = f"{label} — {v.name}"[:300]
        desc = _facility_description(v)
        tags = _hours_tags(v)
        for offset in range(max(1, window_days)):
            d = today + timedelta(days=offset)
            specs.append(
                FunEventSpec(
                    title=title,
                    description=desc,
                    date=d,
                    end_date=d,
                    location_name=v.name,
                    event_url=v.website
                    or "https://askhava.com/categories/things-to-do-and-attractions/family-fun-and-arcades",
                    source_anchor=f"funhours|{v.name}|{d.isoformat()}",
                    tags=list(tags),
                    all_day=True,
                )
            )
    return specs


def funzone_special_event_specs(
    sessions: tuple[SpecialSession, ...] = SPECIAL_SESSIONS,
    *,
    today: date | None = None,
    window_days: int = HOURS_WINDOW_DAYS,
) -> list[FunEventSpec]:
    """Dated, timed special-session occurrences (Cosmic Bowling, Glow in the
    Park) for each matching weekday in the rolling window. Tagged
    ``activity:<slug>`` + ``facet:special`` so they render as distinct destination
    events under the Special Sessions section, never folded into venue hours."""
    today = today or date.today()
    specs: list[FunEventSpec] = []
    for s in sessions:
        tags = [f"activity:{s.venue.activity_slug}", "facet:special"]
        if s.family_friendly:
            tags.append("family")
        for offset in range(max(1, window_days)):
            d = today + timedelta(days=offset)
            if d.weekday() != s.weekday:
                continue
            specs.append(
                FunEventSpec(
                    title=s.title,
                    description=s.description,
                    date=d,
                    end_date=d,
                    location_name=s.venue.name,
                    event_url=s.venue.website
                    or "https://askhava.com/categories/things-to-do-and-attractions/family-fun-and-arcades",
                    source_anchor=f"funspecial|{s.venue.name}|{s.title}|{d.isoformat()}",
                    tags=list(tags),
                    all_day=False,
                    start_time=s.start_time,
                    end_time=s.end_time,
                )
            )
    return specs


def funzone_facilities() -> list[FunVenue]:
    """The curated in-town bowling / billiards / family-fun venue set (no network)."""
    return list(IN_TOWN_VENUES)
