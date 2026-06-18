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

from app.events.family_filter import is_family_event

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
    # "Around town": the catch-all one-off group (special / community / untyped).
    ("events", "Around town", "\U0001F39F️"),
    # "Kids & Family" is a cross-cutting collector (see group_for_tier): every
    # kid/family occurrence — youth classes, Open Swim, story time — lands here
    # so a parent sees everything for kids in one place.
    ("family", "Kids & Family", "\U0001F9D2"),
    ("music", "Music & nightlife", "\U0001F3B6"),
    ("water", "Lake & Boating", "⛵"),
    # Pool activities fold into Kids & Family (open/family swim) or Fitness &
    # classes (lap swim, water aerobics, aqua zumba) — no separate pool group.
    ("classes", "Fitness & classes", "\U0001F3C3"),
)

# Rollup nouns per bucket: (singular, plural). Several read naturally in
# uncounted-noun style ("1 music", "3 on the water", "2 kid-friendly").
GROUP_NOUNS: dict[str, tuple[str, str]] = {
    "events": ("event", "events"),
    "family": ("kid-friendly", "kid-friendly"),
    "music": ("music", "music"),
    "water": ("on the water", "on the water"),
    "classes": ("class", "classes"),
}


def group_for_tier(
    tier: int, *, recurring: bool, title: str = "", tags: list[str] | None = None
) -> str:
    """Map an (importance tier, recurring?) pair to its bucket ``key``.

    Kids & Family is a cross-cutting overlay: any kid/family occurrence (a youth
    class, Open Swim, story time) collects here instead of its activity group so
    a parent has one place to look. Big one-off SPECIAL events stay in their
    marquee group (they headline the day) — everything else defers to the family
    collector first. Pool sessions fold into classes (open/family swim is caught
    by the family overlay above).
    """
    if tier != TIER_SPECIAL and is_family_event(title, tags):
        return "family"
    if recurring or tier in (TIER_CLASS, TIER_AQUATIC):
        return "classes"
    if tier == TIER_MUSIC:
        return "music"
    if tier == TIER_WATER:
        return "water"
    return "events"
