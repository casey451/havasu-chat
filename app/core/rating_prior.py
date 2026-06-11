"""WS-2 Bayesian rating prior — volume-weighted rating sort (Track B2).

The raw ``google_rating DESC`` sort let a 5.0-from-3-reviews listing outrank a
4.7-from-400 one. The fix is the standard Bayesian shrinkage score

    score = (R*n + m*C) / (n + C)

where ``R`` is the listing's rating, ``n`` its review count, ``m`` the
catalog-wide review-weighted mean rating, and ``C`` the prior weight (how many
"phantom" reviews at the global mean every listing starts with).

Calibration (scratch/TRACK_B_DATA_PREP_2026-06-10.md §3, 2026-06-10 prod
export, 1,910 rated providers): C=25 leaves the review-rich head untouched
(top-20 identical to the raw sort) while pulling thin-review outliers toward
the mean in the service-category tail — exactly where the audit's WS-2 wants
the correction. C=100 starts reshuffling the head (13/20 overlap): too
aggressive. C=10/50 behave like 25 at the head; 25 is the middle of the
spec's C≈25–50 range and the value we ship.

``m`` is computed live (review-weighted mean over active, non-draft, rated
providers) and cached for :data:`GLOBAL_MEAN_TTL_SECONDS`; the measured prod
value (≈4.47) is the fallback when the catalog has no rated rows or the
aggregate errors. A NULL rating yields a NULL score (sorts last, as before);
``n`` is COALESCEd to 0, so a rated-but-uncounted row scores exactly ``m``.

This module owns the SQL expression; the liveness dampener
(``app.core.liveness``) keeps multiplying the score at the sort sites, same
as it multiplied the raw rating (bury-don't-remove is orthogonal to the
prior). ORM imports stay inside functions (import-cycle gotcha #17).
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Prior weight C — see module docstring for the calibration. One value, fixed:
# tunable constants invite drift between page and FAQ copy.
BAYESIAN_PRIOR_WEIGHT = 25.0

# Fallback m: the review-weighted global mean measured on the 2026-06-10 prod
# export. Used only when the live aggregate is empty or unavailable.
DEFAULT_GLOBAL_MEAN_RATING = 4.47

# m moves glacially (thousands of reviews behind it), so a long TTL is safe;
# the cache exists to keep the aggregate off every listing-page query.
GLOBAL_MEAN_TTL_SECONDS = 6 * 3600.0

_mean_cache: tuple[float, float] | None = None  # (value, monotonic_fetched_at)


def reset_global_mean_cache() -> None:
    """Drop the cached global mean. Test seam."""
    global _mean_cache  # noqa: PLW0603 — module-level cache by design
    _mean_cache = None


def global_mean_rating(db) -> float:
    """Review-weighted mean rating over live rated providers, TTL-cached.

    ``sum(rating * n) / sum(n)`` rather than a plain AVG: the prior should pull
    thin listings toward where the *review mass* sits, not toward an average
    that 1-review listings can drag around. Any failure (or an empty catalog)
    falls back to :data:`DEFAULT_GLOBAL_MEAN_RATING` — ranking must never 500 a
    listing page.
    """
    global _mean_cache  # noqa: PLW0603 — module-level cache by design
    now = time.monotonic()
    if _mean_cache is not None and now - _mean_cache[1] < GLOBAL_MEAN_TTL_SECONDS:
        return _mean_cache[0]

    from sqlalchemy import func as sa_func

    from app.db.models import Provider

    try:
        num, den = db.query(
            sa_func.sum(Provider.google_rating * Provider.google_review_count),
            sa_func.sum(Provider.google_review_count),
        ).filter(
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            Provider.google_rating.isnot(None),
            Provider.google_review_count.isnot(None),
            Provider.google_review_count > 0,
        ).one()
        value = float(num) / float(den) if num is not None and den else None
    except Exception:  # pragma: no cover - defensive: aggregate must not 500 pages
        logger.warning("global_mean_rating aggregate failed; using fallback", exc_info=True)
        value = None

    if value is None or not (1.0 <= value <= 5.0):
        value = DEFAULT_GLOBAL_MEAN_RATING
    _mean_cache = (value, now)
    return value


def bayesian_rating_expr(m: float):
    """SQL expression for the shrunk rating score, NULL when rating is NULL.

    ``(R * COALESCE(n, 0) + m * C) / (COALESCE(n, 0) + C)`` — NULL ``R``
    propagates to a NULL score (callers sort ``nullslast()``, matching the old
    raw-rating behavior for unrated rows).
    """
    from sqlalchemy import func as sa_func

    from app.db.models import Provider

    n = sa_func.coalesce(Provider.google_review_count, 0)
    c = BAYESIAN_PRIOR_WEIGHT
    return (Provider.google_rating * n + m * c) / (n + c)


def bayesian_score(rating: float | None, review_count: int | None, m: float) -> float | None:
    """Pure-Python mirror of :func:`bayesian_rating_expr` (tests + offline use)."""
    if rating is None:
        return None
    n = float(review_count or 0)
    c = BAYESIAN_PRIOR_WEIGHT
    return (float(rating) * n + m * c) / (n + c)
