"""Lake Havasu golf venues: curated facility set + hours-event specs.

Mirrors :mod:`app.contrib.lakehavasu_pickleball` in shape (pure helpers operate
on data/fixtures with no network; a thin fetch layer wraps them with an
injectable ``httpx.Client``; the loader :mod:`scripts.lhc_golf_load` owns
persistence + reconcile/approve). It differs in *source*: golf hours are not on
a single scrapeable page — courses publish seasonal tee-time hours, Iron Wolf's
**Toptracer** rates/hours are image flyers (handed to the vision pipeline, not
regex-parsed here), Back Nine is a static 24/7 fact, and the simulator lounges
publish fixed weekly hours. So the in-geo-fence venue set is **curated from the
2026-06-25 research** (Appendix A of the reorg plan) rather than HTML-scraped,
with one fixture-testable parse helper (:func:`parse_toptracer_open_days`) for
the Iron Wolf Toptracer page text.

What this module emits (mirroring pickleball):

  * **Facilities** -> ``EntityPayload`` providers under the existing directory
    subcategory ``golf`` (Tier-1 ``outdoors-parks-trails``). The venue kind
    (course / driving range / indoor simulator) is folded into the description
    and stamped on the hours events as a ``venue-kind:*`` tag.
  * **Hours** -> all-day ``Event`` occurrences on a rolling forward window
    (exactly how pickleball open play is published), tagged ``activity:golf`` +
    ``facet:hours`` + ``venue-kind:*`` (+ ``indoor:true`` for simulators). The
    pruner drops aged-out rows so stale hours never linger.

**Geo-fence (Casey 2026-06-25: "no golf outside Lake Havasu"):** only in-town
venues are curated. The out-of-area courses the repo already prunes
(Emerald Canyon/Parker, Cerbat Cliffs/Kingman, Chaparral/Bullhead, El Rio/Mohave
Valley, Havasu Springs/Parker-side) are listed in :data:`OUT_OF_AREA_COURSES`
for documentation and are deliberately NOT emitted.

Records map to ``source="lhc_golf"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Any

import httpx

from app.contrib.ingest_base import EntityPayload
from app.events.time_labels import format_short_time

USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"
REQUEST_TIMEOUT = httpx.Timeout(45.0, connect=20.0)

SOURCE_NAME = "lhc_golf"
# Catalog slug the loader resolves to Provider.category_id. This must be the
# SERVED golf leaf (``golf-courses``, a level-1 leaf under
# ``things-to-do-and-attractions``) — NOT the legacy ``outdoors-parks-trails``
# department, which no longer owns golf and holds zero providers. Targeting the
# department left every net-new curated venue off the public golf leaf (T1.2,
# 2026-07-06); the live active venues only appear because their google_places
# twins already carry ``golf-courses``.
DEFAULT_CATEGORY_SLUG = "golf-courses"
# Second-level Provider.subcategory (already exists in the directory taxonomy).
SUBCATEGORY = "golf"
LEGACY_CATEGORY = "golf"

# Canonical public URL for the golf leaf — the fallback link on curated hours
# rows/events when a venue has no website. The old ``/outdoors-parks-trails/golf``
# path 404s (wrong department + wrong leaf slug); this is the served leaf.
GOLF_LEAF_URL = "https://askhava.com/categories/things-to-do-and-attractions/golf-courses"

# Hours are republished on a rolling forward window and pruned as they age
# (mirrors pickleball open play).
HOURS_WINDOW_DAYS = 7

# Out-of-area courses the repo already deactivates (deactivate_outofarea_golf_*).
# Curated here ONLY so the geo-fence is explicit — these are never emitted.
OUT_OF_AREA_COURSES: tuple[str, ...] = (
    "Emerald Canyon Golf Course",      # Parker
    "Cerbat Cliffs Golf Course",       # Kingman
    "Chaparral Country Club",          # Bullhead City
    "El Rio Golf Club",                # Mohave Valley
    "Havasu Springs Resort Golf",      # ~toward Parker (Casey: out of geo-fence)
)

# S4 liveness guard: in-geo-fence venues that have PERMANENTLY CLOSED. A curated
# venue set can silently keep listing a course that shut down years ago (a closed
# business shown as "Open daily" is the worst directory failure). Mirroring
# OUT_OF_AREA_COURSES, a name here is never emitted as a facility / hours row, and
# the loader (scripts.lhc_golf_load) deactivates any live Provider matching it.
# Match is name-normalized (case/space/punct fold) via ``is_closed_venue``.
CLOSED_VENUES: tuple[str, ...] = (
    # Closed 2018 (Island Golf Club at The Nautical); effluent-irrigation cost
    # tripled and salinity killed the turf. Verified 2026-07-06.
    "Havasu Island Golf Course",
)


def _normalize_venue_name(name: str) -> str:
    """Fold a venue name for closed/duplicate matching: lowercase, collapse
    whitespace, drop punctuation. ``"Havasu Island Golf Course"`` and
    ``"havasu island golf course."`` compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


