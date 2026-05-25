"""Direction C queries -- Discover grid (and forthcoming Eat row + Services).

PR D2 introduces ``discover_grid()``: reads the curated featured-places
JSON (``app/home/curated_discover.json``), optionally enriches business
entries with live hours status from the Provider table, and returns a
list of card dicts ready for the template.

Why a separate module: Direction C diverges from the legacy ``queries.py``
shape (mixed-span masonry, status-pill state machine, photos as data).
Keeping these in their own module avoids polluting the legacy surface
and gives PR D5's category pages a single import seam.

The JSON file is the editorial source-of-truth. Provider rows enrich
status when a card carries a ``slug`` that matches an active Provider;
when no slug or no match, the card falls back to the JSON's static
``status_text`` (and hides the pill entirely when ``status_text`` is
``None``). The renderer never invents hours.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Provider
from app.home.queries import _hours_status

_DATA_PATH = Path(__file__).resolve().parent / "curated_discover.json"


@lru_cache(maxsize=1)
def _load_curated() -> dict[str, Any]:
    """Read and cache the curated places JSON.

    Cached at module level; the small editorial file rarely changes
    and an LRU of size 1 keeps re-renders cheap. If the file is edited
    while uvicorn is running, the cache survives until restart -- this
    is deliberate (the file is rotation data, not config).
    """
    with _DATA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalise_card(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a card dict with all template-facing keys present.

    Missing optional keys default to falsy values so the Jinja partial
    can do ``{% if card.blurb %}`` without ``UndefinedError``. Keeps
    the JSON schema forgiving without sprinkling ``card.get('blurb')``
    through the template.
    """
    return {
        "slug": raw.get("slug"),
        "name": raw["name"],
        "where": raw.get("where") or "",
        "image_url": raw["image_url"],
        "span": int(raw["span"]),
        "pick": bool(raw.get("pick", False)),
        "blurb": raw.get("blurb") or "",
        "meta_line": raw.get("meta_line") or "",
        "status": raw.get("status") or "neutral",
        "status_text": raw.get("status_text"),
    }


def _enrich_from_provider(
    cards: list[dict[str, Any]],
    db: Session | None,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    """Best-effort live-hours overlay for cards with a slug.

    Looks up each slug-bearing card's Provider row. When found and the
    provider has parseable hours, replaces the static ``status`` /
    ``status_text`` with the live values from ``_hours_status``. When
    not found (slug typo, draft provider, no DB session), the static
    JSON values stay in place.

    Never raises -- a single bad provider should not blank the grid.
    """
    if db is None:
        return cards

    slugs = [c["slug"] for c in cards if c.get("slug")]
    if not slugs:
        return cards

    rows = (
        db.query(Provider)
        .filter(
            Provider.slug.in_(slugs),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        .all()
    )
    by_slug = {p.slug: p for p in rows}

    for card in cards:
        slug = card.get("slug")
        if not slug or slug not in by_slug:
            continue
        try:
            status_class, status_text = _hours_status(by_slug[slug], now=now)
        except Exception:
            # Defensive: a malformed hours_structured row should not
            # poison the grid. Fall through to the JSON's static text.
            continue
        if status_class == "unknown":
            # We have a Provider match but no parseable hours -- prefer
            # the editorial copy from JSON over an empty pill.
            continue
        card["status"] = status_class
        card["status_text"] = status_text

    return cards


def discover_grid(
    db: Session | None = None,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the Discover grid card list for ``home_c.html``.

    Args:
        db: SQLAlchemy session for the optional Provider live-status
            join. Pass ``None`` to skip enrichment (tests, demo mode,
            offline rendering).
        now: Datetime to evaluate live hours against. Defaults to the
            curated file's static status when omitted.
        limit: Cap the returned list at N cards. ``None`` returns all
            curated entries (typically 6-12 per the D2 spec).

    Returns:
        List of card dicts shaped for ``_partials/discover_grid.html``.
        Empty list if the curated file is missing or unreadable -- the
        template renders nothing (no "0" copy, per the BUILD.md rule).
    """
    try:
        data = _load_curated()
    except (FileNotFoundError, json.JSONDecodeError):
        # Editorial empty state: the bridge paragraph in home_c.html
        # is the upstream fallback; an empty list here just hides the
        # grid region without surfacing an error to visitors.
        return []

    cards = [_normalise_card(p) for p in data.get("places", [])]
    if limit is not None:
        cards = cards[:limit]

    if now is not None:
        cards = _enrich_from_provider(cards, db, now=now)

    return cards


def reset_cache() -> None:
    """Clear the curated-JSON LRU cache. Test-only seam."""
    _load_curated.cache_clear()
