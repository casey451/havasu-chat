"""Curated category photo override loading."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.categories import queries as cat_queries


def test_load_category_photos_reads_json() -> None:
    photos = cat_queries._load_category_photos()
    assert isinstance(photos, dict)
    assert "hallett-boats" in photos
    assert photos["hallett-boats"].startswith("https://")


def test_resolve_category_card_image_prefers_category_curated() -> None:
    p = SimpleNamespace(
        slug="hallett-boats",
        google_photo_refs=["https://google.example/photo.jpg"],
    )
    url = cat_queries._resolve_category_card_image(p)
    assert url == cat_queries._load_category_photos()["hallett-boats"]
    assert "unsplash.com" in url


def test_resolve_category_card_image_falls_back_to_eat_photos() -> None:
    p = SimpleNamespace(
        slug="mudshark-brewing",
        google_photo_refs=["https://google.example/photo.jpg"],
    )
    with patch.object(
        cat_queries,
        "_load_category_photos",
        return_value={},
    ):
        url = cat_queries._resolve_category_card_image(p)
    assert url == cat_queries._load_eat_photos()["mudshark-brewing"]


def test_resolve_category_card_image_falls_back_to_google_refs() -> None:
    p = SimpleNamespace(
        slug="unknown-provider-slug",
        google_photo_refs=["https://google.example/photo.jpg"],
    )
    assert (
        cat_queries._resolve_category_card_image(p)
        == "https://google.example/photo.jpg"
    )


def test_resolve_category_card_image_none_without_slug_or_refs() -> None:
    p = SimpleNamespace(slug=None, google_photo_refs=None)
    assert cat_queries._resolve_category_card_image(p) is None
