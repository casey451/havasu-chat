"""Unit tests for Lane CT1 — deterministic confidence-tier classifier.

Spec: ``docs/maintainability/ui_data_correctness_spec.md`` §1.2 (the
canonical confidence-band table tied to ``last_verified_at`` +
``verification_method``).

This lane ships the module + tests only. Formatter integration is the
forthcoming Lane CT2.

All record fixtures are duck-typed via ``types.SimpleNamespace`` so
nothing here touches the database — pattern from
``tests/test_home_queries_lane_a.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.chat import confidence_tier as ct
from app.chat.confidence_tier import (
    ConfidenceAssessment,
    ConfidenceTier,
    classify_confidence,
    hedge_phrase,
    is_stale,
)

# ─────────── fixtures / helpers ───────────


_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0)


def _record(
    *,
    last_verified_at: datetime | None = None,
    verification_method: str | None = None,
) -> SimpleNamespace:
    """Duck-typed record (Provider/Event-shaped) for the classifier."""
    return SimpleNamespace(
        last_verified_at=last_verified_at,
        verification_method=verification_method,
    )


def _ago(days: int) -> datetime:
    return _FIXED_NOW - timedelta(days=days)


# ─────────── HIGH-tier cases ───────────


def test_high_owner_confirmed_within_30_days() -> None:
    rec = _record(last_verified_at=_ago(5), verification_method="owner_confirmed")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.HIGH
    assert result.age_days == 5
    assert result.method == "owner_confirmed"


def test_high_owner_confirmed_at_30_day_boundary() -> None:
    """``≤ 30`` is inclusive — a record verified exactly 30 days ago is HIGH."""
    rec = _record(last_verified_at=_ago(30), verification_method="owner_confirmed")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.HIGH
    assert result.age_days == 30


def test_high_manual_within_30_days() -> None:
    rec = _record(last_verified_at=_ago(10), verification_method="manual")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.HIGH
    assert result.age_days == 10


def test_high_scraper_within_7_days() -> None:
    rec = _record(last_verified_at=_ago(5), verification_method="scraper")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.HIGH
    assert result.age_days == 5


def test_high_npi_registry_within_30_days() -> None:
    rec = _record(last_verified_at=_ago(20), verification_method="npi_registry")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.HIGH
    assert result.age_days == 20


# ─────────── MEDIUM-tier cases ───────────


def test_medium_scraper_8_to_30_days() -> None:
    """Scraper between 8 and 30 days drops out of HIGH but stays MEDIUM."""
    rec = _record(last_verified_at=_ago(15), verification_method="scraper")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.MEDIUM
    assert result.age_days == 15


def test_medium_manual_31_to_90_days() -> None:
    """Manual between 31 and 90 days falls to MEDIUM."""
    rec = _record(last_verified_at=_ago(60), verification_method="manual")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.MEDIUM
    assert result.age_days == 60


# ─────────── LOW-tier cases ───────────


def test_low_no_verification_record() -> None:
    """Missing ``last_verified_at`` → LOW with no datetime arithmetic."""
    rec = _record(last_verified_at=None, verification_method="manual")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.LOW
    assert result.age_days is None


def test_low_method_none() -> None:
    """A recent record with method='none' is LOW — method overrides age."""
    rec = _record(last_verified_at=_ago(2), verification_method="none")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.LOW
    # Age is still surfaced for debug, but the tier is locked LOW.
    assert result.age_days == 2


def test_low_method_missing() -> None:
    """``method=None`` (column unset) is LOW even if recently verified."""
    rec = _record(last_verified_at=_ago(2), verification_method=None)
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.LOW


def test_low_older_than_90_days() -> None:
    """Manual past 90 days falls out of MEDIUM into LOW."""
    rec = _record(last_verified_at=_ago(100), verification_method="manual")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.LOW
    assert result.age_days == 100


# ─────────── now/clock plumbing ───────────


def test_classify_uses_now_lake_havasu_when_now_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``now`` is None, the classifier reads ``now_lake_havasu()``.

    We patch the symbol the module imported at module load (``ct.now_lake_havasu``);
    a fixed return makes the age math deterministic.
    """
    fixed = datetime(2026, 5, 8, 12, 0, 0)
    monkeypatch.setattr(ct, "now_lake_havasu", lambda: fixed)

    rec = _record(last_verified_at=fixed - timedelta(days=3), verification_method="manual")
    result = classify_confidence(rec)  # no ``now`` kwarg — must use the patch
    assert result.tier == ConfidenceTier.HIGH
    assert result.age_days == 3


