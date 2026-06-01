"""Category card photo wiring via ``_provider_image_url``."""

from __future__ import annotations

from types import SimpleNamespace

from app.home.queries import _provider_image_url


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
            "/static/biz-photos/resolved-first.jpg",
        ],
        google_photo_refs=[
            "places/ChIJabc/photos/AeeoH123",
            "https://example.com/places/photo1.jpg",
        ],
    )
    assert _provider_image_url(p) == "/static/biz-photos/resolved-first.jpg"


def test_provider_image_url_returns_none_when_only_refs_have_values() -> None:
    p = _provider(
        google_photo_refs=[
            "https://example.com/places/photo1.jpg",
            "/static/biz-photos/photo2.jpg",
        ]
    )
    assert _provider_image_url(p) is None


def test_provider_image_url_skips_google_hosts_and_raw_refs() -> None:
    p = _provider(
        google_photo_refs=[
            "places/ChIJabc/photos/AeeoH123",
            "https://lh3.googleusercontent.com/places/photo1.jpg",
            "https://places.googleapis.com/v1/places/abc/photos/123/media?key=test",
            "https://example.com/places/photo2.jpg",
        ]
    )
    assert _provider_image_url(p) is None


def test_provider_image_url_accepts_http_url() -> None:
    p = _provider(google_photo_refs=["http://example.com/photo.jpg"])
    assert _provider_image_url(p) is None


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


def test_provider_image_url_returns_none_for_raw_ref_only() -> None:
    p = _provider(google_photo_refs=["places/abc/photos/xyz"])
    assert _provider_image_url(p) is None


def test_provider_image_url_prefers_http_over_raw_ref() -> None:
    """Refs are ignored; only google_photo_urls can render."""
    p = _provider(
        google_photo_refs=[
            "https://example.com/photo.jpg",
            "places/abc/photos/xyz",
        ]
    )
    assert _provider_image_url(p) is None


def test_provider_image_url_falls_through_to_static_ref() -> None:
    p = _provider(google_photo_refs=[None, 42, "/static/biz-photos/abc.jpg"])
    assert _provider_image_url(p) is None
