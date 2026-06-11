"""Liveness dampener on the home eat row and chat business lists.

Follow-up to the /categories browse fix (PR #144): two more surfaces ranked
purely on rating/review volume with no recency signal.

  1. ``app.home.queries_c._rating_sort_key`` — SQL ordering behind the home
     eat row: the rating term is scaled by the dampener
     (``FLOOR + (1-FLOOR) * COALESCE(liveness_score, 1)``).
  2. ``app.chat.intents.queries._provider_sort_key`` — Python sort behind
     chat's business lists: rating scaled by ``liveness_dampener``.

Bury-don't-remove invariants hold on both: stale rows still appear, and
NULL ``liveness_score`` (non-Google rows / backfill pending) is a no-op.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from sqlalchemy import delete

from app.chat.intents.queries import _provider_sort_key
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.home.queries_c import _rating_sort_key


def _seed(specs: list[dict]) -> list[str]:
    """Insert active eat-drink providers; return entity ids."""
    with SessionLocal() as db:
        rows = [
            Provider(
                provider_name=spec["name"],
                category="restaurant",
                subcategory="restaurants",
                google_primary_category="restaurant",
                google_rating=spec["rating"],
                google_review_count=spec["review_count"],
                liveness_score=spec["liveness"],
                verified=False,
                draft=False,
                is_active=True,
                pending_review=False,
                source="test-liveness-home-chat",
            )
            for spec in specs
        ]
        db.add_all(rows)
        db.commit()
        return [p.entity_id for p in rows]


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()


# --- 1. home eat row SQL ordering -----------------------------------------


def _sql_order(names: list[str]) -> list[str]:
    """Names from a ``_rating_sort_key``-ordered query, filtered to ours."""
    from app.core.rating_prior import reset_global_mean_cache

    reset_global_mean_cache()  # deterministic m per test (module TTL cache)
    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.provider_name.in_(names))
            .order_by(*_rating_sort_key(db))
            .all()
        )
    return [r.provider_name for r in rows]


def test_home_rating_sort_buries_stale_listing() -> None:
    """A stale 4.9 sinks below a fresh 4.2 (equal review mass)."""
    suf = uuid.uuid4().hex[:8]
    fresh, stale = f"Fresh Kitchen {suf}", f"Stale Kitchen {suf}"
    eids = _seed(
        [
            {"name": fresh, "rating": 4.2, "review_count": 150, "liveness": 0.9},
            {"name": stale, "rating": 4.9, "review_count": 150, "liveness": 0.0},
        ]
    )
    try:
        order = _sql_order([fresh, stale])
        # Bury, don't remove: both rows still surface…
        assert set(order) == {fresh, stale}
        # …but the stale row sinks: equal n means equal Bayesian shrinkage
        # (WS-2 preserves rating order at matched review counts), and the
        # dampener floor halves the stale score: shrunk(4.9) * 0.5 <
        # shrunk(4.2) * 0.95 for any m in [1, 5].
        assert order == [fresh, stale]
    finally:
        _cleanup(eids)


def test_home_rating_sort_null_liveness_unchanged() -> None:
    """NULL liveness rows keep their undampened rating (no false burial)."""
    suf = uuid.uuid4().hex[:8]
    null_lv, scored = f"NoScore Cantina {suf}", f"Scored Cantina {suf}"
    eids = _seed(
        [
            {"name": null_lv, "rating": 4.6, "review_count": 50, "liveness": None},
            {"name": scored, "rating": 4.6, "review_count": 80, "liveness": 0.05},
        ]
    )
    try:
        # NULL → multiplier 1.0: 4.6 beats the dampened 4.6 * 0.525 even
        # though the scored row has more reviews.
        assert _sql_order([null_lv, scored]) == [null_lv, scored]
    finally:
        _cleanup(eids)


# --- 2. chat business-list Python ordering ---------------------------------


def _p(rating, count, liveness):
    return SimpleNamespace(
        google_rating=rating, google_review_count=count, liveness_score=liveness
    )


def test_chat_sort_key_buries_stale_listing() -> None:
    """reverse=True sort: stale 4.9 ranks below fresh 4.2."""
    fresh = _p(4.2, 150, 0.9)
    stale = _p(4.9, 150, 0.0)
    rows = [stale, fresh]
    rows.sort(key=_provider_sort_key, reverse=True)
    assert rows == [fresh, stale]


def test_chat_sort_key_null_liveness_is_noop() -> None:
    """NULL liveness never dampens; ties broken by review count as before."""
    a = _p(4.5, 100, None)
    b = _p(4.5, 80, None)
    rows = [b, a]
    rows.sort(key=_provider_sort_key, reverse=True)
    assert rows == [a, b]


def test_chat_sort_key_unrated_still_sorts_last() -> None:
    """The rated-first tier is unaffected by the dampener."""
    rated_stale = _p(3.0, 20, 0.0)  # dampened to 1.5, but still rated
    unrated = _p(None, 0, 0.9)
    rows = [unrated, rated_stale]
    rows.sort(key=_provider_sort_key, reverse=True)
    assert rows == [rated_stale, unrated]
