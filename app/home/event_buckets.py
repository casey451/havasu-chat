"""Single source of truth for event/class *buckets* across the home page and
the events page (``/events-ui``).

Before Slice C the two surfaces disagreed: the events page grouped occurrences
via :data:`GROUP_DEFS` + :func:`group_for_tier`, while the home week-strip used
its own pill vocabulary. The legends, colors, and rollup nouns drifted. This
module owns the one bucket definition both surfaces consume.

Overlay model (2026-06-19, owner-approved redesign)
---------------------------------------------------
Each occurrence has exactly one **primary** bucket — the activity group it
belongs to (:func:`group_for_tier`): "Happening today" (one-off events + all-day
drop-in rec), Music & nightlife, Lake & boating, or Fitness & classes. On top of
that, **Kids & Family** is an *additive overlay*: every kid/family occurrence is
ALSO listed there (it is NOT removed from its primary group). So a parent taps
one group and sees everything for kids, while Fitness & classes still lists every
class (including the kid ones) in its type subsection. The overlay is built in
:func:`app.home.events_views.day_groups`, not here — this module only owns the
primary mapping and the shared bucket vocabulary.

* the importance-tier *vocabulary* (the ``TIER_*`` constants);
* :data:`GROUP_DEFS` — the ordered ``(key, label, icon)`` buckets, where ``key``
  drives the CSS hooks (so a single key keeps the swatch color identical on both
  surfaces);
* :data:`GROUP_NOUNS` — the rollup nouns per bucket;
* :func:`group_for_tier` — the tier→PRIMARY-bucket mapping (Kids & Family is an
  overlay layered on afterward, so this never returns ``"family"``);
* :func:`is_dropin_rec` — the "all-day / drop-in things to do" classifier
  (Open Swim, Open Play, Open Gym, …) that routes into "Happening today".
"""

from __future__ import annotations

import re

# Importance tiers (lower = more prominent). The owner-approved headline order
# is special > music/nightlife > community > water > other one-off, with the
# pool (aquatic) and recurring-class tiers ranking last.
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
#
# 2026-06-19: "Around town" + "Things to do today" are merged into one
# "Happening today" group (the stable key stays ``"events"`` so CSS swatches and
# the many tests keyed on ``data-group="events"`` keep working). It holds one-off
# events (the 4th of July ceremony, a corn-hole tournament) AND all-day drop-in
# rec (Open Swim, pickleball Open Play) — see :func:`is_dropin_rec`.
GROUP_DEFS: tuple[tuple[str, str, str], ...] = (
    ("events", "Happening today", "\U0001F39F️"),
    # "Kids & Family" is the cross-cutting OVERLAY (see module note + day_groups):
    # every kid/family occurrence is re-listed here in addition to its primary
    # group, so a parent has one place to look.
    ("family", "Kids & Family", "\U0001F9D2"),
    ("music", "Music & nightlife", "\U0001F3B6"),
    ("water", "Lake & Boating", "⛵"),
    ("classes", "Fitness & classes", "\U0001F3C3"),
)

# Rollup nouns per bucket: (singular, plural).
GROUP_NOUNS: dict[str, tuple[str, str]] = {
    "events": ("event", "events"),
    "family": ("kid-friendly", "kid-friendly"),
    "music": ("music", "music"),
    "water": ("on the water", "on the water"),
    "classes": ("class", "classes"),
}

# All-day / drop-in recreation — "show up whenever" activities that are NOT a
# scheduled class and NOT a one-off event: Open Swim, Free/Family/Rec Swim, Open
# Play (pickleball), Open Gym, Open Skate, Public Skate, Open Pool. These route
# into "Happening today" (things-to-do), never the Fitness class list. Word-
# boundary matched. "Open MAT" is deliberately excluded — that is jiu-jitsu and
# must stay in Martial Arts (see app.home.events_views._CLASS_SUBGROUPS).
_DROPIN_REC_RE = re.compile(
    r"\b("
    r"open\s+swim|free\s+swim|family\s+swim|rec(?:reational)?\s+swim|public\s+swim|"
    r"open\s+play|open\s+gym|open\s+skate|public\s+skate|open\s+pool|open\s+rec"
    r")\b",
    re.IGNORECASE,
)


def is_dropin_rec(title: str | None) -> bool:
    """True for all-day / drop-in rec (Open Swim, Open Play, …) — routes to the
    "Happening today" group rather than Fitness & classes. Excludes "Open Mat"."""
    return bool(title) and bool(_DROPIN_REC_RE.search(title))


def group_for_tier(
    tier: int, *, recurring: bool, title: str = "", tags: list[str] | None = None
) -> str:
    """Map an (importance tier, recurring?) pair to its PRIMARY bucket ``key``.

    Kids & Family is no longer returned here — it is an additive overlay built in
    :func:`app.home.events_views.day_groups` (a kid occurrence keeps this primary
    home AND is re-listed under Kids & Family). Drop-in rec (Open Swim, Open Play)
    routes to "Happening today" before the class/water checks so it never lands in
    the Fitness list or the lake group.
    """
    if is_dropin_rec(title):
        return "events"
    if recurring or tier in (TIER_CLASS, TIER_AQUATIC):
        return "classes"
    if tier == TIER_MUSIC:
        return "music"
    if tier == TIER_WATER:
        return "water"
    return "events"
