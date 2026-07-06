"""S2 — street-address validation + normalization."""

from __future__ import annotations

from app.contrib.address_clean import (
    clean_street_address,
    is_valid_street_address,
    normalize_address,
)


def test_real_street_addresses_validate() -> None:
    for a in (
        "2400 Clubhouse Dr, Lake Havasu City, AZ 86406",
        "100 Main St #5, Lake Havasu City AZ",
        "5601 AZ-95 #902, Lake Havasu City, AZ 86404, USA",
    ):
        assert is_valid_street_address(a), a


def test_garbage_addresses_are_rejected() -> None:
    for a in (
        "CMVH+9G, Lake Havasu City, AZ 86406, USA",   # plus-code
        "FJJV+WM, Lake Havasu City, AZ 86403, USA",
        "PO Box 3704, Lake Havasu City, AZ 86405",    # PO box
        "25 Riviera Blvd Llc, Lake Havasu City, AZ 86403, USA",  # entity-suffix street
        "THE SHOPS AT, 5601 AZ-95 #902, Lake Havasu City, AZ",   # leading placeholder
        "Inside 21Glam next to Body & Soul, 2121 Swanson Ave",   # leading placeholder
        "Online Only",
        "Lake Havasu City, AZ 86403",                 # bare city, no street
        "",
        None,
    ):
        assert not is_valid_street_address(a), a


def test_normalize_drops_trailing_usa_and_folds_space() -> None:
    assert normalize_address("2400 Clubhouse Dr,  Lake Havasu City, AZ 86406, USA") == (
        "2400 Clubhouse Dr, Lake Havasu City, AZ 86406"
    )
    assert normalize_address("   ") is None


def test_clean_returns_none_for_garbage_but_keeps_real() -> None:
    assert clean_street_address("CMVH+9G, Lake Havasu City, AZ") is None
    assert clean_street_address("2400 Clubhouse Dr, Lake Havasu City, AZ 86406") == (
        "2400 Clubhouse Dr, Lake Havasu City, AZ 86406"
    )
