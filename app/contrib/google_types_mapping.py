"""Google Places ``types`` array → ``(Category.slug, place_type)`` mapping.

Operator-maintainable. Unmapped types return ``(None, None)`` for Phase 5
operator-queue review. ``place_type`` is ``\"commercial\"``, ``\"place\"``,
or ``None`` when only the slug is known from the table.
"""

from __future__ import annotations

# Google primary/secondary type string → (category_slug, place_type)
_PRIMARY_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "restaurant": ("eat-drink", "commercial"),
    "cafe": ("eat-drink", "commercial"),
    "bar": ("eat-drink", "commercial"),
    "bakery": ("eat-drink", "commercial"),
    "plumber": ("home-property-services", "commercial"),
    "electrician": ("home-property-services", "commercial"),
    "hvac_contractor": ("home-property-services", "commercial"),
    "general_contractor": ("home-property-services", "commercial"),
    "doctor": ("health-wellness-care", "commercial"),
    "dentist": ("health-wellness-care", "commercial"),
    "hospital": ("health-wellness-care", "commercial"),
    "pharmacy": ("health-wellness-care", "commercial"),
    "lodging": ("lodging-vacation-rentals", "commercial"),
    "rv_park": ("lodging-vacation-rentals", "commercial"),
    "store": ("shopping-essentials", "commercial"),
    "supermarket": ("shopping-essentials", "commercial"),
    "grocery_or_supermarket": ("shopping-essentials", "commercial"),
    "gas_station": ("auto-rv-fuel", "commercial"),
    "car_repair": ("auto-rv-fuel", "commercial"),
    "car_dealer": ("auto-rv-fuel", "commercial"),
    "park": ("outdoors-parks-trails", "place"),
    "dog_park": ("outdoors-parks-trails", "place"),
    "marina": ("on-the-water", "place"),
    "beach": ("on-the-water", "place"),
    "veterinary_care": ("pets", "commercial"),
    "pet_store": ("pets", "commercial"),
    "school": ("classes-sports-recreation", "commercial"),
    "gym": ("health-wellness-care", "commercial"),
    "library": ("public-civic-resources", "place"),
    "city_hall": ("public-civic-resources", "place"),
}


def map_google_types_to_slug_and_place_type(types: list[str]) -> tuple[str | None, str | None]:
    """Map Google's ``types`` list in order (primary first) to our taxonomy.

    Returns ``(None, None)`` when nothing matches.
    """
    for t in types:
        if t in _PRIMARY_TYPE_MAP:
            return _PRIMARY_TYPE_MAP[t]
    return (None, None)
