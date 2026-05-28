"""Category card photo wiring via ``_provider_image_url``."""

from __future__ import annotations

from types import SimpleNamespace

from app.home.queries import _provider_image_url


def _provider(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {"google_photo_refs": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_provider_image_url_returns_first_https_url() -> None:
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


def test_provider_image_url_skips_raw_places_refs_only() -> None:
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
