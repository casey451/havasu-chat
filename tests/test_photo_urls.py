"""Unit tests for ``app.providers.photo_urls``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.providers import photo_urls
from app.providers.photo_urls import google_photo_url


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    photo_urls._google_photo_url_cached.cache_clear()
    yield
    photo_urls._google_photo_url_cached.cache_clear()


def test_google_photo_url_builds_expected_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ref = "places/abc/photos/xyz"
    assert google_photo_url(ref) == (
        "https://places.googleapis.com/v1/places/abc/photos/xyz/media"
        "?maxWidthPx=1200&key=test-key"
    )


def test_google_photo_url_returns_none_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    assert google_photo_url("places/abc/photos/xyz") is None


def test_google_photo_url_respects_max_width_px(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    url = google_photo_url("places/a/photos/b", max_width_px=800)
    assert url is not None
    assert "maxWidthPx=800" in url


def test_google_photo_url_lru_cache_returns_same_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ref = "places/cache/photos/hit"
    first = google_photo_url(ref)
    second = google_photo_url(ref)
    assert first is second


@patch("httpx.Client")
def test_google_photo_url_makes_no_outbound_http(
    mock_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    google_photo_url("places/no/http/photos/call")
    mock_cls.assert_not_called()


def test_google_photo_url_logs_ref_not_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "secret-key-value")
    ref = "places/log/photos/discipline"
    logged: list[tuple[str, dict[str, object]]] = []

    def _capture(msg: str, *args: object, extra: dict[str, object] | None = None, **kwargs: object) -> None:
        logged.append((msg, extra or {}))

    monkeypatch.setattr(photo_urls.logger, "info", _capture)
    url = google_photo_url(ref)
    assert url is not None
    assert len(logged) == 1
    assert logged[0][0] == "google_photo_url.issued"
    assert logged[0][1]["ref"] == ref
    assert "key" not in logged[0][1]


def test_google_photo_url_missing_key_emits_sentry_breadcrumb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    crumbs: list[dict] = []

    def _capture(**kwargs: object) -> None:
        crumbs.append(kwargs)

    monkeypatch.setattr(photo_urls.sentry_sdk, "add_breadcrumb", _capture)
    assert google_photo_url("places/missing/photos/key") is None
    assert len(crumbs) == 1
    assert crumbs[0]["category"] == "google_photo_url"
