"""Phase 5.7 — regression guard for the _DISCOVERY_DOMAIN_FALLBACK
extension + the _PRIMARY_TYPE_MAP widening shipped this session
(``entertainment_attractions`` catch-all primary_types per Phase 5.7 §1
anticipation + ``golf_course`` direct mapping for outdoors-parks-trails
+ the long-deferred ``medical_clinic`` direct mapping for
health-wellness-care that closes the V1.5 carry-over flagged in 5.4 +
5.6 close-outs).

5.7 ships under the Narrow scope (3 labels: parks, golf courses, mini
golf) from the entertainment_attractions domain — the fitness_sports
labels are deferred to V1.5 to avoid collision with the existing
``(None, "fitness_sports") -> "health-wellness-care"`` fallback. As a
result, this commit only extends the entertainment_attractions side of
the bundle; the fitness_sports fallback entries shipped in 5.4 are
preserved verbatim (defensive test below).

Mirrors the shape of tests/test_phase5_6_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP
from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, discovery_domain) tuples that surfaced in the Phase 5.7
# kickoff §1 anticipation and must route to ``outdoors-parks-trails``.
# Narrow scope means the actual operator-queue size is expected to be
# small (~5-15 rows pre-fix vs 5.6's 21), but the safety nets are the
# same shape as 5.3/5.4/5.5/5.6.
_ENTERTAINMENT_KEYS: list[tuple[str | None, str]] = [
    (None, "entertainment_attractions"),
    ("tourist_attraction", "entertainment_attractions"),
    ("amusement_park", "entertainment_attractions"),
    ("point_of_interest", "entertainment_attractions"),
    ("establishment", "entertainment_attractions"),
]


@pytest.mark.parametrize("key", _ENTERTAINMENT_KEYS)
def test_entertainment_attractions_fallback_routes_to_outdoors_parks_trails(
    key: tuple[str | None, str],
) -> None:
    """Each entertainment_attractions fallback entry shipped this
    session must persist. Removing any would surface
    entertainment_attractions-discovered rows at category_id=None on
    every future outdoors-parks-trails load.

    Of the 5 entries: ``tourist_attraction`` catches state parks
    (Google often primary-types Cattail Cove SP + Lake Havasu SP as
    ``tourist_attraction`` rather than ``park``); ``amusement_park``
    catches mini golf venues (Google's primary type); ``(None, ...)``
    /``point_of_interest`` / ``establishment`` are the standard
    safety-net shape seen across all 5.x sustainability commits."""
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of the Phase 5.7 fallback extension — "
        "entertainment_attractions-domain rows with this primary_type "
        "will land at category_id=None and need apply-script cleanup."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "outdoors-parks-trails", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected "
        "'outdoors-parks-trails'."
    )


def test_golf_course_primary_type_maps_to_outdoors_parks_trails() -> None:
    """``golf_course`` widening shipped this session: golf courses
    should route to outdoors-parks-trails as ``commercial`` (entry
    fees, staff, business hours — same shape as how the 6 pre-existing
    outdoors-parks-trails state-park entries sit as commercial)
    regardless of which discovery domain surfaces them."""
    assert "golf_course" in _PRIMARY_TYPE_MAP, (
        "Missing _PRIMARY_TYPE_MAP entry for 'golf_course'. Regression "
        "of the Phase 5.7 type-map widening — golf courses will land "
        "at category_id=None unless the discovery domain happens to be "
        "entertainment_attractions (where the fallback would catch them)."
    )
    assert _PRIMARY_TYPE_MAP["golf_course"] == (
        "outdoors-parks-trails",
        "commercial",
    ), (
        f"_PRIMARY_TYPE_MAP['golf_course'] = "
        f"{_PRIMARY_TYPE_MAP['golf_course']!r}, expected "
        "('outdoors-parks-trails', 'commercial')."
    )


def test_medical_clinic_primary_type_maps_to_health_wellness_care() -> None:
    """``medical_clinic`` widening shipped this session (closes V1.5
    carry-over from 5.4 + 5.6 close-outs). Pre-5.7, medical_clinic
    resolved only via the ``(medical_clinic, "health_medical")``
    fallback in _DISCOVERY_DOMAIN_FALLBACK — which works when the
    discovery domain IS health_medical but fails otherwise (5.6 §4
    caught two eye-care providers — Lake Havasu Family Eyecare +
    Barnet Dulaney Perkins — that landed in shopping-essentials via
    the (None, "retail") catch-all). Direct mapping catches them
    regardless of discovery domain."""
    assert "medical_clinic" in _PRIMARY_TYPE_MAP, (
        "Missing _PRIMARY_TYPE_MAP entry for 'medical_clinic'. "
        "Regression of the Phase 5.7 type-map widening — the V1.5 "
        "carry-over from 5.4 + 5.6 close-outs would re-open."
    )
    assert _PRIMARY_TYPE_MAP["medical_clinic"] == (
        "health-wellness-care",
        "commercial",
    ), (
        f"_PRIMARY_TYPE_MAP['medical_clinic'] = "
        f"{_PRIMARY_TYPE_MAP['medical_clinic']!r}, expected "
        "('health-wellness-care', 'commercial')."
    )


def test_phase5_6_retail_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.7 entries didn't disturb the
    Phase 5.6 retail fallback entries (44e8097)."""
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
            f"Phase 5.6 retail fallback entry {key!r} is missing. Regression of 44e8097."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "shopping-essentials"


def test_phase5_5_auto_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.7 entries didn't disturb the
    Phase 5.5 auto fallback entries (4d41944)."""
    required_auto = {
        (None, "auto"),
        ("service", "auto"),
        ("car_rental", "auto"),
        ("point_of_interest", "auto"),
        ("store", "auto"),
    }
    for key in required_auto:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.5 auto fallback entry {key!r} is missing. Regression of 4d41944."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "auto-rv-fuel"


def test_phase5_4_health_medical_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.7 entries didn't disturb the
    Phase 5.4 health_medical fallback entries (fc51940). NOTE: this
    test still asserts the ``(medical_clinic, "health_medical")``
    fallback entry persists EVEN THOUGH ``medical_clinic`` is now also
    in _PRIMARY_TYPE_MAP directly — both can coexist (the
    _PRIMARY_TYPE_MAP lookup happens first; the fallback is a safety
    net for unusual cases where ``medical_clinic`` somehow doesn't hit
    the type-map). Defensive redundancy is the 5.4 + 5.6 documented
    pattern (see _DISCOVERY_DOMAIN_FALLBACK comments at
    ``scripts/places_load.py`` for the medical_clinic + dental_clinic
    treatment)."""
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


def test_phase5_4_fitness_sports_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.7 entries didn't disturb the
    Phase 5.4 fitness_sports fallback entries (fc51940). CRITICAL for
    5.7 specifically — the kickoff §1 Narrow scope decision (deferring
    fitness_sports labels to V1.5) RELIES on the existing
    ``(None, "fitness_sports") -> "health-wellness-care"`` fallback
    staying in place to handle any fitness_sports rows that leak in via
    geo-proximity ambig matches against existing HWC entities."""
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


def test_phase5_3_home_services_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.7 entries didn't disturb the
    Phase 5.3 home_services fallback entries (7c994aa)."""
    required_home_services = {
        (None, "home_services"),
        ("consultant", "home_services"),
        ("laundry", "home_services"),
        ("service", "home_services"),
    }
    for key in required_home_services:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.3 home_services fallback entry {key!r} is missing. Regression of 7c994aa."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "home-property-services"


def test_phase5_2_lake_recreation_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.7 entries didn't disturb the
    Phase 5.2 lake_recreation fallback entries (65b0824)."""
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
            f"Phase 5.2 lake_recreation fallback entry {key!r} is missing. Regression of 65b0824."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "on-the-water"


def test_park_and_dog_park_primary_types_preserved() -> None:
    """Defensive: ensure adding ``golf_course`` next to the existing
    park/dog_park entries in _PRIMARY_TYPE_MAP didn't accidentally
    perturb either. Both should still route to outdoors-parks-trails
    as ``place``-typed."""
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
