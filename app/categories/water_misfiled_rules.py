"""Rules for rows mis-shelved under the ``boat-and-watercraft-rentals`` leaf.

QA diagnostic 2026-06-12 (Phase 4): that leaf was stamped on businesses that do
not rent watercraft — detailing shops ("928DesertDetailing", "Premier
Detailing"), marine repair/sales, and even a saloon. The grab-bag of detailing
shops surfaced for "where can I rent a kayak?".

This module encodes the unambiguous corrections (detailing -> auto/marine
detailing; food/drink venues -> eat-drink) plus the Casey-approved (2026-06-12)
marine sales-vs-repair rule: rental/tour/guide-named rows stay put, supplier/
store types go to ``boat-sales``, and explicit marine-service names go to
``boat-repair-and-service``. Genuine rentals always return ``None``. Used by
``scripts/recategorize_water_misfiled.py`` (DRY-RUN by default; review the
printed change list before --apply).
"""

from __future__ import annotations

from app.contrib.name_leaf_signals import leaf_from_name

# Leaf slugs the corrections target (must exist as level-1 Category slugs).
_DETAILING_LEAF = "auto-marine-detailing"
_FOOD_DRINK_LEAF = "eat-drink"
_BOAT_SALES_LEAF = "boat-sales"
_BOAT_REPAIR_LEAF = "boat-repair-and-service"


def classify_water_misfiled_leaf(
    name: str | None,
    google_primary_category: str | None = None,
    google_categories: str | None = None,
) -> str | None:
    """Return the corrected leaf slug for a row currently shelved under
    ``boat-and-watercraft-rentals`` that clearly is not a rental, or ``None`` to
    leave it untouched.

    Detailing shops and food/drink venues are auto-corrected; marine dealers go
    to ``boat-sales`` and marine-service shops to ``boat-repair-and-service``
    (approved 2026-06-12). Any genuine rental/tour/guide returns ``None``. The
    caller is responsible for scoping to rows whose CURRENT primary leaf is
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

    # Source-parity (2026-07-03): a captained charter, guided water tour, or
    # fishing guide trapped under boat-rentals gets routed to its proper leaf via
    # the shared name-signal rules. Those two leaves (boat-tours-and-charters,
    # fishing-charters-and-guides) are otherwise unreachable for a Google-typed
    # rental row, which is the audit's core "charters are invisible" gap. Only
    # these two are moved here; genuine kayak/jet-ski/watercraft rentals still
    # fall through to the rental guard below and return None (stay put). See
    # docs/audits/2026-07/PARITY_AND_COMPLETENESS_PLAN_2026-07-03.md.
    sig = leaf_from_name(name)
    if sig in ("boat-tours-and-charters", "fishing-charters-and-guides"):
        return sig

    # --- Phase-4 judgment rows (approved 2026-06-12): marine sales vs repair ---
    # CAUTION: genuine rentals in this leaf are ALSO google "service"-typed
    # ("Tortuga Boat Rentals", "Lake Havasu Jet Ski Rentals"), so NEVER map on the
    # service type alone. Exclude rental/tour/guide names first — those stay in the
    # rentals leaf — then take sales only from supplier/store types (rentals are
    # never typed that way) and repair only on explicit marine-service name markers.
    primary = (google_primary_category or "").lower()
    rental_markers = (
        "rent", "rental", "jet ski", "jetski", "kayak", "paddle", "charter",
        "watercraft", "wave", "watersport", "tour", "guide", "valet", "concierge",
    )
    if any(mk in n for mk in rental_markers):
        return None

    # Sales: dealers/suppliers/stores (rentals are never supplier/store-typed).
    if "supplier" in primary or "store" in primary or "dealer" in primary:
        return _BOAT_SALES_LEAF

    # Repair / custom marine shops: explicit service-name markers only.
    repair_markers = (
        "marine", "repair", "fiberglass", "body shop", "rigging", "performance",
        "powersports", "motorsport", "custom", "boat works", "mechanic", "machine worx",
    )
    if any(mk in n for mk in repair_markers):
        return _BOAT_REPAIR_LEAF

    return None