_CLOSED_VENUE_KEYS = frozenset(_normalize_venue_name(n) for n in CLOSED_VENUES)


def is_closed_venue(name: str) -> bool:
    """True when ``name`` is a permanently-closed curated venue (S4 guard)."""
    return _normalize_venue_name(name) in _CLOSED_VENUE_KEYS


@dataclass(frozen=True)
class GolfVenue:
    """One in-town golf venue (curated from research)."""

    name: str
    venue_kind: str  # "course" | "range" | "simulator"
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    indoor: bool = False
    hours_text: str | None = None  # human-readable hours for the description
    blurb: str | None = None
    # Render-time "today hours" for the calendar's curated venue-hours row
    # (golf_hours_rows). ``hours`` maps weekday (Mon=0..Sun=6) -> open spans for a
    # venue we have CLOCK times for (the simulator lounge); ``hours_label`` is the
    # honest fixed label for a course/range whose schedule is seasonal/by-tee-time
    # ("Open daily", "Tee times daily", "Open 6 days/wk", "Open 24/7"). One of the
    # two is always set — never "Hours vary" (Casey 2026-06-28).
    hours: dict[int, list[tuple[time, time]]] = field(default_factory=dict)
    hours_label: str = ""


@dataclass
class GolfEventSpec:
    """A golf hours occurrence. All-day rows use the app's all-day convention
    (start_time 00:00 / end_time None); the description carries the real hours and
    the ``facet:hours`` tag keeps it low-prominence."""

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


def _t(h: int, m: int = 0) -> time:
    return time(h, m)


# The in-geo-fence venue set (Appendix A, 2026-06-25). Coordinates are omitted
# (no geocoder here); the address anchors the provider. Golf USA is left
# directory-only per Casey (not emitted as a simulator venue).
IN_TOWN_VENUES: tuple[GolfVenue, ...] = (
    # Courses
    GolfVenue(
        name="Lake Havasu Golf Club",
        venue_kind="course",
        address="2400 Clubhouse Dr, Lake Havasu City, AZ 86406",
        phone="(928) 855-2719",
        website="https://lakehavasugolfclub.com/",
        hours_text="Open daily; seasonal hours (~6am open in summer — call off-season). "
                   "36 holes (East 'Nassau' + West 'Olde London'). Tee times via "
                   "lakehavasu.teesnap.net.",
        blurb="Municipal 36-hole golf club (East and West courses) in Lake Havasu City.",
        hours_label="Tee times daily",  # seasonal by-tee-time hours
    ),
    GolfVenue(
        name="Iron Wolf Golf & Country Club",
        venue_kind="course",
        address="3275 N Latrobe Dr, Lake Havasu City, AZ 86404",
        phone="(928) 764-1404",
        website="https://ironwolfgcc.com/golf-courses-lake-havasu-az/",
        hours_text="Public 18-hole par-70 course (North Shore); pro-shop hours daily. "
                   "Also home to the Top Tracer driving range.",
        blurb="Public 18-hole golf course on the North Shore; hosts the Toptracer range.",
        hours_label="Open daily",  # pro-shop hours daily
    ),
    GolfVenue(
        name="Bridgewater Links",
        venue_kind="course",
        address="London Bridge Resort, 1477 Queens Bay, Lake Havasu City, AZ 86403",
        website="https://golakehavasu.com/",
        hours_text="9-hole executive course at the London Bridge Resort; resort hours.",
        blurb="9-hole executive course at the London Bridge Resort.",
        hours_label="Open daily",  # London Bridge Resort hours
    ),
    # Havasu Island Golf Course — PERMANENTLY CLOSED (2018); see CLOSED_VENUES.
    # Removed from the emitted set 2026-07-06 (was surfacing as "Open daily").
    # Driving range — Toptracer (hours/rates published as image flyers → vision)
    GolfVenue(
        name="Iron Wolf Top Tracer Range",
        venue_kind="range",
        address="3275 N Latrobe Dr, Lake Havasu City, AZ 86404",
        phone="(928) 764-1404",
        website="https://ironwolfgcc.com/toptracer/",
        hours_text="Toptracer driving range, open 6 days/week. Current rates and exact "
                   "hours are posted as seasonal flyers — see ironwolfgcc.com/toptracer/.",
        blurb="Toptracer-equipped driving range at Iron Wolf (open 6 days/week).",
        hours_label="Open 6 days/wk",  # seasonal flyer hours
    ),
    # Indoor simulators
    GolfVenue(
        name="Back Nine Golf",
        venue_kind="simulator",
        address="Lake Havasu City, AZ",
        website="https://thebackninegolf.com/lake-havasu-city-az/",
        indoor=True,
        hours_text="Indoor golf simulators, open 24/7 (no membership required to book). "
                   "Reserve at book.thebackninegolf.com.",
        blurb="24/7 self-serve indoor golf simulators.",
        hours_label="Open 24/7",
    ),
    GolfVenue(
        name="Golf n' Brews",
        venue_kind="simulator",
        address="2018 McCulloch Blvd N, Unit A, Lake Havasu City, AZ 86403",
        phone="(928) 732-2905",
        website="https://golfnbrews.com/",
        indoor=True,
        hours_text="Indoor golf simulators + bar. Mon–Thu 9am–10pm, Fri–Sat 9am–12am, "
                   "Sun 9am–10pm.",
        blurb="Indoor golf-simulator lounge and bar on McCulloch.",
        # Published weekly hours (golfnbrews.com, Jun 2026). Fri/Sat close at
        # midnight (12 AM == time(0, 0)).
        hours={
            0: [(_t(9), _t(22))],   # Mon 9–10
            1: [(_t(9), _t(22))],   # Tue 9–10
            2: [(_t(9), _t(22))],   # Wed 9–10
            3: [(_t(9), _t(22))],   # Thu 9–10
            4: [(_t(9), _t(0))],    # Fri 9 AM–12 AM
            5: [(_t(9), _t(0))],    # Sat 9 AM–12 AM
            6: [(_t(9), _t(22))],   # Sun 9–10
        },
    ),
)


