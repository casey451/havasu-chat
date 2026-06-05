"""T2.2 — the last-seen debounce map must not grow unbounded.

``_LAST_SEEN_MONO`` was written once per unique session id and never pruned, so
it grew for the whole process lifetime. It now prunes expired entries when it
crosses a soft cap, bounding its size to concurrently-active sessions.
"""

from __future__ import annotations

import pytest

import app.auth.session as session_mod


@pytest.fixture(autouse=True)
def _clear_map() -> None:
    session_mod._LAST_SEEN_MONO.clear()
    yield
    session_mod._LAST_SEEN_MONO.clear()


def test_last_seen_map_prunes_expired_when_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = session_mod._LAST_SEEN_MAX_ENTRIES

    # Fill past the cap with entries stamped at t=0.
    monkeypatch.setattr(session_mod.time, "monotonic", lambda: 0.0)
    for i in range(cap + 5):
        assert session_mod._should_bump_last_seen(f"sess-{i}") is True
    assert len(session_mod._LAST_SEEN_MONO) >= cap

    # Advance well past the debounce window; the next bump prunes the stale lot.
    monkeypatch.setattr(
        session_mod.time, "monotonic", lambda: session_mod.LAST_SEEN_DEBOUNCE_SECONDS + 100.0
    )
    session_mod._should_bump_last_seen("fresh")

    assert len(session_mod._LAST_SEEN_MONO) < cap
    assert "fresh" in session_mod._LAST_SEEN_MONO


def test_debounce_behavior_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    # Within the window: second call is debounced (no bump). Past it: bumps again.
    monkeypatch.setattr(session_mod.time, "monotonic", lambda: 100.0)
    assert session_mod._should_bump_last_seen("s1") is True
    assert session_mod._should_bump_last_seen("s1") is False
    monkeypatch.setattr(
        session_mod.time, "monotonic", lambda: 100.0 + session_mod.LAST_SEEN_DEBOUNCE_SECONDS + 1
    )
    assert session_mod._should_bump_last_seen("s1") is True
