"""WS12 Facebook connector — interface-only, gated no-op until access configured."""

from __future__ import annotations

import pytest

from app.contrib.approval_service import auto_approve_event_sources
from app.events.scrapers.facebook_pages import (
    FACEBOOK_SOURCE,
    WATCHLIST,
    FacebookPagesClient,
    extract_events_from_text,
)


def _clear_fb_env(monkeypatch) -> None:
    for k in ("FB_ACCESS_MODE", "FB_GRAPH_TOKEN", "FB_VENDOR_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_unconfigured_is_noop(monkeypatch) -> None:
    """Default (no access env) -> discover returns [] and never touches FB."""
    _clear_fb_env(monkeypatch)
    assert FacebookPagesClient.is_configured() is False
    assert FacebookPagesClient().discover({}) == []
    assert FacebookPagesClient().run({}) == []


def test_off_mode_is_noop(monkeypatch) -> None:
    _clear_fb_env(monkeypatch)
    monkeypatch.setenv("FB_ACCESS_MODE", "off")
    assert FacebookPagesClient().discover({}) == []


def test_configured_graph_mode_is_recognized_but_unimplemented(monkeypatch) -> None:
    """A configured access path is recognized, but the fetch seam is not wired
    yet — it must fail loudly, never silently scrape."""
    _clear_fb_env(monkeypatch)
    monkeypatch.setenv("FB_ACCESS_MODE", "graph")
    monkeypatch.setenv("FB_GRAPH_TOKEN", "test-token")
    assert FacebookPagesClient.is_configured() is True
    with pytest.raises(NotImplementedError):
        FacebookPagesClient().discover({})


def test_graph_mode_without_token_stays_off(monkeypatch) -> None:
    _clear_fb_env(monkeypatch)
    monkeypatch.setenv("FB_ACCESS_MODE", "graph")  # mode set but no token
    assert FacebookPagesClient.is_configured() is False
    assert FacebookPagesClient().discover({}) == []


def test_extraction_seam_is_unimplemented() -> None:
    with pytest.raises(NotImplementedError):
        extract_events_from_text("Live music Fri 7pm!", page=WATCHLIST[0])


def test_watchlist_is_wellformed() -> None:
    handles = [p.handle for p in WATCHLIST]
    assert len(handles) == len(set(handles)), "duplicate handles in watchlist"
    # The three client-named gaps must be on the list.
    gaps = {p.label for p in WATCHLIST if p.client_named_gap}
    assert {"Altitude Lake Havasu", "Split Finger Athletics", "Barley Brothers"} <= gaps


def test_facebook_is_review_queue_first(monkeypatch) -> None:
    """Facebook findings must never auto-publish (shared with the OpenClaw push
    path) — they land pending for review."""
    monkeypatch.delenv("EVENT_AUTO_APPROVE_SOURCES", raising=False)
    assert FACEBOOK_SOURCE == "facebook_scrape"
    assert FACEBOOK_SOURCE not in auto_approve_event_sources()
