"""Phase 5.5 — regression guard for the _DISCOVERY_DOMAIN_FALLBACK
extension shipped this session (catches the ``auto`` discovery-domain
catch-all primary_types per Phase 5.5 §1 Layer 1 load findings: 179
input rows, 18 landed at category_id=None pre-fix; dominant: ``None``
×5 + ``service`` ×3 + ``car_rental`` ×2, plus ``point_of_interest`` +
``store`` safety nets per kickoff §1 anticipation).

Mirrors the shape of tests/test_phase5_4_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, discovery_domain) tuples that surfaced in the Phase 5.5
# operator queue (or were anticipated by kickoff §1) and must route to
# ``auto-rv-fuel``.
_AUTO_KEYS: list[tuple[str | None, str]] = [
    (None, "auto"),
    ("service", "auto"),
    ("car_rental", "auto"),
    ("point_of_interest", "auto"),
    ("store", "auto"),
]


@pytest.mark.parametrize("key", _AUTO_KEYS)
def test_auto_fallback_routes_to_auto_rv_fuel(
    key: tuple[str | None, str],
) -> None:
    """Each auto fallback entry shipped this session must persist.
    Removing any of these would re-create the operator queue pile on
    every future auto-rv-fuel load (179 inserts in 5.5 §1, 18 unmapped
    pre-fix; dominant: ``None`` ×5 + ``service`` ×3 + ``car_rental`` ×2;
    ``point_of_interest`` + ``store`` safety nets per kickoff §1)."""
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of the Phase 5.5 fallback extension — auto-domain "
        "rows with this primary_type will land at category_id=None and "
        "need apply-script cleanup."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "auto-rv-fuel", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected 'auto-rv-fuel'."
    )


def test_phase5_4_health_medical_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.5 entries didn't disturb the
    Phase 5.4 health_medical fallback entries (fc51940)."""
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
    """Defensive: ensure adding Phase 5.5 entries didn't disturb the
    Phase 5.4 fitness_sports fallback entries (fc51940)."""
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
    """Defensive: ensure adding Phase 5.5 entries didn't disturb the
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
    """Defensive: ensure adding Phase 5.5 entries didn't disturb the
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
