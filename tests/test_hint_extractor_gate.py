"""Signal gate for the per-turn hint extractor (cost/latency fix, 2026-06-04).

The gate must skip the OpenAI call entirely for messages that cannot contain
an age or location hint, pass through messages that plausibly do, and be
disableable via ``HINT_GATE=off``. The OpenAI client is patched at the module
seam (``patch.object`` on ``hint_extractor.OpenAI``) per the mock-seam
invariants in ``app/core/llm_messages.py``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.chat import hint_extractor
from app.chat.hint_extractor import (
    extract_hints,
    get_hint_extractor_telemetry,
    has_hint_signal,
    reset_hint_extractor_telemetry,
)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("HINT_GATE", raising=False)
    monkeypatch.delenv("HINT_EXTRACTOR_MODE", raising=False)
    reset_hint_extractor_telemetry()


def _mock_client(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = content
    completion.usage = None
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    return client


# --- gated out: no API call ------------------------------------------------

NO_SIGNAL_QUERIES = [
    "what's open right now",
    "good things for adults to do",
    "my kid wants something fun",  # prompt refuses bare "kid" — no signal
    "best mexican food",
    "any live music tonight",
]


@pytest.mark.parametrize("q", NO_SIGNAL_QUERIES)
def test_gate_skips_llm_when_no_signal(q: str) -> None:
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints(q) is None
    openai_cls.assert_not_called()


# --- passed through: API call happens --------------------------------------

SIGNAL_QUERIES = [
    "my 6-year-old likes BMX",
    "anything for a teenager",
    "we're staying near the channel",
    "we're in english village",
    "stuff downtown this weekend",
    "by the london bridge",
]


@pytest.mark.parametrize("q", SIGNAL_QUERIES)
def test_signal_queries_reach_llm(q: str) -> None:
    payload = json.dumps({"extracted_hints": {"age": 6, "location": None}})
    client = _mock_client(payload)
    openai_cls = MagicMock(return_value=client)
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        result = extract_hints(q)
    openai_cls.assert_called_once()
    assert result is not None
    assert result.age == 6


@pytest.mark.parametrize("q", SIGNAL_QUERIES)
def test_has_hint_signal_accepts(q: str) -> None:
    assert has_hint_signal(q)


@pytest.mark.parametrize("q", NO_SIGNAL_QUERIES)
def test_has_hint_signal_rejects(q: str) -> None:
    assert not has_hint_signal(q)


# --- signal present but model finds nothing --------------------------------


def test_signal_query_null_envelope_returns_none() -> None:
    client = _mock_client(json.dumps({"extracted_hints": None}))
    with patch.object(hint_extractor, "OpenAI", MagicMock(return_value=client)):
        assert extract_hints("open until 9 tonight?") is None


# --- kill switch ------------------------------------------------------------


def test_kill_switch_restores_per_turn_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HINT_GATE", "off")
    client = _mock_client(json.dumps({"extracted_hints": None}))
    openai_cls = MagicMock(return_value=client)
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        extract_hints("what's open right now")
    openai_cls.assert_called_once()


# --- guard rails unchanged ---------------------------------------------------


def test_empty_query_still_short_circuits() -> None:
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints("   ") is None
    openai_cls.assert_not_called()


def test_missing_api_key_still_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints("my 6-year-old likes BMX") is None
    openai_cls.assert_not_called()


# --- near-me exclusion (HANDOFF #1) -----------------------------------------

NEAR_ME_QUERIES = [
    "tacos near me",
    "best mexican food near me",
    "restaurants nearby",
    "anything fun near here",
    "coffee near by",
]


@pytest.mark.parametrize("q", NEAR_ME_QUERIES)
def test_near_me_is_not_a_signal(q: str) -> None:
    assert not has_hint_signal(q)


@pytest.mark.parametrize("q", NEAR_ME_QUERIES)
def test_near_me_skips_llm(q: str) -> None:
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints(q) is None
    openai_cls.assert_not_called()


def test_near_a_real_place_still_signals() -> None:
    # The exclusion must not swallow genuine "near <place>" hints.
    assert has_hint_signal("we're staying near the island")
    assert has_hint_signal("a hotel near the london bridge")


# --- HINT_EXTRACTOR_MODE ----------------------------------------------------


def test_mode_off_never_calls_even_with_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HINT_EXTRACTOR_MODE", "off")
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints("my 6-year-old likes BMX") is None
    openai_cls.assert_not_called()


def test_mode_always_calls_without_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HINT_EXTRACTOR_MODE", "always")
    client = _mock_client(json.dumps({"extracted_hints": None}))
    openai_cls = MagicMock(return_value=client)
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        extract_hints("what's open right now")
    openai_cls.assert_called_once()


def test_mode_conditional_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # No env set (fixture clears both) -> conditional: no-signal query is skipped.
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints("what's open right now") is None
    openai_cls.assert_not_called()


def test_mode_wins_over_legacy_hint_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # HINT_EXTRACTOR_MODE is authoritative even when the legacy alias disagrees.
    monkeypatch.setenv("HINT_GATE", "off")  # legacy -> would mean "always"
    monkeypatch.setenv("HINT_EXTRACTOR_MODE", "conditional")  # explicit wins
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints("what's open right now") is None
    openai_cls.assert_not_called()


def test_invalid_mode_falls_back_to_conditional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HINT_EXTRACTOR_MODE", "banana")
    openai_cls = MagicMock()
    with patch.object(hint_extractor, "OpenAI", openai_cls):
        assert extract_hints("what's open right now") is None
    openai_cls.assert_not_called()


# --- telemetry --------------------------------------------------------------


def test_telemetry_counts_prefilter_skip_and_call() -> None:
    client = _mock_client(json.dumps({"extracted_hints": {"age": 6, "location": None}}))
    with patch.object(hint_extractor, "OpenAI", MagicMock(return_value=client)):
        extract_hints("what's open right now")  # no signal -> skipped_prefilter
        extract_hints("my 6-year-old likes BMX")  # signal -> called
    counts = get_hint_extractor_telemetry()
    assert counts["skipped_prefilter"] == 1
    assert counts["called"] == 1
    assert counts["memoized"] == 0


def test_telemetry_counts_mode_off_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HINT_EXTRACTOR_MODE", "off")
    with patch.object(hint_extractor, "OpenAI", MagicMock()):
        extract_hints("my 6-year-old likes BMX")
    assert get_hint_extractor_telemetry()["skipped_mode_off"] == 1
