"""Unit tests for ``app.providers.photo_urls``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.providers import photo_urls
from app.providers.photo_urls import (
    first_renderable_google_photo,
    iter_renderable_google_photos,
    resolve_photo_ref,
)


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    photo_urls._google_photo_url_cached.cache_clear()
    photo_urls._resolve_photo_ref_cached.cache_clear()
    yield
    photo_urls._google_photo_url_cached.cache_clear()
    photo_urls._resolve_photo_ref_cached.cache_clear()


# (google_photo_url / resolve_photo_refs tests were deleted 2026-07-02 with
# their functions — the live pipeline uses resolve_photo_ref, below.)


_RESOLVED_FIXTURE_URL = "https://lh3.googleusercontent.com/places/photo_fixture_abc123"


@patch("httpx.Client")
def test_resolve_photo_ref_returns_https_url(
    mock_client_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ref = "places/ChIJfixture/photos/AeeoHfixture"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = _RESOLVED_FIXTURE_URL
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    assert resolve_photo_ref(ref) == _RESOLVED_FIXTURE_URL
    mock_client.get.assert_called_once()
    called_url = mock_client.get.call_args[0][0]
    assert ref in called_url
    assert "maxWidthPx=1200" in called_url


@pytest.mark.parametrize(
    "bad_ref",
    [
        "",
        "   ",
        "ChIJabc/AeeoH123",
        "not-a-places-ref",
        "places/foo/bar",
    ],
)
def test_resolve_photo_ref_returns_none_for_malformed_refs(
    bad_ref: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    assert resolve_photo_ref(bad_ref) is None


@patch("httpx.Client")
def test_resolve_photo_ref_returns_none_on_http_error(
    mock_client_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.url = "https://places.googleapis.com/v1/places/x/photos/y/media"
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    assert resolve_photo_ref("places/x/photos/y") is None


def test_resolve_photo_ref_returns_none_without_raising_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    assert resolve_photo_ref("places/x/photos/y") is None


@patch("httpx.Client")
def test_resolve_photo_ref_returns_none_on_transport_error(
    mock_client_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectError("offline")
    mock_client_cls.return_value = mock_client

    assert resolve_photo_ref("places/x/photos/y") is None


# ──────────────── iter_renderable_google_photos / first_renderable_google_photo ────────────────


def _provider(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "google_photo_urls": None,
        "google_photo_refs": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_iter_renderable_prefers_urls_column_over_refs() -> None:
    p = _provider(
        google_photo_urls=["/static/biz-photos/a.jpg"],
        google_photo_refs=["https://example.com/b.jpg"],
    )
    assert list(iter_renderable_google_photos(p)) == [
        "/static/biz-photos/a.jpg",
    ]


def test_iter_renderable_falls_through_when_urls_has_zero_renderable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw Places refs are no longer upgraded in render path."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_urls=[None, None],
        google_photo_refs=["places/abc/photos/xyz"],
    )
    assert list(iter_renderable_google_photos(p)) == []


def test_iter_renderable_ignores_refs_column_even_when_renderable_values_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_refs=[
            "places/a/photos/1",
            "https://example.com/literal.jpg",
            "/static/biz-photos/local.webp",
        ],
    )
    out = list(iter_renderable_google_photos(p))
    assert out == []


def test_iter_renderable_skips_google_hosts_and_raw_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    p = _provider(
        google_photo_refs=[
            "places/a/photos/1",
            "https://lh3.googleusercontent.com/literal.jpg",
            "https://places.googleapis.com/v1/places/a/photos/1/media?key=test",
        ],
    )
    assert list(iter_renderable_google_photos(p)) == []


def test_iter_renderable_skips_non_string_and_empty_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_refs=[
            None,
            42,
            "",
            "   ",
            "places/valid/photos/ref",
        ],
    )
    assert list(iter_renderable_google_photos(p)) == []


def test_first_renderable_returns_none_when_no_columns() -> None:
    p = _provider()
    assert first_renderable_google_photo(p) is None


def test_first_renderable_returns_first_from_iter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_urls=[
            "/static/biz-photos/first.jpg",
            "/static/biz-photos/second.jpg",
        ],
    )
    assert first_renderable_google_photo(p) == "/static/biz-photos/first.jpg"
