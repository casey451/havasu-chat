"""Phase 5.8 — regression guard for the _PRIMARY_TYPE_MAP extension
shipped this session (7 direct mappings for the events (cat-2) primary
types — event_venue / art_gallery / museum / live_music_venue /
movie_theater / bowling_alley / amusement_arcade — per Phase 5.8 §1
sustainability commit Option A).

5.8 ships under the Narrow scope (the 7 labels deferred in 5.7's
Narrow scope: event venues, live music venues, art galleries, museums,
movie theaters, bowling alleys, arcades) from the
entertainment_attractions domain. The cat-7 labels (parks, golf
courses, mini golf) are already absorbed by 5.7 and stay deferred for
5.8. The 5.7 ``(None, "entertainment_attractions") ->
"outdoors-parks-trails"`` catch-all stays in place; the 7 new direct
mappings beat the catch-all per the resolver order in
``scripts/places_load._resolve_category_id`` (direct ``_PRIMARY_TYPE_MAP``
lookup runs before the ``_DISCOVERY_DOMAIN_FALLBACK`` lookup), so
wildlife_refuge / tourist_attraction etc. continue to land in cat-7
while the 7 event primary_types route to cat-2.

Mirrors the shape of tests/test_phase5_7_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP
from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, (expected_slug, expected_entity_type)) tuples for the
# 7 direct mappings shipped this session. The ``commercial``-vs-``place``
# split follows the 5.8 kickoff §1 starting point: event_venue /
# live_music_venue / movie_theater / bowling_alley / amusement_arcade
# charge admission/cover/tickets and are unambiguously commercial;
# art_gallery and museum start as ``place`` (free showrooms / public-good
# small museums) and the §2 audit can flip individual entries to
# ``commercial`` if they charge admission.
_EVENTS_PRIMARY_TYPES: list[tuple[str, tuple[str, str]]] = [
    ("event_venue", ("events", "commercial")),
    ("art_gallery", ("events", "place")),
    ("museum", ("events", "place")),
    ("live_music_venue", ("events", "commercial")),
    ("movie_theater", ("events", "commercial")),
    ("bowling_alley", ("events", "commercial")),
    ("amusement_arcade", ("events", "commercial")),
]


@pytest.mark.parametrize("primary_type,expected", _EVENTS_PRIMARY_TYPES)
def test_events_primary_type_maps_to_events(
    primary_type: str, expected: tuple[str, str]
) -> None:
    """Each events primary_type direct mapping shipped this session must
    persist. Removing any would cause that primary_type to fall through
    to the 5.7 catch-all ``(None, "entertainment_attractions") ->
    "outdoors-parks-trails"`` and mis-route into cat-7 instead of cat-2."""
    assert primary_type in _PRIMARY_TYPE_MAP, (
        f"Missing _PRIMARY_TYPE_MAP entry for {primary_type!r}. "
        "Regression of the Phase 5.8 §1 sustainability extension — "
        f"{primary_type!r} would fall through to the 5.7 "
        "``(None, 'entertainment_attractions') -> 'outdoors-parks-trails'`` "
        "catch-all and land in cat-7 instead of cat-2."
    )
    assert _PRIMARY_TYPE_MAP[primary_type] == expected, (
        f"_PRIMARY_TYPE_MAP[{primary_type!r}] = "
        f"{_PRIMARY_TYPE_MAP[primary_type]!r}, expected {expected!r}."
    )


def test_events_art_gallery_and_museum_start_as_place_typed() -> None:
    """Defensive: art_gallery and museum are intentionally ``place``-typed
    at the 5.8 §1 starting point (free showrooms / public-good small
    museums). The 5.8 kickoff §1 explicitly flags this is a starting
    point, and the §2 audit may flip individual entries to ``commercial``
    if they charge admission. This test guards against accidental flips
    of the type-map default itself (which would change all newly-loaded
    art galleries + museums in one go and break the operator's per-entry
    audit workflow)."""
    assert _PRIMARY_TYPE_MAP["art_gallery"][1] == "place", (
        f"_PRIMARY_TYPE_MAP['art_gallery'] entity_type = "
        f"{_PRIMARY_TYPE_MAP['art_gallery'][1]!r}, expected 'place'. "
        "If the operator wants commercial, flip individual entries via "
        "the §2 audit apply-script — not the type-map default."
    )
    assert _PRIMARY_TYPE_MAP["museum"][1] == "place", (
        f"_PRIMARY_TYPE_MAP['museum'] entity_type = "
        f"{_PRIMARY_TYPE_MAP['museum'][1]!r}, expected 'place'. "
        "If the operator wants commercial, flip individual entries via "
        "the §2 audit apply-script — not the type-map default."
    )


def test_phase5_7_entertainment_attractions_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.7 entertainment_attractions fallback entries (``1dfd28e``).
    CRITICAL for 5.8 specifically — the kickoff §1 Option A pattern
    RELIES on the 5.7 catch-all staying in place to route
    wildlife_refuge / tourist_attraction / etc. to cat-7 (while the 7
    new direct ``_PRIMARY_TYPE_MAP`` entries beat the catch-all for the
    event primary_types per the resolver order)."""
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
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "outdoors-parks-trails", (
            f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] = "
            f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected "
            "'outdoors-parks-trails'."
        )


