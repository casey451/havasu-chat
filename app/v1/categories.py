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

# Legacy Provider.category / Tier-1 slug hints → master bucket id.
_LEGACY_CATEGORY_TO_BUCKET: dict[str, str] = {
    "events": "events",
    "food_drink": "food-drink",
    "food": "food-drink",
    "restaurant": "food-drink",
    "bakery": "food-drink",
    "on_the_water": "recreation-outdoors",
    "outdoors_parks_trails": "recreation-outdoors",
    "classes_sports_recreation": "sports-fitness",
    "shopping_essentials": "shopping",
    "home_property_services": "services",
    "health_wellness_care": "services",
    "auto_rv_fuel": "services",
    "pets": "services",
    "public_civic_resources": "services",
    "lodging_vacation_rentals": "stay",
    "eat-drink": "food-drink",
    "on-the-water": "recreation-outdoors",
    "things-to-do": "events",
    "services": "services",
}


def bucket_for_legacy_category(category: str | None) -> str:
    if not category:
        return "services"
    key = category.strip().lower().replace(" ", "_")
    return _LEGACY_CATEGORY_TO_BUCKET.get(key, _LEGACY_CATEGORY_TO_BUCKET.get(category, "services"))
