"""Curated editorial collections — slug -> grouped places landing data.

Editorial groupings like "Dog-friendly patios" or "Best sunset spots".
The JSON file (``app/home/curated_collections.json``) is the source of
truth; this module reads it at request time (cached) and exposes a
loader + lookup, mirroring the ``queries_c`` / ``themed_groups`` patterns.

Defensive by contract: a missing or corrupt file degrades to "no
collections" and an unknown slug returns ``None``. Nothing here raises
on bad data, so a stale editorial entry can never 500 the route — the
route turns a ``None`` lookup into a clean 404.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent / "curated_collections.json"

# Accent classes the template understands; anything else collapses to
# "neutral" so a JSON typo can't leak an unstyled class into the page.
_VALID_ACCENTS: frozenset[str] = frozenset({"warm", "fresh", "water", "neutral"})


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    """Read and cache the curated collections JSON.

    Returns ``{}`` on any file-read or parse failure. Cached at module
    level; the small editorial file rarely changes and an LRU of size 1
    keeps re-renders cheap. If the file is edited while uvicorn runs,
    the cache survives until restart (deliberate — rotation data, not
    config). Use ``reset_cache()`` to clear in tests.
    """
    try:
        with _DATA_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _normalise_place(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Shape a place entry, or ``None`` if it has no display name.

    Reuses the ``curated_discover`` entry keys (slug / name / where /
    image_url / blurb / meta_line). Missing optional keys default to
    falsy values so the Jinja template can ``{% if place.blurb %}``
    without ``UndefinedError``.
    """
    name = raw.get("name")
    if not name:
        return None
    slug = raw.get("slug")
    return {
        "slug": str(slug) if slug else None,
        "name": str(name),
        "where": raw.get("where") or "",
        "image_url": raw.get("image_url") or None,
        "blurb": raw.get("blurb") or "",
        "meta_line": raw.get("meta_line") or "",
    }


def _normalise_collection(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Shape a collection, or ``None`` if it lacks a slug or title.

    Drops malformed place entries silently rather than failing the whole
    collection — a single bad entry must not blank an otherwise-good page.
    """
    slug = raw.get("slug")
    title = raw.get("title")
    if not slug or not title:
        return None
    accent = raw.get("accent") or "neutral"
    if accent not in _VALID_ACCENTS:
        accent = "neutral"
    places: list[dict[str, Any]] = []
    for entry in raw.get("places", []) or []:
        if not isinstance(entry, dict):
            continue
        place = _normalise_place(entry)
        if place is not None:
            places.append(place)
    return {
        "slug": str(slug).strip().lower(),
        "title": str(title),
        "blurb": raw.get("blurb") or "",
        "accent": accent,
        "places": places,
    }


@lru_cache(maxsize=1)
def _index() -> dict[str, dict[str, Any]]:
    """Return ``{slug: collection}`` from the curated file.

    Cached alongside ``_load_raw``; cleared by ``reset_cache()``.
    Malformed collections (missing slug/title) are skipped.
    """
    data = _load_raw()
    out: dict[str, dict[str, Any]] = {}
    for raw in data.get("collections", []) or []:
        if not isinstance(raw, dict):
            continue
        coll = _normalise_collection(raw)
        if coll is not None:
            out[coll["slug"]] = coll
    return out


def list_collections() -> list[dict[str, Any]]:
    """Return all curated collections in file order.

    Empty list when the file is missing/corrupt — callers (e.g. a home
    browse entry point) gate on truthiness, so the section simply hides.
    """
    return list(_index().values())


def get_collection(slug: str) -> dict[str, Any] | None:
    """Return the collection for ``slug``, or ``None`` if unknown.

    Slug is normalised (stripped + lowercased) before lookup. Never
    raises — the route turns ``None`` into a 404.
    """
    if not slug:
        return None
    return _index().get(slug.strip().lower())


def is_collection_slug(slug: str) -> bool:
    """True if ``slug`` names a known curated collection."""
    return get_collection(slug) is not None


def reset_cache() -> None:
    """Clear the curated-JSON LRU caches. Test-only seam.

    Tolerant lookup of ``cache_clear`` mirrors ``queries_c.reset_cache``
    so a test that monkeypatches a loader to a plain lambda doesn't blow
    up teardown.
    """
    for fn in (_load_raw, _index):
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()
