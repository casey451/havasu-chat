"""Lake Havasu City Pickleball Association (LHCPBA) scrape: fetch + parse helpers.

Source: https://www.lakehavasupickleball.com (a Wix site). Mirrors
:mod:`app.contrib.usapickleball` in shape: pure parse helpers operate on fetched
HTML strings (so they unit-test against fixtures with no network), and a thin
fetch layer wraps them with an injectable ``httpx.Client``. The loader
(:mod:`scripts.lakehavasu_pickleball_load`) owns persistence + reconcile/approve
hand-off.

What this module extracts from the **static** HTML (no browser needed):

  * **Facilities** -> ``EntityPayload`` providers. The Places-to-Play page links
    each venue to Google Maps; the maps URL carries the canonical coordinates as
    ``!3d<lat>!4d<lng>``, so we get accurate geo without a geocoder. Address,
    cost, and a prose blurb come from the surrounding page text (the prose is
    folded into ``Provider.description`` per the product decision -- there is no
    separate knowledge/FAQ store in Ask Hava).

  * **Activities** -> recurring ``Program`` specs (round robins, beginner
    lessons, novice clinics) parsed from the Organized-Play pages.

  * **PickleFest** -> a dated ``Event`` spec parsed from the Tournaments page.

Open play is published as **all-day events** per venue (:func:`open_play_event_specs`)
on a rolling forward window. The site's calendar widget is a third-party
``plugin.eventscalendar.co`` iframe with no JSON API that renders unreliably for
a headless scraper, so open-play events are derived from the reliably-scraped
facility list instead -- keeping this module network-light and browser-free.

Records map to ``source="lakehavasu_pickleball"``. Facilities carry the
``racquet-sports`` subcategory; the loader resolves the Tier-1
``classes-sports-recreation`` slug to ``Provider.category_id``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.contrib.ingest_base import EntityPayload

BASE_URL = "https://www.lakehavasupickleball.com"
USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"
REQUEST_TIMEOUT = httpx.Timeout(45.0, connect=20.0)

SOURCE_NAME = "lakehavasu_pickleball"
# Tier-1 catalog slug (resolved to Provider.category_id by the loader). Pickleball
# lives under the Sports/Fitness bucket whose public page is classes-sports-recreation.
DEFAULT_CATEGORY_SLUG = "classes-sports-recreation"
# Second-level Provider.subcategory (see app/categories/subcategories.py).
SUBCATEGORY = "racquet-sports"
# Legacy Provider.category string; derive_subcategory maps it back to SUBCATEGORY.
LEGACY_CATEGORY = "pickleball"

ORG_NAME = "Lake Havasu City Pickleball Association"
ORG_PHONE: str | None = None  # the site exposes no phone; contact is via a web form

# Page paths on the site (also the per-record source_url anchors).
FACILITIES_URL = f"{BASE_URL}/places-to-play"
ROUND_ROBIN_URL = f"{BASE_URL}/round-robin"
INSTRUCTION_URL = f"{BASE_URL}/beginner-novice-pickleball-instruct-1"
TOURNAMENTS_URL = f"{BASE_URL}/tournaments"
MEMBERSHIP_URL = f"{BASE_URL}/membership"
CALENDAR_URL = f"{BASE_URL}/calendar"

# Open-play all-day events are published for a rolling forward window and pruned
# as they age (mirrors the aquatic-event pattern in parks_rec_loader).
OPEN_PLAY_WINDOW_DAYS = 7

# Maps URL: ...!3d<lat>!4d<lng> are the canonical place coordinates.
_MAPS_LATLNG_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
# Street + "Lake Havasu City, AZ <zip>" -- the page writes a few small variants.
_ADDRESS_RE = re.compile(
    r"(\d{3,5}\s+[A-Za-z0-9.\s]+?),?\s*"
    r"(?:Lake Havasu City|LHC),?\s*AZ\s*(\d{5})",
    re.I,
)
_ZIP_RE = re.compile(r"\b(\d{5})\b")
# "$3/per session", "$5.00 per session", "$3 per session", "It's FREE to play"
_COST_RE = re.compile(r"\$\s*(\d+(?:\.\d{2})?)", re.I)
_FREE_RE = re.compile(r"\bfree to play\b|\bit'?s free\b|\bfree\b", re.I)
_PICKLEFEST_RE = re.compile(r"PickleFest\s*(\d{4})", re.I)
# "scheduled for 2/27/26 - 3/1/26"
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{2,4})\s*[-–]\s*(\d{1,2})/(\d{1,2})/(\d{2,4})"
)

# Number-word -> int for court counts written out in prose ("sixteen courts").
_NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
}

# Canonical venue anchors. The maps link text is messy ("at Dick Samp Park"),
# so we key venues by a stable substring of the maps link text and attach a
# clean display name + whether courts are indoor/outdoor.
_VENUE_ANCHORS: tuple[tuple[str, str, bool], ...] = (
    # (match-substring in link text, clean display name, indoor?)
    ("Mike Delaney", "Mike Delaney Pickleball Complex at Dick Samp Park", False),
    ("Aquatic Center", "Lake Havasu City Aquatic Center", True),
    ("Ark Center", "The Ark Center", True),
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Facility:
    """One pickleball venue parsed from the Places-to-Play page."""

    name: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    cost: str | None = None
    indoor_courts: int | None = None
    outdoor_courts: int | None = None
    blurb: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProgramSpec:
    """A recurring activity (round robin, lesson, clinic, or open-play block).

    Shape matches what the loader needs to build a ``ProgramApprovalFields``.
    ``schedule_days`` are full weekday names ("Monday", ...). ``source_anchor``
    is a stable per-program fragment appended to the page URL for dedup.
    """

    title: str
    description: str
    location_name: str
    location_address: str | None = None
    cost: str | None = None
    schedule_days: list[str] = field(default_factory=list)
    start_time: str | None = None  # "HH:MM"
    end_time: str | None = None  # "HH:MM"
    activity_category: str = "sports"
    tags: list[str] = field(default_factory=lambda: ["sports"])
    contact_url: str = ROUND_ROBIN_URL
    source_anchor: str = ""


@dataclass
class EventSpec:
    """A dated event. ``all_day`` open-play events render as all-day in Ask Hava
    (the loader writes ``start_time=00:00`` + ``end_time=None``, the app's all-day
    convention); dated one-offs like PickleFest are timed."""

    title: str
    description: str
    date: date
    end_date: date | None
    location_name: str
    event_url: str
    source_anchor: str
    all_day: bool = False


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    s = re.sub(r"\s+", " ", text).strip()
    return s or None


def page_text(html: str) -> str:
    """Visible text of a page, newline-joined (resilient to Wix markup churn)."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def _parse_year(yy: str) -> int:
    n = int(yy)
    return 2000 + n if n < 100 else n


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------


