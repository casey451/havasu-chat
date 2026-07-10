"""WS6 — event/data quality lint (read-only detectors).

Pure rules that FLAG suspicious rows for the review queue; they never mutate
data. Each is the machine-checkable form of a real 2026-07-06 audit defect
(spec §14.3 / §6.3):

  * AM/PM flip — an event starting 12 AM–8 AM at a normal venue is almost always
    a PM time typed as AM ("Glow in the Dark Painting" at 5:30 AM; "Kids Pizza
    Party Cooking Class" at 5:15 AM). A whitelist exempts activities that
    legitimately start this early (lap swim, sunrise kayak, a gym open).
  * venue-hours-as-event — a row whose text reads as open-hours, not a dated
    occurrence ("Golf Course — Bridgewater Links · Open daily", "Open 24/7").
  * P&R venue-not-a-facility — a Parks & Rec row whose "Where" is not a named
    facility (a bare room like "Kitchen", a room code, or a mis-mapped instructor
    name like "Jane Camlin") — the same field-scramble the Glow row had.
  * name↔category contradiction — a B2B/wholesale name landing in a consumer
    food/drink/retail category ("Western States Restaurant Consulting" under
    Restaurants).

These are detectors, not fixers: a human (or a gated reclassify) resolves what
they surface, so a false positive costs a review, never a bad auto-edit. Wiring
them into the publish gate + a nightly audit is a follow-up; this module is the
reusable, tested core.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from typing import Any

# ── AM/PM flip ────────────────────────────────────────────────────────────────
# The suspicious pre-dawn window: [12 AM, 8 AM). A start here at an ordinary venue
# is almost always a PM time typed as AM. This only FLAGS for review — it never
# rewrites a time. The whitelist (below) exempts activities that legitimately
# begin this early, so a real 5:30 AM lap swim isn't a needless review.
_EARLY_START = time(0, 0)
_EARLY_END = time(8, 0)

# Activities that genuinely start before 8 AM — a pre-dawn start is expected here,
# not an AM/PM flip. Keyword match against the title (and venue). Kept tight: the
# cost of a miss is a needless review, but we don't want to whitelist so broadly
# that a real flip ("Kids Pizza Party Cooking Class" 5:15 AM) slips through.
_EARLY_OK_RE = re.compile(
    r"\b("
    r"lap\s+swim|master'?s?\s+swim|masters|early[-\s]?bird|"
    r"sunrise|sunup|dawn\s+patrol|"
    r"gym|fitness|cross\s*fit|boot\s*camp|spin(?:\s+class)?|"
    r"yoga|pilates|"
    # watersports skew early (on-water before the lake gets hot/busy). No trailing
    # \b on paddleboard/kayak/watersport so the -ing / -s inflections match.
    r"fishing|kayak\w*|paddle\w*|watersports?|"
    r"5k|10k|fun\s+run|half\s+marathon|marathon"
    r")\b",
    re.IGNORECASE,
)


def is_early_activity(title: str | None, venue: str | None = None) -> bool:
    """True when the event is a type that legitimately begins before 8 AM
    (a lap swim, a sunrise kayak/yoga/paddle, a gym open, a fishing tournament, a
    fun-run) — so a pre-dawn start is expected, not an AM/PM flip."""
    text = f"{title or ''} {venue or ''}"
    return bool(_EARLY_OK_RE.search(text))


def suspect_ampm_flip(
    start_time: time | None,
    *,
    venue_is_24h: bool = False,
    is_overnight: bool = False,
    early_ok: bool = False,
) -> bool:
    """True when ``start_time`` is in [12:00 AM, 8:00 AM) at a venue that isn't
    24-hour, the event doesn't legitimately run overnight, and it isn't a
    known-early activity (``early_ok`` — see :func:`is_early_activity`)."""
    if start_time is None or venue_is_24h or is_overnight or early_ok:
        return False
    return _EARLY_START <= start_time < _EARLY_END


# ── movie showtime plausibility (AM/PM flip) ──────────────────────────────────
# A showtime before this floor is almost always a PM time typed as AM (a 4 PM
# show stored as "4 AM" — a real 2026-07 defect: Moana @ Movies Havasu). The
# earliest LEGITIMATE showtime in town is the ~9:30 AM summer kids series, so
# 9 AM is a safe general floor. A kids/family matinee is whitelisted down to a
# slightly earlier floor (8 AM) — enough that a genuine early matinee is never
# quarantined, but NOT a blanket pass: an absurd time (a 4 AM "kids" show) is
# still caught, so a mis-tagged flip can't ride the whitelist through.
_SHOWTIME_FLOOR = time(9, 0)
_KIDS_SERIES_FLOOR = time(8, 0)
_KIDS_SERIES_RE = re.compile(
    r"kids?\s+(?:series|club)|summer\s+(?:kids|movie|film)|family\s+series|"
    r"sensory(?:\s+friendly|\s+showing|\s+screening)?|little\s+movie",
    re.IGNORECASE,
)


def is_kids_series(title: str | None = None, tags: Any = None) -> bool:
    """True for a kids/family matinee series — the one legitimately-early showing
    (the ~9:30 AM summer series). Detected by a series title or a kids/family
    series tag; the caller also passes the ``is_free`` summer-series flag in as an
    extra whitelist signal."""
    if title and _KIDS_SERIES_RE.search(title):
        return True
    toks = {str(t).strip().lower() for t in (tags or [])}
    return bool(toks & {"kids", "kids-series", "family", "family-series", "summer-series"})


def suspect_showtime(show_time: time | None, *, kids_series: bool = False) -> bool:
    """True when a movie showtime is implausibly early — almost always a PM time
    entered as AM. Before 9 AM at either theater; a kids-series matinee gets a
    slightly lower 8 AM floor (whitelisted, but an absurd 4 AM show is still
    caught)."""
    if show_time is None:
        return False
    return show_time < (_KIDS_SERIES_FLOOR if kids_series else _SHOWTIME_FLOOR)


# ── venue-hours-as-event ──────────────────────────────────────────────────────
# "Open daily", "Open 24/7", "Open 9 AM - 5 PM" read as hours, NOT a dated event.
# Guarded so real events survive: "Open Swim", "Open Mic", "Open House", "Open
# Play" are common event titles and must NOT match.
_VENUE_HOURS_RE = re.compile(
    r"\bopen\s+(?:daily|24\s*/\s*7|24\s*hours|"
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*[-–to]+)",
    re.IGNORECASE,
)


def reads_as_venue_hours(title: str | None, description: str | None = None) -> bool:
    """True when the row's text describes open-hours rather than a dated event."""
    text = f"{title or ''} {description or ''}"
    return bool(_VENUE_HOURS_RE.search(text))