_VENUE_KIND_LABEL = {
    "course": "Golf Course",
    "range": "Driving Range — Toptracer",
    "simulator": "Indoor Golf Simulators",
}


def _facility_description(v: GolfVenue) -> str:
    bits: list[str] = []
    if v.blurb:
        bits.append(v.blurb)
    if v.hours_text:
        bits.append(f"Hours: {v.hours_text}")
    if v.website:
        bits.append(f"Details: {v.website}")
    return " ".join(bits)


def facility_to_entity_payload(
    v: GolfVenue, *, category_slug: str = DEFAULT_CATEGORY_SLUG
) -> EntityPayload:
    """Map a :class:`GolfVenue` to a source-agnostic :class:`EntityPayload`."""
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


def _hours_tags(v: GolfVenue) -> list[str]:
    """Canonical namespaced tags for a golf hours occurrence (the Phase-1 scheme):
    one activity slug, the hours facet, the venue kind, and indoor for sims."""
    tags = ["activity:golf", "facet:hours", f"venue-kind:{v.venue_kind}"]
    if v.indoor:
        tags.append("indoor:true")
    return tags


def golf_hours_event_specs(
    venues: tuple[GolfVenue, ...] = IN_TOWN_VENUES,
    *,
    today: date | None = None,
    window_days: int = HOURS_WINDOW_DAYS,
) -> list[GolfEventSpec]:
    """All-day golf hours occurrences per venue across a rolling forward window.

    Mirrors pickleball open play: one all-day row per venue per day, pruned as it
    ages. The real hours live in the description; ``facet:hours`` keeps the row
    low-prominence ("open today") rather than a destination event.
    """
    today = today or date.today()
    specs: list[GolfEventSpec] = []
    for v in venues:
        if is_closed_venue(v.name):
            continue  # permanently-closed venue (S4) — never emit hours rows
        kind_label = _VENUE_KIND_LABEL.get(v.venue_kind, "Golf")
        title = f"{kind_label} — {v.name}"[:300]
        desc = _facility_description(v)
        tags = _hours_tags(v)
        for offset in range(max(1, window_days)):
            d = today + timedelta(days=offset)
            specs.append(
                GolfEventSpec(
                    title=title,
                    description=desc,
                    date=d,
                    end_date=d,
                    location_name=v.name,
                    event_url=v.website or GOLF_LEAF_URL,
                    source_anchor=f"golfhours|{v.name}|{d.isoformat()}",
                    tags=list(tags),
                    all_day=True,
                )
            )
    return specs


