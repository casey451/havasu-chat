"""Seven top-level catalog buckets from the master spec (§3.9)."""

from __future__ import annotations

from typing import Final

MASTER_BUCKETS: Final[tuple[dict[str, str], ...]] = (
    {"id": "events", "label": "Events", "slug": "events"},
    {"id": "food-drink", "label": "Food & Drink", "slug": "food-drink"},
    {"id": "recreation-outdoors", "label": "Recreation & Outdoors", "slug": "recreation-outdoors"},
    {"id": "sports-fitness", "label": "Sports, Fitness & Classes", "slug": "sports-fitness"},
    {"id": "shopping", "label": "Shopping", "slug": "shopping"},
    {"id": "services", "label": "Services", "slug": "services"},
    {"id": "stay", "label": "Stay", "slug": "stay"},
)

# Master-bucket slugs (API / Browse Havasu) → public Tier-1 ``/categories/{slug}``
# pages. Shared by ``/categories/{bucket}`` and ``/lake-havasu/categories/{bucket}``.
BUCKET_SLUG_REDIRECTS: Final[dict[str, str]] = {
    "events": "/categories/things-to-do",
    "food-drink": "/categories/eat-drink",
    "recreation-outdoors": "/categories/on-the-water",
    "sports-fitness": "/categories/classes-sports-recreation",
    "shopping": "/categories/shopping-essentials",
    "services": "/categories/services",
    "stay": "/categories/lodging-vacation-rentals",
}

# Legacy ``Provider.category`` value → master bucket id.
#
# IMPORTANT: keys are the *actual* legacy category strings the catalog stores
# (``lake_recreation``, ``retail``, ``lodging``, ``fitness_sports`` …) — see
# ``CATEGORY_FILTERS`` in ``app/categories/queries.py`` and the seed data. The
# earlier version keyed on spec-style slugs (``on_the_water``,
# ``shopping_essentials`` …) that never matched a stored value, so every row fell
# through to the ``services`` default — zeroing Recreation/Sports/Shopping/Stay
# and inflating Services across the whole ``/api/v1`` surface (counts, the
# ``?category=`` business filter, and the serialized per-business bucket). This
# map mirrors the legacy→subcategory→bucket taxonomy in
# ``app/categories/subcategories.py`` so the API agrees with the public pages.
# A few Tier-1 route slugs are kept as aliases for callers that pass those.
_LEGACY_CATEGORY_TO_BUCKET: dict[str, str] = {
    # Food & Drink
    "food_drink": "food-drink",
    "food": "food-drink",
    "restaurant": "food-drink",
    "bakery": "food-drink",
    # Recreation & Outdoors
    "lake_recreation": "recreation-outdoors",
    "boat_rental": "recreation-outdoors",
    "boat_repair": "recreation-outdoors",
    "recreation": "recreation-outdoors",
    # Sports, Fitness & Classes
    "fitness_sports": "sports-fitness",
    "fitness": "sports-fitness",
    "childcare_education": "sports-fitness",
    "education": "sports-fitness",
    "edu": "sports-fitness",
    # Shopping
    "retail": "shopping",
    # Services
    "home_services": "services",
    "general_contractor": "services",
    "plumbing": "services",
    "auto": "services",
    "health_medical": "services",
    "professional_services": "services",
    "real_estate": "services",
    "insurance": "services",
    "financial": "services",
    "legal": "services",
    "pets": "services",
    "pet": "services",
    "veterinary": "services",
    "beauty_personal_care": "services",
    "religion_community": "services",
    "services": "services",
    # Stay
    "lodging": "stay",
    # Events (calendar bucket also gathers attraction/venue providers)
    "events": "events",
    "entertainment_attractions": "events",
    "tourism": "events",
    "event_venue": "events",
    # Tier-1 route-slug aliases (callers that pass a public slug).
    "eat-drink": "food-drink",
    "on-the-water": "recreation-outdoors",
    "things-to-do": "events",
}


def bucket_for_legacy_category(category: str | None) -> str:
    if not category:
        return "services"
    key = category.strip().lower().replace(" ", "_")
    return _LEGACY_CATEGORY_TO_BUCKET.get(key, _LEGACY_CATEGORY_TO_BUCKET.get(category, "services"))