def test_classify_defensive_on_object_without_fields() -> None:
    """A duck-typed object with no relevant attrs returns LOW, not AttributeError."""

    class Bare:
        pass

    result = classify_confidence(Bare(), now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.LOW
    assert result.age_days is None
    assert result.method is None


# ─────────── assessment carrier shape ───────────


def test_assessment_carries_age_days_for_high() -> None:
    rec = _record(last_verified_at=_ago(7), verification_method="owner_confirmed")
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.HIGH
    assert isinstance(result.age_days, int)
    assert result.age_days == 7


def test_assessment_carries_age_days_none_for_unverified() -> None:
    rec = _record(last_verified_at=None, verification_method=None)
    result = classify_confidence(rec, now=_FIXED_NOW)
    assert result.tier == ConfidenceTier.LOW
    assert result.age_days is None


def test_assessment_rationale_is_short_string() -> None:
    """Rationale is debug-grade prose: short, non-empty, present for every tier."""
    cases = [
        _record(last_verified_at=_ago(5), verification_method="owner_confirmed"),  # HIGH
        _record(last_verified_at=_ago(15), verification_method="scraper"),  # MEDIUM
        _record(last_verified_at=None, verification_method=None),  # LOW (no record)
        _record(last_verified_at=_ago(2), verification_method="none"),  # LOW (opt-out)
        _record(last_verified_at=_ago(120), verification_method="manual"),  # LOW (stale)
    ]
    for rec in cases:
        result: ConfidenceAssessment = classify_confidence(rec, now=_FIXED_NOW)
        assert isinstance(result.rationale, str)
        assert 0 < len(result.rationale) <= 60


# ─────────── is_stale convenience ───────────


def test_is_stale_default_30_days() -> None:
    """Default threshold is 30 days; ``>`` strict, so 30 is not stale."""
    fresh = _record(last_verified_at=_ago(29), verification_method="manual")
    stale = _record(last_verified_at=_ago(31), verification_method="manual")
    assert is_stale(fresh, now=_FIXED_NOW) is False
    assert is_stale(stale, now=_FIXED_NOW) is True


def test_is_stale_null_treated_as_stale() -> None:
    rec = _record(last_verified_at=None, verification_method=None)
    assert is_stale(rec, now=_FIXED_NOW) is True


def test_is_stale_custom_threshold() -> None:
    rec = _record(last_verified_at=_ago(10), verification_method="manual")
    assert is_stale(rec, threshold_days=7, now=_FIXED_NOW) is True
    assert is_stale(rec, threshold_days=30, now=_FIXED_NOW) is False


# ─────────── hedge_phrase ───────────


def test_hedge_phrase_high_is_empty() -> None:
    """HIGH speaks plainly — no hedge fragment."""
    assert hedge_phrase(ConfidenceTier.HIGH) == ""


def test_hedge_phrase_medium_short_and_factual() -> None:
    """MEDIUM hedge is non-empty and free of evaluative superlatives."""
    phrase = hedge_phrase(ConfidenceTier.MEDIUM)
    assert phrase
    assert isinstance(phrase, str)
    lowered = phrase.lower()
    for banned in ("best", "amazing", "perfect", "incredible", "favorite"):
        assert banned not in lowered


def test_hedge_phrase_low_recommends_calling() -> None:
    """LOW hedge nudges the caller to verify before acting."""
    phrase = hedge_phrase(ConfidenceTier.LOW).lower()
    assert "calling" in phrase or "confirm" in phrase
