"""Single source of truth for event/class *buckets* across the home page and
the events page (``/events-ui``).

Before Slice C the two surfaces disagreed: the events page grouped occurrences
via :data:`GROUP_DEFS` + :func:`group_for_tier`, while the home week-strip used
its own pill vocabulary (Special / Lake & Boating / Music / Community / Class)
in :mod:`app.home.sandstone`. The legends, colors, and rollup nouns drifted.

This module owns the one bucket definition both surfaces consume:

* the importance-tier *vocabulary* (the ``TIER_*`` constants) — the keyword
  classifier that turns a title into a tier (``_event_tier``) still lives in
  :mod:`app.home.sandstone`, which imports these constants;
* :data:`GROUP_DEFS` — the ordered ``(key, label, icon)`` buckets, where ``key``
  drives the CSS hooks (``ev-acc-swatch--KEY`` on the events page and
  ``wev KEY`` / ``leg KEY`` on the home strip), so a single key keeps the swatch
  color identical on both surfaces;
* :data:`GROUP_NOUNS` — the rollup nouns per bucket;
* :func:`group_for_tier` — the tier→bucket mapping.

Keeping these here breaks what would otherwise be a circular import: the home
strip (sandstone) needs the bucket mapping, and the events page (events_views)
needs the keyword classifier that lives in sandstone.
"""

from __future__ import annotations

import re

# Importance tiers (lower = more prominent). The owner-approved headline order
# is special > music/nightlife > community > water > other one-off, with the
# pool (aquatic) and recurring-class tiers ranking last. These are the canonical
# definitions; :mod:`app.home.sandstone` imports them (re-exported there under
# the historical ``_TIER_*`` names that tests reference).
(
    TIER_SPECIAL,
    TIER_MUSIC,
    TIER_COMMUNITY,
    TIER_WATER,
    TIER_OTHER,
    TIER_AQUATIC,
    TIER_CLASS,
) = range(7)

# The one bucket set, in the owner-approved display order: (key, label, icon).
# ``key`` is the stable CSS/JSON hook (never user-visible); ``label`` is the
# display name shown in the events-page accordions and the home-strip legend.
GROUP_DEFS: tuple[tuple[str, str, str], ...] = (
    # "Around town": the catch-all one-off group (special / untyped). Civic items
    # used to land here; they now have their own "City & Government" bucket below.
    ("events", "Happening today", "\U0001F39F️"),
    # "Kids & Family" is a cross-cutting collector (see group_for_tier): every
    # kid/family occurrence — youth classes, Open Swim, story time — lands here
    # so a parent sees everything for kids in one place.
    ("family", "Kids & Family", "\U0001F9D2"),
    # "Seniors" is also a cross-cutting OVERLAY (2026-06-19): every senior-tagged
    # occurrence (the Senior Center activities, community lunch, special events)
    # is re-listed here in addition to its primary group. Built in day_groups.
    ("seniors", "Seniors", "\U0001F9D3"),
    # "City & Government" (P1): council/board/commission meetings, public
    # hearings, and other civic-government items — a "need to know" group, kept
    # out of the leisure-oriented "Happening today" list. Routed by is_civic.
    ("civic", "City & Government", "\U0001F3DB️"),
    ("music", "Music & nightlife", "\U0001F3B6"),
    ("water", "Lake & Boating", "⛵"),
    # Pool activities fold into Kids & Family (open/family swim) or Fitness &
    # classes (lap swim, water aerobics, aqua zumba) — no separate pool group.
    # "Fitness & sports" (renamed from "Fitness & classes" — most of the calendar's
    # recurring items are sports, not instructional classes; Casey 2026-06-24).
    # Key stays "classes" so CSS hooks / rollup-noun mapping don't churn.
    ("classes", "Fitness & sports", "\U0001F3C3"),
)

# Rollup nouns per bucket: (singular, plural). Several read naturally in
# uncounted-noun style ("1 music", "3 on the water", "2 kid-friendly").
GROUP_NOUNS: dict[str, tuple[str, str]] = {
    "events": ("event", "events"),
    "family": ("kid-friendly", "kid-friendly"),
    "seniors": ("senior activity", "senior activities"),
    "civic": ("city meeting", "city meetings"),
    "music": ("music", "music"),
    "water": ("on the water", "on the water"),
    "classes": ("class", "classes"),
}


