"""Phase 5.10 -- regression guard for the _PRIMARY_TYPE_MAP + _DISCOVERY_
DOMAIN_FALLBACK extensions shipped this session (5 direct mappings for
lodging-vacation-rentals (cat-10) primary_types + 1 new lodging domain
catch-all -- per Phase 5.10 1 sustainability commit Option A).

5.10 ships under the Narrow scope (5 of the labels in the
lodging-vacation-rentals two-domain bundle): the 5 lodging-domain labels
(hotels, motels, resorts, vacation rentals, bed and breakfast). All
lake_recreation-domain labels (24 in places_categories.json) are
deferred to V1.5 -- marina/boat shape already absorbed by 5.2's
on-the-water scrape via the 5.2 ``(None, "lake_recreation") ->
"on-the-water"`` catch-all at
``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK:216``; RV parks +
campgrounds + mobile_home_park + camping_cabin already in cat-10 via
either the pre-Phase-5 ``rv_park`` direct mapping or the secondary-
types[] first-match on the existing ``lodging`` direct mapping.

The 5 new direct ``_PRIMARY_TYPE_MAP`` entries beat the new ``(None,
"lodging")`` catch-all per the resolver order in
``scripts/places_load._resolve_category_id`` (direct ``_PRIMARY_TYPE_MAP``
lookup at Layer 2 runs before the ``_DISCOVERY_DOMAIN_FALLBACK`` lookup
at Layer 3). All 5 land in cat-10 either way (same destination), so the
direct mappings document intent + provide the explicit ``commercial``
entity_type that the catch-all alone can't supply.

Mirrors the shape of tests/test_phase5_9_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP
from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, (expected_slug, expected_entity_type)) tuples for the
# 5 direct mappings shipped this session. All 5 start as ``commercial``
# per the 5.10 kickoff 1 Option A starting point (fee-based, staffed).
# The 2 audit can flip individual entries to ``place`` if there's a
# public-good edge case (rare for lodging -- pools are amenities, not
# primary identity).
_CAT10_PRIMARY_TYPES: list[tuple[str, tuple[str, str]]] = [
    ("hotel", ("lodging-vacation-rentals", "commercial")),
    ("motel", ("lodging-vacation-rentals", "commercial")),
    ("resort_hotel", ("lodging-vacation-rentals", "commercial")),
    ("extended_stay_hotel", ("lodging-vacation-rentals", "commercial")),
    ("bed_and_breakfast", ("lodging-vacation-rentals", "commercial")),
]


@pytest.mark.parametrize("primary_type,expected", _CAT10_PRIMARY_TYPES)
def test_cat10_primary_type_maps_to_lodging_vacation_rentals(
    primary_type: str, expected: tuple[str, str]
) -> None:
    """Each cat-10 primary_type direct mapping shipped this session must
    persist. Removing any direct mapping would cause the type to fall
    through to either the secondary-types[] match on the existing
    ``lodging`` direct mapping (still cat-10 -- visible behavior preserved
    if Google emits ``lodging`` as a secondary type) OR to the new
    ``(None, "lodging")`` catch-all (also cat-10). But the direct
    mapping documents intent + is defensive against Google's types[]
    array changes (e.g., if Google ever stops emitting ``lodging`` as a
    secondary for hotel-primary entities)."""
    assert primary_type in _PRIMARY_TYPE_MAP, (
        f"Missing _PRIMARY_TYPE_MAP entry for {primary_type!r}. "
        "Regression of the Phase 5.10 1 sustainability extension."
    )
    assert _PRIMARY_TYPE_MAP[primary_type] == expected, (
        f"_PRIMARY_TYPE_MAP[{primary_type!r}] = "
        f"{_PRIMARY_TYPE_MAP[primary_type]!r}, expected {expected!r}."
    )


def test_phase5_10_lodging_catch_all_present() -> None:
    """The NEW ``(None, "lodging") -> "lodging-vacation-rentals"``
    catch-all shipped this session covers any unmapped lodging
    primary_types Google emits for the 5 in-scope labels (hotels,
    motels, resorts, vacation rentals, bed and breakfast). No prior
    phase populated the lodging domain in the fallback. The 5.10 1
    load surfaced one such case -- Vanderpump Rules Lake Havasu Luxury
    Villa (primary=``service``, _first_seen_domain=``lodging``, types[]
    without the ``lodging`` secondary that would otherwise catch it via
    the existing ``"lodging": ("lodging-vacation-rentals", "commercial")``
    direct mapping). This catch-all routes that edge case + any future
    similar cases to cat-10 instead of operator queue."""
    assert (None, "lodging") in _DISCOVERY_DOMAIN_FALLBACK, (
        "Missing lodging catch-all in _DISCOVERY_DOMAIN_FALLBACK. "
        "Regression of the Phase 5.10 1 sustainability extension."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "lodging")] == "lodging-vacation-rentals"


def test_phase5_10_pre_existing_lodging_and_rv_park_mappings_preserved() -> None:
    """Defensive: the pre-Phase-5 ``lodging`` + ``rv_park`` direct
    mappings to cat-10 must persist after the 5.10 extension. The 5.10
    0 DB spot-check found 31 pre-existing cat-10 entries that depend
    on these mappings (14 rv_park entries via the ``rv_park`` direct
    map; 7 lodging-primary vacation rentals via the ``lodging`` direct
    map; and 4 distinct non-mapped primary types -- campground,
    mobile_home_park, camping_cabin, service -- caught via the
    secondary-types[] first-match on ``lodging``). If either mapping
    breaks, those 31 entries would drift to operator-queue on next
    re-pull."""
    assert "lodging" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["lodging"] == (
        "lodging-vacation-rentals",
        "commercial",
    )
    assert "rv_park" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["rv_park"] == (
        "lodging-vacation-rentals",
        "commercial",
    )


def test_phase5_10_cat10_entries_are_all_commercial() -> None:
    """Defensive: all 5 cat-10 primary types shipped this session are
    intentionally ``commercial``-typed at the 5.10 1 starting point
    (fee-based, staffed lodging properties). The 2 audit may flip
    individual entries to ``place`` for public-good edge cases (rare),
    but this test guards against accidental flips of the type-map
    default itself."""
    for pt, (_, entity_type) in _CAT10_PRIMARY_TYPES:
        assert _PRIMARY_TYPE_MAP[pt][1] == "commercial", (
            f"_PRIMARY_TYPE_MAP[{pt!r}] entity_type = "
            f"{_PRIMARY_TYPE_MAP[pt][1]!r}, expected 'commercial'. "
            "If the operator wants ``place`` for a specific entry, "
            "flip via the 2 audit apply-script -- not the type-map "
            "default."
        )


def test_phase5_9_cat12_primary_type_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.9 cat-12 primary_type direct mappings (``0af5f73``)."""
    required_cat12 = {
        "child_care_agency": ("classes-sports-recreation", "commercial"),
        "preschool": ("classes-sports-recreation", "commercial"),
        "music_school": ("classes-sports-recreation", "commercial"),
        "driving_school": ("classes-sports-recreation", "commercial"),
        "tutor": ("classes-sports-recreation", "commercial"),
        "personal_trainer": ("classes-sports-recreation", "commercial"),
        "swimming_pool": ("classes-sports-recreation", "place"),
        "tennis_court": ("classes-sports-recreation", "place"),
        "pickleball_court": ("classes-sports-recreation", "place"),
    }
    for primary_type, expected in required_cat12.items():
        assert primary_type in _PRIMARY_TYPE_MAP, (
            f"Phase 5.9 cat-12 direct mapping {primary_type!r} is missing. Regression of 0af5f73."
        )
        assert _PRIMARY_TYPE_MAP[primary_type] == expected


