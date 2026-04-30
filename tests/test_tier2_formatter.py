"""Tests for ``app.chat.tier2_formatter`` — Anthropic mocked for LLM-only paths."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.chat import tier2_catalog_render
from app.chat import tier2_formatter as tf


def _msg(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=120,
        output_tokens=40,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[block], usage=usage)


def _program_row(name: str = "Altitude") -> dict:
    return {
        "type": "program",
        "id": "x",
        "name": name,
        "provider_name": "Prov",
        "activity_category": "Fun",
        "age_range": None,
        "schedule_days": ["Sat"],
        "schedule_hours": "09:00-11:00",
        "cost": None,
        "description": "",
        "tags": [],
    }


def test_simple_query_returns_nonempty() -> None:
    rows = [
        {
            "type": "event",
            "name": "Fair",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Park",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    out, tin, tout = tf.format("what is on", rows)
    assert out == "Fair on January 1, 2030 from 10:00 AM to 12:00 PM at Park."
    assert tin == 0 and tout == 0


def test_explicit_rec_instructions_removed_from_tier2_formatter() -> None:
    prompt = Path(__file__).resolve().parents[1] / "prompts" / "tier2_formatter.txt"
    body = prompt.read_text(encoding="utf-8").lower()
    for cue in ("pick one", "which is best", "worth it", "your favorite", "what would you do"):
        assert cue not in body


def test_explicit_rec_user_message_contains_query_text() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("Pick Altitude.")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            tf.format("pick one thing to do Saturday", [_program_row()])
    user = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "pick one thing to do Saturday" in user


def test_format_empty_rows_returns_deterministic_no_matching_catalog_rows() -> None:
    fake = MagicMock()
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            out, tin, tout = tf.format("anything", [])
    assert out == "No matching catalog rows."
    assert tin == 0 and tout == 0
    fake.messages.create.assert_not_called()


def test_sdk_error_returns_none() -> None:
    fake = MagicMock()
    fake.messages.create.side_effect = RuntimeError("boom")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", [_program_row("E")])
    assert text is None and tin is None and tout is None


def test_empty_model_text_returns_none() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("   ")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", [_program_row()])
    assert text is None and tin == 120 and tout == 40


def test_invocation_kwargs() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("ok")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            tf.format("events tomorrow", [_program_row()])
    kw = fake.messages.create.call_args.kwargs
    assert kw["max_tokens"] == 400
    assert kw["temperature"] == 0.3
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_system_prompt_contains_grounding_guardrails() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("ok")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            tf.format("events tomorrow", [_program_row()])

    system_text = fake.messages.create.call_args.kwargs["system"][0]["text"]
    assert "Grounding guardrails (additive to §6.7)" in system_text
    assert "every concrete detail must be directly row-backed" in system_text
    assert (
        "Never invent venue, address, event time window, duration, organizer, or pricing details."
        in system_text
    )


def test_format_all_event_rows_returns_deterministic_tuple() -> None:
    rows = [
        {
            "type": "event",
            "name": "A",
            "date": "2030-01-01",
            "start_time": "09:00",
            "end_time": "10:00",
            "location_name": "L",
            "description": "",
            "event_url": "",
            "tags": [],
        },
        {
            "type": "event",
            "name": "B",
            "date": "2030-01-02",
            "start_time": "11:00",
            "end_time": "12:00",
            "location_name": "M",
            "description": "",
            "event_url": "",
            "tags": [],
        },
    ]
    fake = MagicMock()
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", rows)
    assert text is not None
    assert tin == 0 and tout == 0
    fake.messages.create.assert_not_called()


def test_format_mixed_event_and_program_calls_llm() -> None:
    rows = [
        {
            "type": "event",
            "name": "E",
            "date": "2030-01-01",
            "start_time": "09:00",
            "end_time": "10:00",
            "location_name": "L",
            "description": "",
            "event_url": "",
            "tags": [],
        },
        _program_row(),
    ]
    fake = MagicMock()
    fake.messages.create.return_value = _msg("mixed ok")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", rows)
    assert text == "mixed ok"
    assert tin == 120 and tout == 40
    fake.messages.create.assert_called_once()


def test_format_all_program_rows_calls_llm() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("programs ok")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", [_program_row(), _program_row("Other")])
    assert text == "programs ok"
    fake.messages.create.assert_called_once()


def test_format_render_exception_returns_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(_q: str, _rows: list) -> str:
        raise RuntimeError("render boom")

    monkeypatch.setattr(tier2_catalog_render, "render_tier2_events", boom)
    rows = [
        {
            "type": "event",
            "name": "X",
            "date": "2030-01-01",
            "start_time": "09:00",
            "end_time": "10:00",
            "location_name": "L",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    text, tin, tout = tf.format("q", rows)
    assert text is None and tin is None and tout is None
    assert any("deterministic render failed" in r.message for r in caplog.records)


def test_strip_legacy_fallback_removes_imported_prefix_after_date_time_header() -> None:
    """Catalog descriptions store Date:/Time: lines before the legacy RS scaffolding."""
    raw = (
        "Date: 2026-05-15\nTime: 09:00\n\n"
        "Imported from River Scene. Event URL: https://riverscenemagazine.com/events/x/ "
        "Real text."
    )
    out = tf._strip_legacy_fallback(raw)
    assert out.startswith("Date: 2026-05-15")
    assert "Time: 09:00" in out
    assert "Imported from River Scene" not in out
    assert "Real text." in out


def test_legacy_fallback_regex_matches_at_nonzero_offset() -> None:
    raw = (
        "Header line\n\nImported from River Scene. Event URL: https://riverscenemagazine.com/events/z/ "
        "Tail content."
    )
    m = tf._LEGACY_FALLBACK_RE.search(raw)
    assert m is not None and m.start() > 0
    assert tf._strip_legacy_fallback(raw) == "Header line\n\nTail content."


def test_strip_legacy_fallback_passes_clean_description() -> None:
    raw = "A normal event description with details about the event."
    assert tf._strip_legacy_fallback(raw) == raw


def test_strip_legacy_fallback_handles_none_and_empty() -> None:
    assert tf._strip_legacy_fallback(None) == ""
    assert tf._strip_legacy_fallback("") == ""


def test_format_strips_legacy_fallback_in_event_rows() -> None:
    """All-events deterministic branch must not surface pre-commit-1 scaffolding."""
    rows = [
        {
            "type": "event",
            "name": "Test Event",
            "date": "2026-05-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Test Venue",
            "description": (
                "Date: 2026-05-15\nTime: 10:00\n\n"
                "Imported from River Scene. Event URL: https://riverscenemagazine.com/events/x/ "
                "Real text."
            ),
            "event_url": "https://impact928.com/",
            "tags": [],
        }
    ]
    out, tin, tout = tf.format("any query", rows)
    assert out is not None
    assert tin == 0 and tout == 0
    assert "Imported from River Scene" not in out
    assert "Real text." in out
