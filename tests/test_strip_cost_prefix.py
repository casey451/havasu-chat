"""strip_cost_prefix: peel a cost token a feed bled into the venue field (ED-cost).

The live bug was a venue stored as ``"$45 - Aquatic Center"`` — a price the source
put in the location field. The helper removes a leading price/``free`` token only
when a separator follows, so real venue names are never mangled.
"""

from __future__ import annotations

import pytest

from app.contrib.event_record import strip_cost_prefix


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The bug: price + separator + real venue -> just the venue.
        ("$45 - Aquatic Center", "Aquatic Center"),
        ("Free | London Bridge", "London Bridge"),
        ("$10-$25 — Rotary Park", "Rotary Park"),
        ("$3.00 - Lake Havasu City Aquatic Center", "Lake Havasu City Aquatic Center"),
        ("$5 to $10: Rotary Park", "Rotary Park"),
        ("  $20 — SARA Park  ", "SARA Park"),
        # Untouched: no leading price, or a price/number with no following separator.
        ("Aquatic Center", "Aquatic Center"),
        ("1420 McCulloch Blvd N", "1420 McCulloch Blvd N"),
        ("Freedom Park", "Freedom Park"),
        ("$5 Pizza Place", "$5 Pizza Place"),  # embedded price, no separator
        ("$45", "$45"),  # bare price, no separator -> left as-is (not the bug shape)
        # Empty / None.
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_strip_cost_prefix(raw: str | None, expected: str | None) -> None:
    assert strip_cost_prefix(raw) == expected
