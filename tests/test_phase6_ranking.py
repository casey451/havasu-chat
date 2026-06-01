"""Phase 6.3 — heat-aware + time-aware card ranking."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.ranking import (
    HEAT_BIAS_INDOOR_WEIGHT,
    HEAT_BIAS_THRESHOLD_F,
    CardRankInput,
    compute_card_rank,
)
from app.core.timezone import LAKE_HAVASU_TZ


def _inp(**kwargs: object) -> CardRankInput:
    base = {"distance_km": 1.0, "name": "Alpha"}
    base.update(kwargs)
    return CardRankInput(**base)  # type: ignore[arg-type]


def test_closer_distance_ranks_higher() -> None:
    near = compute_card_rank(_inp(distance_km=0.5, name="Near"))
    far = compute_card_rank(_inp(distance_km=5.0, name="Far"))
    assert near > far


def test_heat_bias_fires_above_threshold() -> None:
    outdoor = compute_card_rank(
        _inp(heat_exposure="outdoor"), temperature_f=HEAT_BIAS_THRESHOLD_F + 1
    )
    indoor = compute_card_rank(
        _inp(heat_exposure="indoor"), temperature_f=HEAT_BIAS_THRESHOLD_F + 1
    )
    assert indoor > outdoor
    boost = indoor - compute_card_rank(
        _inp(heat_exposure="indoor"), temperature_f=HEAT_BIAS_THRESHOLD_F
    )
    assert boost == pytest.approx((1.0 / 2.0) * HEAT_BIAS_INDOOR_WEIGHT, rel=1e-6)


def test_shaded_gets_partial_heat_boost() -> None:
    outdoor = compute_card_rank(_inp(heat_exposure="outdoor"), temperature_f=101.0)
    shaded = compute_card_rank(_inp(heat_exposure="shaded"), temperature_f=101.0)
    assert shaded > outdoor


def test_no_heat_bias_for_outdoor_or_null() -> None:
    at_threshold = compute_card_rank(_inp(heat_exposure="outdoor"), temperature_f=100.0)
    hot = compute_card_rank(_inp(heat_exposure="outdoor"), temperature_f=105.0)
    assert at_threshold == hot
    null_exposure = compute_card_rank(_inp(heat_exposure=None), temperature_f=110.0)
    outdoor = compute_card_rank(_inp(heat_exposure="outdoor"), temperature_f=110.0)
    assert null_exposure == outdoor


def test_heat_bias_strictly_greater_than_threshold() -> None:
    at_100 = compute_card_rank(_inp(heat_exposure="indoor"), temperature_f=100.0)
    at_100_1 = compute_card_rank(_inp(heat_exposure="indoor"), temperature_f=100.1)
    assert at_100_1 > at_100


def test_sort_stable_alphabetical_within_bucket() -> None:
    now = datetime(2026, 7, 15, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    a_score = compute_card_rank(_inp(distance_km=1.0, name="AAA"), now=now, temperature_f=105.0)
    z_score = compute_card_rank(_inp(distance_km=1.0, name="ZZZ"), now=now, temperature_f=105.0)
    assert a_score == z_score


def test_verified_boost_integrates() -> None:
    unverified = compute_card_rank(_inp(verified=False, verified_boost=0.2))
    verified = compute_card_rank(_inp(verified=True, verified_boost=0.2))
    assert verified > unverified


def test_open_now_boost_integrates() -> None:
    closed = compute_card_rank(_inp(is_open_now=False, open_now_boost=0.15))
    open_now = compute_card_rank(_inp(is_open_now=True, open_now_boost=0.15))
    assert open_now > closed


def test_ranking_reproducible() -> None:
    inp = _inp(heat_exposure="shaded", verified=True, is_open_now=True)
    a = compute_card_rank(inp, temperature_f=102.0)
    b = compute_card_rank(inp, temperature_f=102.0)
    assert a == b
