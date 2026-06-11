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


# --- WS-4 (Track B2): normalize_full_address + parse_zip ---------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The concatenation artifact WS-4 exists to kill: suffix doubled.
        (
            "123 Main St, Lake Havasu City, AZ 86403, Lake Havasu City",
            "123 Main St, Lake Havasu City, AZ 86403",
        ),
        # Doubled with the zip only in the inner copy: zip survives.
        (
            "123 Main St, Lake Havasu City, AZ 86403, Lake Havasu City, AZ",
            "123 Main St, Lake Havasu City, AZ 86403",
        ),
        # Tripled.
        (
            "123 Main St, Lake Havasu, AZ, Lake Havasu City, Lake Havasu City, AZ 86404",
            "123 Main St, Lake Havasu City, AZ 86404",
        ),
        # A street that NAMES the lake still fixes cleanly (single in-street
        # mention is legitimate — only the suffix repeat was the bug).
        (
            "950 N Lake Havasu Ave Ste 2, Lake Havasu City, AZ 86403, Lake Havasu City",
            "950 N Lake Havasu Ave Ste 2, Lake Havasu City, AZ 86403",
        ),
        # Comma/space runs collapse even with a single suffix.
        (
            "123 Main St,,  Lake Havasu City, AZ 86403",
            "123 Main St, Lake Havasu City, AZ 86403",
        ),
        # Already canonical -> no change signalled.
        ("123 Main St, Lake Havasu City, AZ 86403", None),
        # City-only strings are review material, never auto-fixed.
        ("Lake Havasu City, AZ 86403, Lake Havasu City", None),
        ("Lake Havasu City", None),
        # Empty-ish input.
        ("", None),
        (None, None),
    ],
)
def test_normalize_full_address(raw, expected) -> None:
    from app.core.address import normalize_full_address

    assert normalize_full_address(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123 Main St, Lake Havasu City, AZ 86403", "86403"),
        ("123 Main St, Lake Havasu City, AZ 86404-1234", "86404"),
        # Last zip wins (the doubled-suffix shape).
        ("123 Main St, AZ 86403, Lake Havasu City, AZ 86406", "86406"),
        # A 5-digit street number is NOT a zip (864xx prefix required).
        ("12345 N Desert Rd", None),
        ("86403 looks like a zip but leads the string", "86403"),
        ("no digits here", None),
        (None, None),
    ],
)
def test_parse_zip(raw, expected) -> None:
    from app.core.address import parse_zip

    assert parse_zip(raw) == expected


def test_loader_format_address_never_doubles_city() -> None:
    """WS-4 'never concatenate': a scraped street already carrying the city
    suffix composes to a single canonical tail in both loaders."""
    from types import SimpleNamespace

    from app.contrib.pdga_courses import format_address as pdga_format
    from app.contrib.usapickleball import format_address as pickle_format

    payload = SimpleNamespace(
        street="1340 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        city="Lake Havasu City",
        state="AZ",
        postal="86403",
    )
    for fmt in (pdga_format, pickle_format):
        out = fmt(payload)
        assert out == "1340 McCulloch Blvd N, Lake Havasu City, AZ 86403"
        assert out.lower().count("lake havasu") == 1
