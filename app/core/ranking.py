"""Time-aware + heat-aware card ranking for Tier 1 category streams (Phase 6.3).

Pure functions only — no DB or ORM imports at module top (gotcha #17).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Phase 8 wires real conditions; 6.3 uses a stub so heat-bias is testable in prod UI.
STUB_CURRENT_TEMPERATURE_F = 105.0

HEAT_BIAS_THRESHOLD_F = 100.0
HEAT_BIAS_INDOOR_WEIGHT = 0.20
HEAT_BIAS_SHADED_WEIGHT = 0.10

DEFAULT_VERIFIED_BOOST = 0.15
DEFAULT_OPEN_NOW_BOOST = 0.10
DEFAULT_BOAT_ACCESS_BOOST = 0.12
DEFAULT_MOBILE_SERVICE_BOOST = 0.10


@dataclass(frozen=True)
class CardRankInput:
    """ORM-neutral inputs for :func:`compute_card_rank`."""

    distance_km: float
    name: str
    heat_exposure: str | None = None
    verified: bool = False
    is_open_now: bool | None = None
    boat_access_populated: bool = False
    mobile_service: bool = False
    verified_boost: float = DEFAULT_VERIFIED_BOOST
    open_now_boost: float = DEFAULT_OPEN_NOW_BOOST
    boat_access_boost: float = DEFAULT_BOAT_ACCESS_BOOST
    mobile_service_boost: float = DEFAULT_MOBILE_SERVICE_BOOST


def compute_card_rank(
    inp: CardRankInput,
    *,
    now: datetime | None = None,
    temperature_f: float | None = None,
) -> float:
    """Return a descending sort score (higher = ranks earlier).

    Base score favors closer venues. When ``temperature_f`` is strictly above
    :data:`HEAT_BIAS_THRESHOLD_F`, indoor and shaded venues receive fractional boosts.
    Additional boosts are additive fractions of the base score.
    """
    _ = now  # reserved for future time-decay; server clock via call-site ``now``
    dist = max(0.0, float(inp.distance_km))
    base = 1.0 / (1.0 + dist)

    score = base

    temp = temperature_f if temperature_f is not None else STUB_CURRENT_TEMPERATURE_F
    if temp > HEAT_BIAS_THRESHOLD_F:
        hx = (inp.heat_exposure or "").strip().lower()
        if hx == "indoor":
            score += base * HEAT_BIAS_INDOOR_WEIGHT
        elif hx == "shaded":
            score += base * HEAT_BIAS_SHADED_WEIGHT

    if inp.verified and inp.verified_boost:
        score += base * inp.verified_boost
    if inp.is_open_now is True and inp.open_now_boost:
        score += base * inp.open_now_boost
    if inp.boat_access_populated and inp.boat_access_boost:
        score += base * inp.boat_access_boost
    if inp.mobile_service and inp.mobile_service_boost:
        score += base * inp.mobile_service_boost

    return score


def rank_sort_key(
    inp: CardRankInput,
    *,
    now: datetime | None = None,
    temperature_f: float | None = None,
) -> tuple[float, str]:
    """Tuple for ``sorted(..., key=rank_sort_key)`` — descending rank, then name."""
    return (-compute_card_rank(inp, now=now, temperature_f=temperature_f), (inp.name or "").lower())


__all__ = [
    "CardRankInput",
    "HEAT_BIAS_INDOOR_WEIGHT",
    "HEAT_BIAS_SHADED_WEIGHT",
    "HEAT_BIAS_THRESHOLD_F",
    "STUB_CURRENT_TEMPERATURE_F",
    "compute_card_rank",
    "rank_sort_key",
]
