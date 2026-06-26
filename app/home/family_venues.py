"""Curated youth- & family-venue hours for the calendar's "Kids & Family" group.

The events table answers "what's *scheduled* today". It does not answer "what's
simply *open* for kids today" — the toddler playground, the pizza arcade, the
trampoline park, the youth gym/dojo class blocks. Those are recurring open
hours, not dated events, so they never appeared on the calendar and a parent
scanning a quiet weekday saw "nothing for kids" even though several family
places were open.

This module is a small, hand-curated dataset of those venues plus a read-time
helper (:func:`open_today_rows`) that yields accordion-row dicts shaped exactly
like :func:`app.home.events_views.day_groups` rows, so they drop into the
"Kids & Family" group with no template work and no fabricated event rows.

Honesty contract (matches the rest of the calendar): we ONLY publish a
day-gated "Open H–H" row for a venue whose weekly hours we are reasonably
confident about. Venues whose schedule lives only on Facebook / a booking
platform — or whose hours we could not confirm — live in :data:`DIRECTORY`
with a link to their own schedule and NO invented times. Update hours here when
they change (single source of truth); every fact carries a source comment.

Weekday convention: Monday=0 … Sunday=6 (``datetime.date.weekday()``).
Hours sourced June 2026; see relay/ research notes. Items marked VERIFY were
single-sourced — confirm before leaning on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

from app.events.time_labels import format_short_time

# Sort rank that places always-open venue rows AFTER timed events and even
# after the "Time TBD" rows (which use rank 1 — see time_labels.time_sort_key).
_OPEN_ROW_RANK = 2


@dataclass(frozen=True)
class FamilyVenue:
    """A youth/family venue with (optional) confident weekly open hours.

    ``hours`` maps weekday (Mon=0..Sun=6) → list of (open, close) spans. A
    missing or empty weekday means closed that day. When ``hours`` is empty the
    venue is directory-only (surfaced with a link, never a fabricated time).
    """

    name: str
    kind: str  # short descriptor, e.g. "Indoor playground", "Martial arts"
    url: str
    address: str = ""
    age_note: str = ""
    hours: dict[int, list[tuple[time, time]]] = field(default_factory=dict)
    verify: bool = False  # single-sourced hours — confirm before relying
    # Venue-type slug for the Things-to-Do "Bowling, Billiards & Family Fun"
    # cluster (bowling / billiards / trampoline / family-fun). Empty = not a
    # funzone venue (won't surface in that cluster). See funzone_hours_rows.
    venue_kind: str = ""
    # True for kid/family venues that surface in the Kids & Family "Open today
    # for kids" overlay. Pool-hall/pub billiards are family=False (funzone only).
    family: bool = True


def _h(h: int, m: int = 0) -> time:
    return time(h, m)


# --- Drop-in family venues with confident weekly hours ----------------------
# These yield day-gated "Open H–H" rows in the Kids & Family group.

OPEN_VENUES: tuple[FamilyVenue, ...] = (
    FamilyVenue(
        name="The Spot — Pizza & Arcade",
        kind="Pizza & arcade",
        url="https://thespotlhc.com/",
        address="3612 Jamaica Blvd S",
        age_note="All ages — arcade for kids, lounge for adults",
        venue_kind="family-fun",
        # Source: Yelp (Jun 2026), thespotlhc.com, golakehavasu.com.
        hours={
            6: [(_h(12), _h(21))],  # Sun 12–9
            # Mon (0) + Tue (1) closed
            2: [(_h(15), _h(21))],  # Wed 3–9
            3: [(_h(15), _h(21))],  # Thu 3–9
            4: [(_h(15), _h(22))],  # Fri 3–10
            5: [(_h(12), _h(22))],  # Sat 12–10
        },
    ),
    FamilyVenue(
        name="Sunshine Indoor Play",
        kind="Indoor toddler playground",
        url="https://www.sunshineindoorplay.com/",
        address="5601 AZ-95 N, Unit H814",
        age_note="Babies, toddlers & preschoolers",
        venue_kind="family-fun",
        # Source: sunshineindoorplay.com, Yelp (May 2026). VERIFY summer hours.
        hours={
            1: [(_h(9), _h(17))],   # Tue 9–5
            2: [(_h(9), _h(17))],   # Wed 9–5
            3: [(_h(9), _h(17))],   # Thu 9–5
            4: [(_h(9), _h(19))],   # Fri 9–7
            5: [(_h(9), _h(14))],   # Sat 9–2
            # Sun (6) + Mon (0) closed
        },
        verify=True,
    ),
    FamilyVenue(
        name="Altitude Trampoline Park",
        kind="Trampoline park",
        url="https://www.altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/",
        address="5601 Hwy 95 N, Unit 404-D",
        age_note="All ages — dedicated toddler area",
        venue_kind="trampoline",
        # Source: altitudetrampolinepark.com, Yelp (May 2026). VERIFY summer hours.
        hours={
            0: [(_h(11), _h(19))],  # Mon 11–7
            1: [(_h(10), _h(19))],  # Tue 10–7
            2: [(_h(11), _h(19))],  # Wed 11–7
            3: [(_h(10), _h(19))],  # Thu 10–7
            4: [(_h(11), _h(20))],  # Fri 11–8
            5: [(_h(10), _h(21))],  # Sat 10–9
            6: [(_h(11), _h(19))],  # Sun 11–7
        },
        verify=True,
    ),
    FamilyVenue(
        name="Havasu Lanes",
        kind="Bowling",
        url="https://www.havasulanesaz.com/",
        address="2128 McCulloch Blvd N",
        age_note="Bumper lanes & arcade for kids · Rock & Bowl black-light "
        "bowling Fri & Sat 6 PM–close",
        # Source: havasulanesaz.com home (Hours of Operation) + SPECIALS page
        # (Rock & Bowl cosmic/neon nights), read Jun 2026. 32-lane center.
        hours={
            0: [(_h(12), _h(21))],  # Mon 12–9
            1: [(_h(12), _h(21))],  # Tue 12–9
            2: [(_h(12), _h(21))],  # Wed 12–9
            3: [(_h(12), _h(21))],  # Thu 12–9
            4: [(_h(12), _h(23))],  # Fri 12–11
            5: [(_h(12), _h(23))],  # Sat 12–11
            6: [(_h(12), _h(19))],  # Sun 12–7
        },
        venue_kind="bowling",
    ),
    # --- Billiards / pool halls (funzone cluster; not kid venues) -----------
    # family=False so they surface ONLY in Things to Do → Billiards, never in the
    # Kids & Family "Open today for kids" overlay.
    FamilyVenue(
        name="Mr. Lucky's Billiards & Pub",
        kind="Billiards & pub",
        url="https://mrluckysbilliardsaz.com/",
        address="3313 Maricopa Ave",
        age_note="14 tables · full bar · leagues & tournaments",
        # Source: mrluckysbilliardsaz.com, golakehavasu.com (Jun 2026).
        hours={d: [(_h(11), _h(23))] for d in range(7)},  # daily 11 AM–11 PM
        venue_kind="billiards",
        family=False,
    ),
    FamilyVenue(
        name="In the Pocket Billiard",
        kind="Billiards hall",
        url="https://www.yelp.com/biz/in-the-pocket-billiard-lake-havasu-city",
        address="2871 Indian Pipe Dr",
        # Hours not confirmed → surfaced with a "Hours vary" label, never a
        # fabricated time (honesty contract).
        venue_kind="billiards",
        family=False,
    ),
    FamilyVenue(
        name="Lady Lee's Billiards Hall",
        kind="Billiards hall",
        url="https://www.facebook.com/people/Lady-Lees/",
        age_note="Billiards · Monday-night dance party",
        venue_kind="billiards",
        family=False,
    ),
)


# --- Directory-only places (link out; NO fabricated hours) ------------------
# Surfaced as static "More for kids & families" data — schedules live on each
# venue's own site / Facebook / booking platform. Kept here so the data has a
# single home even though it does not (yet) feed the day-gated rows.

DIRECTORY: tuple[FamilyVenue, ...] = (
    FamilyVenue("Arevalo Academy (MMA / kids martial arts)", "Martial arts",
                "https://arevaloacademy.com/schedule/", "3611 Jamaica Blvd S #A"),
    FamilyVenue("Footlite School of Dance", "Dance studio",
                "https://www.footliteschoolofdance.com/", "3325 Maricopa Ave #106"),
    FamilyVenue("Arizona Coast Performing Arts", "Dance studio",
                "https://www.arizonacoastperformingarts.com/", "3476 McCulloch Blvd"),
    FamilyVenue("Aqua Beginnings (swim lessons)", "Swim school",
                "https://aquabeginnings.com/"),
    FamilyVenue("Bless This Nest (kids art clubs & camps)", "Kids art studio",
                "https://blessthisnestlhc.com/", "2886 Sweetwater Ave #B-108"),
    FamilyVenue("Movies Havasu", "Movie theater",
                "https://www.movieshavasu.com/", "180 Swanson Ave"),
    FamilyVenue("Mohave County Library — Lake Havasu (free kids storytimes)", "Library",
                "https://www.mohavecountylibrary.us/lake-havasu-city-branch/"),
    FamilyVenue("Lake Havasu Lions FC (youth soccer)", "Youth sports",
                "https://www.havasulions.com/"),
    FamilyVenue("Lake Havasu Little League (baseball/softball)", "Youth sports",
                "https://www.sportsengine.com/org/lake-havasu-little-league"),
)


def _fmt_span(open_t: time, close_t: time) -> str:
    """One span: "3–9 PM" (drop the redundant first meridiem when it matches),
    "9 AM–2 PM" when they differ."""
    o = format_short_time(open_t)
    c = format_short_time(close_t)
    o_mer = o.rsplit(" ", 1)[-1]
    c_mer = c.rsplit(" ", 1)[-1]
    if o_mer == c_mer:
        return f"{o[: -(len(o_mer) + 1)]}–{c}"
    return f"{o}–{c}"


def _span_label(spans: list[tuple[time, time]]) -> str:
    """"3–9 PM" / "9 AM–5 PM, 6–8 PM" from one or more open spans."""
    return ", ".join(_fmt_span(o, c) for o, c in spans)


def open_today_rows(day: date) -> list[dict[str, Any]]:
    """Accordion-row dicts for family venues open on ``day``.

    Shaped like :func:`app.home.events_views.day_groups` rows so the caller can
    extend the "Kids & Family" group directly. Always-open venues sort after
    timed events (rank :data:`_OPEN_ROW_RANK`). Venues closed ``day`` (or with
    no confident hours) are omitted — never a fabricated "open" claim.
    """
    weekday = day.weekday()
    rows: list[dict[str, Any]] = []
    for v in OPEN_VENUES:
        if not v.family:
            continue  # billiards/pub venues belong to the funzone cluster only
        spans = v.hours.get(weekday)
        if not spans:
            continue
        rows.append(
            {
                # Bare hours range ("9 AM–5 PM") — no "Open" verb. The section
                # heading ("Open today for kids") already says these are open
                # hours, so the prefix was redundant noise on every row.
                "sort": (_OPEN_ROW_RANK, spans[0][0]),
                "time_label": _span_label(spans),
                "title": f"{v.name} · {v.kind}",
                "venue": v.age_note or v.address,
                "url": v.url,
                "recurring": False,
                "ongoing": True,  # drop-in venue hours, not a scheduled class
            }
        )
    rows.sort(key=lambda r: r["sort"])
    return rows


# Funzone (bowling/billiards/trampoline/arcade) venue-type cluster under Things
# to Do. The hours rows sort BEFORE the day's timed events within their sub-
# section (rank -1) so a venue reads "hours, then its events" (Casey 2026-06-26).
_FUNZONE_HOURS_RANK = -1
HOURS_VARY_LABEL = "Hours vary"
FUNZONE_KINDS: frozenset[str] = frozenset({"bowling", "billiards", "trampoline", "family-fun"})


def funzone_hours_rows(day: date) -> list[dict[str, Any]]:
    """Accordion-row dicts for the Things-to-Do "Bowling, Billiards & Family Fun"
    cluster — every funzone venue, carrying its venue-kind so the events split
    files it under Billiards / Bowling / Trampoline / Arcade & Family Fun.

    A venue with confident weekly hours shows its real "12–11 PM" window (and is
    omitted on a day it is closed — never a fabricated "open" claim); a venue
    whose hours we cannot confirm shows "Hours vary" rather than "Time TBD".
    Shaped like :func:`open_today_rows` (drops straight into the day-view "events"
    group), with ``activity:<kind>`` + ``facet:hours`` tags so the split routes it
    and the auto-expand rule reads it as a listing (not an event)."""
    weekday = day.weekday()
    rows: list[dict[str, Any]] = []
    for v in OPEN_VENUES:
        if v.venue_kind not in FUNZONE_KINDS:
            continue
        if v.hours:
            spans = v.hours.get(weekday)
            if not spans:
                continue  # known schedule, closed today → omit
            time_label = _span_label(spans)
            sort_t = spans[0][0]
        else:
            time_label = HOURS_VARY_LABEL  # schedule unconfirmed
            sort_t = time(0, 0)
        rows.append(
            {
                "sort": (_FUNZONE_HOURS_RANK, sort_t),
                "time_label": time_label,
                "title": f"{v.name} · {v.kind}",
                "venue": v.age_note or v.address,
                "url": v.url,
                "recurring": False,
                "ongoing": True,  # venue hours, not an event
                "tags": [f"activity:{v.venue_kind}", "facet:hours"],
            }
        )
    rows.sort(key=lambda r: r["sort"])
    return rows


# -- Studio class schedules (real, published times) --------------------------
# Two youth studios publish a full weekly class grid. Rather than a single
# "open hours" row (which read as a misleading "Classes 3–9" block covering the
# whole building-open window), we list each *real* class under its matching
# Kids & Family youth subsection — Youth Gymnastics / Youth Martial Arts — with
# the class name, day, time, and (where published) age range, so a parent can
# actually plan around it. Honesty contract still holds: only times the studio
# itself publishes; no fabricated blocks. Refresh when the studio updates its
# grid (a twice-weekly scraper, once built, becomes the source of truth here).


@dataclass(frozen=True)
class StudioClass:
    """One published class: weekday (Mon=0..Sun=6) + start/end + optional age."""

    name: str
    weekday: int
    start: time
    end: time
    age_note: str = ""


@dataclass(frozen=True)
class Studio:
    """A youth studio whose individual classes file under one youth subsection."""

    name: str  # full venue name
    short: str  # short suffix shown in the row title ("… · Universal Sonics")
    section: str  # Kids & Family subsection these classes belong to
    activity: str  # provider-activity hint (taxonomy fallback routing)
    url: str  # link to the studio's full schedule
    classes: tuple[StudioClass, ...] = ()


def _c(name: str, wd: int, sh: int, sm: int, eh: int, em: int, age: str = "") -> StudioClass:
    return StudioClass(name, wd, time(sh, sm), time(eh, em), age)


STUDIOS: tuple[Studio, ...] = (
    Studio(
        name="Lake Havasu Black Belt Academy",
        short="Black Belt Academy",
        section="Youth Martial Arts",
        activity="Martial Arts",
        url="https://www.lakehavasublackbeltacademy.com/schedule/",
        # Source: lakehavasublackbeltacademy.com/schedule weekly grid, read
        # Jun 2026. Adult-only blocks (Adult/Teen, Adult Self Defense, Tai Chi)
        # are intentionally left off the youth listing.
        classes=(
            _c("Beginners", 0, 16, 0, 16, 40),
            _c("Advanced", 0, 16, 45, 17, 25),
            _c("Black Belt", 0, 17, 30, 18, 0),
            _c("Tigers", 1, 16, 0, 16, 30, "Ages 3–6"),
            _c("Black Belt", 1, 16, 35, 17, 5),
            _c("Legacy", 1, 17, 5, 17, 35),
            _c("Advanced", 1, 17, 40, 18, 15),
            _c("Beginner", 1, 18, 20, 19, 0),
            _c("Beginner", 2, 16, 0, 16, 40),
            _c("Beginner Weapons", 2, 16, 40, 17, 0),
            _c("Advanced", 2, 17, 5, 17, 20),
            _c("Advanced Weapons", 2, 17, 25, 18, 10),
            _c("Tiny Tigers", 3, 15, 45, 16, 10, "Ages 2–3"),
            _c("Tigers", 3, 16, 15, 16, 45, "Ages 3–6"),
            _c("Leadership / Xtreme", 3, 16, 50, 17, 25),
            _c("Sparring", 3, 17, 30, 18, 30),
            _c("Tigers", 4, 16, 0, 16, 30, "Ages 3–6"),
            _c("Beginner", 4, 16, 35, 17, 10),
            _c("Advanced", 4, 17, 15, 18, 0),
            _c("Technique / Fundamentals", 4, 18, 5, 18, 30),
        ),
    ),
    Studio(
        name="Universal Sonics Gymnastics & Cheer",
        short="Universal Sonics",
        section="Youth Gymnastics",
        activity="Gymnastics",
        # http only — the https cert is broken (renders a login/error page).
        url="http://www.universalgymnasticslakehavasu.com/index.php?componentName=ClassScheduleDeluxe&scid=73927",
        # Source: universalgymnasticslakehavasu.com class schedule, read Jun
        # 2026. Recreational / preschool enrollable classes only; by-placement
        # competitive team & all-star practices are left off the public listing.
        classes=(
            _c("Firecrackers Gymnastics", 0, 15, 0, 16, 15),
            _c("Recreational Gymnastics", 0, 16, 0, 17, 0, "Ages 5–9"),
            _c("Dynamites Gymnastics", 0, 16, 0, 17, 30),
            _c("Recreational Gymnastics", 0, 17, 0, 18, 0),
            _c("Sparklers Gymnastics", 1, 15, 0, 16, 30),
            _c("Boys Athletics", 1, 15, 30, 16, 30, "Ages 5–10"),
            _c("Tiny Tumblers", 1, 16, 30, 17, 15, "Ages 3–4"),
            _c("Recreational Gymnastics", 1, 16, 30, 17, 30, "Ages 5–9"),
            _c("Tiny Tumblers", 1, 17, 30, 18, 15, "Ages 3–4"),
            _c("Recreational Tumbling", 1, 17, 30, 18, 30, "Ages 8+"),
            _c("Boys Athletics", 1, 18, 30, 19, 30, "Ages 11+"),
            _c("Firecrackers Gymnastics", 2, 15, 0, 16, 0),
            _c("Recreational Gymnastics", 2, 16, 0, 17, 0, "Ages 5–9"),
            _c("Dynamites Gymnastics", 2, 16, 0, 17, 30),
            _c("Recreational Gymnastics", 2, 16, 45, 17, 45, "Ages 9+"),
            _c("Lil Firecrackers", 2, 17, 0, 18, 0),
            _c("Tiny Tumblers", 2, 17, 30, 18, 15, "Ages 3–4"),
            _c("Sparklers Gymnastics", 3, 15, 0, 16, 30),
            _c("Recreational Cheer", 3, 15, 30, 16, 30, "Ages 5+"),
            _c("Recreational Gymnastics", 3, 16, 30, 17, 30, "Ages 5–9"),
            _c("Gym Tots", 3, 17, 30, 18, 0, "Ages 6 mo–3 yr · parent participation"),
            _c("Tiny Tumblers", 3, 18, 0, 18, 45, "Ages 3–4"),
        ),
    ),
)

# Studio class rows interleave with timed events by start time (rank 1), so they
# sit naturally among the day's scheduled occurrences within their subsection.
_CLASS_ROW_RANK = 1


def class_today_rows(day: date) -> list[dict[str, Any]]:
    """Accordion-row dicts for studio classes that meet on ``day``.

    Shaped like :func:`open_today_rows` rows, but ``ongoing`` is false and each
    row carries an explicit ``subgroup`` so it files under the studio's youth
    subsection (Youth Gymnastics / Youth Martial Arts) instead of "Open today
    for kids". Only the studio's real, published class times are emitted.
    """
    weekday = day.weekday()
    rows: list[dict[str, Any]] = []
    for s in STUDIOS:
        for c in s.classes:
            if c.weekday != weekday:
                continue
            rows.append(
                {
                    "sort": (_CLASS_ROW_RANK, c.start),
                    "time_label": _fmt_span(c.start, c.end),
                    "title": f"{c.name} · {s.short}",
                    "venue": c.age_note,
                    "url": s.url,
                    "recurring": True,
                    "ongoing": False,
                    "subgroup": s.section,
                    "activity": s.activity,
                }
            )
    rows.sort(key=lambda r: r["sort"])
    return rows
