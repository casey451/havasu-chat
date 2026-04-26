"""Tests for :mod:`app.eval.confabulation_evidence` (spec §5.1 tests 8, 9, 10, 11)."""

from __future__ import annotations

import pytest

from app.chat import tier2_formatter
from app.eval import confabulation_evidence as ev


@pytest.fixture(autouse=True)
def _restore_tier2_format():
    """Ensure the formatter is never left patched after a test."""
    yield
    ev.restore()


def test_confabulation_evidence_install_restore():
    """Spec section 5.1 test 8: install/replace, restore/put back; double-install and double-restore are safe."""
    real = tier2_formatter.format
    assert not ev._installed
    assert tier2_formatter.format is real

    ev.install()
    assert ev._installed
    assert tier2_formatter.format is not real
    assert tier2_formatter.format is ev._format_wrapper

    # Idempotent second install
    ev.install()
    assert tier2_formatter.format is ev._format_wrapper

    ev.restore()
    assert not ev._installed
    assert tier2_formatter.format is real

    # Idempotent second restore
    ev.restore()
    assert not ev._installed
    assert tier2_formatter.format is real


def test_confabulation_evidence_exception_safety(monkeypatch: pytest.MonkeyPatch):
    """Spec section 5.1 test 9: inner raise still resets ContextVar; no stale evidence for a later call."""
    real = tier2_formatter.format
    ev.install()
    try:

        def boom(
            _q: str, _r: list[dict]
        ) -> tuple[str | None, int | None, int | None]:
            raise ValueError("inner boom")

        monkeypatch.setattr(ev, "_original_format", boom, raising=True)

        with pytest.raises(ValueError, match="inner boom"):
            tier2_formatter.format("q1", [])

        # Default must be visible again in this context (no leaked (q1, rows))
        assert ev.tier2_evidence.get() is None

        def ok(
            q: str, r: list[dict]
        ) -> tuple[str | None, int | None, int | None]:
            return "ok", 0, 0

        monkeypatch.setattr(ev, "_original_format", ok, raising=True)
        tier2_formatter.format("q2", [{"type": "provider", "name": "X"}])
        after = ev.tier2_evidence.get()
        # After the call returns, the wrapper's finally has reset the var
        assert after is None
    finally:
        ev.restore()
        assert tier2_formatter.format is real


def test_confabulation_evidence_no_install_no_overhead():
    """Spec section 5.1 test 10: without install(), ``format`` is the original object (identity)."""
    from app.chat.tier2_formatter import format as format_fn

    assert tier2_formatter.format is format_fn


def test_confabulation_evidence_return_passthrough(monkeypatch: pytest.MonkeyPatch):
    """Spec section 5.1 test 11: wrapper forwards 3-tuple unchanged (success and failure shapes)."""
    real = tier2_formatter.format
    ev.install()
    try:

        def all_none(
            _q: str, _r: list[dict]
        ) -> tuple[str | None, int | None, int | None]:
            return None, None, None

        def empty_response_tokens(
            _q: str, _r: list[dict]
        ) -> tuple[str | None, int | None, int | None]:
            return None, 7, 8

        def success(
            _q: str, _r: list[dict]
        ) -> tuple[str | None, int | None, int | None]:
            return "text", 1, 2

        monkeypatch.setattr(ev, "_original_format", all_none, raising=True)
        assert tier2_formatter.format("a", []) == (None, None, None)

        monkeypatch.setattr(ev, "_original_format", empty_response_tokens, raising=True)
        assert tier2_formatter.format("a", []) == (None, 7, 8)

        monkeypatch.setattr(ev, "_original_format", success, raising=True)
        assert tier2_formatter.format("a", []) == ("text", 1, 2)
    finally:
        ev.restore()
        assert tier2_formatter.format is real
