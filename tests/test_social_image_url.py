"""Share-safe provider og:image / JSON-LD image resolution (UI plan 1.6).

``social_image_url`` is the last gate before a hero URL reaches a social meta
tag. It must always return an absolute URL, and must never emit a transient
Google host (which rotates and breaks already-shared link previews).
"""

from __future__ import annotations

import pytest

from app.providers.photo_urls import _HOUSE_IMAGE_PATH, social_image_url
from app.seo.urls import absolute_url


@pytest.fixture
def house() -> str:
    return absolute_url(_HOUSE_IMAGE_PATH)


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_missing_photo_falls_back_to_house(missing: str | None, house: str) -> None:
    assert social_image_url(missing) == house


def test_local_static_photo_is_made_absolute() -> None:
    assert social_image_url("/static/biz-photos/abc.jpg") == absolute_url(
        "/static/biz-photos/abc.jpg"
    )


@pytest.mark.parametrize(
    "blocked",
    [
        "https://lh3.googleusercontent.com/places/photo1.jpg",
        "https://places.googleapis.com/v1/places/abc/photos/123/media?key=test",
        "https://maps.gstatic.com/photo.jpg",
    ],
)
def test_transient_google_hosts_fall_back_to_house(blocked: str, house: str) -> None:
    assert social_image_url(blocked) == house


def test_safe_remote_url_is_returned_unchanged() -> None:
    url = "https://cdn.example.com/owner-uploaded/hero.jpg"
    assert social_image_url(url) == url


@pytest.mark.parametrize(
    "weird",
    [
        "places/ChIJabc/photos/AeeoH123",  # bare Places ref
        "//example.com/protocol-relative.jpg",  # protocol-relative
        "ftp://example.com/x.jpg",  # non-http scheme
    ],
)
def test_unknown_shapes_fall_back_to_house(weird: str, house: str) -> None:
    assert social_image_url(weird) == house


def test_result_is_always_absolute() -> None:
    for candidate in (None, "/static/x.jpg", "https://cdn.example.com/x.jpg", "junk"):
        assert social_image_url(candidate).startswith("http")
