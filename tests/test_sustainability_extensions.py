"""Phase 5.7+5.9+5.10+5.11 V1.5 carry — sustainability layer extensions test guard.

Verifies the 14 new direct mappings added in the
sustainability_extensions_apply commit resolve to the expected
(category_slug, place_type) tuples.

The mappings close 4 deferred carries:
- 5.7 carry: wildlife_refuge → outdoors-parks-trails
- 5.9 carry: athletic_field + 5 cat-12 types → classes-sports-recreation
- 5.10 carry: camping_cabin + 3 cat-10 types → lodging-vacation-rentals
- 5.11 carry: pet_supply_store + 2 cat-11 types → pets

`church` is intentionally NOT covered (operator-decide between cat-12 vs
cat-13; see outputs/v1_5_carry_inventory_triage.md §4 carry #29 + the
sustainability_extensions_apply artifact §5 narrative).
"""

from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP

# Each tuple: (primary_type, expected_slug, expected_place_type)
SUSTAINABILITY_EXTENSIONS: list[tuple[str, str, str]] = [
    # 5.7 carry — wildlife_refuge → cat-7
    ("wildlife_refuge", "outdoors-parks-trails", "place"),
    # 5.9 carry — 6 cat-12 types
    ("athletic_field", "classes-sports-recreation", "place"),
    ("educational_institution", "classes-sports-recreation", "commercial"),
    ("primary_school", "classes-sports-recreation", "commercial"),
    ("sports_complex", "classes-sports-recreation", "place"),
    ("sports_club", "classes-sports-recreation", "commercial"),
    ("country_club", "classes-sports-recreation", "commercial"),
    # 5.10 carry — 4 cat-10 types
    ("camping_cabin", "lodging-vacation-rentals", "commercial"),
    ("cottage", "lodging-vacation-rentals", "commercial"),
    ("mobile_home_park", "lodging-vacation-rentals", "place"),
    ("guest_house", "lodging-vacation-rentals", "commercial"),
    # 5.11 carry — 3 cat-11 types
    ("pet_supply_store", "pets", "commercial"),
    ("animal_shelter", "pets", "place"),
    ("aquarium_store", "pets", "commercial"),
]


@pytest.mark.parametrize(
    "primary_type,expected_slug,expected_place_type", SUSTAINABILITY_EXTENSIONS
)
def test_sustainability_extension_direct_mapping(
    primary_type: str,
    expected_slug: str,
    expected_place_type: str,
) -> None:
    """Each new mapping resolves to the expected (slug, place_type) tuple."""
    assert primary_type in _PRIMARY_TYPE_MAP, (
        f"{primary_type!r} should be in _PRIMARY_TYPE_MAP after the "
        f"sustainability_extensions_apply commit lands"
    )
    actual_slug, actual_place_type = _PRIMARY_TYPE_MAP[primary_type]
    assert actual_slug == expected_slug, (
        f"{primary_type!r}: expected slug {expected_slug!r}, got {actual_slug!r}"
    )
    assert actual_place_type == expected_place_type, (
        f"{primary_type!r}: expected place_type {expected_place_type!r}, got {actual_place_type!r}"
    )


def test_church_intentionally_unmapped() -> None:
    """`church` is a 5.9 carry candidate but operator-decide pending —
    asserts the artifact's §5 narrative ("church omitted") stays honest.

    If a future commit DOES map `church`, delete this test in the same
    commit + update outputs/v1_5_carry_inventory_triage.md §4 carry #29.
    """
    assert "church" not in _PRIMARY_TYPE_MAP, (
        "`church` was omitted from the sustainability_extensions_apply "
        "commit per operator-decide between cat-12 (5.9 The Ark Center "
        "context) vs cat-13 (religious / nonprofit). If this test fails, "
        "the mapping was added — update outputs/v1_5_carry_inventory_triage.md "
        "§4 carry #29 to reflect the disposition."
    )
