"""Address string helpers shared by SEO/profile surfaces.

Single-city directory: stored ``Location.address`` / ``Provider.address``
strings usually carry the full formatted form ("123 Main St, Lake Havasu
City, AZ 86403"). Schema.org ``PostalAddress.streetAddress`` must hold only
the street line -- the locality/region/zip live in their own fields -- or the
city and state are emitted twice in the JSON-LD (and in the visible NAP line
built from the same parts).
"""

from __future__ import annotations

import re
from typing import Optional

# Trailing ", Lake Havasu (City), AZ|Arizona( 86403(-1234)?)?(, USA)?" -- any
# of the city / state / zip / country parts optional, commas-or-spaces between
# them, any case. The optional USA tail (2026-06-10 prod run): Google-formatted
# addresses end ", USA", which otherwise blocks the suffix match entirely.
_CITY_STATE_ZIP_SUFFIX = re.compile(
    r"""
    [\s,]+                                  # separator before the suffix
    lake\s+havasu(?:\s+city)?               # "Lake Havasu" or "Lake Havasu City"
    (?:[\s,]+(?:az|ariz\.?|arizona))?       # optional state
    (?:[\s,]+\d{5}(?:-\d{4})?)?             # optional zip / zip+4
    (?:[\s,]+(?:usa|u\.s\.a\.|united\s+states))?  # optional country
    [\s,]*$                                 # trailing junk
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A bare "(AZ|Arizona)( zip)?(, USA)?" tail with no city -- e.g.
# "123 Main St, AZ 86403".
_STATE_ZIP_SUFFIX = re.compile(
    r"""
    [\s,]+
    (?:az|ariz\.?|arizona)
    (?:[\s,]+\d{5}(?:-\d{4})?)?
    (?:[\s,]+(?:usa|u\.s\.a\.|united\s+states))?
    [\s,]*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def street_line(address: Optional[str]) -> Optional[str]:
    """The street-only line of a stored full address (for ``streetAddress``).

    Strips one trailing ", Lake Havasu City, AZ 86403"-shaped suffix (city
    name with or without "City", "AZ"/"Arizona" optional, zip optional, commas
    and spacing forgiven). When the whole string IS the city (no street part
    in front), it is returned unchanged rather than emptied. Everything else
    passes through untouched -- use the stored full string everywhere a
    complete address is wanted.
    """
    if not address:
        return address
    text = address.strip()
    if not text:
        return address
    stripped = _CITY_STATE_ZIP_SUFFIX.sub("", text)
    if stripped == text:
        stripped = _STATE_ZIP_SUFFIX.sub("", text)
    stripped = stripped.rstrip(" ,\t")
    # "Lake Havasu City, AZ 86403" with no street in front: the remainder is
    # the city itself, not a street line -- leave the stored string alone.
    if not stripped or stripped.lower() in ("lake havasu", "lake havasu city"):
        return address
    return stripped


# WS-4 (Track B2) helpers below: the city-repeat concatenation artifact
# ("123 Main St, Lake Havasu City, AZ 86403, Lake Havasu City") came from
# loaders appending city/state/zip to street strings that already carried the
# suffix. Loaders now pre-strip with street_line(); these helpers normalize
# the rows the bug already produced and parse zips out of address text.

# Lake Havasu City zips. Single-city directory: a bare 5-digit \b\d{5}\b would
# false-positive on 5-digit street numbers, so zips are recognized by the 864
# prefix instead. Extend if the directory ever spans beyond 8640x.
_ZIP_IN_TEXT = re.compile(r"\b(864\d{2})(?:-\d{4})?\b")

_WHITESPACE_RUNS = re.compile(r"\s{2,}")
_COMMA_RUNS = re.compile(r"\s*,(?:\s*,)+\s*")

# A CITY-SHAPED mention: "Lake Havasu( City)" followed by a comma or end of
# string. Plain substring counting drowned the 2026-06-10 prod run in false
# positives — "N Lake Havasu Ave" is a street, "Lake Havasu State Park" and
# "Go Lake Havasu Visitor Center" are venue names; none of them is a repeated
# city suffix. The comma/end anchor keeps those out while still matching the
# real artifact shapes ("..., Lake Havasu City, AZ ..., Lake Havasu City").
_CITY_SUFFIX_MENTION = re.compile(
    r"lake\s+havasu(?:\s+city)?\s*(?:,|$)", re.IGNORECASE
)

# A string that is ONLY the city (+ optional state/zip), no street in front —
# e.g. "Lake Havasu City, AZ 86403". Not a fixable street line.
_CITY_ONLY = re.compile(
    r"""^lake\s+havasu(?:\s+city)?
        (?:[\s,]+(?:az|ariz\.?|arizona))?
        (?:[\s,]+\d{5}(?:-\d{4})?)?$""",
    re.IGNORECASE | re.VERBOSE,
)


def parse_zip(address: Optional[str]) -> Optional[str]:
    """The last Lake-Havasu-shaped zip (864xx) in an address string, or None."""
    if not address:
        return None
    matches = _ZIP_IN_TEXT.findall(address)
    return matches[-1] if matches else None


def count_city_mentions(text: Optional[str]) -> int:
    """How many CITY-SHAPED "Lake Havasu (City)," mentions ``text`` carries.

    The shared flag heuristic for the WS-4 script and the portal queue: 2+
    means a repeated city suffix (the concatenation artifact); street names
    ("N Lake Havasu Ave") and venue names ("Lake Havasu State Park") don't
    count. See _CITY_SUFFIX_MENTION.
    """
    if not text:
        return 0
    return len(_CITY_SUFFIX_MENTION.findall(text))


def normalize_full_address(address: Optional[str]) -> Optional[str]:
    """One canonical ``street, Lake Havasu City, AZ [zip]`` form, or None.

    Fixes the WS-4 mechanical queue's shapes: repeated trailing city/state/zip
    suffixes collapse to a single canonical tail (preserving any zip found in
    the original text), comma/whitespace runs collapse, and an unchanged or
    unfixable string returns None so callers can tell "no change" from
    "fixed". A string whose street part never emerges (the address IS the
    city, or the repeat is not a trailing suffix) also returns None — those
    rows belong to the pattern-check review queue, not an auto-fix.
    """
    if not address or not address.strip():
        return None
    original = address.strip()
    zip_code = parse_zip(original)

    # Collapse comma/whitespace runs first so suffix regexes see clean seams.
    text = _COMMA_RUNS.sub(", ", original)
    text = _WHITESPACE_RUNS.sub(" ", text).strip().strip(",").strip()

    # Strip trailing city/state/zip suffixes to a fixpoint -> the street line.
    street = text
    while True:
        stripped = street_line(street)
        if stripped == street or not stripped:
            break
        street = stripped
    # Dangling separators left at the seam (the Go Lake Havasu feed's
    # "...422 English Village |" pipe shape) come off before rebuilding.
    street = (street or "").strip().strip(",|").strip()

    if not street or _CITY_ONLY.match(street):
        return None  # nothing but the city: review-queue material, not a fix
    if count_city_mentions(street) >= 1:
        # The street part still ends in a city-shaped mention after suffix
        # stripping — the repeat is not a trailing-suffix artifact and needs
        # human eyes. In-street NAMES ("950 N Lake Havasu Ave", "Lake Havasu
        # State Park, 699 ...") don't count as city mentions; see
        # count_city_mentions.
        return None

    tail = "Lake Havasu City, AZ"
    if zip_code:
        tail = f"{tail} {zip_code}"
    fixed = f"{street}, {tail}"
    return fixed if fixed != original else None
