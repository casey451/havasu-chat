"""Phase 6.4 — themed group slug → constituent Tier-1 category slugs.

Hardcoded for V1; Phase 10 may relocate the source of truth.
"""

from __future__ import annotations

THEMED_GROUPS: dict[str, list[str]] = {
    "eat-drink-group": ["eat-drink"],
    "health-fitness-group": ["health-wellness-care", "classes-sports-recreation"],
    "on-the-water-group": ["on-the-water"],
    "home-auto-group": ["home-property-services", "auto-rv-fuel", "professional-services"],
    "things-to-do-group": [
        "events",
        "outdoors-parks-trails",
        "classes-sports-recreation",
    ],
}

_GROUP_LABELS: dict[str, str] = {
    "eat-drink-group": "Eat & Drink",
    "health-fitness-group": "Health & Fitness",
    "on-the-water-group": "Lake Life",
    "home-auto-group": "Home & Auto",
    "things-to-do-group": "Things to Do",
}

_GROUP_ONE_LINERS: dict[str, str] = {
    "eat-drink-group": (
        "Restaurants, cafés, bars, and lake-side dining — curated for Lake Havasu locals."
    ),
    "health-fitness-group": (
        "Care, wellness, classes, and recreation — doctors to drop-in sports."
    ),
    "on-the-water-group": ("Marinas, launches, rentals, and everything tied to lake life."),
    "home-auto-group": (
        "Home pros, property and professional services, auto, RV, and fuel around town."
    ),
    "things-to-do-group": (
        "Events, outdoor recreation, and classes — what to do around Lake Havasu."
    ),
}

_GROUP_ACCENTS: dict[str, str] = {
    "eat-drink-group": "warm",
    "health-fitness-group": "fresh",
    "on-the-water-group": "water",
    "home-auto-group": "neutral",
    "things-to-do-group": "warm",
}


def get_categories_for_group(group_slug: str) -> list[str]:
    """Return constituent category slugs for a themed group, or empty if unknown."""
    return list(THEMED_GROUPS.get(group_slug.strip().lower(), ()))


def get_group_for_category(category_slug: str) -> str | None:
    """Return themed group slug containing ``category_slug``, if any."""
    cat = category_slug.strip().lower()
    for group_slug, cats in THEMED_GROUPS.items():
        if cat in cats:
            return group_slug
    return None


def group_label(group_slug: str) -> str:
    return _GROUP_LABELS.get(group_slug, group_slug.replace("-", " ").title())


def group_one_liner(group_slug: str) -> str:
    return _GROUP_ONE_LINERS.get(group_slug, "Browse trusted local listings.")


def group_accent(group_slug: str) -> str:
    return _GROUP_ACCENTS.get(group_slug, "neutral")


def is_themed_group_slug(slug: str) -> bool:
    return slug.strip().lower() in THEMED_GROUPS


def is_map_scope_slug(slug: str) -> bool:
    """True if slug is a Tier-1 category or a themed group."""
    s = slug.strip().lower()
    if is_themed_group_slug(s):
        return True
    from app.api.routes.category_pages import TIER_1_CATEGORY_SLUGS

    return s in TIER_1_CATEGORY_SLUGS


def resolve_map_categories(slug: str) -> list[str] | None:
    """Resolve category slug list for map/category stream scope."""
    s = slug.strip().lower()
    if is_themed_group_slug(s):
        cats = get_categories_for_group(s)
        return cats if cats else None
    from app.api.routes.category_pages import TIER_1_CATEGORY_SLUGS

    if s in TIER_1_CATEGORY_SLUGS:
        return [s]
    return None
