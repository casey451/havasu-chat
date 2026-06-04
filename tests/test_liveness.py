"""Unit tests for ``app.core.liveness`` — scoring, tiers, and rank dampener."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.liveness import (
    DAMPENER_FLOOR,
    NO_REVIEW_RECENCY,
    STALE_VERIFY_RECENCY,
    TIER_LIKELY_INACTIVE,
    TIER_NO_REVIEW_DATA,
    TIER_OK,
    TIER_STALE_VERIFY,
    compute_liveness,
    liveness_dampener,
    liveness_tier,
    recency_component,
)

REF = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _ago(days: float) -> datetime:
    return REF - timedelta(days=days)


# --- recency component ---


def test_recency_no_timestamp_is_neutral() -> None:
    assert recency_component(0, None, REF) == NO_REVIEW_RECENCY


def test_recency_fresh_high_volume_near_one() -> None:
    # 100 reviews, last one 30 days ago — clearly alive.
    r = recency_component(100, _ago(30), REF)
    assert r == pytest.approx(0.90, abs=0.02)


def test_recency_high_volume_stale_is_low() -> None:
    # 47 reviews silent for 772 days — death signal.
    r = recency_component(47, _ago(772), REF)
    assert r < 0.15


def test_recency_low_volume_stale_stays_moderate() -> None:
    # 4 reviews quiet for 400 days is normal; grace is wide.
    r = recency_component(4, _ago(400), REF)
    assert r > 0.25


def test_recency_future_timestamp_clamps_to_one() -> None:
    # A review stamped slightly ahead of ref_now must not exceed 1.0.
    r = recency_component(10, REF + timedelta(days=2), REF)
    assert r == pytest.approx(1.0, abs=1e-9)


# --- tiers (mirror the handoff's validated cases) ---


def test_tier_high_volume_stale_is_likely_inactive() -> None:
    assert liveness_tier(3.0, 47, _ago(772), REF) == TIER_LIKELY_INACTIVE


def test_tier_low_volume_stale_is_ok() -> None:
    assert liveness_tier(4.5, 4, _ago(400), REF) == TIER_OK


def test_tier_no_timestamp_is_no_review_data() -> None:
    assert liveness_tier(4.5, 0, None, REF) == TIER_NO_REVIEW_DATA
    # Even with a review count, a missing timestamp means no recency evidence.
    assert liveness_tier(4.5, 50, None, REF) == TIER_NO_REVIEW_DATA


def test_tier_stale_low_volume_is_stale_verify_not_inactive() -> None:
    # Very old but only 3 reviews: recency < 0.25 but the < 10 review floor
    # keeps it out of likely_inactive → stale_verify.
    r = recency_component(3, _ago(1677), REF)
    assert r < STALE_VERIFY_RECENCY
    assert liveness_tier(4.0, 3, _ago(1677), REF) == TIER_STALE_VERIFY


def test_tier_fresh_is_ok() -> None:
    assert liveness_tier(4.7, 480, _ago(20), REF) == TIER_OK


# --- full score + edges ---


def test_compute_liveness_zero_reviews_none_rating() -> None:
    # count=0, rating=None: recency neutral (0.5), quality at the prior, pop ~0.
    score = compute_liveness(None, 0, None, REF)
    assert 0.0 < score < 1.0


def test_compute_liveness_fresh_popular_beats_stale_unpopular() -> None:
    fresh = compute_liveness(4.7, 480, _ago(20), REF)
    stale = compute_liveness(3.0, 47, _ago(772), REF)
    assert fresh > stale


def test_compute_liveness_in_unit_range() -> None:
    for rating, count, newest in [
        (None, 0, None),
        (5.0, 10164, _ago(1)),
        (1.0, 1, _ago(3000)),
    ]:
        score = compute_liveness(rating, count, newest, REF)
        assert 0.0 <= score <= 1.0


# --- dampener ---


def test_dampener_null_is_no_op() -> None:
    assert liveness_dampener(None) == 1.0


def test_dampener_zero_halves() -> None:
    assert liveness_dampener(0.0) == DAMPENER_FLOOR


def test_dampener_one_is_no_op() -> None:
    assert liveness_dampener(1.0) == pytest.approx(1.0)


def test_dampener_monotonic() -> None:
    assert liveness_dampener(0.2) < liveness_dampener(0.8)
