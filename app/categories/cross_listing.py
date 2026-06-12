"""Curated hybrid-venue cross-listings (manual; no schema change).

A leaf page lists entities whose **primary** ``entity_categories`` link is the
leaf. A genuine hybrid — a pizza place that is ALSO an arcade ("The Spot"), a
bowling alley with a pub — can hold only ONE primary leaf, so it vanishes from
the other surface. This map additively surfaces a specific entity on a
**secondary** leaf without touching its primary link.

Why not just render the non-primary ``entity_categories`` rows? Because the A.3
migration left every entity's OLD pre-migration category as a stale
``is_primary=False`` row; rendering those would resurface entities on the wrong
leaves. A curated, explicit map is the safe alternative.

Keyed by the surviving entity's stable ``Entity.slug`` so a cross-listing
survives re-scrapes. **Empty by default** — populate after the duplicate-cluster
cleanup picks the surviving entity for each hybrid, then add the slug here.
"""

from __future__ import annotations

# leaf slug -> entity slugs to ADDITIONALLY surface on that leaf's page.
#
# "The Spot" is a genuine hybrid: its primary leaf is `restaurants` (so it owns
# one primary `entity_categories` link there), but it is also an arcade. This
# surfaces it on the arcade leaf too, without touching its restaurants primary.
# Keyed to the `the-spot` entity (Casey's 2026-06-12 straggler keep-decision:
# the richer twin — 712 Google reviews + photos — over the duplicate
# `the-spot-pizza-arcade-more`, which was deactivated).
CROSS_LISTED_ENTITY_SLUGS: dict[str, frozenset[str]] = {
    "family-fun-and-arcades": frozenset({"the-spot"}),
}


def cross_listed_slugs_for_leaf(leaf_slug: str | None) -> frozenset[str]:
    """Entity slugs to additionally surface on ``leaf_slug`` (empty if none)."""
    if not leaf_slug:
        return frozenset()
    return CROSS_LISTED_ENTITY_SLUGS.get(leaf_slug.strip().lower(), frozenset())
