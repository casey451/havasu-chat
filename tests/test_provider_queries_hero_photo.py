"""Phase 2B.1 — three-tier ``derive_hero_photo`` / ``derive_gallery``."""

from __future__ import annotations

from types import SimpleNamespace

from app.providers.queries import derive_gallery, derive_hero_photo


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


def test_derive_hero_photo_tier3_skips_raw_refs_without_urls_column() -> None:
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        google_photo_refs=["places/ChIJabc/photos/AeeoH123", "https://g/2.jpg"],
    )
    assert derive_hero_photo(p) == "https://g/2.jpg"


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