# ── name ↔ category contradiction ─────────────────────────────────────────────
# B2B / trade tokens that don't belong in a consumer food/drink/retail category.
_B2B_RE = re.compile(
    r"\b(consulting|consultant|consultants|wholesale|distribution|distributor|"
    r"distributors|supply|supplies|manufacturing|manufacturer)\b",
    re.IGNORECASE,
)
# Category slugs (leaf or department) where a consumer expects an actual place to
# eat/drink/shop — a B2B name here is a misfile.
_CONSUMER_CATEGORY_TOKENS: frozenset[str] = frozenset(
    {
        "eat-and-drink", "restaurant", "restaurants", "bars", "bars-and-breweries",
        "cafes", "cafes-and-coffee", "coffee", "breweries", "food",
        "shopping-and-retail", "retail", "grocery",
    }
)


def name_category_contradiction(name: str | None, category_slug: str | None) -> str | None:
    """Return the offending B2B token when a wholesale/consulting name sits in a
    consumer food/drink/retail category, else None."""
    if not name or not category_slug:
        return None
    slug = category_slug.strip().lower()
    if not any(tok in slug for tok in _CONSUMER_CATEGORY_TOKENS):
        return None
    m = _B2B_RE.search(name)
    return m.group(1).lower() if m else None


# ── P&R venue-must-be-a-named-facility ────────────────────────────────────────
# A Parks & Rec vision row's "Where" must be a real, NAMED facility. The monthly
# grid prints the INSTRUCTOR (and sometimes a bare room word) in the activity
# cell, so a person's name ("Jane Camlin") or an unqualified room ("Kitchen",
# "Room 153") lands in the venue slot. Ingest KEEPS such a string when it looks
# place-ish (#750, deliberately permissive to avoid over-holding); this lint is
# the stricter POST-HOC signal — a live P&R event whose venue is not a named
# facility is worth a human glance (which Community Center? which kitchen?).
# Non-P&R events are never checked: "known facility" is a P&R-only concept.
_PR_URL_MARKER = "/185/parks-recreation#cal"


