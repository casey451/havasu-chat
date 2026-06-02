"""Loader for the verified GEO/AEO FAQ + landing content asset.

LANE B6 (Phase B). The content itself lives in ``content/category_faqs.json``
— a frozen, adversarially-verified asset (see its ``_meta`` block). This module
only reads it and exposes typed lookups keyed by:

  * category slug — a ``CATEGORY_FILTERS`` route key (eat-drink, services, ...)
  * intent key    — one of the ten top intents (eat_find, boat_rental, ...)

No fact is synthesized here. ``has_data`` flags whether the target has real
catalog-backed listings (True) or renders the honest "coverage being built"
copy (False); the FAQ/landing copy is identical-source either way.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONTENT_PATH = Path(__file__).resolve().parent / "content" / "category_faqs.json"


@dataclass(frozen=True)
class FaqTarget:
    """One landing target's verified content."""

    key: str
    has_data: bool
    title: str
    intro: str
    meta_description: str
    faqs: tuple[dict[str, str], ...]

    @property
    def faq_list(self) -> list[dict[str, str]]:
        """FAQs as a plain list (template / JSON-LD friendly)."""
        return [dict(f) for f in self.faqs]


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    """Read and cache the raw JSON asset. Returns ``{}`` on any read failure."""
    try:
        with _CONTENT_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _build_target(key: str, blob: Any) -> FaqTarget | None:
    if not isinstance(blob, dict):
        return None
    landing = blob.get("landing") or {}
    if not isinstance(landing, dict):
        landing = {}
    raw_faqs = blob.get("faqs") or []
    faqs: list[dict[str, str]] = []
    for faq in raw_faqs:
        if not isinstance(faq, dict):
            continue
        q = str(faq.get("q") or "").strip()
        a = str(faq.get("a") or "").strip()
        if q and a:
            faqs.append({"q": q, "a": a})
    return FaqTarget(
        key=key,
        has_data=bool(blob.get("has_data")),
        title=str(landing.get("title") or "").strip(),
        intro=str(landing.get("intro") or "").strip(),
        meta_description=str(landing.get("meta_description") or "").strip(),
        faqs=tuple(faqs),
    )


@lru_cache(maxsize=1)
def _category_index() -> dict[str, FaqTarget]:
    out: dict[str, FaqTarget] = {}
    for key, blob in (_raw().get("categories") or {}).items():
        target = _build_target(str(key), blob)
        if target is not None:
            out[str(key)] = target
    return out


@lru_cache(maxsize=1)
def _intent_index() -> dict[str, FaqTarget]:
    out: dict[str, FaqTarget] = {}
    for key, blob in (_raw().get("intents") or {}).items():
        target = _build_target(str(key), blob)
        if target is not None:
            out[str(key)] = target
    return out


def category_faq_target(slug: str | None) -> FaqTarget | None:
    """Verified content for a ``CATEGORY_FILTERS`` slug, or None if unmapped."""
    if not slug:
        return None
    return _category_index().get(slug.strip().lower())


def intent_faq_target(key: str | None) -> FaqTarget | None:
    """Verified content for a top-intent key, or None if unmapped."""
    if not key:
        return None
    return _intent_index().get(key.strip().lower())


def all_category_slugs() -> list[str]:
    """Sorted list of every category slug with verified content."""
    return sorted(_category_index().keys())


def all_intent_keys() -> list[str]:
    """Sorted list of every intent key with verified content."""
    return sorted(_intent_index().keys())