def test_phase5_9_childcare_education_catch_all_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.9 childcare_education catch-all (``0af5f73``)."""
    assert (None, "childcare_education") in _DISCOVERY_DOMAIN_FALLBACK
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "childcare_education")] == "classes-sports-recreation"


def test_phase5_8_events_primary_type_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.8 events primary_type direct mappings (``0b426e1``)."""
    required_events = {
        "event_venue": ("events", "commercial"),
        "art_gallery": ("events", "place"),
        "museum": ("events", "place"),
        "live_music_venue": ("events", "commercial"),
        "movie_theater": ("events", "commercial"),
        "bowling_alley": ("events", "commercial"),
        "amusement_arcade": ("events", "commercial"),
    }
    for primary_type, expected in required_events.items():
        assert primary_type in _PRIMARY_TYPE_MAP, (
            f"Phase 5.8 events direct mapping {primary_type!r} is missing. Regression of 0b426e1."
        )
        assert _PRIMARY_TYPE_MAP[primary_type] == expected


def test_phase5_7_golf_course_and_medical_clinic_primary_types_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.7 ``golf_course`` + ``medical_clinic`` widenings
    (``1dfd28e``)."""
    assert _PRIMARY_TYPE_MAP["golf_course"] == (
        "outdoors-parks-trails",
        "commercial",
    )
    assert _PRIMARY_TYPE_MAP["medical_clinic"] == (
        "health-wellness-care",
        "commercial",
    )


def test_phase5_7_entertainment_attractions_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.7 entertainment_attractions fallback entries (``1dfd28e``)."""
    required_entertainment_attractions = {
        (None, "entertainment_attractions"),
        ("tourist_attraction", "entertainment_attractions"),
        ("amusement_park", "entertainment_attractions"),
        ("point_of_interest", "entertainment_attractions"),
        ("establishment", "entertainment_attractions"),
    }
    for key in required_entertainment_attractions:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.7 entertainment_attractions fallback entry {key!r} "
            "is missing. Regression of 1dfd28e."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "outdoors-parks-trails"


