"""Single source of user-facing department display labels (Phase 2 / IA v2).

The live taxonomy stores department names in the DB ``Category.name``. Renaming a
department *for users* does NOT require a prod-DB write: every renderer routes its
display string through :func:`display_label`, so slugs and DB rows stay untouched
(SEO and data remain stable) while the visible label changes.

Source of truth: ``docs/proposals/taxonomy_v2_build_spec.json`` → ``label_only_renames``.

Scope: this module covers **label-only** renames. The structural changes (merging
Outdoors & Recreation + Things to Do, splitting Community & Civic into City &
Government + Worship & Nonprofits, promoting Tattoo & Piercing to its own
department) are prod-DB operations handled in the gated structural slice, not here.
"""

from __future__ import annotations

# Department slug -> v2 user-facing label. Slugs absent here fall back to the live
# ``Category.name`` (i.e. unchanged: eat-and-drink, health-and-medical, and the
# departments awaiting the structural slice).
DEPARTMENT_DISPLAY_LABELS: dict[str, str] = {
    "on-the-water": "Lake & Boating",
    # Phase 2 structural: outdoors merged into this dept; slug kept (a master
    # bucket already owns 'things-to-do'), label updated for users.
    "things-to-do-and-attractions": "Things to Do",
    "family-and-education": "For Kids & Families",
    "beauty-and-personal-care": "Salons & Spas",
    "fitness-and-wellness": "Fitness & Classes",
    "pets": "Pets & Vets",
    "home-and-property-services": "Home Services",
    "auto-rv-and-marine": "Auto & Boat Service",
    "shopping-and-retail": "Shopping",
    "professional-and-financial": "Professional & Money",
    "lodging": "Places to Stay",
}


def display_label(slug: str, fallback: str = "") -> str:
    """User-facing department name for ``slug``.

    Returns the v2 override when one exists, else ``fallback`` (the live
    ``Category.name``), else a title-cased form of the slug as a last resort.
    """
    override = DEPARTMENT_DISPLAY_LABELS.get(slug)
    if override:
        return override
    return fallback or slug.replace("-", " ").title()


# Canonical names for the rendered departments that have NO override above, so a
# label-only consumer (the /map scope tabs) can resolve a final label WITHOUT a
# DB round-trip and stay byte-identical to the directory + home grid, which call
# ``display_label(slug, Category.name)``. Kept in sync with the live
# ``Category.name`` for these slugs (verified 2026-06-23).
_DEPARTMENT_BASE_LABELS: dict[str, str] = {
    "eat-and-drink": "Eat & Drink",
    "health-and-medical": "Health & Medical",
    "city-and-government": "City & Government",
    "worship-and-nonprofits": "Worship & Nonprofits",
    "tattoo": "Tattoo & Piercing",
    "events": "Events",
}


def department_label(slug: str) -> str:
    """Final user-facing label for a canonical DEPARTMENT slug, DB-free.

    Override (:data:`DEPARTMENT_DISPLAY_LABELS`) wins, else the canonical base
    name, else a title-cased slug. Equals ``display_label(slug, Category.name)``
    for every rendered department — the DB-free path used where loading the
    taxonomy would be wasteful (the /map scope tabs).
    """
    return (
        DEPARTMENT_DISPLAY_LABELS.get(slug)
        or _DEPARTMENT_BASE_LABELS.get(slug)
        or slug.replace("-", " ").title()
    )


# Phase 3.2 label unification: the /map scope selector uses the LEGACY tier-1
# slugs (routing/scope ids consumed by map.js — unchanged), but its TAB LABELS
# used to come from a separate hand-kept dict that drifted from the directory
# ("Outdoors & Recreation" vs "Things to Do", "Lake Life" vs "Lake & Boating").
# This maps each legacy scope to its canonical department so the tab reads the
# SAME label as the directory + home grid. Slugs/routes are untouched.
MAP_SCOPE_TO_DEPARTMENT: dict[str, str] = {
    "eat-drink": "eat-and-drink",
    "on-the-water": "on-the-water",
    "outdoors-parks-trails": "things-to-do-and-attractions",
    "classes-sports-recreation": "fitness-and-wellness",
    "shopping-essentials": "shopping-and-retail",
    "home-property-services": "home-and-property-services",
    "health-wellness-care": "health-and-medical",
    "auto-rv-fuel": "auto-rv-and-marine",
    "lodging-vacation-rentals": "lodging",
    "pets": "pets",
    "public-civic-resources": "city-and-government",
    "events": "events",
}


def map_scope_label(scope_slug: str) -> str:
    """Department-canonical label for a /map category scope (Phase 3.2), so the
    map tab reads identically to the directory + home grid. Falls back to a
    title-cased slug for any scope with no department mapping."""
    dept = MAP_SCOPE_TO_DEPARTMENT.get(scope_slug)
    if dept:
        return department_label(dept)
    return scope_slug.replace("-", " ").title()
