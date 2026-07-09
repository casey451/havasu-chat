"""Google Places type → A.3 directory **leaf** slug (single source of truth).

The live category surface is the A.3 department/leaf tree (level-0 department →
level-1 leaf, rendered by ``app/categories/leaf_pages.py``). This module maps a
Google Places ``types[]`` array straight to the correct **leaf slug** so a
freshly scraped business auto-files onto the right leaf page on ingest —
replacing the one-time, hand/LLM-built ``docs/proposals/A-migration-PROD-final.csv``
whose divergent mapping filed annual *events* (``event_venue``) under
*Family Fun & Arcades* (the 2026-06-11 misfile Casey reported).

It returns two things:

* ``leaf_slug`` — an A.3 level-1 leaf slug, or ``None`` when there is no
  *confident* leaf match. ``None`` means "let the caller fall back to the legacy
  13-category resolver"; this module never guesses an ambiguous bucket.
* ``non_directory`` — ``True`` for calendar-event venue types (``event_venue``
  and banquet/wedding halls) that must **never** be filed onto a directory leaf.
  Those belong to the events calendar feed (``entity_type='event'``). This is
  the guardrail that stops the event→arcade class of misfile at ingest time.

Design rules:

* **Directory types always win over the guardrail.** A restaurant that also
  carries a secondary ``event_venue`` type files as ``restaurants``; only a row
  whose types resolve to *no* directory leaf AND carry an event-venue type is
  treated as non-directory.
* **Conservative.** Only unambiguous types are mapped. Ambiguous ones
  (``hospital``, ``home_goods_store``, ``locksmith`` …) return ``(None, False)``
  and keep the existing behavior — adding a wrong mapping would create a *new*
  misfile, which is worse than leaving a type on the legacy resolver.
* **Exact-token match.** Types are matched whole (``"school"`` ≠
  ``"driving_school"``), checked primary-first, first hit wins.

Every leaf slug in :data:`_TYPE_TO_LEAF` is asserted against
``docs/proposals/taxonomy-seed.json`` by ``tests/test_leaf_type_mapping.py`` so a
typo or a renamed leaf fails CI instead of silently routing to nowhere.

Per Casey's 2026-06-11 decision: bowling alleys / arcades / trampoline parks /
indoor play are **directory venues** under ``family-fun-and-arcades``; only true
calendar events (Buses by the Bridge, Desert Storm) go to the events feed.
"""

from __future__ import annotations

# Calendar-event venue types — never a directory leaf. A row whose types resolve
# to no directory leaf but include one of these is routed to the events feed
# (entity_type='event') rather than dropped onto Family Fun & Arcades.
NON_DIRECTORY_TYPES: frozenset[str] = frozenset(
    {
        "event_venue",
        "banquet_hall",
        "wedding_venue",
    }
)