def test_phase5_4_fitness_sports_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.4 fitness_sports fallback entries (``fc51940``)."""
    required_fitness_sports = {
        (None, "fitness_sports"),
        ("sports_school", "fitness_sports"),
        ("health", "fitness_sports"),
        ("tennis_court", "fitness_sports"),
        ("athletic_field", "fitness_sports"),
        ("consultant", "fitness_sports"),
        ("point_of_interest", "fitness_sports"),
    }
    for key in required_fitness_sports:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.4 fitness_sports fallback entry {key!r} is missing. Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_4_health_medical_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.4 health_medical fallback entries (``fc51940``)."""
    required_health_medical = {
        (None, "health_medical"),
        ("health", "health_medical"),
        ("medical_clinic", "health_medical"),
        ("dental_clinic", "health_medical"),
        ("skin_care_clinic", "health_medical"),
        ("wellness_center", "health_medical"),
        ("spa", "health_medical"),
        ("non_profit_organization", "health_medical"),
        ("apartment_building", "health_medical"),
        ("service", "health_medical"),
        ("point_of_interest", "health_medical"),
    }
    for key in required_health_medical:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.4 health_medical fallback entry {key!r} is missing. Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_x_other_domain_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.10 entries didn't disturb the
    Phase 5.2 / 5.3 / 5.5 / 5.6 domain fallback entries
    (``65b0824`` / ``7c994aa`` / ``4d41944`` / ``44e8097``)."""
    # 5.2 lake_recreation -- CRITICAL for 5.10 specifically, this is
    # the OTHER half of the lodging-vacation-rentals two-domain bundle
    # and the 5.10 kickoff 1 Narrow scope decision relies on this
    # catch-all continuing to route lake_recreation primary_types to
    # on-the-water.
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "lake_recreation")] == "on-the-water"
    assert _DISCOVERY_DOMAIN_FALLBACK[("tour_agency", "lake_recreation")] == "on-the-water"
    # 5.3 home_services
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "home_services")] == "home-property-services"
    # 5.5 auto
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "auto")] == "auto-rv-fuel"
    assert _DISCOVERY_DOMAIN_FALLBACK[("car_rental", "auto")] == "auto-rv-fuel"
    # 5.6 retail
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "retail")] == "shopping-essentials"
    assert _DISCOVERY_DOMAIN_FALLBACK[("shopping_mall", "retail")] == "shopping-essentials"


def test_park_and_dog_park_primary_types_preserved() -> None:
    """Defensive: ensure adding the 5 cat-10 primary_type entries near
    the existing park/dog_park entries in _PRIMARY_TYPE_MAP didn't
    accidentally perturb either. Both should still route to
    outdoors-parks-trails as ``place``-typed."""
    assert _PRIMARY_TYPE_MAP["park"] == ("outdoors-parks-trails", "place")
    assert _PRIMARY_TYPE_MAP["dog_park"] == ("outdoors-parks-trails", "place")
