"""Name-based leaf routing for business kinds Google can't type precisely.

Google Places gives martial-arts and dance businesses generic primary types
(``gym`` / ``school`` / ``point_of_interest``), so the type-based leaf resolver
(``app/contrib/leaf_type_mapping.py`` → ``scripts/places_load._resolve_category_id``)
can't file them onto the ``martial-arts`` / ``dance-studios`` leaves — they land
on gyms / k-12-schools / kids-classes instead. This is the routing gap behind the
2026-06-17 Phase 4 re-file, where 8 already-scraped dojos/dance studios were found
misfiled.

This module routes by NAME instead, conservatively: only a confident signal maps,
everything else returns ``None`` so the caller keeps its existing type-based
resolution. It reuses ``subcategories._MARTIAL_ARTS_NAME`` (the audit's matcher)
and adds a tight dance matcher that deliberately ignores bare "dance" (so
nightlife like "Dance Club" / "Dance Hall" is NOT mis-routed) and bare
"performing arts" (ambiguous with theatres).

Known conservative miss: a dojo with no martial keyword in its name (e.g.
"Arevalo Academy") won't match — those rare cases stay on type/manual routing
rather than risk a false positive. The leaf slugs returned are asserted live by
``tests/test_name_leaf_rules.py``.
"""

from __future__ import annotations

import re

from app.categories.subcategories import _MARTIAL_ARTS_NAME

# Tight dance matcher — qualified terms only. Bare ``\bdance\b`` is intentionally
# excluded (it would catch "Dance Club" / "Dance Hall" nightlife). "performing
# arts" is excluded too (ambiguous with theatres, e.g. a community playhouse).
_DANCE_NAME = re.compile(
    r"\bballet\b|school of dance|dance (?:studio|studios|academy|center|centre)",
    re.I,
)

# Leaf slugs this module can route to (level-1 Category slugs, live on prod).
MARTIAL_ARTS_LEAF = "martial-arts"
DANCE_LEAF = "dance-studios"


def leaf_for_name(name: str | None) -> str | None:
    """A confident A.3 leaf slug for ``name`` by name signal alone, or ``None``.

    Martial arts is checked before dance (a "Martial Arts & Dance" hybrid is
    overwhelmingly a dojo). Conservative — an unmatched name returns ``None`` so
    the caller falls back to type-based routing.
    """
    if not name:
        return None
    if _MARTIAL_ARTS_NAME.search(name):
        return MARTIAL_ARTS_LEAF
    if _DANCE_NAME.search(name):
        return DANCE_LEAF
    return None
