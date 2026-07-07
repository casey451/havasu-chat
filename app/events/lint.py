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
    return findings
