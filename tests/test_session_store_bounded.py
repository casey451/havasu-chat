"""P1-9: the in-memory chat session store (app.core.session.sessions) is bounded
so a flood of client-supplied session_ids can't grow it without limit."""

from __future__ import annotations

import pytest

import app.core.session as session_mod


def test_session_store_evicts_when_over_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = dict(session_mod.sessions)
    session_mod.sessions.clear()
    monkeypatch.setattr(session_mod, "MAX_SESSIONS", 10)
    try:
        for i in range(20):
            session_mod.clear_session_state(f"evict-{i}")
            session_mod.touch_session(f"evict-{i}")
        assert len(session_mod.sessions) <= 10
        # The most recently active sessions survive; the earliest are evicted.
        assert "evict-19" in session_mod.sessions
        assert "evict-0" not in session_mod.sessions
    finally:
        session_mod.sessions.clear()
        session_mod.sessions.update(saved)
