"""Whether an event ``location_name`` is a geocodable venue, and its map URL.

F7 (2026-06-30): many parks-and-rec events store the *organization*
("Lake Havasu City Parks & Recreation") or the bare city
("Lake Havasu City") as ``location_name`` -- the venue itself was never in
the source. Geocoding those sends users to the dept office or the downtown
centroid, not where the event actually is. A "Directions" button that routes
to the wrong place is worse than none, so we render no link for those values
(the location text still shows). This is a single display-layer gate, so it
covers every source -- parks-rec, allevents, legistar, and anything future --
without a per-row data backfill (the real venue is not reliably recoverable
from the descriptions).

Real venues that merely *start* with the city ("Lake Havasu City Aquatic
Center", "Lake Havasu City BMX", "Lake Havasu Senior Center") are geocodable
and keep their Directions link -- the gate is an exact, case-insensitive match
against a small set of known org/placeholder strings, never a prefix.
"""

from __future__ import annotations

from urllib.parse import quote

# Exact (case-insensitive) location_name values that are an organization or the
# bare city rather than a geocodable venue. Matched whole-string, never as a
# prefix, so specific venues that begin with "Lake Havasu" are unaffected.
_NON_VENUE_LOCATIONS: frozenset[str] = frozenset(
    {
        "lake havasu",
        "lake havasu city",
        "lake havasu city, az",
        "lhc",
        "lake havasu city parks & recreation",
        "lake havasu city parks and recreation",
        "parks & recreation",
        "parks and recreation",
        "parks & rec",
        "parks and rec",
    }
)


def is_geocodable_venue(location_name: str | None) -> bool:
    """True when ``location_name`` names a place we can usefully map to."""
    if not location_name:
        return False
    return location_name.strip().casefold() not in _NON_VENUE_LOCATIONS


def directions_url(location_name: str | None) -> str | None:
    """Google Maps directions URL for a venue, or None when not geocodable."""
    if not is_geocodable_venue(location_name):
        return None
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(location_name.strip())}"
