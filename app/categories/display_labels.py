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
