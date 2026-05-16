"""Phase 5.4 — regression guard for the _DISCOVERY_DOMAIN_FALLBACK
extension shipped this session (catches health_medical + fitness_sports
catch-all primary_types per Phase 5.4 §1 Layer 1 load findings: 282
inserts, 111 landed at category_id=None pre-fix).

Mirrors the shape of tests/test_phase5_3_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, discovery_domain) tuples that surfaced in the Phase 5.4
# operator queue and must route to ``health-wellness-care``.
_HEALTH_MEDICAL_KEYS: list[tuple[str | None, str]] = [
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
]

_FITNESS_SPORTS_KEYS: list[tuple[str | None, str]] = [
    (None, "fitness_sports"),
    ("sports_school", "fitness_sports"),
    ("health", "fitness_sports"),
    ("tennis_court", "fitness_sports"),
    ("athletic_field", "fitness_sports"),
    ("consultant", "fitness_sports"),
    ("point_of_interest", "fitness_sports"),
]


@pytest.mark.parametrize("key", _HEALTH_MEDICAL_KEYS)
def test_health_medical_fallback_routes_to_health_wellness_care(
    key: tuple[str | None, str],
) -> None:
    """Each health_medical fallback entry shipped this session must
    persist. Removing any of these would re-create the operator queue
    pile on every future health-wellness-care load (282 rows in 5.4 §1,
    111 unmapped pre-fix; dominant: ``health`` ×47 + ``medical_clinic``
    ×36)."""
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of the Phase 5.4 fallback extension — health_medical "
        "rows with this primary_type will land at category_id=None and "
        "need apply-script cleanup."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected 'health-wellness-care'."
    )


@pytest.mark.parametrize("key", _FITNESS_SPORTS_KEYS)
def test_fitness_sports_fallback_routes_to_health_wellness_care(
    key: tuple[str | None, str],
) -> None:
    """Each fitness_sports fallback entry shipped this session must
    persist. Phase 5.4 §1 surfaced sports_school ×6, athletic_field /
    consultant / tennis_court / point_of_interest ×1 each, plus the
    defensive (None, ...) entry."""
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of the Phase 5.4 fallback extension — fitness_sports "
        "rows with this primary_type will land at category_id=None."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected 'health-wellness-care'."
    )


def test_phase5_3_home_services_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.4 entries didn't disturb the
    Phase 5.3 home_services fallback entries (7c994aa)."""
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
    """Defensive: ensure adding Phase 5.4 entries didn't disturb the
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
            f"Phase 5.2 lake_recreation fallback entry {key!r} is missing. "
            "Regression of 65b0824."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "on-the-water"
