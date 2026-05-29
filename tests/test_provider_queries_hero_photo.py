"""Phase 2B.1 — three-tier ``derive_hero_photo`` / ``derive_gallery``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers import photo_urls
from app.providers.queries import derive_gallery, derive_hero_photo


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    """The raw-ref upgrade now flows through ``iter_renderable_google_photos``
    which calls a cached ``google_photo_url``. Clear between tests so a
    test that sets the API key doesn't leak a cached URL into a test that
    expects ``None`` (key unset).
    """
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


def test_derive_hero_photo_tier3_prefers_google_photo_urls() -> None:
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_urls=["https://lh3.googleusercontent.com/resolved.jpg"],
        google_photo_refs=["places/x/photos/y", "https://g/2.jpg"],
    )
    assert derive_hero_photo(p) == "https://lh3.googleusercontent.com/resolved.jpg"


def test_derive_hero_photo_tier3_falls_through_raw_ref_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an API key, raw refs cannot upgrade and we fall through to
    the next renderable entry. Keeps the previous behavior intact when the
    backfill helper has nothing to work with."""
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=["places/ChIJabc/photos/AeeoH123", "https://g/2.jpg"],
    )
    assert derive_hero_photo(p) == "https://g/2.jpg"


def test_derive_hero_photo_tier3_upgrades_raw_ref_when_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Track C symmetry fix: raw Places refs are upgraded via
    :func:`google_photo_url` for the profile path too, matching the
    home/categories ``_provider_image_url`` behavior. Before the fix
    (PR #41 / PR #43 split), the profile silently dropped raw refs and a
    provider whose backfill never ran would render only on the home card.
    """
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=["places/ChIJabc/photos/AeeoH123", "https://g/2.jpg"],
    )
    url = derive_hero_photo(p)
    assert url is not None
    assert url.startswith(
        "https://places.googleapis.com/v1/places/ChIJabc/photos/AeeoH123/media"
    )
    assert "key=test-key" in url


def test_derive_hero_photo_tier3_raw_ref_only_provider_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The specific case PR #41/PR #43 created drift on: provider has only
    a raw Places ref (no ``google_photo_urls`` backfill, no http ref). Hero
    now resolves via upgrade rather than returning ``None``.
    """
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=["places/only/photos/raw"],
    )
    url = derive_hero_photo(p)
    assert url is not None
    assert "places/only/photos/raw/media" in url


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


def test_derive_gallery_owner_then_google() -> None:
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
    hero = "https://lh3.googleusercontent.com/hero.jpg"
    extra = "https://lh3.googleusercontent.com/gallery.jpg"
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_urls=[hero, extra],
        google_photo_refs=["places/ChIJabc/photos/AeeoH123", "places/extra"],
    )
    g = derive_gallery(p)
    assert g == ["https://m/1.webp", extra]


def test_derive_gallery_mixed_resolved_urls_and_literal_refs() -> None:
    resolved = "https://lh3.googleusercontent.com/resolved.jpg"
    literal = "https://g/1.jpg"
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={"hero_pin_photo_url": "https://pin/hero.jpg"},
        google_photo_urls=[resolved, literal],
        google_photo_refs=["places/ChIJabc/photos/AeeoH123", literal],
    )
    assert derive_gallery(p) == [resolved, literal]


def test_derive_gallery_hero_dedupe_with_resolved_urls() -> None:
    hero = "https://lh3.googleusercontent.com/hero.jpg"
    extra = "https://lh3.googleusercontent.com/extra.jpg"
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_urls=[hero, extra],
        google_photo_refs=["places/hero/photos/one", "places/extra/photos/two"],
    )
    assert derive_hero_photo(p) == hero
    assert derive_gallery(p) == [extra]
