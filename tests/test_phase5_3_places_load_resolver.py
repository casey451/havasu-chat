"""Phase 5.3 — regression guard for 7c994aa (_DISCOVERY_DOMAIN_FALLBACK
extends for home_services domain).
"""

from __future__ import annotations

import pytest

from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK


@pytest.mark.parametrize(
    "primary_type",
    [None, "consultant", "laundry", "service"],
)
def test_home_services_fallback_routes_to_home_property_services(
    primary_type: str | None,
) -> None:
    """The 4 home_services fallback entries shipped at 7c994aa must
    persist. Each was added because a primary_type surfaced in the 5.3
    live load (282 input, 70 unmapped pre-fix) with that type and the
    home_services discovery domain. Removing any of these would re-create
    the 'operator queue' pile on every future home-property-services
    load."""
    key = (primary_type, "home_services")
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of 7c994aa — home_services rows with this primary_type "
        "will land at category_id=None and need apply-script cleanup."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "home-property-services", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected 'home-property-services'."
    )


def test_lake_recreation_fallback_entries_preserved() -> None:
    """Defensive: ensure adding home_services entries didn't disturb the
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