# Google Places type → A.3 leaf slug. Conservative: only unambiguous types.
_TYPE_TO_LEAF: dict[str, str] = {
    # -- Eat & Drink --
    "restaurant": "restaurants",
    "american_restaurant": "restaurants",
    "pizza_restaurant": "restaurants",
    "seafood_restaurant": "restaurants",
    "mexican_restaurant": "restaurants",
    "italian_restaurant": "restaurants",
    "breakfast_restaurant": "restaurants",
    "barbecue_restaurant": "restaurants",
    "diner": "restaurants",
    "bar": "bars-and-breweries",
    "wine_bar": "bars-and-breweries",
    "pub": "bars-and-breweries",
    "brewery": "bars-and-breweries",
    "bakery": "bakeries-and-desserts",
    "dessert_shop": "bakeries-and-desserts",
    "ice_cream_shop": "bakeries-and-desserts",
    "cafe": "cafes-and-coffee",
    "coffee_shop": "cafes-and-coffee",
    "meal_takeaway": "quick-bites-and-takeout",
    "meal_delivery": "quick-bites-and-takeout",
    "fast_food_restaurant": "quick-bites-and-takeout",
    # -- On the Water --
    "marina": "marinas-and-launch-ramps",
    "harbor": "marinas-and-launch-ramps",
    "beach": "beaches-and-swim-areas",
    "boat_rental": "boat-and-watercraft-rentals",
    "boat_dealer": "boat-sales",
    # -- Outdoors & Recreation --
    "park": "parks-and-playgrounds",
    "dog_park": "dog-parks",
    "golf_course": "golf-courses",
    # -- Things to Do & Attractions (the reported family) --
    # Casey 2026-06-11: bowling / arcades / trampoline / indoor play are
    # directory venues here, NOT events-feed entries.
    "bowling_alley": "family-fun-and-arcades",
    "amusement_arcade": "family-fun-and-arcades",
    "video_arcade": "family-fun-and-arcades",
    "amusement_park": "family-fun-and-arcades",
    "amusement_center": "family-fun-and-arcades",
    "indoor_playground": "family-fun-and-arcades",
    "trampoline_park": "family-fun-and-arcades",
    "museum": "museums-and-galleries",
    "art_gallery": "museums-and-galleries",
    "movie_theater": "theaters-and-cinema",
    "performing_arts_theater": "theaters-and-cinema",
    "casino": "casinos-and-gaming",
    "tour_agency": "tours-and-sightseeing",
    # -- Health & Medical --
    "doctor": "primary-care",
    "pediatrician": "primary-care",
    "dentist": "dentists-and-orthodontists",
    "orthodontist": "dentists-and-orthodontists",
    "pharmacy": "pharmacies",
    "chiropractor": "chiropractic",
    "physiotherapist": "physical-therapy",
    "optometrist": "eye-care",
    "dermatologist": "dermatology-and-skin",
    "psychologist": "mental-and-behavioral-health",
    # -- Fitness & Wellness --
    "gym": "gyms-and-fitness-centers",
    "fitness_center": "gyms-and-fitness-centers",
    "yoga_studio": "yoga-and-pilates",
    # -- Pets --
    "veterinary_care": "veterinarians",
    "pet_store": "pet-stores-and-supplies",
    "pet_supply_store": "pet-stores-and-supplies",
    "aquarium_store": "pet-stores-and-supplies",
    "dog_groomer": "grooming",
    "pet_boarding": "boarding-and-daycare",
    "dog_trainer": "training",
    # -- Home & Property Services --
    "plumber": "plumbing",
    "electrician": "electrical",
    "hvac_contractor": "hvac",
    "general_contractor": "general-contractors",
    "roofing_contractor": "roofing",
    "moving_company": "movers",
    "lawn_care_service": "landscaping-and-lawn",
    "pest_control_service": "pest-control",
    "cleaning_service": "cleaning",
    # -- Auto, RV & Marine --
    "car_repair": "auto-repair",
    "car_dealer": "car-dealerships",
    "gas_station": "gas-stations",
    "car_wash": "car-wash",
    "oil_change_service": "auto-repair",
    "tire_shop": "tires",
    "auto_parts_store": "auto-parts",
    "motorcycle_dealer": "powersports-and-atv",
    "rv_repair": "rv-sales-and-service",
    # -- Shopping & Retail --
    "supermarket": "grocery-and-markets",
    "grocery_store": "grocery-and-markets",
    "grocery_or_supermarket": "grocery-and-markets",
    "clothing_store": "clothing-and-apparel",
    "electronics_store": "appliances-and-electronics",
    "hardware_store": "hardware-and-home-improvement",
    "convenience_store": "convenience",
    "furniture_store": "furniture-and-mattress",
    "jewelry_store": "jewelry",
    "shoe_store": "shoes",
    "sporting_goods_store": "sporting-goods",
    "florist": "florists",
    # -- Professional & Financial --
    "accounting": "accountants-and-tax",
    "insurance_agency": "insurance",
    "real_estate_agency": "real-estate",
    "lawyer": "attorneys",
    "bank": "banks-and-credit-unions",
    # -- Family & Education --
    "preschool": "preschools-and-childcare",
    "child_care_agency": "preschools-and-childcare",
    "primary_school": "k-12-schools",
    "secondary_school": "k-12-schools",
    "school": "k-12-schools",
    "music_school": "music-lessons",
    "university": "colleges-and-higher-ed",
    # -- Community & Civic --
    "library": "libraries",
    "city_hall": "government-and-mvd",
    "local_government_office": "government-and-mvd",
    "church": "places-of-worship",
    "place_of_worship": "places-of-worship",
    "post_office": "post-office",
    # -- Lodging --
    "hotel": "hotels-and-motels",
    "motel": "hotels-and-motels",
    "resort_hotel": "hotels-and-motels",
    "extended_stay_hotel": "hotels-and-motels",
    "bed_and_breakfast": "hotels-and-motels",
    "lodging": "hotels-and-motels",
    "rv_park": "rv-parks-and-campgrounds",
    "campground": "rv-parks-and-campgrounds",
    "camping_cabin": "rv-parks-and-campgrounds",
}


def _leaf_for_primary(tok: str) -> str | None:
    """Leaf slug for a single PRIMARY google type, or ``None``."""
    slug = _TYPE_TO_LEAF.get(tok)
    if slug is not None:
        return slug
    # Any specific "<style>_restaurant" primary is a restaurant (taco_restaurant,
    # hamburger_restaurant, sushi_restaurant …). Dict hits above take precedence,
    # so fast_food_restaurant still routes to quick-bites-and-takeout.
    if tok.endswith("_restaurant"):
        return "restaurants"
    return None


def map_google_types_to_leaf_slug(
    types: list[str] | tuple[str, ...] | None,
) -> tuple[str | None, bool]:
    """Map a Google ``types[]`` array to ``(leaf_slug, non_directory)``.

    **PRIMARY TYPE ONLY** — only the first (authoritative primary) type is used.
    Secondary google types are too noisy for leaf-level precision: a department
    store lists ``shoe_store``/``jewelry_store``/``clothing_store``, a thrift
    shop lists a dozen product types, so matching *any* token in the array
    produced wrong leaves (the 2026-06-12 backfill incident: Dillard's → shoes,
    a book exchange → jewelry). An unmapped primary returns ``(None, False)`` so
    the caller keeps the existing/legacy assignment rather than guessing from a
    secondary token.

    * ``(slug, False)`` — confident A.3 leaf from the primary type.
    * ``(None, True)``  — primary is a calendar-event venue (``event_venue`` …);
      caller must NOT assign a directory category (route to the events feed).
    * ``(None, False)`` — no confident primary match; fall back to legacy.
    """
    toks = [str(t).strip().lower() for t in (types or []) if t]
    if not toks:
        return None, False
    primary = toks[0]
    slug = _leaf_for_primary(primary)
    if slug is not None:
        return slug, False
    if primary in NON_DIRECTORY_TYPES:
        return None, True
    return None, False