# ---------------------------------------------------------------------------
# Toptracer page parse helper (fixture-testable) + injectable fetch
# ---------------------------------------------------------------------------
_OPEN_DAYS_RE = re.compile(r"open\s+(\d+)\s+days?\s*(?:/|\bper\b|\ba\b)?\s*week", re.IGNORECASE)


def parse_toptracer_open_days(html_or_text: str) -> int | None:
    """Extract "open N days/week" from the Iron Wolf Toptracer page, or None.

    The page's rates/hours are image flyers (handed to the vision pipeline, not
    parsed here); the only reliable machine-readable fact is the open-days line.
    Accepts raw HTML or visible text."""
    m = _OPEN_DAYS_RE.search(html_or_text or "")
    return int(m.group(1)) if m else None


def _get(url: str, *, client: httpx.Client | None) -> str:
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as c:
            return _get(url, client=c)
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def fetch_toptracer_open_days(*, client: httpx.Client | None = None) -> int | None:
    """Live-check the Toptracer open-days fact (best-effort; curated fallback is
    "6 days/week"). Network-light and optional — the curated hours stand alone."""
    try:
        return parse_toptracer_open_days(
            _get("https://ironwolfgcc.com/toptracer/", client=client)
        )
    except Exception:  # noqa: BLE001 — curated fallback covers a fetch failure
        return None


def golf_facilities() -> list[GolfVenue]:
    """The curated in-geo-fence golf venue set (no network), minus any venue
    that has permanently closed (S4 liveness guard)."""
    return [v for v in IN_TOWN_VENUES if not is_closed_venue(v.name)]


# ---------------------------------------------------------------------------
# Curated "today hours" calendar rows (mirrors family_venues.funzone_hours_rows)
# ---------------------------------------------------------------------------
_GOLF_HOURS_RANK = -1  # venue-hours rows sort before the day's timed events


def _fmt_span(open_t: time, close_t: time) -> str:
    """One open span: "9 AM–10 PM" — drop the redundant first meridiem when it
    matches the close, EXCEPT when either endpoint is 12 (noon/midnight), so a
    9am-to-midnight span reads the unambiguous "9 AM–12 AM" rather than "9–12 AM"."""
    o = format_short_time(open_t)
    c = format_short_time(close_t)
    o_mer = o.rsplit(" ", 1)[-1]
    c_mer = c.rsplit(" ", 1)[-1]
    if o_mer == c_mer and not o.startswith("12") and not c.startswith("12"):
        return f"{o[: -(len(o_mer) + 1)]}–{c}"
    return f"{o}–{c}"


def golf_hours_rows(day: date) -> list[dict[str, Any]]:
    """Curated "today hours" accordion rows for the in-town golf venues.

    Shaped like the funzone/family curated rows (drops straight into
    ``events_views`` day groups), carrying ``activity:golf`` + ``facet:hours`` +
    ``venue-kind:*`` tags so the events split files each row under its group
    (courses → Sports & Fitness, range/simulators → Things to Do). Every venue
    shows a REAL clock span (the simulator lounge with published hours) or an
    honest fixed label ("Open daily" / "Tee times daily" / "Open 6 days/wk" /
    "Open 24/7") — never "Hours vary". A venue closed ``day`` is omitted.
    """
    weekday = day.weekday()
    rows: list[dict[str, Any]] = []
    for v in IN_TOWN_VENUES:
        if is_closed_venue(v.name):
            continue  # permanently-closed venue (S4) — never render an hours row
        if v.hours:
            spans = v.hours.get(weekday)
            if not spans:
                continue  # known weekly schedule, closed today → omit
            time_label = ", ".join(_fmt_span(o, c) for o, c in spans)
            sort_t = spans[0][0]
        elif v.hours_label:
            time_label = v.hours_label
            sort_t = time(0, 0)
        else:
            continue  # no curated hours → omit rather than fabricate or "Hours vary"
        kind_label = _VENUE_KIND_LABEL.get(v.venue_kind, "Golf")
        tags = ["activity:golf", "facet:hours", f"venue-kind:{v.venue_kind}"]
        if v.indoor:
            tags.append("indoor:true")
        rows.append(
            {
                "sort": (_GOLF_HOURS_RANK, sort_t),
                "time_label": time_label,
                "title": f"{kind_label} — {v.name}",
                "venue": v.name,
                "url": v.website or GOLF_LEAF_URL,
                "recurring": False,
                "ongoing": True,  # venue hours, not a scheduled event
                "tags": tags,
            }
        )
    rows.sort(key=lambda r: r["sort"])
    return rows