def _is_parks_rec(event: Any) -> bool:
    """True for a Parks & Rec vision row (source tag or the synthetic #cal URL)."""
    if "parks_rec" in (getattr(event, "source", "") or "").lower():
        return True
    return _PR_URL_MARKER in (getattr(event, "event_url", "") or "").lower()


def parks_rec_venue_unrecognized(venue: str | None) -> bool:
    """True when a P&R venue string is present but is not a NAMED facility (a bare
    room word, a room code, or a mis-mapped instructor name). Lazily imports the
    facility classifier so this pure module stays import-light."""
    if not venue or not venue.strip():
        return False
    from app.contrib.lhc_parks_rec_calendar import is_known_facility

    return not is_known_facility(venue, strict=True)


# ── landmark venue vs. the real venue in the prose ────────────────────────────
# A Go Lake Havasu / CVB event is often tagged to the shared visitor-center
# placeholder ("Go Lake Havasu Visitor Center") while its description names the
# real venue ("Red, White and Blue Bunco Party" … Mudshark Public House). Ingest
# recovery (field_recovery) auto-corrects when a LOCATION: line is present; this
# lint is the POST-HOC signal for the rows that slipped through — a live event
# whose venue is the placeholder while the prose names a distinct real venue is
# worth a human glance (which is it — the visitor center, or Mudshark?). Source-
# agnostic: any row with the placeholder venue is checked, GLH included.
def landmark_venue_mismatch(venue: str | None, description: str | None) -> str | None:
    """Return the real venue named in the description when ``venue`` is the shared
    visitor-center placeholder but the prose names a distinct, real venue; else
    ``None``. Lazily imports the venue helpers so this module stays import-light."""
    from app.contrib.event_record import extract_venue_from_text
    from app.contrib.ingest_suppression import is_placeholder_address

    if not is_placeholder_address(venue):
        return None
    real = extract_venue_from_text(description)
    if not real:
        return None
    # Don't flag when the "real" venue is the placeholder again, or the same string.
    if is_placeholder_address(real) or real.strip().lower() == (venue or "").strip().lower():
        return None
    return real


# ── weekday-in-title mismatch ─────────────────────────────────────────────────
# A title that names a weekday ("Taco Tuesday", "Monday Night Trivia", "First
# Friday") asserts the day it happens. When the actual date falls on a DIFFERENT
# weekday, the date (or the title) is wrong — a real class of ingest slip when a
# recurring series is stamped onto the wrong occurrence. Fires only on a SINGLE,
# unambiguous weekday token: a "Mon/Wed/Fri" listing or two different day names
# names a schedule, not this date, so it's left alone.
_WEEKDAY_INDEX: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_WEEKDAY_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.IGNORECASE
)


def weekday_title_mismatch(title: str | None, event_date: Any = None) -> str | None:
    """Return a note when ``title`` names exactly one weekday that isn't the event's
    actual weekday; else ``None``. Needs a ``date``-like with ``.weekday()``
    (Mon=0…Sun=6). Multiple distinct day names → ``None`` (a recurring-schedule
    label, not a claim about this date)."""
    if not title or event_date is None or not callable(getattr(event_date, "weekday", None)):
        return None
    named = {m.group(1).lower() for m in _WEEKDAY_RE.finditer(title)}
    if len(named) != 1:
        return None
    day = next(iter(named))
    actual_idx = event_date.weekday()
    if _WEEKDAY_INDEX[day] == actual_idx:
        return None
    actual = next(k for k, v in _WEEKDAY_INDEX.items() if v == actual_idx)
    return f"title names {day.title()} but the date is a {actual.title()}"


# ── season / holiday annotation out of season ─────────────────────────────────
# A season or holiday word in the TITLE asserts a time of year. "Summer Concert"
# in December, "Halloween Bash" in July, "Christmas Market" in April — the date is
# almost certainly wrong (or the row is a stale duplicate from another season).
# Title-only + word-boundaried so a venue/series name ("Springboard", a
# "Waterfall" hike) is never caught.
_SEASON_MONTHS: dict[str, frozenset[int]] = {
    "spring": frozenset({3, 4, 5}),
    "summer": frozenset({6, 7, 8}),
    "fall": frozenset({9, 10, 11}),
    "autumn": frozenset({9, 10, 11}),
    "winter": frozenset({12, 1, 2}),
}
_SEASON_RE = re.compile(r"\b(spring|summer|fall|autumn|winter)\b", re.IGNORECASE)
_HOLIDAY_MONTHS: list[tuple[re.Pattern[str], frozenset[int]]] = [
    (re.compile(r"\b(?:halloween|trick[-\s]?or[-\s]?treat|spooktacular)\b", re.I), frozenset({10})),
    (re.compile(r"\b(?:christmas|xmas|santa|festival of (?:trees|lights))\b", re.I), frozenset({11, 12})),
    (re.compile(r"\bthanksgiving\b", re.I), frozenset({11})),
    (re.compile(r"\bnew year'?s?\b", re.I), frozenset({12, 1})),
    (re.compile(r"\bvalentine'?s?\b", re.I), frozenset({2})),
    (re.compile(r"\b(?:st\.?\s*patrick'?s?|shamrock)\b", re.I), frozenset({3})),
    (re.compile(r"\bcinco de mayo\b", re.I), frozenset({5})),
    (re.compile(r"\beaster\b", re.I), frozenset({3, 4})),
    (re.compile(r"\b(?:independence day|4th of july|fourth of july|july 4th?)\b", re.I), frozenset({7})),
    (re.compile(r"\boktoberfest\b", re.I), frozenset({9, 10})),
]