def _maps_links(html: str) -> list[tuple[str, float | None, float | None]]:
    """(link-text, lat, lng) for every Google-Maps anchor on the page."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, float | None, float | None]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "google.com/maps" not in href:
            continue
        m = _MAPS_LATLNG_RE.search(href)
        lat = float(m.group(1)) if m else None
        lng = float(m.group(2)) if m else None
        out.append((_clean(a.get_text(" ", strip=True)) or "", lat, lng))
    return out


def _venue_block(text: str, name_fragment: str, all_fragments: list[str]) -> str:
    """Slice of ``text`` from ``name_fragment`` up to the next venue heading."""
    low = text.lower()
    start = low.find(name_fragment.lower())
    if start < 0:
        return ""
    ends = [
        low.find(f.lower(), start + len(name_fragment))
        for f in all_fragments
        if f.lower() != name_fragment.lower()
    ]
    ends = [e for e in ends if e > start]
    stop = min(ends) if ends else len(text)
    return text[start:stop]


# Longest-first so "sixteen" wins over "six" in the alternation.
_NUMBER_WORDS_ALT = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
# A count (1-2 digit number or number-word) followed within up to 3 words by
# "court(s)", e.g. "sixteen dedicated outdoor pickleball courts" or "Three indoor
# courts". The digit count is capped at two digits so a nearby 5-digit ZIP
# (e.g. "AZ 86406 ... Three indoor courts") can't be mistaken for a court count.
_COURTS_RE = re.compile(
    r"\b(\d{1,2}|" + _NUMBER_WORDS_ALT + r")\s+(?:[A-Za-z]+\s+){0,3}courts?\b",
    re.I,
)


def _count_courts(block: str) -> tuple[int | None, int | None]:
    """(indoor, outdoor) court counts pulled from a venue blurb.

    Heuristic: the first "<N> ... court(s)" phrase gives the count; indoor vs
    outdoor is decided by which keyword the single-venue block uses (these
    blocks describe one venue, so they are not mixed).
    """
    m = _COURTS_RE.search(block)
    if not m:
        return None, None
    raw_n = m.group(1)
    n = int(raw_n) if raw_n.isdigit() else _NUMBER_WORDS.get(raw_n.lower())
    if n is None:
        return None, None
    low = block.lower()
    has_indoor = "indoor" in low
    has_outdoor = "outdoor" in low
    if has_indoor and not has_outdoor:
        return n, None
    if has_outdoor and not has_indoor:
        return None, n
    # Ambiguous or unlabeled: default to outdoor (the common public-court case).
    return None, n


def _cost_phrase(block: str) -> str | None:
    """Human-readable cost for a venue blurb."""
    m = _COST_RE.search(block)
    if m:
        return f"${m.group(1)} per session"
    if _FREE_RE.search(block):
        return "Free"
    return None


def parse_facilities(html: str) -> list[Facility]:
    """Parse the Places-to-Play page into venue records.

    Venues are anchored on their Google-Maps link (which yields clean
    coordinates); address/cost/court-count/blurb come from the page text block
    that follows each venue heading.
    """
    text = page_text(html)
    links = _maps_links(html)
    fragments = [frag for frag, _, _ in _VENUE_ANCHORS]

    # Map each venue anchor -> best coordinates from a matching maps link.
    coords: dict[str, tuple[float | None, float | None]] = {}
    for frag, _name, _indoor in _VENUE_ANCHORS:
        for ltext, lat, lng in links:
            if frag.lower() in ltext.lower() and lat is not None:
                coords[frag] = (lat, lng)
                break

    facilities: list[Facility] = []
    for frag, display_name, _indoor in _VENUE_ANCHORS:
        block = _venue_block(text, frag, fragments)
        if not block:
            continue
        lat, lng = coords.get(frag, (None, None))
        addr = None
        am = _ADDRESS_RE.search(block.replace("\n", " "))
        if am:
            street = _clean(am.group(1))
            addr = f"{street}, Lake Havasu City, AZ {am.group(2)}"
        indoor, outdoor = _count_courts(block)
        facilities.append(
            Facility(
                name=display_name,
                lat=lat,
                lng=lng,
                address=addr,
                cost=_cost_phrase(block),
                indoor_courts=indoor,
                outdoor_courts=outdoor,
                blurb=_clean(block),
            )
        )
    return facilities


def _facility_description(f: Facility) -> str:
    """Fold the venue prose into a compact Provider.description.

    Leads with the structured facts (courts, cost) then a trimmed blurb so the
    chat layer can answer "where / how much / indoor or outdoor" directly.
    """
    bits: list[str] = []
    courts: list[str] = []
    if f.indoor_courts:
        courts.append(f"{f.indoor_courts} indoor")
    if f.outdoor_courts:
        courts.append(f"{f.outdoor_courts} outdoor")
    if courts:
        bits.append("Pickleball courts: " + ", ".join(courts) + ".")
    if f.cost:
        bits.append(f"Cost: {f.cost}.")
    bits.append(
        f"A pickleball venue coordinated by the {ORG_NAME}. "
        f"See schedule and details at {FACILITIES_URL}."
    )
    # A trimmed slice of the original prose for richer Q&A, capped for sanity.
    if f.blurb:
        trimmed = f.blurb[:600].rsplit(" ", 1)[0]
        bits.append(trimmed)
    return " ".join(bits)


def facility_to_entity_payload(
    f: Facility,
    *,
    category_slug: str = DEFAULT_CATEGORY_SLUG,
) -> EntityPayload:
    """Map a :class:`Facility` to a source-agnostic :class:`EntityPayload`."""
    return EntityPayload(
        name=f.name,
        entity_type="place",
        lat=f.lat,
        lng=f.lng,
        address=f.address,
        phone=ORG_PHONE,
        website=FACILITIES_URL,
        description=_facility_description(f),
        category_slug=category_slug,
        legacy_category=LEGACY_CATEGORY,
        google_place_id=None,
        source=SOURCE_NAME,
    )


# ---------------------------------------------------------------------------
# Activities (round robins, lessons, clinics) -> ProgramSpec
# ---------------------------------------------------------------------------


def parse_round_robin(html: str) -> list[ProgramSpec]:
    """Parse the Round Robin page into a single recurring program spec.

    Round robins are member-only, skill-grouped, ~100-minute sessions. The page
    does not publish fixed weekday/time (it's seasonal + SignUpGenius driven), so
    we publish one informational program describing how/when they run.
    """
    text = page_text(html)
    if "round robin" not in text.lower():
        return []
    desc = (
        "Weekly skill-grouped Round Robins run by the Lake Havasu City Pickleball "
        "Association (member-only; invitations via SignUp Genius). Each ~100-minute "
        "session is six games with rotating partners and opponents, grouped by skill "
        "level. Round robins are seasonal and typically start in December. "
        f"Details: {ROUND_ROBIN_URL}."
    )
    return [
        ProgramSpec(
            title="LHCPBA Round Robins",
            description=desc,
            location_name="Mike Delaney Pickleball Complex at Dick Samp Park",
            cost="Member-only event",
            schedule_days=[],
            activity_category="sports",
            tags=["sports", "adult"],
            contact_url=ROUND_ROBIN_URL,
            source_anchor="round-robin",
        )
    ]


def parse_instruction(html: str) -> list[ProgramSpec]:
    """Parse the Beginner/Novice instruction page into program specs."""
    text = page_text(html)
    low = text.lower()
    specs: list[ProgramSpec] = []
    ark_addr = "2700 Jamaica Blvd S, Lake Havasu City, AZ 86406"
    if "beginner" in low:
        specs.append(
            ProgramSpec(
                title="LHCPBA Beginner Pickleball Lessons",
                description=(
                    "Free first beginner lesson from the Lake Havasu City Pickleball "
                    "Association at the ARK Center indoor gym. Equipment provided; wear "
                    "court shoes. Covers equipment, court layout, basic strokes, "
                    "positioning, and scoring (~1.5 hours). Seasonal -- typically resumes "
                    f"in December. Details: {INSTRUCTION_URL}."
                ),
                location_name="The Ark Center",
                location_address=ark_addr,
                cost="First lesson free",
                activity_category="sports",
                tags=["sports", "beginner"],
                contact_url=INSTRUCTION_URL,
                source_anchor="beginner-lessons",
            )
        )
    if "novice" in low:
        specs.append(
            ProgramSpec(
                title="LHCPBA Novice Pickleball Clinics",
                description=(
                    "Follow-up novice clinics (below 3.0 skill level) from the Lake "
                    "Havasu City Pickleball Association at the ARK Center: guided "
                    "skills/drills plus play. $5 per session (court reservation). "
                    f"Seasonal -- typically resumes in December. Details: {INSTRUCTION_URL}."
                ),
                location_name="The Ark Center",
                location_address=ark_addr,
                cost="$5 per session",
                activity_category="sports",
                tags=["sports", "novice"],
                contact_url=INSTRUCTION_URL,
                source_anchor="novice-clinics",
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Tournaments (PickleFest) -> EventSpec
# ---------------------------------------------------------------------------


def parse_tournaments(html: str, *, today: date | None = None) -> list[EventSpec]:
    """Parse the Tournaments page for a dated PickleFest event.

    Only emits an event when an explicit date range is present and the event is
    not in the past relative to ``today``.
    """
    today = today or date.today()
    text = page_text(html)
    year_m = _PICKLEFEST_RE.search(text)
    range_m = _DATE_RANGE_RE.search(text)
    if not range_m:
        return []
    sm, sd, sy, em, ed, ey = range_m.groups()
    try:
        start = date(_parse_year(sy), int(sm), int(sd))
        end = date(_parse_year(ey), int(em), int(ed))
    except ValueError:
        return []
    if end < today:
        return []
    label = f"PickleFest {year_m.group(1)}" if year_m else "PickleFest"
    desc = (
        f"{label} -- the Lake Havasu City Pickleball Association's annual pickleball "
        f"tournament and biggest fundraiser, held at the Mike Delaney Pickleball "
        f"Complex at Dick Samp Park. Registration via pickleballtournaments.com. "
        f"Details: {TOURNAMENTS_URL}."
    )
    return [
        EventSpec(
            title=label,
            description=desc,
            date=start,
            end_date=end,
            location_name="Mike Delaney Pickleball Complex at Dick Samp Park",
            event_url=TOURNAMENTS_URL,
            source_anchor=f"picklefest-{start.isoformat()}",
        )
    ]


# ---------------------------------------------------------------------------
# Fetch layer (injectable httpx.Client)
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def _get(url: str, *, client: httpx.Client | None) -> str:
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT, headers=_headers(), follow_redirects=True
        ) as c:
            return _get(url, client=c)
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def fetch_facilities(*, client: httpx.Client | None = None) -> list[Facility]:
    return parse_facilities(_get(FACILITIES_URL, client=client))


def fetch_activities(*, client: httpx.Client | None = None) -> list[ProgramSpec]:
    specs = parse_round_robin(_get(ROUND_ROBIN_URL, client=client))
    specs += parse_instruction(_get(INSTRUCTION_URL, client=client))
    return specs


def fetch_tournaments(
    *, client: httpx.Client | None = None, today: date | None = None
) -> list[EventSpec]:
    return parse_tournaments(_get(TOURNAMENTS_URL, client=client), today=today)


# ---------------------------------------------------------------------------
# Open play -> all-day events
# ---------------------------------------------------------------------------


def _open_play_description(f: Facility) -> str:
    bits = [f"Drop-in pickleball open play at {f.name}, coordinated by the {ORG_NAME}."]
    if f.cost:
        bits.append(f"Cost: {f.cost}.")
    bits.append(
        "Sessions and times vary by day and season -- see the current schedule at "
        f"{CALENDAR_URL}."
    )
    return " ".join(bits)


def open_play_event_specs(
    facilities: list[Facility],
    *,
    today: date | None = None,
    window_days: int = OPEN_PLAY_WINDOW_DAYS,
) -> list[EventSpec]:
    """All-day open-play events per venue across a rolling forward window.

    Open play is an ongoing, near-daily drop-in activity rather than a single
    dated event, so we publish one all-day event per venue per day for the next
    ``window_days`` days and let the pruner drop them as they age (mirrors the
    aquatic-schedule pattern). Derived from the reliably-scraped facility list,
    so it does not depend on the JS calendar widget rendering.
    """
    today = today or date.today()
    specs: list[EventSpec] = []
    for f in facilities:
        if not f.name:
            continue
        desc = _open_play_description(f)
        for offset in range(max(1, window_days)):
            d = today + timedelta(days=offset)
            specs.append(
                EventSpec(
                    title=f"Pickleball Open Play – {f.name}"[:300],
                    description=desc,
                    date=d,
                    end_date=d,
                    location_name=f.name,
                    event_url=CALENDAR_URL,
                    source_anchor=f"openplay|{f.name}|{d.isoformat()}",
                    all_day=True,
                )
            )
    return specs
