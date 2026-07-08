"""WS10 /lake hub — curated launch-ramp data + the on-the-water tile links.

The live conditions module and the rentals/marinas/repair subcategory lists are
assembled in the route from EXISTING sources (``build_today_payload`` +
the ``/categories/on-the-water`` leaves); this module holds the one piece with no
directory home yet: the public launch ramps and their fees.

Ramp facts are curated (like :mod:`app.home.family_venues` /
:mod:`app.events.senior_center`): each carries a ``source_url`` so a reader can
verify, and fees/hours are transcribed from the cited public source — never
fabricated. **Update here when a ramp's fee or hours change** (single source of
truth). Transcribed Jul 2026 from lhcaz.gov, azstateparks.com and
golakehavasu.com; confirm fees against the source before leaning on them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LaunchRamp:
    """One public motorized launch ramp with its (verifiable) fee + hours."""

    name: str
    area: str  # where it is (address / area)
    fee: str  # honest fee label — "Free" or the transcribed day-use fee
    hours: str  # when you can launch
    note: str  # lanes / features
    source_url: str  # authoritative source the reader can verify


# The public MOTORIZED launch ramps in / near Lake Havasu City, nearest first.
# State-park fees verified Jul 2026 against azstateparks.com/fee-schedule (which
# changed Feb 2025 — older aggregator figures were stale). AZ State Parks revise
# fees ANNUALLY, so both state-park cards cite the fee-schedule page and the page
# carries "confirm at the gate" microcopy. Update here when the schedule changes.
LAUNCH_RAMPS: tuple[LaunchRamp, ...] = (
    LaunchRamp(
        name="Site Six Launch Ramp",
        area="591 Beachcomber Blvd — across London Bridge, on the Island",
        fee="Free",
        hours="Open 24 hours",
        note="The city's free public ramp — 3 lanes, fish-cleaning station, restrooms. No overnight parking.",
        source_url="https://www.lhcaz.gov/335/Site-Six",
    ),
    LaunchRamp(
        name="Lake Havasu State Park — Windsor Beach",
        area="699 London Bridge Rd — 1 mi north of the bridge",
        fee="$20 Mon–Thu · $25 Fri–Sun and holidays (per vehicle, 1–4 adults)",
        hours="Launch 24 hours · office 6 AM–5 PM",
        note="12 boat lanes plus dedicated PWC lanes; courtesy docks.",
        source_url="https://azstateparks.com/fee-schedule",
    ),
    LaunchRamp(
        name="Cattail Cove State Park",
        area="~15 mi south of town on AZ-95",
        fee="$10 single-occupant vehicle · $20 for 2–4 people",
        hours="8 AM–5 PM · self-pay 5 PM–8 AM",
        note="One ramp, 4 lanes — south-lake access near Havasu Springs.",
        source_url="https://azstateparks.com/fee-schedule",
    ),
)


@dataclass(frozen=True)
class PaddleLaunch:
    """A free, non-motorized (kayak / canoe / SUP) launch — no ramp fee."""

    name: str
    source_url: str


# Free kayak / canoe / SUP launches — grouped apart from the motorized ramps so a
# paddler isn't shown a motor-ramp fee that doesn't apply to them.
_PADDLE_SRC = "https://www.golakehavasu.com/things-to-do/boating/launch-ramps-marinas/"
PADDLE_LAUNCHES: tuple[PaddleLaunch, ...] = (
    PaddleLaunch("London Bridge Beach", _PADDLE_SRC),
    PaddleLaunch("Rotary Community Park", _PADDLE_SRC),
    PaddleLaunch("Castle Rock Bay", _PADDLE_SRC),
    PaddleLaunch("Mesquite Bay", _PADDLE_SRC),
)


# The on-the-water subcategory tiles → real filtered leaf lists. Link-only (no
# counts) so a tile can never disagree with the leaf page's own number (WS7).
_LAKE_TILES: tuple[tuple[str, str, str], ...] = (
    (
        "Boat & watercraft rentals",
        "Pontoons, waverunners, kayaks",
        "/categories/on-the-water/boat-and-watercraft-rentals",
    ),
    (
        "Marinas & fuel",
        "Slips, fuel docks, launch ramps",
        "/categories/on-the-water/marinas-and-launch-ramps",
    ),
    (
        "Boat tours & charters",
        "Fishing, sunset & lake tours",
        "/categories/on-the-water/boat-tours-and-charters",
    ),
    (
        "Boat repair & service",
        "Mechanics, detailing, storage",
        "/categories/auto-rv-and-marine/boat-repair-and-service",
    ),
)


def lake_tiles() -> list[dict[str, str]]:
    """The on-the-water subcategory tiles (label + blurb + real leaf URL)."""
    return [{"label": lbl, "blurb": blurb, "url": url} for lbl, blurb, url in _LAKE_TILES]
