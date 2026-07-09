"""P2-2: per-venue diversification of the Tier-3 events context.

The Aquatic Center's daily recurring Open Swim slots flooded the standalone-events
context, so heat/coping Tier-3 answers over-relied on it. _diversify_events_by_venue
caps each venue's occurrences while keeping chronological order. Pure helper — no DB.
"""

from __future__ import annotations

from app.chat.context_builder import _diversify_events_by_venue


class _Ev:
    def __init__(self, title: str, venue: str) -> None:
        self.title = title
        self.location_name = venue


def test_caps_per_venue_and_keeps_order() -> None:
    evs = [_Ev(f"swim{i}", "Aquatic Center") for i in range(5)]
    evs += [_Ev("trampoline", "Altitude"), _Ev("movie", "Cinema")]
    out = _diversify_events_by_venue(evs, limit=10, per_venue_cap=2)
    venues = [e.location_name for e in out]
    assert venues.count("Aquatic Center") == 2          # flooding venue capped
    assert "Altitude" in venues and "Cinema" in venues  # other venues surface
    assert out[0].location_name == "Aquatic Center"     # chronological order kept


def test_respects_overall_limit() -> None:
    evs = [_Ev(f"e{i}", f"Venue{i}") for i in range(10)]
    out = _diversify_events_by_venue(evs, limit=3, per_venue_cap=2)
    assert len(out) == 3


def test_events_without_venue_are_never_capped() -> None:
    evs = [_Ev(f"e{i}", "") for i in range(5)]
    out = _diversify_events_by_venue(evs, limit=10, per_venue_cap=2)
    assert len(out) == 5
