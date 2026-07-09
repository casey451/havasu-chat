"""Tests for ``app.search.ranking`` composite heuristic (Phase 2B.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.search.ranking import (
    CATEGORY_MATCH_BONUS,
    NAME_MATCH_BONUS,
    REVIEW_BONUS_MAX,
    Tier2RankInputs,
    composite_rank_float,
    review_count_bonus,
    search_ranking_v2_enabled,
)


def test_composite_rank_featured_adds_25() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    r = composite_rank_float(
        Tier2RankInputs(fts_score=0.0, last_verified_at=None, featured=True, ref_now=ref)
    )
    assert r == 25.0


def test_composite_rank_verified_within_30_days_adds_30() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    lv = ref - timedelta(days=5)
    r = composite_rank_float(
        Tier2RankInputs(fts_score=1.0, last_verified_at=lv, featured=False, ref_now=ref)
    )
    assert r == 31.0


def test_composite_rank_verified_30_to_90_days_adds_15() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    lv = ref - timedelta(days=45)
    r = composite_rank_float(
        Tier2RankInputs(fts_score=0.0, last_verified_at=lv, featured=False, ref_now=ref)
    )
    assert r == 15.0


def test_composite_rank_stale_verification_zero_bonus() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    lv = ref - timedelta(days=100)
    r = composite_rank_float(
        Tier2RankInputs(fts_score=2.0, last_verified_at=lv, featured=False, ref_now=ref)
    )
    assert r == 2.0


def test_composite_rank_null_last_verified_no_bonus() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    r = composite_rank_float(
        Tier2RankInputs(fts_score=3.0, last_verified_at=None, featured=False, ref_now=ref)
    )
    assert r == 3.0


def test_composite_rank_stacks_featured_and_fresh() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    lv = ref - timedelta(days=3)
    r = composite_rank_float(
        Tier2RankInputs(fts_score=0.5, last_verified_at=lv, featured=True, ref_now=ref)
    )
    assert r == 0.5 + 30.0 + 25.0


# --- liveness dampener (bury stale listings; NULL → unchanged) ---


def test_composite_rank_null_liveness_unchanged() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    base = composite_rank_float(
        Tier2RankInputs(fts_score=10.0, last_verified_at=None, featured=False, ref_now=ref)
    )
    with_null = composite_rank_float(
        Tier2RankInputs(
            fts_score=10.0,
            last_verified_at=None,
            featured=False,
            ref_now=ref,
            liveness_score=None,
        )
    )
    assert base == with_null == 10.0


def test_composite_rank_zero_liveness_halves() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    r = composite_rank_float(
        Tier2RankInputs(
            fts_score=10.0,
            last_verified_at=None,
            featured=False,
            ref_now=ref,
            liveness_score=0.0,
        )
    )
    assert r == 5.0


def test_composite_rank_liveness_orders_equal_base() -> None:
    ref = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    def score(liveness: float) -> float:
        return composite_rank_float(
            Tier2RankInputs(
                fts_score=10.0,
                last_verified_at=None,
                featured=False,
                ref_now=ref,
                liveness_score=liveness,
            )
        )

    assert score(0.9) > score(0.2)


# ── ranking v2: category-assignment match + bounded review lift (item 6) ──────
_REF = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _mk(**kw: object) -> Tier2RankInputs:
    base: dict[str, object] = dict(
        fts_score=0.0, last_verified_at=None, featured=False, ref_now=_REF
    )
    base.update(kw)
    return Tier2RankInputs(**base)  # type: ignore[arg-type]


def test_v1_inputs_unchanged_by_v2_defaults() -> None:
    # category_match=False, review_count=None contribute nothing → the v1 sum.
    assert composite_rank_float(_mk(fts_score=5.0, featured=True)) == 5.0 + 25.0


def test_category_match_adds_bonus() -> None:
    assert composite_rank_float(_mk(category_match=True)) == CATEGORY_MATCH_BONUS


def test_field_identity_ladder_name_gt_category_gt_description() -> None:
    # At equal everything-else: NAME (60) > CATEGORY (35) > description/FTS-only (0).
    name = composite_rank_float(_mk(name_match=True))
    category = composite_rank_float(_mk(category_match=True))
    description = composite_rank_float(_mk())
    assert name > category > description
    assert (name, category, description) == (NAME_MATCH_BONUS, CATEGORY_MATCH_BONUS, 0.0)


def test_review_bonus_is_bounded_and_monotonic() -> None:
    assert review_count_bonus(None) == 0.0
    assert review_count_bonus(0) == 0.0
    assert 0.0 < review_count_bonus(5) < review_count_bonus(500) <= REVIEW_BONUS_MAX
    # Even an absurd count never exceeds the cap (log-normalised, clamped).
    assert review_count_bonus(10_000_000) <= REVIEW_BONUS_MAX + 1e-9


def test_review_count_breaks_ties_among_equal_relevance() -> None:
    low = composite_rank_float(_mk(name_match=True, review_count=3))
    high = composite_rank_float(_mk(name_match=True, review_count=800))
    assert high > low  # more reviews wins only when the relevance tier is equal


def test_high_review_weak_match_cannot_beat_a_zero_review_name_match() -> None:
    # The core guarantee: review count can't let a weakly-relevant listing dominate.
    name_no_reviews = composite_rank_float(_mk(name_match=True, review_count=0))
    category_max_reviews = composite_rank_float(_mk(category_match=True, review_count=10_164))
    description_max_reviews = composite_rank_float(_mk(review_count=10_164))
    assert name_no_reviews > category_max_reviews > description_max_reviews


def test_v2_flag_reads_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("SEARCH_RANKING_V2", raising=False)
    assert search_ranking_v2_enabled() is False
    monkeypatch.setenv("SEARCH_RANKING_V2", "1")
    assert search_ranking_v2_enabled() is True
    monkeypatch.setenv("SEARCH_RANKING_V2", "off")
    assert search_ranking_v2_enabled() is False


def test_tier2_sql_adds_v2_terms_only_when_provided() -> None:
    from sqlalchemy import literal_column
    from sqlalchemy.dialects import postgresql

    from app.db.models import Entity, Provider
    from app.search.ranking import tier2_rank_score_sql

    def _sql(**kw: object) -> str:
        expr = tier2_rank_score_sql(
            "(plumber)",
            last_verified_col=Entity.last_verified_at,
            featured_col=Provider.featured,
            ref_now=_REF,
            **kw,  # type: ignore[arg-type]
        )
        return str(expr.compile(dialect=postgresql.dialect())).lower()

    v1 = _sql()
    v2 = _sql(
        category_match_cond=literal_column("1=1"),
        review_count_col=Provider.google_review_count,
    )
    assert "least" not in v1 and "1=1" not in v1  # v1 order untouched
    assert "least" in v2  # the bounded review lift
    assert "1=1" in v2  # the reused assigned-category EXISTS condition
