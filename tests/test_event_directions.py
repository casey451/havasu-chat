"""F7: a "Directions" link renders only for geocodable venues, never for the
parks-rec org or the bare-city placeholders that misdirect users."""

from __future__ import annotations

import pytest

from app.events.directions import directions_url, is_geocodable_venue

# Org / bare-city placeholders that geocode to the wrong place -> no link.
NON_VENUES = [
    "Lake Havasu City Parks & Recreation",
    "lake havasu city parks & recreation",  # case-insensitive
    "Lake Havasu City Parks and Recreation",
    "Parks & Recreation",
    "Parks & Rec",
    "Lake Havasu City",
    "  Lake Havasu City  ",  # surrounding whitespace
    "Lake Havasu",
    "LHC",
    "",
    None,
]

# Real venues -- including ones that merely START with the city -> keep link.
VENUES = [
    "Lake Havasu City Aquatic Center",
    "Lake Havasu City BMX",
    "Lake Havasu Senior Center",
    "Jane Camlin",
    "Rotary Community Park",
    "Star Cinemas",
    "Mike Delaney Pickleball Complex at Dick Samp Park",
]


@pytest.mark.parametrize("name", NON_VENUES)
def test_non_venue_has_no_directions(name: str | None) -> None:
    assert is_geocodable_venue(name) is False
    assert directions_url(name) is None


@pytest.mark.parametrize("name", VENUES)
def test_real_venue_gets_directions(name: str) -> None:
    assert is_geocodable_venue(name) is True
    url = directions_url(name)
    assert url is not None
    assert url.startswith("https://www.google.com/maps/dir/?api=1&destination=")
    # The destination is URL-encoded (spaces never raw).
    assert " " not in url


def test_directions_url_encodes_the_venue() -> None:
    url = directions_url("Jane Camlin")
    assert url == "https://www.google.com/maps/dir/?api=1&destination=Jane%20Camlin"
