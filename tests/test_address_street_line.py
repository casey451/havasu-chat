"""Unit tests for app.core.address.street_line (JSON-LD streetAddress fix).

Bug: ``derive_postal_address`` copied the full stored address string into the
schema.org ``streetAddress`` while also emitting ``addressLocality`` "Lake
Havasu City" and ``addressRegion`` "AZ" -- city/state appeared twice in the
LocalBusiness JSON-LD and in the visible NAP line built from the same parts.
"""

from __future__ import annotations

import pytest

from app.core.address import street_line
from app.providers.queries import derive_postal_address


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The canonical duplicated form.
        ("123 Main St, Lake Havasu City, AZ 86403", "123 Main St"),
        # No zip.
        ("123 Main St, Lake Havasu City, AZ", "123 Main St"),
        # No state.
        ("123 Main St, Lake Havasu City", "123 Main St"),
        # "Lake Havasu" without "City".
        ("123 Main St, Lake Havasu, AZ 86403", "123 Main St"),
        # Spelled-out state.
        ("123 Main St, Lake Havasu City, Arizona 86403", "123 Main St"),
        # Zip+4.
        ("123 Main St, Lake Havasu City, AZ 86403-1234", "123 Main St"),
        # Weird spacing / missing commas / case.
        ("123 Main St,Lake Havasu City,AZ 86403", "123 Main St"),
        ("123 Main St  ,  lake havasu city , az  86403 ", "123 Main St"),
        ("123 Main St Lake Havasu City AZ 86403", "123 Main St"),
        # Suite line kept.
        ("950 N Lake Havasu Ave Ste 2, Lake Havasu City, AZ 86403", "950 N Lake Havasu Ave Ste 2"),
        # Bare state+zip tail with no city.
        ("123 Main St, AZ 86403", "123 Main St"),
        # Already street-only: untouched.
        ("123 Main St", "123 Main St"),
        # Street that NAMES the lake but isn't a city suffix: untouched.
        ("950 N Lake Havasu Ave", "950 N Lake Havasu Ave"),
    ],
)
def test_strips_city_state_zip_suffix(raw: str, expected: str) -> None:
    assert street_line(raw) == expected


def test_address_that_is_just_the_city_is_unchanged() -> None:
    # No street part in front -- never strip to an empty string.
    assert street_line("Lake Havasu City, AZ 86403") == "Lake Havasu City, AZ 86403"
    assert street_line("Lake Havasu City") == "Lake Havasu City"


def test_none_and_blank_pass_through() -> None:
    assert street_line(None) is None
    assert street_line("") == ""
    assert street_line("   ") == "   "


def test_derive_postal_address_strips_duplicated_city_state() -> None:
    """Regression: a full stored address no longer duplicates city/state in
    the structured parts (street carries only the street line)."""

    class _P:
        address = "123 Main St, Lake Havasu City, AZ 86403"
        entity = None

    out = derive_postal_address(_P())
    assert out == {"street": "123 Main St", "city": "Lake Havasu City", "state": "AZ"}
