"""Unit tests for app.home.pullquote (BUILD.md step 4 SWR cache)."""

from __future__ import annotations

import threading
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.home import pullquote
from app.home.mock_data import render_voice_links
from app.home.pullquote import _DEFAULT_QUOTE, _TTL, _CacheState


@pytest.fixture(autouse=True)
def _reset_pullquote_cache() -> None:
    """Isolate module-level cache between tests."""
    pullquote._cache = _CacheState()
    yield
    pullquote._cache = _CacheState()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def test_cold_cache_returns_default(db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh cache serves the hard fallback and schedules a background refresh."""
    spawned: list[bool] = []

    def _capture_spawn(_maker) -> None:
        spawned.append(True)

    monkeypatch.setattr(pullquote, "_maybe_spawn_refresh", _capture_spawn)
    monkeypatch.setattr(pullquote, "call_anthropic_messages", MagicMock())

    result = pullquote.get_quote(db)

    assert result["quote"] == _DEFAULT_QUOTE
    assert _DEFAULT_QUOTE in result["quote_html"]
    assert "refreshed" in result["byline"]
    assert spawned == [True]


def test_fresh_cache_returns_cached_no_llm_call(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Within TTL, serve cached quote without touching the LLM."""
    now = now_lake_havasu()
    cached_quote = "The channel is busy tonight."
    pullquote._cache.quote = cached_quote
    pullquote._cache.quote_html = render_voice_links(cached_quote)
    pullquote._cache.expires_at = now + _TTL

    def _boom(*_a, **_kw):
        raise AssertionError("LLM must not be called on fresh cache hit")

    monkeypatch.setattr(pullquote, "call_anthropic_messages", _boom)

    result = pullquote.get_quote(db)

    assert result["quote"] == cached_quote
    assert cached_quote in result["quote_html"]


def test_stale_cache_serves_stale_triggers_refresh(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired cache returns the previous quote synchronously and refreshes async."""
    now = now_lake_havasu()
    stale_quote = "Stale but still on the page."
    pullquote._cache.quote = stale_quote
    pullquote._cache.quote_html = render_voice_links(stale_quote)
    pullquote._cache.expires_at = now - timedelta(minutes=5)

    refresh_done = threading.Event()
    original_worker = pullquote._refresh_worker

    def _worker_that_signals(session_maker) -> None:
        try:
            original_worker(session_maker)
        finally:
            refresh_done.set()

    monkeypatch.setattr(pullquote, "_refresh_worker", _worker_that_signals)
    monkeypatch.setattr(pullquote, "_generate", lambda *_a, **_kw: None)

    result = pullquote.get_quote(db)

    assert result["quote"] == stale_quote
    assert refresh_done.wait(timeout=5.0), "background refresh did not finish"


def test_llm_failure_does_not_raise(db, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM errors yield None from _generate; get_quote still returns a dict."""
    monkeypatch.setattr(
        pullquote,
        "call_anthropic_messages",
        MagicMock(side_effect=RuntimeError("api down")),
    )

    assert pullquote._generate(db, now=now_lake_havasu()) is None

    result = pullquote.get_quote(db)
    assert result["quote"]
    assert result["quote_html"]
    assert "refreshed" in result["byline"]


def test_render_voice_links_escapes_html() -> None:
    """Script tags in link labels must not reach the template as raw HTML."""
    raw = "See [evil<script>alert(1)</script>](https://example.com) tonight."
    html = render_voice_links(raw)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
