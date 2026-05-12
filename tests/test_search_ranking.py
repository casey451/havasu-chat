"""Tests for ``app.search.ranking`` composite heuristic (Phase 2B.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.search.ranking import Tier2RankInputs, composite_rank_float


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
