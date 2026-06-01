"""Cross-surface symmetry: profile, home, categories share one builder."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.categories import queries as cat_queries
from app.home.queries import _provider_image_url
from app.providers import photo_urls
from app.providers.queries import derive_hero_photo


@pytest.fixture(autouse=True)
def _clear_photo_url_cache() -> None:
    photo_urls._google_photo_url_cached.cache_clear()
    yield
    photo_urls._google_photo_url_cached.cache_clear()


def _raw_ref_only_provider() -> SimpleNamespace:
    """A provider whose ingest backfill never landed.

    ``google_photo_urls`` is ``None`` (the backfill column shape when the
    helper hasn't run), the only available source is a raw Places resource
    name in ``google_photo_refs``. Owner ``Photo`` rows are empty and no
    pinned hero is set, so all three surfaces fall through to the Google
    photo columns.
    """
    ent = SimpleNamespace(photos=[])
    return SimpleNamespace(
        entity=ent,
        attributes={},
        slug="unknown-slug-not-in-curated-or-eat-json",
        google_photo_urls=None,
        google_photo_refs=["places/ChIJfixture/photos/AeeoHfixture"],
    )


def test_raw_ref_provider_renders_same_url_on_profile_home_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw refs are not upgraded in render path; all surfaces return None."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _raw_ref_only_provider()

    assert derive_hero_photo(p) is None
    assert _provider_image_url(p) is None
    assert cat_queries._resolve_category_card_image(p) is None


def test_raw_ref_provider_returns_none_uniformly_when_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``GOOGLE_PLACES_API_KEY`` is unset, the upgrade returns
    ``None`` and all three surfaces fall through to ``None`` — still
    symmetric, just without a photo to show."""
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    p = _raw_ref_only_provider()

    assert derive_hero_photo(p) is None
    assert _provider_image_url(p) is None
    assert cat_queries._resolve_category_card_image(p) is None


def test_resolved_urls_still_win_over_raw_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backfill stays authoritative: when ``google_photo_urls`` has a
    renderable entry, the raw-ref fallback is not consulted."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ent = SimpleNamespace(photos=[])
    resolved = "/static/biz-photos/backfilled.jpg"
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        slug="unknown-slug-not-in-curated-or-eat-json",
        google_photo_urls=[resolved],
        google_photo_refs=["places/raw/photos/should-be-ignored"],
    )
    assert derive_hero_photo(p) == resolved
    assert _provider_image_url(p) == resolved
    assert cat_queries._resolve_category_card_image(p) == resolved


def test_empty_urls_column_falls_through_to_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When urls has no renderable values and refs are raw, all surfaces return None."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        slug="unknown-slug-not-in-curated-or-eat-json",
        google_photo_urls=[None, None],
        google_photo_refs=["places/fallback/photos/ref"],
    )
    assert derive_hero_photo(p) is None
    assert _provider_image_url(p) is None
    assert cat_queries._resolve_category_card_image(p) is None


def test_curated_category_photo_still_overrides_raw_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Category card's curated-JSON override takes precedence over the
    Google photo columns. The hoisted upgrade must not change this layering.
    """
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        slug="curated-slug-xyz",
        google_photo_urls=None,
        google_photo_refs=["places/raw/photos/ref"],
    )
    curated = {"curated-slug-xyz": "https://curated.example/hero.jpg"}
    with patch.object(cat_queries, "_load_category_photos", return_value=curated):
        assert (
            cat_queries._resolve_category_card_image(p)
            == "https://curated.example/hero.jpg"
        )
