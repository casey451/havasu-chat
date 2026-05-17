"""Phase 5.9 — regression guard for the _PRIMARY_TYPE_MAP + _DISCOVERY_
DOMAIN_FALLBACK extensions shipped this session (9 direct mappings for
classes-sports-recreation (cat-12) primary_types + 1 new childcare_
education domain catch-all — per Phase 5.9 §1 sustainability commit
Option A).

5.9 ships under the Narrow scope (9 of the 16 labels in the
classes-sports-recreation two-domain bundle): the 5 childcare_education
labels (daycare, preschools, tutoring, music lessons, driving schools)
+ 4 cat-12-native fitness_sports labels (personal trainers, swimming
pools, tennis courts, pickleball). The 7 HWC-absorbed fitness_sports
labels (gyms, yoga, pilates, crossfit, martial arts, jiu-jitsu, dance)
are deferred to V1.5 — they continue to route to HWC via the 5.4
``(None, "fitness_sports") -> "health-wellness-care"`` catch-all at
``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK``.

The 9 new direct ``_PRIMARY_TYPE_MAP`` entries beat the catch-all per
the resolver order in ``scripts/places_load._resolve_category_id``
(direct ``_PRIMARY_TYPE_MAP`` lookup at Layer 2 runs before the
``_DISCOVERY_DOMAIN_FALLBACK`` lookup at Layer 3). The CRITICAL case is
``tennis_court`` — the 5.4 ``fc51940`` commit registered
``("tennis_court", "fitness_sports") -> "health-wellness-care"`` in the
fallback, but the new direct map below routes ``tennis_court`` to
cat-12 instead. ``test_phase5_9_tennis_court_direct_mapping_beats_
phase5_4_fallback`` is the dedicated assert.

Mirrors the shape of tests/test_phase5_8_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP
from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, (expected_slug, expected_entity_type)) tuples for the
# 9 direct mappings shipped this session. The ``commercial``-vs-``place``
# split follows the 5.9 kickoff §1 Option A starting point: the 5
# childcare_education types + personal_trainer are unambiguously
# ``commercial`` (fee-based, staffed); the 3 public-amenity types
# (swimming_pool / tennis_court / pickleball_court) start as ``place``
# (city-park amenities, free or municipal-fee access). The §2 audit can
# flip individual entries to ``commercial`` if they're membership-club
# venues (e.g. an HOA pool or private tennis club).
_CAT12_PRIMARY_TYPES: list[tuple[str, tuple[str, str]]] = [
    # childcare_education domain (5)
    ("child_care_agency", ("classes-sports-recreation", "commercial")),
    ("preschool", ("classes-sports-recreation", "commercial")),
    ("music_school", ("classes-sports-recreation", "commercial")),
    ("driving_school", ("classes-sports-recreation", "commercial")),
    ("tutor", ("classes-sports-recreation", "commercial")),
    # fitness_sports domain — cat-12 native (4)
    ("personal_trainer", ("classes-sports-recreation", "commercial")),
    ("swimming_pool", ("classes-sports-recreation", "place")),
    ("tennis_court", ("classes-sports-recreation", "place")),
    ("pickleball_court", ("classes-sports-recreation", "place")),
]


@pytest.mark.parametrize("primary_type,expected", _CAT12_PRIMARY_TYPES)
def test_cat12_primary_type_maps_to_classes_sports_recreation(
    primary_type: str, expected: tuple[str, str]
) -> None:
    """Each cat-12 primary_type direct mapping shipped this session must
    persist. For the 5 childcare_education types, removing the direct
    mapping would cause them to fall through to the new ``(None,
    "childcare_education") -> "classes-sports-recreation"`` catch-all
    (same destination, so visible behavior would be preserved — but the
    direct mapping documents intent + provides the entity_type
    ``commercial`` vs ``place`` distinction that the catch-all alone
    can't supply). For the 4 fitness_sports types, removing the direct
    mapping would cause them to fall through to the Phase 5.4 ``(None,
    "fitness_sports") -> "health-wellness-care"`` catch-all and
    mis-route into cat-5 HWC instead of cat-12 — a real regression."""
    assert primary_type in _PRIMARY_TYPE_MAP, (
        f"Missing _PRIMARY_TYPE_MAP entry for {primary_type!r}. "
        "Regression of the Phase 5.9 §1 sustainability extension."
    )
    assert _PRIMARY_TYPE_MAP[primary_type] == expected, (
        f"_PRIMARY_TYPE_MAP[{primary_type!r}] = "
        f"{_PRIMARY_TYPE_MAP[primary_type]!r}, expected {expected!r}."
    )


def test_phase5_9_tennis_court_direct_mapping_beats_phase5_4_fallback() -> None:
    """CRITICAL: ``tennis_court`` is BOTH in the 5.9 _PRIMARY_TYPE_MAP
    direct mapping (to cat-12 as ``place``) AND in the 5.4
    _DISCOVERY_DOMAIN_FALLBACK (``("tennis_court", "fitness_sports") ->
    "health-wellness-care"``). The resolver order in
    ``scripts/places_load._resolve_category_id`` runs the direct
    ``_PRIMARY_TYPE_MAP`` lookup BEFORE the ``_DISCOVERY_DOMAIN_FALLBACK``
    lookup (Layer 2 before Layer 3), so direct map wins. This test
    documents the dual-presence and guards against accidental removal
    of EITHER entry — removing the direct map would mis-route to
    cat-5 HWC; removing the fallback entry would break the 5.4
    HWC scope semantics."""
    assert "tennis_court" in _PRIMARY_TYPE_MAP, (
        "Missing _PRIMARY_TYPE_MAP entry for 'tennis_court'. "
        "Regression of the Phase 5.9 §1 sustainability extension — "
        "tennis_court would fall through to the 5.4 "
        "``('tennis_court', 'fitness_sports') -> 'health-wellness-care'`` "
        "catch-all and land in cat-5 HWC instead of cat-12."
    )
    assert _PRIMARY_TYPE_MAP["tennis_court"] == (
        "classes-sports-recreation",
        "place",
    )
    # And the 5.4 fallback entry must still exist (the resolver order
    # makes it dormant for tennis_court but it documents the 5.4 HWC
    # scope and could fire for other fitness_sports primary types).
    assert ("tennis_court", "fitness_sports") in _DISCOVERY_DOMAIN_FALLBACK
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[("tennis_court", "fitness_sports")]
        == "health-wellness-care"
    )


def test_phase5_9_childcare_education_catch_all_present() -> None:
    """The NEW ``(None, "childcare_education") ->
    "classes-sports-recreation"`` catch-all shipped this session covers
    any unmapped childcare_education primary_types Google emits for the
    5 in-scope labels (daycare, preschools, tutoring, music lessons,
    driving schools). No prior phase populated this domain in the
    fallback, so this entry is the safety net for label-coverage gaps
    in the 5 direct mappings."""
    assert (None, "childcare_education") in _DISCOVERY_DOMAIN_FALLBACK, (
        "Missing childcare_education catch-all in _DISCOVERY_DOMAIN_FALLBACK. "
        "Regression of the Phase 5.9 §1 sustainability extension."
    )
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "childcare_education")]
        == "classes-sports-recreation"
    )


def test_phase5_9_pool_court_entity_type_is_place() -> None:
    """Defensive: swimming_pool / tennis_court / pickleball_court are
    intentionally ``place``-typed at the 5.9 §1 starting point (public
    municipal amenities — city pools, public courts). The §2 audit may
    flip individual entries to ``commercial`` for membership-club
    venues, but this test guards against accidental flips of the
    type-map default itself (which would change all newly-loaded
    pool/court entries in one go and break the operator's per-entry
    audit workflow)."""
    for pt in ("swimming_pool", "tennis_court", "pickleball_court"):
        assert _PRIMARY_TYPE_MAP[pt][1] == "place", (
            f"_PRIMARY_TYPE_MAP[{pt!r}] entity_type = "
            f"{_PRIMARY_TYPE_MAP[pt][1]!r}, expected 'place'. "
            "If the operator wants commercial, flip individual entries "
            "via the §2 audit apply-script — not the type-map default."
        )


def test_phase5_9_pre_existing_school_mapping_preserved() -> None:
    """Defensive: the pre-Phase-5 ``school`` -> cat-12 mapping must
    persist after the 5.9 extension. The 5.9 §0 DB spot-check expects
    0-5 pre-existing cat-12 entries from the ``school`` primary_type
    catching prior-phase scrapes; if this mapping breaks, those entries
    would drift to operator-queue."""
    assert "school" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["school"] == (
        "classes-sports-recreation",
        "commercial",
    )


def test_phase5_9_pre_existing_gym_mapping_to_hwc_preserved() -> None:
    """Defensive: the pre-Phase-5 ``gym`` -> cat-5 HWC mapping must
    persist. The 5.4 HWC absorption ingested all LHC gyms via this
    direct mapping; the 5.9 lane explicitly does NOT touch gym (per the
    Narrow scope decision deferring 7 HWC-absorbed fitness types to
    V1.5). If this mapping breaks, gyms would re-route via the 5.4
    ``(None, "fitness_sports")`` catch-all (still HWC — same
    destination — but the documented direct mapping is the canonical
    routing)."""
    assert "gym" in _PRIMARY_TYPE_MAP
    assert _PRIMARY_TYPE_MAP["gym"] == ("health-wellness-care", "commercial")


def test_phase5_8_events_primary_type_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.9 entries didn't disturb the
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
            f"Phase 5.8 events direct mapping {primary_type!r} is missing. "
            "Regression of 0b426e1."
        )
        assert _PRIMARY_TYPE_MAP[primary_type] == expected


def test_phase5_7_entertainment_attractions_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.9 entries didn't disturb the
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


def test_phase5_7_golf_course_and_medical_clinic_primary_types_preserved() -> None:
    """Defensive: ensure adding Phase 5.9 entries didn't disturb the
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


def test_phase5_4_fitness_sports_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.9 entries didn't disturb the
    Phase 5.4 fitness_sports fallback entries (``fc51940``). CRITICAL
    for 5.9 specifically — the kickoff §1 Option A decision relies on
    the 5.4 ``(None, "fitness_sports") -> "health-wellness-care"``
    catch-all staying in place to continue routing the 7 HWC-absorbed
    fitness types (gym/yoga/pilates/crossfit/martial/jiu_jitsu/dance)
    to HWC. The 4 new cat-12-native direct mappings beat this catch-all
    via resolver order for personal_trainer / swimming_pool /
    tennis_court / pickleball_court."""
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
            f"Phase 5.4 fitness_sports fallback entry {key!r} is missing. "
            "Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_4_health_medical_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.9 entries didn't disturb the
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
            f"Phase 5.4 health_medical fallback entry {key!r} is missing. "
            "Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_x_other_domain_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.9 entries didn't disturb the
    Phase 5.2 / 5.3 / 5.5 / 5.6 domain fallback entries
    (``65b0824`` / ``7c994aa`` / ``4d41944`` / ``44e8097``)."""
    # 5.2 lake_recreation
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "lake_recreation")] == "on-the-water"
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[("tour_agency", "lake_recreation")]
        == "on-the-water"
    )
    # 5.3 home_services
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "home_services")]
        == "home-property-services"
    )
    # 5.5 auto
    assert _DISCOVERY_DOMAIN_FALLBACK[(None, "auto")] == "auto-rv-fuel"
    assert _DISCOVERY_DOMAIN_FALLBACK[("car_rental", "auto")] == "auto-rv-fuel"
    # 5.6 retail
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[(None, "retail")] == "shopping-essentials"
    )
    assert (
        _DISCOVERY_DOMAIN_FALLBACK[("shopping_mall", "retail")]
        == "shopping-essentials"
    )


def test_park_and_dog_park_primary_types_preserved() -> None:
    """Defensive: ensure adding the 9 cat-12 primary_type entries near
    the existing park/dog_park entries in _PRIMARY_TYPE_MAP didn't
    accidentally perturb either. Both should still route to
    outdoors-parks-trails as ``place``-typed."""
    assert _PRIMARY_TYPE_MAP["park"] == ("outdoors-parks-trails", "place")
    assert _PRIMARY_TYPE_MAP["dog_park"] == ("outdoors-parks-trails", "place")
