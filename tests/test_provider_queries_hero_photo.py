"""Phase 2B.1 — three-tier ``derive_hero_photo`` / ``derive_gallery``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers import photo_urls
from app.providers.photo_urls import google_photo_url
from app.providers.queries import derive_gallery, derive_hero_photo


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    photo_urls._google_photo_url_cached.cache_clear()
    yield
    photo_urls._google_photo_url_cached.cache_clear()


def test_derive_hero_photo_tier1_owner_photo() -> None:
    ph = SimpleNamespace(
        is_hero=True, status="live", hero_url="https://cdn/o/hero.webp"
    )
    ent = SimpleNamespace(photos=[ph])
    p = SimpleNamespace(entity=ent, attributes={}, google_photo_refs=None)
    assert derive_hero_photo(p) == "https://cdn/o/hero.webp"


def test_derive_hero_photo_tier2_pinned_when_no_owner_hero() -> None:
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={"hero_pin_photo_url": "https://pin/x.jpg"},
        google_photo_refs=["https://g/1.jpg"],
    )
    assert derive_hero_photo(p) == "https://pin/x.jpg"


def test_derive_hero_photo_tier3_resolves_raw_places_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ref = "places/x/photos/y"
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=[ref, "https://g/2.jpg"],
    )
    assert derive_hero_photo(p) == google_photo_url(ref)


def test_derive_hero_photo_tier3_none_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=["places/ChIJabc/photos/AeeoH123", "https://g/2.jpg"],
    )
    assert derive_hero_photo(p) is None


def test_derive_hero_photo_tier3_returns_full_url_when_present() -> None:
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=["https://g/1.jpg", "https://g/2.jpg"],
    )
    assert derive_hero_photo(p) == "https://g/1.jpg"


def test_derive_hero_photo_none_when_empty() -> None:
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(entity=ent, attributes={}, google_photo_refs=None)
    assert derive_hero_photo(p) is None


def test_derive_gallery_owner_then_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ref = "places/ChIJabc/photos/AeeoH123"
    p1 = SimpleNamespace(
        is_hero=False,
        status="live",
        display_order=1,
        medium_url="https://m/1.webp",
        cdn_url=None,
        thumbnail_url=None,
        hero_url=None,
    )
    ent = SimpleNamespace(photos=[p1])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=[ref],
    )
    g = derive_gallery(p)
    assert g == ["https://m/1.webp"]


def test_derive_gallery_mixed_raw_refs_and_literal_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    raw = "places/ChIJabc/photos/AeeoH123"
    literal = "https://g/1.jpg"
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={"hero_pin_photo_url": "https://pin/hero.jpg"},
        google_photo_refs=[raw, literal],
    )
    assert derive_gallery(p) == [google_photo_url(raw), literal]


def test_derive_gallery_hero_dedupe_with_constructed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    hero_ref = "places/hero/photos/one"
    extra_ref = "places/extra/photos/two"
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=[hero_ref, extra_ref],
    )
    hero = derive_hero_photo(p)
    gallery = derive_gallery(p)
    assert hero == google_photo_url(hero_ref)
    assert gallery == [google_photo_url(extra_ref)]
