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
    # Label verb for the time chip: "Open" for drop-in venues, "Classes" for
    # studios whose published block is class time, not public open hours.
    open_verb: str = "Open"
    hours: dict[int, list[tuple[time, time]]] = field(default_factory=dict)
    verify: bool = False  # single-sourced hours — confirm before relying


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
        name="Universal Sonics Gymnastics & Cheer",
        kind="Gymnastics & cheer",
        url="http://www.universalgymnasticslakehavasu.com/",
        address="2245 N Kiowa Blvd",
        age_note="12 months–18 yrs · see schedule for class times",
        open_verb="Classes",
        # Source: chamberofcommerce.com, universalgymnasticslakehavasu.com.
        # VERIFY summer hours. Building class window; exact class times on site.
        hours={
            0: [(_h(15), _h(21))],   # Mon 3–9
            1: [(_h(15), _h(21))],   # Tue 3–9
            2: [(_h(15), _h(21))],   # Wed 3–9
            3: [(_h(15), _h(21))],   # Thu 3–9
            4: [(_h(15), _h(18, 30))],  # Fri 3–6:30
        },
        verify=True,
    ),
    FamilyVenue(
        name="Lake Havasu Black Belt Academy",
        kind="Martial arts (Taekwondo)",
        url="https://www.lakehavasublackbeltacademy.com/schedule/",
        address="597 N Lake Havasu Ave #2",
        age_note="Kids & up · ATA Tigers, Karate for Kids",
        open_verb="Classes",
        # Source: lakehavasublackbeltacademy.com/schedule.
        hours={
            0: [(_h(16), _h(19))],      # Mon 4–7
            1: [(_h(16), _h(19, 30))],  # Tue 4–7:30
            2: [(_h(16), _h(19))],      # Wed 4–7
            3: [(_h(16), _h(19))],      # Thu 4–7
            4: [(_h(16), _h(19))],      # Fri 4–7
        },
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
                "https://www.footliteschoolofdance.com/classes", "3325 Maricopa Ave #106"),
    FamilyVenue("Arizona Coast Performing Arts", "Dance studio",
                "https://www.arizonacoastperformingarts.com/", "3476 McCulloch Blvd"),
    FamilyVenue("Aqua Beginnings (swim lessons)", "Swim school",
                "https://aquabeginnings.com/"),
    FamilyVenue("Havasu Lanes (bowling, bumper lanes)", "Bowling",
                "https://www.havasulanesaz.com/"),
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
        spans = v.hours.get(weekday)
        if not spans:
            continue
        rows.append(
            {
                "sort": (_OPEN_ROW_RANK, spans[0][0]),
                "time_label": f"{v.open_verb} {_span_label(spans)}",
                "title": f"{v.name} · {v.kind}",
                "venue": v.age_note or v.address,
                "url": v.url,
                "recurring": False,
            }
        )
    rows.sort(key=lambda r: r["sort"])
    return rows