# All-day / drop-in recreation (Open Swim, Open Play, Open Gym, …) — NOT a
# scheduled class and NOT a one-off event. Routes into "Happening today". Word-
# boundary matched. "Open MAT" is excluded (that is jiu-jitsu -> Martial Arts).
_DROPIN_REC_RE = re.compile(
    r"\b("
    r"open\s+swim|free\s+swim|family\s+swim|rec(?:reational)?\s+swim|public\s+swim|"
    r"open\s+play|open\s+gym|open\s+skate|public\s+skate|open\s+pool|open\s+rec"
    r")\b",
    re.IGNORECASE,
)


def is_dropin_rec(title: str | None) -> bool:
    """True for all-day / drop-in rec — routes to "Happening today", not the
    Fitness class list. Excludes "Open Mat" (jiu-jitsu)."""
    return bool(title) and bool(_DROPIN_REC_RE.search(title))


# Civic / government items: council/board/commission meetings, public hearings,
# city/town hall business. The taxonomy source of truth (P1) — both the events
# bucket routing below AND the importance-tier classifier in
# :mod:`app.home.sandstone` consume :func:`is_civic` so the keyword list lives in
# exactly one place. Word-boundary matched (with an optional plural/gerund tail)
# so "dj" inside "aDJustment" can't mis-route a Board of Adjustment to music.
_CIVIC_HINTS = (
    "civic", "government", "city council", "council", "commission",
    "board of adjustment", "school board", "board meeting", "public hearing",
    "city hall", "town hall", "planning and zoning", "city manager",
)
_CIVIC_RE = re.compile(
    "|".join(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b" for h in _CIVIC_HINTS),
    re.IGNORECASE,
)


def is_civic(title: str | None, tags: list[str] | None = None) -> bool:
    """True for a council/board/commission/public-hearing civic item. The civic
    scrapers already tag these rows ("civic", "government", "meeting"), so the
    tag words alone route them; the title hints catch untagged sources."""
    joined = (title or "") + " " + " ".join(tags or [])
    return bool(_CIVIC_RE.search(joined))


def group_for_tier(
    tier: int, *, recurring: bool, title: str = "", tags: list[str] | None = None
) -> str:
    """Map an (importance tier, recurring?) pair to its PRIMARY bucket ``key``.

    Kids & Family and Seniors are additive OVERLAYS built in
    :func:`app.home.events_views.day_groups` (an occurrence keeps this primary
    home AND is re-listed under the overlay), so this never returns "family" or
    "seniors". Drop-in rec (Open Swim, Open Play) routes to "Happening today"
    before the class/water checks so it never lands in the Fitness list.
    """
    if is_dropin_rec(title):
        return "events"
    # Civic items go to "City & Government" BEFORE the recurring/class check so a
    # regularly-scheduled council meeting can't be swept into the Fitness list.
    if is_civic(title, tags):
        return "civic"
    # Event-vs-class gate (2026-06-23): a one-off item from the event feed carries
    # the ``events`` source tag; it is a happening, never a fitness/pool class —
    # even if a loose keyword tripped the class/aquatic tier (live: "Splash Bash!
    # Red, White & Blue" and "HEAT Hotel Stars, Stripes & Splashes" landed in
    # "Other classes" because "splash" reads aquatic). Genuine classes come from
    # the class/program ingest (tags ``aquatics``/``sports``/``food``/…), never
    # ``events``, so this routes the real one-offs to "Happening today" without
    # pulling any actual class out of the Fitness list.
    if tier in (TIER_CLASS, TIER_AQUATIC) and tags and "events" in {
        str(t).strip().lower() for t in tags
    }:
        return "events"
    # Genuine fitness/aquatic classes — the only tiers that belong in the Fitness
    # & classes list.
    if tier in (TIER_CLASS, TIER_AQUATIC):
        return "classes"
    # Typed leisure tiers route by TIER even when the item recurs. A WEEKLY Open
    # Mic / Karaoke / Live Music / Comedy night is music; a weekly lake event is
    # on the water; a weekly Bingo / Trivia / market is a community "Happening
    # today" item — none of these are fitness classes. (The bare ``recurring``
    # flag used to short-circuit to "classes" here, sweeping every recurring
    # venue-social event into Fitness & classes — the calendar mis-routing this
    # fixes. ``_event_tier`` already maps a recurring item with NO stronger
    # keyword to TIER_CLASS, so genuine generic classes still land above.)
    if tier == TIER_MUSIC:
        return "music"
    if tier == TIER_WATER:
        return "water"
    if tier == TIER_COMMUNITY:
        return "events"
    # A recurring item with no stronger tier reads as an ongoing class (defensive:
    # ``_event_tier`` normally encodes this as TIER_CLASS already).
    if recurring:
        return "classes"
    return "events"