_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def season_out_of_season(title: str | None, event_date: Any = None) -> str | None:
    """Return a note when a season/holiday word in ``title`` contradicts the event's
    month; else ``None``. When the title also names the event's ACTUAL month (a
    deliberate cross-season theme like 'Christmas in July'), it is not flagged."""
    if not title or event_date is None or not isinstance(getattr(event_date, "month", None), int):
        return None
    month = event_date.month
    if re.search(rf"\b{_MONTH_NAMES[month - 1]}\b", title, re.IGNORECASE):
        return None
    m = _SEASON_RE.search(title)
    if m and month not in _SEASON_MONTHS[m.group(1).lower()]:
        return f"title says {m.group(1).title()} but the date is in month {month:02d}"
    for pat, months in _HOLIDAY_MONTHS:
        if pat.search(title) and month not in months:
            return f"title names a holiday/observance out of its season (date month {month:02d})"
    return None


# ── generic / address venue ───────────────────────────────────────────────────
# The rendered venue should be a NAMED place. A bare street address ("2144
# McCulloch Blvd N") means ingest never resolved a venue name; a contentless
# placeholder ("TBD", "Online", "Various") means there's nothing for a visitor to
# navigate to. Both warrant a review before launch. (An established DISTRICT like
# "Downtown Lake Havasu" is a real, navigable answer — not flagged.)
_GENERIC_VENUES: frozenset[str] = frozenset({
    "tbd", "tba", "n/a", "na", "none", "online", "virtual", "various",
    "various locations", "to be announced", "to be determined", "location tbd",
    "location varies", "varies", "multiple locations", "citywide",
})
_STREET_ADDRESS_RE = re.compile(
    r"^\s*\d{2,6}\s+.*\b(?:blvd|boulevard|st|street|ave|avenue|dr|drive|rd|road|"
    r"way|ln|lane|hwy|highway|ct|court|pkwy|parkway|pl|place|cir|circle|"
    r"loop|trail|terr|terrace)\b",
    re.IGNORECASE,
)


def generic_venue_reason(venue: str | None) -> str | None:
    """Return why a venue is non-navigable — a contentless placeholder or a bare
    street address — else ``None``. An empty/absent venue is a different concern
    (missing venue, checked at render) and returns ``None`` here."""
    if not venue or not venue.strip():
        return None
    v = venue.strip()
    if v.lower() in _GENERIC_VENUES:
        return f"venue {v!r} is a generic placeholder, not a named place"
    if _STREET_ADDRESS_RE.match(v):
        return f"venue {v!r} is a bare street address, not a named place"
    return None


# ── missing start time ────────────────────────────────────────────────────────
def missing_time(start_time: time | None, *, all_day: bool = False) -> bool:
    """True when an event has no start time and isn't explicitly all-day — it will
    render with a blank/'TBD' time, which reads as unfinished data."""
    return start_time is None and not all_day


# ── ALL-CAPS shouting title ───────────────────────────────────────────────────
_TITLE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'&-]*")


def is_shouting_title(title: str | None) -> bool:
    """True when a title has two or more all-caps words of length ≥4 — a formatting
    defect to normalize ('SUMMER BLOWOUT SALE'). Short acronyms/brands (USA, BMX,
    VBS) never reach the 2×length-4 bar, so 'USA BMX Race' is not flagged."""
    if not title:
        return False
    longcaps = [w for w in _TITLE_WORD_RE.findall(title) if len(w) >= 4 and w.isupper()]
    return len(longcaps) >= 2


