"""WS6 — event/data quality lint (read-only detectors).

Pure rules that FLAG suspicious rows for the review queue; they never mutate
data. Each is the machine-checkable form of a real 2026-07-06 audit defect
(spec §14.3 / §6.3):

  * AM/PM flip — an event starting 12 AM–7 AM at a normal venue is almost always
    a PM time typed as AM ("Glow in the Dark Painting" at 5:30 AM).
  * venue-hours-as-event — a row whose text reads as open-hours, not a dated
    occurrence ("Golf Course — Bridgewater Links · Open daily", "Open 24/7").
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
# The suspicious pre-dawn window. Real events do start before 7 AM (sunrise yoga,
# a fishing tournament), so this only FLAGS for review — it never rewrites a time.
_EARLY_START = time(0, 0)
_EARLY_END = time(7, 0)


def suspect_ampm_flip(
    start_time: time | None, *, venue_is_24h: bool = False, is_overnight: bool = False
) -> bool:
    """True when ``start_time`` is in [12:00 AM, 7:00 AM) at a venue that isn't
    24-hour and the event doesn't legitimately run overnight."""
    if start_time is None or venue_is_24h or is_overnight:
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
    ``end_time``, ``description``). Returns every rule it trips."""
    findings: list[LintFinding] = []
    start_time = getattr(event, "start_time", None)
    if suspect_ampm_flip(start_time, is_overnight=_is_overnight(event)):
        findings.append(
            LintFinding("ampm_flip", f"starts {start_time} — probable PM entered as AM")
        )
    if reads_as_venue_hours(getattr(event, "title", None), getattr(event, "description", None)):
        findings.append(
            LintFinding("venue_hours_as_event", "text reads as open-hours, not a dated event")
        )
    return findings
