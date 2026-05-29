"""Unit tests for ``app.providers.photo_urls``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from types import SimpleNamespace

from app.providers import photo_urls
from app.providers.photo_urls import (
    first_renderable_google_photo,
    google_photo_url,
    iter_renderable_google_photos,
    resolve_photo_ref,
    resolve_photo_refs,
)


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    photo_urls._google_photo_url_cached.cache_clear()
    photo_urls._resolve_photo_ref_cached.cache_clear()
    yield
    photo_urls._google_photo_url_cached.cache_clear()
    photo_urls._resolve_photo_ref_cached.cache_clear()


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


_RESOLVED_FIXTURE_URL = (
    "https://lh3.googleusercontent.com/places/photo_fixture_abc123"
)


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


@patch("app.providers.photo_urls.resolve_photo_ref")
def test_resolve_photo_refs_parallel_shape(mock_resolve: MagicMock) -> None:
    mock_resolve.side_effect = [
        "https://lh3.googleusercontent.com/a",
        None,
    ]
    out = resolve_photo_refs(
        ["places/a/photos/1", "places/a/photos/2"],
    )
    assert out == [
        "https://lh3.googleusercontent.com/a",
        None,
    ]


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
        google_photo_urls=["https://lh3.googleusercontent.com/a.jpg"],
        google_photo_refs=["https://lh3.googleusercontent.com/b.jpg"],
    )
    assert list(iter_renderable_google_photos(p)) == [
        "https://lh3.googleusercontent.com/a.jpg",
    ]


def test_iter_renderable_falls_through_when_urls_has_zero_renderable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial backfill that resolved every entry to ``None`` previously
    short-circuited and silently dropped the refs. Track C: refs become the
    fallback when urls yields zero renderable entries."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_urls=[None, None],
        google_photo_refs=["places/abc/photos/xyz"],
    )
    out = list(iter_renderable_google_photos(p))
    assert len(out) == 1
    assert "places/abc/photos/xyz/media" in out[0]


def test_iter_renderable_upgrades_raw_refs_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_refs=[
            "places/a/photos/1",
            "https://lh3.googleusercontent.com/literal.jpg",
            "places/b/photos/2",
        ],
    )
    out = list(iter_renderable_google_photos(p))
    assert len(out) == 3
    assert "places/a/photos/1/media" in out[0]
    assert out[1] == "https://lh3.googleusercontent.com/literal.jpg"
    assert "places/b/photos/2/media" in out[2]


def test_iter_renderable_skips_raw_refs_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    p = _provider(
        google_photo_refs=[
            "places/a/photos/1",
            "https://lh3.googleusercontent.com/literal.jpg",
        ],
    )
    assert list(iter_renderable_google_photos(p)) == [
        "https://lh3.googleusercontent.com/literal.jpg",
    ]


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
    out = list(iter_renderable_google_photos(p))
    assert len(out) == 1
    assert "places/valid/photos/ref/media" in out[0]


def test_first_renderable_returns_none_when_no_columns() -> None:
    p = _provider()
    assert first_renderable_google_photo(p) is None


def test_first_renderable_returns_first_from_iter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_refs=[
            "places/first/photos/one",
            "places/second/photos/two",
        ],
    )
    url = first_renderable_google_photo(p)
    assert url is not None
    assert "places/first/photos/one/media" in url
