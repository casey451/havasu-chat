"""Cross-surface symmetry: profile, home, categories share one builder.

PR #41 collapsed the provider profile path to ``first_renderable_google_photo``
and dropped its raw-ref upgrade. PR #43 then added a raw-ref upgrade to the
home/categories path (``_provider_image_url``), citing symmetry with
``derive_hero_photo`` — but by then the symmetry was already gone, leaving a
narrow asymmetry: a provider with only raw Places refs (no
``google_photo_urls`` backfill, no owner ``Photo`` rows) rendered on the
home card and category card but showed the gradient placeholder on its
profile.

Track C hoists the raw-ref upgrade into ``iter_renderable_google_photos``
so every surface that reads Google photo columns picks it up uniformly.
These tests guard the contract: for the same provider shape, the profile
hero, home image, and category card resolver must return the same URL.
"""

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
    """Single source of truth: ``iter_renderable_google_photos`` upgrades
    raw refs once, so all three call sites return the same URL."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    p = _raw_ref_only_provider()

    profile_url = derive_hero_photo(p)
    home_url = _provider_image_url(p)
    # category resolver falls through to ``_provider_image_url`` when the
    # slug is absent from both curated photo JSONs.
    category_url = cat_queries._resolve_category_card_image(p)

    assert profile_url is not None
    assert profile_url == home_url == category_url


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
    resolved = "https://lh3.googleusercontent.com/backfilled.jpg"
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
    """``google_photo_urls = [None, None]`` — the shape after a partial
    backfill where every resolve call returned ``None``. The refs fallback
    now triggers (previously only home/categories did this; profile did
    not). All three surfaces converge on the upgraded raw ref.
    """
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    ent = SimpleNamespace(photos=[])
    p = SimpleNamespace(
        entity=ent,
        attributes={},
        slug="unknown-slug-not-in-curated-or-eat-json",
        google_photo_urls=[None, None],
        google_photo_refs=["places/fallback/photos/ref"],
    )
    profile_url = derive_hero_photo(p)
    home_url = _provider_image_url(p)
    category_url = cat_queries._resolve_category_card_image(p)

    assert profile_url is not None
    assert profile_url == home_url == category_url
    assert "places/fallback/photos/ref/media" in profile_url


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
