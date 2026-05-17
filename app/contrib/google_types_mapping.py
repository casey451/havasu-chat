"""Google Places ``types`` array → ``(Category.slug, place_type)`` mapping.

Operator-maintainable. Unmapped types return ``(None, None)`` for Phase 5
operator-queue review. ``place_type`` is ``\"commercial\"``, ``\"place\"``,
or ``None`` when only the slug is known from the table.

Phase 5 expansion (2026-05-13): types[] coverage extended for the 6 Tier 1
categories per ``outputs/cursor_brief_phase_5_tier_1_data.md`` §3.1-§3.6.
``hair_salon`` / ``beauty_salon`` / ``nail_salon`` explicitly map to
``(None, None)`` so they route to the operator-queue rather than getting
absorbed into the wrong category — implements the Phase 5 prereq §3.1.a
lock ("skip beauty_personal_care in Phase 5; revisit V1.5").
"""

from __future__ import annotations

# Google primary/secondary type string → (category_slug, place_type).
# Organized by Tier 1 category in the order recommended at brief §9
# starting-sequence. Tier 2/3 entries follow at the end.
_PRIMARY_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    # Tier 1.1 — Eat & Drink (brief §3.1)
    "restaurant": ("eat-drink", "commercial"),
    "cafe": ("eat-drink", "commercial"),
    "bar": ("eat-drink", "commercial"),
    "bakery": ("eat-drink", "commercial"),
    "meal_delivery": ("eat-drink", "commercial"),
    "meal_takeaway": ("eat-drink", "commercial"),
    "fast_food_restaurant": ("eat-drink", "commercial"),
    "dessert_shop": ("eat-drink", "commercial"),
    "wine_bar": ("eat-drink", "commercial"),
    "pub": ("eat-drink", "commercial"),
    "pizza_restaurant": ("eat-drink", "commercial"),
    "seafood_restaurant": ("eat-drink", "commercial"),
    "mexican_restaurant": ("eat-drink", "commercial"),
    "breakfast_restaurant": ("eat-drink", "commercial"),
    "barbecue_restaurant": ("eat-drink", "commercial"),
    "coffee_shop": ("eat-drink", "commercial"),
    "ice_cream_shop": ("eat-drink", "commercial"),

    # Tier 1.2 — On the Water (brief §3.2). marinas/beaches are places;
    # dealers/rentals are commercial — Google's types[] doesn't always
    # disambiguate, so the to_entity_payload caller may override
    # place_type when the venue name signals dealer-vs-marina.
    "marina": ("on-the-water", "place"),
    "beach": ("on-the-water", "place"),
    "harbor": ("on-the-water", "place"),
    "boat_dealer": ("on-the-water", "commercial"),
    "boat_rental": ("on-the-water", "commercial"),
    # Phase 5.2 §1 Layer 1 load surfaced two more Google primary types
    # that are unambiguously on-the-water but had been routing to the
    # operator queue (category_id=None). Added 2026-05-15 — the load
    # produced 0 ferry_service + 0 fishing_pier post-this-extension
    # because the few in the bbox already loaded with category_id=None;
    # operator runs apply_on_the_water_promote_unmapped.py to backfill,
    # then this extension catches future loads automatically.
    "fishing_pier": ("on-the-water", "place"),
    "ferry_service": ("on-the-water", "commercial"),

    # Tier 1.3 — Home & Property Services (brief §3.3)
    "plumber": ("home-property-services", "commercial"),
    "electrician": ("home-property-services", "commercial"),
    "hvac_contractor": ("home-property-services", "commercial"),
    "general_contractor": ("home-property-services", "commercial"),
    "roofing_contractor": ("home-property-services", "commercial"),
    "painter": ("home-property-services", "commercial"),
    "locksmith": ("home-property-services", "commercial"),
    "moving_company": ("home-property-services", "commercial"),
    "storage": ("home-property-services", "commercial"),
    "lawn_care_service": ("home-property-services", "commercial"),
    "home_inspection": ("home-property-services", "commercial"),
    "pest_control_service": ("home-property-services", "commercial"),
    "cleaning_service": ("home-property-services", "commercial"),
    "appliance_repair": ("home-property-services", "commercial"),

    # Tier 1.4 — Health, Wellness & Care (brief §3.4)
    "doctor": ("health-wellness-care", "commercial"),
    "dentist": ("health-wellness-care", "commercial"),
    "hospital": ("health-wellness-care", "commercial"),
    "pharmacy": ("health-wellness-care", "commercial"),
    "gym": ("health-wellness-care", "commercial"),
    "physiotherapist": ("health-wellness-care", "commercial"),
    "chiropractor": ("health-wellness-care", "commercial"),
    "optometrist": ("health-wellness-care", "commercial"),
    "orthodontist": ("health-wellness-care", "commercial"),
    "pediatrician": ("health-wellness-care", "commercial"),
    "psychologist": ("health-wellness-care", "commercial"),
    "dermatologist": ("health-wellness-care", "commercial"),
    "medical_lab": ("health-wellness-care", "commercial"),
    "home_health_care_service": ("health-wellness-care", "commercial"),
    # ``medical_clinic`` widening (Phase 5.7 §1 sustainability commit;
    # closes the V1.5 carry-over flagged in 5.4 + 5.6 close-outs §3).
    # Pre-5.7, ``medical_clinic`` resolved only via the
    # ``(medical_clinic, "health_medical")`` entry in
    # ``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK`` — which works
    # when the discovery domain IS ``health_medical``, but fails when a
    # medical_clinic primary_type surfaces under a different discovery
    # domain (5.6 §4 caught two eye-care providers — Lake Havasu Family
    # Eyecare + Barnet Dulaney Perkins — that landed in shopping-
    # essentials via the ``(None, "retail")`` catch-all because their
    # ``medical_clinic`` type wasn't in _PRIMARY_TYPE_MAP directly).
    # Adding the direct mapping catches them regardless of discovery
    # domain.
    "medical_clinic": ("health-wellness-care", "commercial"),

    # Tier 1.5 — Auto, RV & Fuel (brief §3.5). `rv_park` stays in
    # `lodging-vacation-rentals` per prereq §3.1.b lock (where-you-stay
    # framing); `rv_repair` lives here as part of the auto-RV bundle.
    "gas_station": ("auto-rv-fuel", "commercial"),
    "car_repair": ("auto-rv-fuel", "commercial"),
    "car_dealer": ("auto-rv-fuel", "commercial"),
    "car_wash": ("auto-rv-fuel", "commercial"),
    "oil_change_service": ("auto-rv-fuel", "commercial"),
    "tire_shop": ("auto-rv-fuel", "commercial"),
    "auto_parts_store": ("auto-rv-fuel", "commercial"),
    "motorcycle_dealer": ("auto-rv-fuel", "commercial"),
    "rv_repair": ("auto-rv-fuel", "commercial"),

    # Tier 1.6 — Shopping, Grocery & Essentials (brief §3.6)
    "store": ("shopping-essentials", "commercial"),
    "supermarket": ("shopping-essentials", "commercial"),
    "grocery_or_supermarket": ("shopping-essentials", "commercial"),
    "clothing_store": ("shopping-essentials", "commercial"),
    "electronics_store": ("shopping-essentials", "commercial"),
    "hardware_store": ("shopping-essentials", "commercial"),
    "convenience_store": ("shopping-essentials", "commercial"),
    "furniture_store": ("shopping-essentials", "commercial"),
    "home_goods_store": ("shopping-essentials", "commercial"),
    "liquor_store": ("shopping-essentials", "commercial"),
    "book_store": ("shopping-essentials", "commercial"),
    "florist": ("shopping-essentials", "commercial"),
    "jewelry_store": ("shopping-essentials", "commercial"),

    # Tier 2/3 — non-Tier-1 categories already mapped pre-Phase-5
    "lodging": ("lodging-vacation-rentals", "commercial"),
    "rv_park": ("lodging-vacation-rentals", "commercial"),
    "park": ("outdoors-parks-trails", "place"),
    "dog_park": ("outdoors-parks-trails", "place"),
    # ``golf_course`` widening (Phase 5.7 §1 sustainability commit). Golf
    # courses are outdoors-and-parks-coded for the consumer-discovery
    # surface but are ``commercial`` (entry fees, staff, business hours)
    # rather than ``place``-typed like a city park. Same shape as how the
    # 6 pre-existing outdoors-parks-trails entries (Avalon Park, Cattail
    # Cove SP, Dick Samp Memorial, Lake Havasu SP, Rotary Community Park,
    # SARA Park) all sit as ``commercial`` — most LHC-area state parks
    # charge entry fees and have staffed visitor centers.
    "golf_course": ("outdoors-parks-trails", "commercial"),

    # Phase 5.8 §1 sustainability — events (cat-2) direct mappings.
    # Pre-5.8, the only entertainment_attractions resolver path for these
    # primary_types was the catch-all ``(None, "entertainment_attractions")
    # -> "outdoors-parks-trails"`` added in 5.7's ``1dfd28e``. That catch-
    # all is correct for 5.7's scope (wildlife_refuge / tourist_attraction
    # / point_of_interest under entertainment_attractions land in cat-7)
    # but would mis-route the 7 deferred event primary_types if they
    # surfaced. 5.8's Narrow scope (the 7 labels deferred in 5.7 — event
    # venues, live music venues, art galleries, museums, movie theaters,
    # bowling alleys, arcades) surfaces these primary_types directly;
    # direct _PRIMARY_TYPE_MAP entries beat the catch-all per the
    # resolver order in ``scripts/places_load._resolve_category_id``, so
    # cat-7 routing remains correct for wildlife_refuge /
    # tourist_attraction while these 7 route to cat-2.
    #
    # ``commercial``-vs-``place`` split: event_venue / live_music_venue /
    # movie_theater / bowling_alley / amusement_arcade charge admission
    # or cover/tickets and are unambiguously commercial. art_gallery and
    # museum are the gray area — many LHC galleries are free showrooms
    # for sale and small museums are often free / donation-based — so
    # they start as ``place`` per the 5.8 kickoff §1 starting point. The
    # §2 audit can flip individual entries to ``commercial`` if they
    # charge admission (Lake Havasu Museum of History is the likely
    # flip candidate).
    "event_venue": ("events", "commercial"),
    "art_gallery": ("events", "place"),
    "museum": ("events", "place"),
    "live_music_venue": ("events", "commercial"),
    "movie_theater": ("events", "commercial"),
    "bowling_alley": ("events", "commercial"),
    "amusement_arcade": ("events", "commercial"),

    "veterinary_care": ("pets", "commercial"),
    "pet_store": ("pets", "commercial"),

    # Phase 5.9 §1 sustainability — classes-sports-recreation (cat-12)
    # direct mappings. 5.9 Narrow scope is 9 of the 16 labels in the
    # ``classes-sports-recreation`` two-domain bundle
    # (``childcare_education`` + ``fitness_sports`` per
    # ``app/contrib/google_places_scraper.py:DISCOVERY_CATEGORY_TO_DOMAINS``):
    # the 5 childcare_education labels in-scope + 4 cat-12-native
    # fitness_sports labels (the 7 HWC-absorbed fitness_sports labels —
    # gyms/yoga/pilates/crossfit/martial_arts/jiu_jitsu/dance — deferred
    # to V1.5 per kickoff §1 Narrow-scope decision; they continue to
    # route to HWC via the 5.4 ``(None, "fitness_sports") ->
    # "health-wellness-care"`` catch-all at
    # ``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK:260``).
    #
    # Direct ``_PRIMARY_TYPE_MAP`` entries beat the ``_DISCOVERY_DOMAIN_
    # FALLBACK`` catch-all per the resolver order in
    # ``scripts/places_load._resolve_category_id`` (Layer 2 types-map
    # lookup runs before Layer 3 domain-fallback). The CRITICAL case is
    # ``tennis_court``: the 5.4 ``fc51940`` commit added
    # ``("tennis_court", "fitness_sports") -> "health-wellness-care"`` to
    # the catch-all, but the direct ``("tennis_court",
    # ("classes-sports-recreation", "place"))`` mapping below beats it
    # via resolver order so 5.9 tennis_court entries route correctly to
    # cat-12 instead of cat-5.
    #
    # ``commercial`` vs ``place`` split: childcare/preschool/music/
    # driving/tutor + personal_trainer are ``commercial`` (fee-based,
    # staffed); public swimming pools / tennis courts / pickleball
    # courts are ``place`` (city-park amenities, free or municipal-fee
    # access). The §2 audit can flip individual entries to
    # ``commercial`` if they're membership-club venues.
    #
    # The new ``(None, "childcare_education") ->
    # "classes-sports-recreation"`` catch-all at
    # ``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK`` covers any
    # unmapped childcare_education primary_types (no prior phase
    # populated the childcare_education domain).
    "child_care_agency": ("classes-sports-recreation", "commercial"),
    "preschool": ("classes-sports-recreation", "commercial"),
    "music_school": ("classes-sports-recreation", "commercial"),
    "driving_school": ("classes-sports-recreation", "commercial"),
    "tutor": ("classes-sports-recreation", "commercial"),
    "personal_trainer": ("classes-sports-recreation", "commercial"),
    "swimming_pool": ("classes-sports-recreation", "place"),
    "tennis_court": ("classes-sports-recreation", "place"),
    "pickleball_court": ("classes-sports-recreation", "place"),

    "school": ("classes-sports-recreation", "commercial"),
    "library": ("public-civic-resources", "place"),
    "city_hall": ("public-civic-resources", "place"),

    # Explicit Phase 5 skip: beauty / personal-care types route to the
    # operator queue rather than getting absorbed into eat-drink or
    # shopping-essentials. Per prereq checklist §3.1.a operator decision-
    # lock ("skip in Phase 5"); revisit V1.5 when the final home is
    # decided. Without these explicit `(None, None)` entries, Google's
    # types[] for a hair salon would fall through to (None, None) anyway,
    # but listing them defensively documents the intentional skip + lets
    # the operator queue surface them for review rather than silently
    # ignoring them.
    "hair_salon": (None, None),
    "beauty_salon": (None, None),
    "nail_salon": (None, None),
}


def map_google_types_to_slug_and_place_type(types: list[str]) -> tuple[str | None, str | None]:
    """Map Google's ``types`` list in order (primary first) to our taxonomy.

    Returns ``(None, None)`` when nothing matches.
    """
    for t in types:
        if t in _PRIMARY_TYPE_MAP:
            return _PRIMARY_TYPE_MAP[t]
    return (None, None)