def test_phase5_7_golf_course_primary_type_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.7 ``golf_course`` widening (``1dfd28e``)."""
    assert "golf_course" in _PRIMARY_TYPE_MAP, (
        "Missing _PRIMARY_TYPE_MAP entry for 'golf_course'. "
        "Regression of the Phase 5.7 type-map widening."
    )
    assert _PRIMARY_TYPE_MAP["golf_course"] == (
        "outdoors-parks-trails",
        "commercial",
    )


def test_phase5_7_medical_clinic_primary_type_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.7 ``medical_clinic`` widening (``1dfd28e``)."""
    assert "medical_clinic" in _PRIMARY_TYPE_MAP, (
        "Missing _PRIMARY_TYPE_MAP entry for 'medical_clinic'. "
        "Regression of the Phase 5.7 type-map widening — the V1.5 "
        "carry-over from 5.4 + 5.6 close-outs would re-open."
    )
    assert _PRIMARY_TYPE_MAP["medical_clinic"] == (
        "health-wellness-care",
        "commercial",
    )


def test_phase5_6_retail_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.6 retail fallback entries (``44e8097``)."""
    required_retail = {
        (None, "retail"),
        ("service", "retail"),
        ("supplier", "retail"),
        ("point_of_interest", "retail"),
        ("establishment", "retail"),
        ("store", "retail"),
        ("shopping_mall", "retail"),
    }
    for key in required_retail:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.6 retail fallback entry {key!r} is missing. "
            "Regression of 44e8097."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "shopping-essentials"


def test_phase5_5_auto_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.5 auto fallback entries (``4d41944``)."""
    required_auto = {
        (None, "auto"),
        ("service", "auto"),
        ("car_rental", "auto"),
        ("point_of_interest", "auto"),
        ("store", "auto"),
    }
    for key in required_auto:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.5 auto fallback entry {key!r} is missing. "
            "Regression of 4d41944."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "auto-rv-fuel"


def test_phase5_4_health_medical_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
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


def test_phase5_4_fitness_sports_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
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
            f"Phase 5.4 fitness_sports fallback entry {key!r} is missing. "
            "Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_3_home_services_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.3 home_services fallback entries (``7c994aa``)."""
    required_home_services = {
        (None, "home_services"),
        ("consultant", "home_services"),
        ("laundry", "home_services"),
        ("service", "home_services"),
    }
    for key in required_home_services:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.3 home_services fallback entry {key!r} is missing. "
            "Regression of 7c994aa."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "home-property-services"


def test_phase5_2_lake_recreation_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.8 entries didn't disturb the
    Phase 5.2 lake_recreation fallback entries (``65b0824``)."""
    required_lake_rec = {
        (None, "lake_recreation"),
        ("service", "lake_recreation"),
        ("tour_agency", "lake_recreation"),
        ("tourist_attraction", "lake_recreation"),
        ("tourist_information_center", "lake_recreation"),
        ("point_of_interest", "lake_recreation"),
        ("supplier", "lake_recreation"),
        ("sporting_goods_store", "lake_recreation"),
        ("adventure_sports_center", "lake_recreation"),
    }
    for key in required_lake_rec:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.2 lake_recreation fallback entry {key!r} is missing. "
            "Regression of 65b0824."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "on-the-water"


def test_park_and_dog_park_primary_types_preserved() -> None:
    """Defensive: ensure adding the 7 events primary_type entries near
    the existing park/dog_park/golf_course entries in _PRIMARY_TYPE_MAP
    didn't accidentally perturb either. Both should still route to
    outdoors-parks-trails as ``place``-typed."""
    assert _PRIMARY_TYPE_MAP["park"] == ("outdoors-parks-trails", "place"), (
        f"_PRIMARY_TYPE_MAP['park'] = {_PRIMARY_TYPE_MAP['park']!r}, "
        "expected ('outdoors-parks-trails', 'place'). Regression of "
        "the pre-Phase-5 park mapping."
    )
    assert _PRIMARY_TYPE_MAP["dog_park"] == (
        "outdoors-parks-trails",
        "place",
    ), (
        f"_PRIMARY_TYPE_MAP['dog_park'] = "
        f"{_PRIMARY_TYPE_MAP['dog_park']!r}, expected "
        "('outdoors-parks-trails', 'place'). Regression of the "
        "pre-Phase-5 dog_park mapping."
    )
