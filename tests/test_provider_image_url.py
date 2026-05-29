"""Category card photo wiring via ``_provider_image_url``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.home.queries import _provider_image_url
from app.providers import photo_urls


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    photo_urls._google_photo_url_cached.cache_clear()
    yield
    photo_urls._google_photo_url_cached.cache_clear()


def _provider(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "google_photo_refs": None,
        "google_photo_urls": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_provider_image_url_prefers_google_photo_urls() -> None:
    p = _provider(
        google_photo_urls=[
            "https://lh3.googleusercontent.com/resolved-first.jpg",
        ],
        google_photo_refs=[
            "places/ChIJabc/photos/AeeoH123",
            "https://lh3.googleusercontent.com/places/photo1.jpg",
        ],
    )
    assert (
        _provider_image_url(p)
        == "https://lh3.googleusercontent.com/resolved-first.jpg"
    )


def test_provider_image_url_returns_first_https_url_from_refs() -> None:
    p = _provider(
        google_photo_refs=[
            "places/ChIJabc/photos/AeeoH123",
            "https://lh3.googleusercontent.com/places/photo1.jpg",
            "https://lh3.googleusercontent.com/places/photo2.jpg",
        ]
    )
    assert _provider_image_url(p) == "https://lh3.googleusercontent.com/places/photo1.jpg"


def test_provider_image_url_accepts_http_url() -> None:
    p = _provider(google_photo_refs=["http://example.com/photo.jpg"])
    assert _provider_image_url(p) == "http://example.com/photo.jpg"


def test_provider_image_url_skips_raw_places_refs_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without GOOGLE_PLACES_API_KEY, raw refs cannot upgrade; result is None.
    # Explicit delenv so the test is hermetic against dev shells / .env files
    # that have the key set.
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    p = _provider(
        google_photo_refs=[
            "places/ChIJabc/photos/AeeoH123",
            "ChIJabc/AeeoH123",
        ]
    )
    assert _provider_image_url(p) is None


def test_provider_image_url_none_when_refs_empty() -> None:
    p = _provider(google_photo_refs=[])
    assert _provider_image_url(p) is None


def test_provider_image_url_none_when_refs_null() -> None:
    p = _provider(google_photo_refs=None)
    assert _provider_image_url(p) is None


def test_provider_image_url_upgrades_raw_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw Places refs get upgraded via google_photo_url helper."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(google_photo_refs=["places/abc/photos/xyz"])
    url = _provider_image_url(p)
    assert url is not None
    assert url.startswith("https://places.googleapis.com/v1/")
    assert "key=test-key" in url


def test_provider_image_url_returns_none_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw refs return None when GOOGLE_PLACES_API_KEY is unset."""
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    p = _provider(google_photo_refs=["places/abc/photos/xyz"])
    assert _provider_image_url(p) is None


def test_provider_image_url_prefers_http_over_raw_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """http URLs win even when raw refs follow."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(
        google_photo_refs=[
            "https://example.com/photo.jpg",
            "places/abc/photos/xyz",
        ]
    )
    assert _provider_image_url(p) == "https://example.com/photo.jpg"


def test_provider_image_url_falls_through_to_raw_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-string candidates are skipped; raw ref still upgrades."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _provider(google_photo_refs=[None, 42, "places/abc/photos/xyz"])
    url = _provider_image_url(p)
    assert url is not None
    assert url.startswith("https://places.googleapis.com/v1/")
