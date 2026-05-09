"""Backlog #48 — negation-aware skip in ``_enforce_low_tier_phone``."""

from __future__ import annotations

import pytest

from app.chat import tier2_formatter as tf
from app.chat.confidence_tier import ConfidenceTier

_FLAG = tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR


def _low_row(*, phone: str, name: str = "Test Biz") -> dict:
    return {
        "type": "provider",
        "provider_name": name,
        "phone": phone,
        "confidence_hint": ConfidenceTier.LOW.value,
    }


@pytest.mark.parametrize(
    "voice",
    [
        "I don't have any plumbers listed in the Lake Havasu catalog.",
        "Sorry — no plumbers listed here.",
        "Not in the catalog — try contributing one.",
        "I don't see any plumbing businesses in our rows.",
        "No results for that trade.",
    ],
)
def test_negation_voice_skips_phone_append(monkeypatch: pytest.MonkeyPatch, voice: str) -> None:
    monkeypatch.setenv(_FLAG, "true")
    rows = [_low_row(phone="(928) 732-0099")]
    out = tf._enforce_low_tier_phone(voice, rows)
    assert out == voice
    assert "Their listed number is" not in out


def test_without_negation_still_appends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_FLAG, "true")
    voice = "Crestline Plumbing might work for that job."
    rows = [_low_row(phone="(928) 855-3333", name="Crestline Plumbing")]
    out = tf._enforce_low_tier_phone(voice, rows)
    assert "Their listed number is (928) 855-3333" in out
    assert "recommend calling to confirm" in out.lower()
