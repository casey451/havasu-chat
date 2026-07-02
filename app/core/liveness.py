"""Listing liveness scoring — bury likely-dead businesses, never remove them.

Pure functions only — no DB or ORM imports (mirrors ``app/core/ranking.py``).

The liveness score (0–1) blends three signals: how recently the newest review
landed, a Bayesian-smoothed rating, and review-count popularity. It feeds a
*multiplicative dampener* on existing rank scores (see :func:`liveness_dampener`)
so a stale listing sinks but is never excluded — Casey's locked preference is
that a false-negative (dead business still listed, ranked low) is acceptable but
a false-positive (active business hidden) is not.

Validated against ``outputs/listing_liveness_ranking.xlsx`` (May 18 2026 pull,
2,647 places): 2,008 ok / 164 stale_verify / 90 likely_inactive / 385
no_review_data. The constants below are the validated values — Casey iterates on
them via the xlsx prototype first, so treat them as locked here.

Known drift: recency decays between data pulls but the stored score is static.
Acceptable — pulls are roughly monthly and the backfill recomputes. Pass
``ref_now`` explicitly for testability.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

# --- liveness component weights (sum to 1.0) ---
RECENCY_WEIGHT = 0.45
QUALITY_WEIGHT = 0.35
POPULARITY_WEIGHT = 0.20

# --- recency: exponential half-life decay with volume-adaptive grace ---
# grace = GRACE_BASE_DAYS + GRACE_VOLUME_SCALE / sqrt(max(review_count, 1)).
# A low-volume business going quiet is normal; a high-volume one going silent is
# a death signal, so grace shrinks as review volume grows.
GRACE_BASE_DAYS = 90.0
GRACE_VOLUME_SCALE = 1095.0
# Neutral recency when no review timestamp is available (no evidence either way).
NO_REVIEW_RECENCY = 0.5

# --- quality: Bayesian rating with prior pulling toward the citywide mean ---
# GLOBAL_MEAN is the citywide review-weighted mean from the May 2026 pull;
# recompute opportunistically on future pulls. BAYESIAN_PRIOR_M is the prior
# weight (in pseudo-reviews). MAX_RATING scales the result into 0–1.
GLOBAL_MEAN = 4.46
BAYESIAN_PRIOR_M = 10.0
MAX_RATING = 5.0

# --- popularity: log review count normalized by the busiest listing ---
MAX_COUNT = 10164

# --- tier thresholds (admin/triage labels, not user-facing) ---
LIKELY_INACTIVE_MIN_REVIEWS = 10
LIKELY_INACTIVE_RECENCY = 0.15
STALE_VERIFY_RECENCY = 0.25

TIER_LIKELY_INACTIVE = "likely_inactive"
TIER_STALE_VERIFY = "stale_verify"
TIER_NO_REVIEW_DATA = "no_review_data"
TIER_OK = "ok"

# --- dampener: final = base_rank * (FLOOR + (1 - FLOOR) * liveness) ---
# Worst case (liveness=0) halves a listing's rank; it is never zeroed. NULL
# liveness is treated as 1.0 (no dampening) so non-Google entities are unaffected.
DAMPENER_FLOOR = 0.5



def _days_since(newest_review_at: datetime, ref_now: datetime) -> float:
    """Whole + fractional days between ``newest_review_at`` and ``ref_now``.

    Both are coerced to UTC-aware before subtraction so naive timestamps (e.g.
    SQLite round-trips) compare cleanly. Negative deltas (a review timestamped
    slightly ahead of ``ref_now``) clamp to 0.
    """
    nr = newest_review_at if newest_review_at.tzinfo else newest_review_at.replace(tzinfo=UTC)
    ref = ref_now if ref_now.tzinfo else ref_now.replace(tzinfo=UTC)
    return max(0.0, (ref - nr).total_seconds() / 86400.0)


def recency_component(
    review_count: int | None,
    newest_review_at: datetime | None,
    ref_now: datetime,
) -> float:
    """Exponential half-life decay of the newest review, 0–1.

    ``recency = exp(-ln(2) * days_since_newest / grace)`` where
    ``grace = GRACE_BASE_DAYS + GRACE_VOLUME_SCALE / sqrt(max(review_count, 1))``.
    Returns :data:`NO_REVIEW_RECENCY` when no review timestamp is available.
    """
    if newest_review_at is None:
        return NO_REVIEW_RECENCY
    n = max(1, int(review_count or 0))
    grace = GRACE_BASE_DAYS + GRACE_VOLUME_SCALE / math.sqrt(n)
    days = _days_since(newest_review_at, ref_now)
    return math.exp(-math.log(2.0) * days / grace)


def quality_component(rating: float | None, review_count: int | None) -> float:
    """Bayesian-smoothed rating scaled to 0–1.

    ``((rating * n) + (GLOBAL_MEAN * m)) / ((n + m) * MAX_RATING)``. A null rating
    falls back to :data:`GLOBAL_MEAN` so the smoothed value lands at the prior.
    """
    n = max(0, int(review_count or 0))
    r = GLOBAL_MEAN if rating is None else float(rating)
    return ((r * n) + (GLOBAL_MEAN * BAYESIAN_PRIOR_M)) / ((n + BAYESIAN_PRIOR_M) * MAX_RATING)


def popularity_component(review_count: int | None) -> float:
    """Log-scaled review count normalized by the busiest listing, 0–1."""
    n = max(0, int(review_count or 0))
    return math.log1p(n) / math.log1p(MAX_COUNT)


def compute_liveness(
    rating: float | None,
    review_count: int | None,
    newest_review_at: datetime | None,
    ref_now: datetime,
) -> float:
    """Blend recency, quality, and popularity into a 0–1 liveness score."""
    recency = recency_component(review_count, newest_review_at, ref_now)
    quality = quality_component(rating, review_count)
    popularity = popularity_component(review_count)
    return RECENCY_WEIGHT * recency + QUALITY_WEIGHT * quality + POPULARITY_WEIGHT * popularity


def liveness_tier(
    rating: float | None,
    review_count: int | None,
    newest_review_at: datetime | None,
    ref_now: datetime,
) -> str:
    """Admin/triage tier label for a listing (not user-facing).

    - ``no_review_data``: no review timestamp.
    - ``likely_inactive``: ``review_count >= 10`` AND recency < 0.15.
    - ``stale_verify``: recency < 0.25.
    - ``ok``: everything else.
    """
    if newest_review_at is None:
        return TIER_NO_REVIEW_DATA
    recency = recency_component(review_count, newest_review_at, ref_now)
    n = int(review_count or 0)
    if n >= LIKELY_INACTIVE_MIN_REVIEWS and recency < LIKELY_INACTIVE_RECENCY:
        return TIER_LIKELY_INACTIVE
    if recency < STALE_VERIFY_RECENCY:
        return TIER_STALE_VERIFY
    return TIER_OK


def liveness_dampener(liveness_score: float | None) -> float:
    """Multiplier applied to a base rank score: ``FLOOR + (1 - FLOOR) * liveness``.

    NULL liveness returns 1.0 (no dampening) so non-Google-sourced entities are
    unaffected. ``liveness=0`` returns :data:`DAMPENER_FLOOR` (halves the rank);
    ``liveness=1`` returns 1.0.
    """
    if liveness_score is None:
        return 1.0
    return DAMPENER_FLOOR + (1.0 - DAMPENER_FLOOR) * float(liveness_score)


__all__ = [
    "DAMPENER_FLOOR",
    "GLOBAL_MEAN",
    "MAX_COUNT",
    "compute_liveness",
    "liveness_dampener",
    "liveness_tier",
    "popularity_component",
    "quality_component",
    "recency_component",
]
