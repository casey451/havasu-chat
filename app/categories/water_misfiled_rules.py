"""Rules for rows mis-shelved under the ``boat-and-watercraft-rentals`` leaf.

QA diagnostic 2026-06-12 (Phase 4): that leaf was stamped on businesses that do
not rent watercraft — detailing shops ("928DesertDetailing", "Premier
Detailing"), marine repair/sales, and even a saloon. The grab-bag of detailing
shops surfaced for "where can I rent a kayak?".

This module encodes only the **unambiguous** corrections (detailing -> auto/marine
detailing; food/drink venues -> eat-drink). Marine repair vs sales is a judgment
call Casey makes per row, so those return ``None`` here and are left untouched —
mirroring ``health_beauty_leaf_rules`` ("minimal blast radius"). Used by
``scripts/recategorize_water_misfiled.py`` (DRY-RUN by default).
"""

from __future__ import annotations

# Leaf slugs the corrections target (must exist as level-1 Category slugs).
_DETAILING_LEAF = "auto-marine-detailing"
_FOOD_DRINK_LEAF = "eat-drink"


def classify_water_misfiled_leaf(
    name: str | None,
    google_primary_category: str | None = None,
    google_categories: str | None = None,
) -> str | None:
    """Return the corrected leaf slug for a row currently shelved under
    ``boat-and-watercraft-rentals`` that clearly is not a rental, or ``None`` to
    leave it untouched.

    Conservative by design: only detailing shops and food/drink venues are
    auto-corrected. Marine repair / sales / suppliers return ``None`` (Casey
    decides sales vs repair per row), and any genuine rental returns ``None``.
    The caller is responsible for scoping to rows whose CURRENT primary leaf is
    ``boat-and-watercraft-rentals`` so this never touches an already-correct row.
    """
    n = (name or "").lower()

    # Detailing / wash / ceramic-coating shops -> auto-marine-detailing.
    if "detail" in n:
        return _DETAILING_LEAF

    # Food / drink venues mis-shelved as boat rentals -> eat-drink.
    food_markers = ("saloon", "tavern", "grill", "brewery", "cantina", "taqueria")
    if any(mk in n for mk in food_markers):
        return _FOOD_DRINK_LEAF
    # " bar" as a word (avoid "barrett", "barber") — trailing or standalone token.
    if n.endswith(" bar") or " bar " in n or " bar & " in n:
        return _FOOD_DRINK_LEAF

    return None
