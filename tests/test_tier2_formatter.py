"""Tests for ``app.chat.tier2_formatter`` — Anthropic client is always mocked."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.chat import tier2_formatter as tf


def _msg(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(input_tokens=120, output_tokens=40, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[block], usage=usage)


def test_simple_query_returns_nonempty() -> None:
    rows = [
        {"type": "event", "id": "1", "name": "Fair", "date": "2030-01-01", "location_name": "Park"},
    ]
    fake = MagicMock()
    fake.messages.create.return_value = _msg("Here is the fair at the park on that date.")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            out, tin, tout = tf.format("what is on", rows)
    assert out
    assert tin == 120 and tout == 40
    assert "fair" in out.lower()


def test_explicit_rec_query_includes_option3_cues_in_system_prompt() -> None:
    prompt = Path(__file__).resolve().parents[1] / "prompts" / "tier2_formatter.txt"
    body = prompt.read_text(encoding="utf-8").lower()
    assert "pick one" in body
    assert "your favorite" in body or "favorite" in body


def test_explicit_rec_user_message_contains_query_text() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("Pick Altitude.")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            tf.format("pick one thing to do Saturday", [{"type": "program", "id": "x", "name": "Altitude"}])
    user = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "pick one thing to do Saturday" in user


def test_empty_rows_still_calls_api() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("No catalog rows were supplied.")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            out, _, _ = tf.format("anything", [])
    assert out
    user = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "[]" in user or "Catalog rows" in user


def test_sdk_error_returns_none() -> None:
    fake = MagicMock()
    fake.messages.create.side_effect = RuntimeError("boom")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", [{"type": "event", "id": "1", "name": "E"}])
    assert text is None and tin is None and tout is None


def test_empty_model_text_returns_none() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("   ")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            text, tin, tout = tf.format("q", [{"type": "event", "id": "1", "name": "E"}])
    assert text is None and tin == 120 and tout == 40


def test_invocation_kwargs() -> None:
    fake = MagicMock()
    fake.messages.create.return_value = _msg("ok")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        with patch.object(anthropic, "Anthropic", return_value=fake):
            tf.format("events tomorrow", [{"type": "event", "id": "1", "name": "E"}])
    kw = fake.messages.create.call_args.kwargs
    assert kw["max_tokens"] == 400
    assert kw["temperature"] == 0.3
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