# ── category ↔ title-keyword contradiction ────────────────────────────────────
# The complement of name↔category: a TITLE keyword naming a clearly different
# domain than the assigned category/tags. Seed case is the naive water→boating
# classifier stamping "Shark" (a themed kids event) into Boating. Kept to a tight,
# high-confidence table; matched against a lowercased "category + tags" haystack.
_KEYWORD_CATEGORY_RULES: list[tuple[re.Pattern[str], frozenset[str], str]] = [
    (re.compile(r"\bshark\b", re.I), frozenset({"boat", "marine", "watersport"}),
     "'shark' theme in a boating/marine category"),
    (re.compile(r"\b(?:yoga|pilates|zumba|spin\s+class)\b", re.I),
     frozenset({"eat", "drink", "restaurant", "bar", "brew", "retail", "shopping"}),
     "a fitness class in a food/drink/retail category"),
    (re.compile(r"\b(?:story\s?time|book\s+club)\b", re.I),
     frozenset({"boat", "marine", "nightlife", "bar"}),
     "a library/story program in an unrelated category"),
    (re.compile(r"\b(?:wine|beer|brew|cocktail|happy\s+hour|tequila|margarita)\b", re.I),
     frozenset({"kids", "family"}),
     "an alcohol-themed title in a family/kids category"),
]


def category_keyword_contradiction(title: str | None, category: str | None) -> str | None:
    """Return a note when a title keyword names a domain that contradicts the
    assigned ``category`` (a lowercased slug or 'category + tags' string); else
    ``None``. Conservative by design."""
    if not title or not category:
        return None
    slug = category.strip().lower()
    for pat, bad_tokens, note in _KEYWORD_CATEGORY_RULES:
        if pat.search(title) and any(tok in slug for tok in bad_tokens):
            return note
    return None


# ── aggregate over an event row ───────────────────────────────────────────────
@dataclass(frozen=True)
class LintFinding:
    rule: str
    detail: str


def _is_overnight(event: Any) -> bool:
    """A genuinely overnight event: an end time earlier than the start time."""
    st = getattr(event, "start_time", None)
    et = getattr(event, "end_time", None)
    return st is not None and et is not None and et < st


def lint_event(event: Any) -> list[LintFinding]:
    """Read-only lint for one event-like row (needs ``title``, ``start_time``,
    ``end_time``, ``description``, ``location_name``; ``source``/``event_url``
    gate the P&R venue rule). Returns every rule it trips."""
    findings: list[LintFinding] = []
    start_time = getattr(event, "start_time", None)
    title = getattr(event, "title", None)
    venue = getattr(event, "location_name", None)
    early_ok = is_early_activity(title, venue)
    if suspect_ampm_flip(start_time, is_overnight=_is_overnight(event), early_ok=early_ok):
        findings.append(
            LintFinding("ampm_flip", f"starts {start_time} — probable PM entered as AM")
        )
    if reads_as_venue_hours(title, getattr(event, "description", None)):
        findings.append(
            LintFinding("venue_hours_as_event", "text reads as open-hours, not a dated event")
        )
    if _is_parks_rec(event) and parks_rec_venue_unrecognized(venue):
        findings.append(
            LintFinding(
                "venue_not_facility",
                f"venue {venue!r} is not a named P&R facility — probable room/instructor in the Where",
            )
        )
    real_venue = landmark_venue_mismatch(venue, getattr(event, "description", None))
    if real_venue:
        findings.append(
            LintFinding(
                "landmark_venue_mismatch",
                f"venue is the visitor-center placeholder; description names {real_venue!r}",
            )
        )
    event_date = getattr(event, "date", None)
    wd = weekday_title_mismatch(title, event_date)
    if wd:
        findings.append(LintFinding("weekday_mismatch", wd))
    ssn = season_out_of_season(title, event_date)
    if ssn:
        findings.append(LintFinding("season_out_of_season", ssn))
    gv = generic_venue_reason(venue)
    if gv:
        findings.append(LintFinding("generic_venue", gv))
    if missing_time(start_time, all_day=bool(getattr(event, "all_day", False))):
        findings.append(LintFinding("missing_time", "no start time — add a time or mark all-day"))
    if is_shouting_title(title):
        findings.append(LintFinding("allcaps_title", "title is ALL-CAPS — normalize casing"))
    ck = category_keyword_contradiction(title, getattr(event, "category", None))
    if ck:
        findings.append(LintFinding("category_keyword_contradiction", ck))
    return findings
