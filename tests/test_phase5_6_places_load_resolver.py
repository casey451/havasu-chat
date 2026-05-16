"""Phase 5.6 — regression guard for the _DISCOVERY_DOMAIN_FALLBACK
extension shipped this session (catches the ``retail`` discovery-domain
catch-all primary_types per Phase 5.6 §1 Layer 1 load findings: 268
input rows, 21 landed at category_id=None pre-fix; 10 visible as
Providers with NULL category_id {``service`` ×3 (IT/electronics service
shops — Havasu Technologies, Vertical IT, Whiz Kid Computer Services),
``None`` ×1 (Havasu Computers)}, the other 11 inside the 181-row
ambig-skip pool. Six edge cases (``corporate_office`` / ``manufacturer``
/ ``garden`` / ``farm`` / ``health`` / ``community_center``)
intentionally LEFT in operator queue for per-row review since their
types aren't consistently retail).

Mirrors the shape of tests/test_phase5_5_places_load_resolver.py.
"""

from __future__ import annotations

import pytest

from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK

# (primary_type, discovery_domain) tuples that surfaced in the Phase 5.6
# operator queue (or were anticipated by kickoff §1) and must route to
# ``shopping-essentials``.
_RETAIL_KEYS: list[tuple[str | None, str]] = [
    (None, "retail"),
    ("service", "retail"),
    ("supplier", "retail"),
    ("point_of_interest", "retail"),
    ("establishment", "retail"),
    ("store", "retail"),
    ("shopping_mall", "retail"),
]


@pytest.mark.parametrize("key", _RETAIL_KEYS)
def test_retail_fallback_routes_to_shopping_essentials(
    key: tuple[str | None, str],
) -> None:
    """Each retail fallback entry shipped this session must persist.
    Removing any of these would re-create the operator queue pile on
    every future shopping-essentials load (268 inserts in 5.6 §1, 21
    unmapped pre-fix; visible distribution: ``service`` ×3 + ``None``
    ×1, plus ``supplier`` / ``point_of_interest`` / ``establishment``
    safety nets per kickoff §1 anticipation; ``store`` defensive against
    google_types_mapping changes; ``shopping_mall`` covers The Shops at
    Lake Havasu)."""
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of the Phase 5.6 fallback extension — retail-domain "
        "rows with this primary_type will land at category_id=None and "
        "need apply-script cleanup."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "shopping-essentials", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected 'shopping-essentials'."
    )


def test_phase5_5_auto_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.6 entries didn't disturb the
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
            f"Phase 5.5 auto fallback entry {key!r} is missing. "
            "Regression of 4d41944."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "auto-rv-fuel"


def test_phase5_4_health_medical_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.6 entries didn't disturb the
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
            f"Phase 5.4 health_medical fallback entry {key!r} is missing. "
            "Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_4_fitness_sports_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.6 entries didn't disturb the
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
            f"Phase 5.4 fitness_sports fallback entry {key!r} is missing. "
            "Regression of fc51940."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "health-wellness-care"


def test_phase5_3_home_services_fallback_entries_preserved() -> None:
    """Defensive: ensure adding Phase 5.6 entries didn't disturb the
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
    """Defensive: ensure adding Phase 5.6 entries didn't disturb the
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
