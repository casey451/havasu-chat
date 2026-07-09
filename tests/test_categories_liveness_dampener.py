"""Liveness dampener on the ``/categories/{slug}`` browse surface (Sandstone).

PR #104 wired the liveness dampener into the legacy ``/category/{slug}``
surface (``app/api/routes/category_pages.py``) but the WP-5 browse loop in
``app/categories/queries.py`` shipped without it, so stale-but-once-popular
listings kept riding their old rating to the top of every category. These
tests pin the dampener on all three ordering paths of the new surface:

  1. ``category_cards`` (the card grid) — SQL ``_dampened_rating_sort_key``.
  2. ``category_listing`` SQL-only path (rating sort) — same SQL key.
  3. ``category_listing`` favorites sort — Python ``weighted_favorites_score``
     scaled by ``liveness_dampener``.

Bury-don't-remove invariants: a stale listing still renders (never excluded),
and a NULL ``liveness_score`` changes nothing (non-Google rows unaffected).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.categories.queries import (
    CategoryFacets,
    category_cards,
    category_listing,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)


def _seed(specs: list[dict]) -> list[str]:
    """Insert active eat-drink providers from ``specs``; return entity ids.

    Each spec: name (unique-suffixed by caller), rating, review_count,
    liveness (None = no score / non-Google row).
    """
    with SessionLocal() as db:
        rows = []
        for spec in specs:
            rows.append(
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
                    source="test-liveness-dampener",
                )
            )
        db.add_all(rows)
        db.commit()
        return [p.entity_id for p in rows]


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()


def _positions(cards: list[dict], names: list[str]) -> dict[str, int]:
    order = [c["name"] for c in cards]
    return {n: order.index(n) for n in names}


def test_category_cards_stale_sinks_below_fresh_peer() -> None:
    """Card grid: identical rating/volume, low liveness sorts after fresh."""
    suf = uuid.uuid4().hex[:8]
    fresh, stale = f"Fresh Cafe {suf}", f"Stale Cafe {suf}"
    # Same rating and review count — only the liveness score differs.
    eids = _seed(
        [
            {"name": fresh, "rating": 4.8, "review_count": 200, "liveness": 0.95},
            {"name": stale, "rating": 4.8, "review_count": 200, "liveness": 0.05},
        ]
    )
    try:
        with SessionLocal() as db:
            cards = category_cards(db, "eat-drink", now=_NOW, limit=500)
        pos = _positions(cards, [fresh, stale])
        # Bury, don't remove: the stale row still renders…
        assert stale in {c["name"] for c in cards}
        # …but after its otherwise-identical fresh peer.
        assert pos[fresh] < pos[stale]
    finally:
        _cleanup(eids)


def test_category_cards_dampener_buries_higher_rated_stale_listing() -> None:
    """A stale 4.9 sinks below a fresh 4.2 (dampener floor halves the rating)."""
    suf = uuid.uuid4().hex[:8]
    fresh, stale = f"Fresh Diner {suf}", f"Stale Diner {suf}"
    eids = _seed(
        [
            {"name": fresh, "rating": 4.2, "review_count": 150, "liveness": 0.9},
            {"name": stale, "rating": 4.9, "review_count": 150, "liveness": 0.0},
        ]
    )
    try:
        with SessionLocal() as db:
            cards = category_cards(db, "eat-drink", now=_NOW, limit=500)
        pos = _positions(cards, [fresh, stale])
        # 4.9 * 0.5 (floor) = 2.45 < 4.2 * 0.95 — the stale row sinks.
        assert pos[fresh] < pos[stale]
    finally:
        _cleanup(eids)


def test_null_liveness_is_not_dampened() -> None:
    """NULL liveness (non-Google row / backfill pending) ranks undampened."""
    suf = uuid.uuid4().hex[:8]
    null_lv, scored = f"NoScore Grill {suf}", f"Scored Grill {suf}"
    eids = _seed(
        [
            # Identical rating; the NULL-liveness row has FEWER reviews, so if
            # the dampener wrongly penalized NULL it would lose twice over.
            {"name": null_lv, "rating": 4.6, "review_count": 50, "liveness": None},
            {"name": scored, "rating": 4.6, "review_count": 80, "liveness": 0.05},
        ]
    )
    try:
        with SessionLocal() as db:
            cards = category_cards(db, "eat-drink", now=_NOW, limit=500)
        pos = _positions(cards, [null_lv, scored])
        # NULL → multiplier 1.0: effective 4.6 beats the dampened 4.6*0.525.
        assert pos[null_lv] < pos[scored]
    finally:
        _cleanup(eids)


def test_listing_sql_rating_sort_applies_dampener(monkeypatch) -> None:
    """``category_listing`` SQL-only rating path dampens too. This path is the
    shuffle-off rollback (the daily-shuffle default supersedes it when on), so
    exercise it with ``RANKING_DAILY_SHUFFLE=0``."""
    monkeypatch.setenv("RANKING_DAILY_SHUFFLE", "0")
    suf = uuid.uuid4().hex[:8]
    fresh, stale = f"Fresh Bistro {suf}", f"Stale Bistro {suf}"
    eids = _seed(
        [
            {"name": fresh, "rating": 4.5, "review_count": 120, "liveness": 0.9},
            {"name": stale, "rating": 4.9, "review_count": 120, "liveness": 0.0},
        ]
    )
    try:
        with SessionLocal() as db:
            cards, total = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(), limit=500
            )
        names = {c["name"] for c in cards}
        assert {fresh, stale} <= names, "both rows must render (bury, never remove)"
        pos = _positions(cards, [fresh, stale])
        assert pos[fresh] < pos[stale]
        assert total >= 2
    finally:
        _cleanup(eids)


def test_high_volume_listing_outranks_thin_review_outlier() -> None:
    """4.1 ranking fix: a 3,878-review 4.6 (In-N-Out scale) ranks ABOVE a
    20-review 4.7 outlier, even with NULL liveness (no dampening on either).

    Reproduces the reported symptom and pins the volume-confidence correction.
    A high catalog mean (seeded via an anchor with most of the review mass)
    is the worst case — shrinkage alone would float the thin 4.7 above the
    thick 4.6; the log-review-count bonus keeps the credible-volume row on top.
    """
    suf = uuid.uuid4().hex[:8]
    thick, thin = f"In N Out {suf}", f"Thin Gem {suf}"
    anchor = f"Mean Anchor {suf}"  # pushes the live review-weighted mean up
    eids = _seed(
        [
            {"name": thick, "rating": 4.6, "review_count": 3878, "liveness": None},
            {"name": thin, "rating": 4.7, "review_count": 20, "liveness": None},
            {"name": anchor, "rating": 4.7, "review_count": 9000, "liveness": None},
        ]
    )
    try:
        from app.core.rating_prior import reset_global_mean_cache

        reset_global_mean_cache()
        with SessionLocal() as db:
            cards = category_cards(db, "eat-drink", now=_NOW, limit=500)
        pos = _positions(cards, [thick, thin])
        assert pos[thick] < pos[thin], "credible-volume 4.6 must outrank thin 4.7"
    finally:
        _cleanup(eids)
        from app.core.rating_prior import reset_global_mean_cache

        reset_global_mean_cache()


def test_listing_favorites_sort_applies_dampener() -> None:
    """Favorites (weighted) sort scales the Bayesian score by the dampener."""
    suf = uuid.uuid4().hex[:8]
    fresh, stale = f"Fresh Tap {suf}", f"Stale Tap {suf}"
    # Equal weighted_favorites_score inputs; only liveness separates them.
    eids = _seed(
        [
            {"name": fresh, "rating": 4.7, "review_count": 300, "liveness": 0.9},
            {"name": stale, "rating": 4.7, "review_count": 300, "liveness": 0.05},
        ]
    )
    try:
        with SessionLocal() as db:
            cards, _total = category_listing(
                db,
                "eat-drink",
                now=_NOW,
                facets=CategoryFacets(sort="favorites"),
                limit=500,
            )
        pos = _positions(cards, [fresh, stale])
        assert pos[fresh] < pos[stale]
    finally:
        _cleanup(eids)
