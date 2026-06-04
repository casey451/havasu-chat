"""Time-aware + heat-aware card ranking for Tier 1 category streams (Phase 6.3).

Pure functions only — no DB or ORM imports at module top (gotcha #17).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from app.core.liveness import liveness_dampener

if TYPE_CHECKING:
    from app.providers.view_models import HavaCardViewModel

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
    # Liveness dampener input (0–1). ``None`` → no dampening (multiplier 1.0),
    # so non-Google entities are unaffected. See ``app/core/liveness.py``.
    liveness_score: float | None = None


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

    # Liveness dampener — bury likely-dead listings without excluding them.
    # Applied last so it scales the fully-boosted score; NULL → multiplier 1.0.
    score *= liveness_dampener(inp.liveness_score)

    return score


def rank_sort_key(
    inp: CardRankInput,
    *,
    now: datetime | None = None,
    temperature_f: float | None = None,
) -> tuple[float, str]:
    """Tuple for ``sorted(..., key=rank_sort_key)`` — descending rank, then name."""
    return (-compute_card_rank(inp, now=now, temperature_f=temperature_f), (inp.name or "").lower())


# Phase 8a: the live-temperature helper `read_current_temperature_f(db)` lives
# in `app.core.conditions_temperature` (which imports STUB_CURRENT_TEMPERATURE_F
# from this module as a fallback). Do NOT re-export it from here — that creates
# a circular import. Callers should `from app.core.conditions_temperature
# import read_current_temperature_f` directly.


def compute_event_card_rank(
    *,
    event: Any,
    occurrence_date: date,
    now_temp_f: float = STUB_CURRENT_TEMPERATURE_F,
    distance_mi: float | None = None,
    user_in_boat_mode: bool = False,
    venue_heat_exposure: str | None = None,
    venue_boat_access: bool = False,
    today: date | None = None,
) -> float:
    """Mirror :func:`compute_card_rank` for event cards (Phase 9b)."""
    today = today or date.today()
    days_ahead = (occurrence_date - today).days
    base = 1.0

    if days_ahead == 0:
        base *= 1.30
    elif days_ahead == 1:
        base *= 1.15
    elif days_ahead <= 7 and occurrence_date.weekday() >= 5:
        base *= 1.10
    elif days_ahead <= 7:
        base *= 1.05

    if distance_mi is not None:
        dist_km = max(0.0, distance_mi * 1.60934)
        base *= 1.0 / (1.0 + dist_km)

    if now_temp_f > HEAT_BIAS_THRESHOLD_F:
        hx = (venue_heat_exposure or "").strip().lower()
        if hx == "indoor":
            base *= 1.0 + HEAT_BIAS_INDOOR_WEIGHT

    if user_in_boat_mode and venue_boat_access:
        base *= 1.10

    if bool(getattr(event, "featured", False)):
        base *= 1.25

    return base


def _cap_event_share(
    cards: list[tuple[HavaCardViewModel, float]],
    *,
    max_event_pct: float = 0.40,
    limit: int = 30,
) -> list[tuple[HavaCardViewModel, float]]:
    """Cap event cards at ``max_event_pct`` of the visible themed-group stream."""
    ranked = sorted(cards, key=lambda p: -p[1])
    output: list[tuple[HavaCardViewModel, float]] = []
    event_count = 0
    for vm, score in ranked:
        if vm.entity_type == "event":
            projected = event_count / max(1, len(output) + 1)
            if projected >= max_event_pct:
                continue
            event_count += 1
        output.append((vm, score))
        if len(output) >= limit:
            break
    return output


__all__ = [
    "CardRankInput",
    "HEAT_BIAS_INDOOR_WEIGHT",
    "HEAT_BIAS_SHADED_WEIGHT",
    "HEAT_BIAS_THRESHOLD_F",
    "STUB_CURRENT_TEMPERATURE_F",
    "_cap_event_share",
    "compute_card_rank",
    "compute_event_card_rank",
    "rank_sort_key",
]
