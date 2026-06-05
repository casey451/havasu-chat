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

# Trailing ", Lake Havasu (City), AZ|Arizona( 86403(-1234)?)?" -- any of the
# city / state / zip parts optional, commas-or-spaces between them, any case.
_CITY_STATE_ZIP_SUFFIX = re.compile(
    r"""
    [\s,]+                                  # separator before the suffix
    lake\s+havasu(?:\s+city)?               # "Lake Havasu" or "Lake Havasu City"
    (?:[\s,]+(?:az|ariz\.?|arizona))?       # optional state
    (?:[\s,]+\d{5}(?:-\d{4})?)?             # optional zip / zip+4
    [\s,]*$                                 # trailing junk
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A bare "(AZ|Arizona)( zip)?" tail with no city -- e.g. "123 Main St, AZ 86403".
_STATE_ZIP_SUFFIX = re.compile(
    r"""
    [\s,]+
    (?:az|ariz\.?|arizona)
    (?:[\s,]+\d{5}(?:-\d{4})?)?
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
