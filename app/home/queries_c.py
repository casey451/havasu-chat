"""Direction C queries -- Discover grid + Eat row (and forthcoming Services).

PR D2 introduces ``discover_grid()``: reads the curated featured-places
JSON (``app/home/curated_discover.json``), optionally enriches business
entries with live hours status from the Provider table, and returns a
list of card dicts ready for the template.

PR D3 introduces ``eat_row()``: the inverse pattern. Provider rows in
the legacy food/drink ``category`` buckets are the source of truth;
the curated photo map (``app/home/curated_eat_photos.json``) is a
side-table that supplies an Unsplash image keyed by ``Provider.slug``.
Cards without a curated photo fall back to a CSS gradient and still
render. Filter is "open or closing soon now" via ``_hours_status``;
sort is ``google_rating`` desc (NULLs last). Cap at 12.

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
_EAT_PHOTOS_PATH = Path(__file__).resolve().parent / "curated_eat_photos.json"

# Legacy ``Provider.category`` string values that map to "Eat & Drink".
# Source: ``app.home.queries.LEGACY_PROVIDER_CATEGORY_LABELS`` -- the four
# keys whose label is "Eat & Drink". Hardcoded here (not imported) to keep
# this module self-contained and to make the food/drink slug surface
# explicit at the call site. If new strings appear in prod (e.g.
# "cafe", "pub"), add them here and to the legacy map.
_FOOD_DRINK_CATEGORIES: tuple[str, ...] = (
    "food_drink",
    "food",
    "restaurant",
    "bakery",
)

# Status classes from ``_hours_status`` that count as "open right now"
# for the eat row's "Open right now, by neighborhood" framing. We include
# "closing-soon" because a restaurant closing in 20 minutes is still a
# real option for someone deciding where to eat.
_OPEN_NOW_STATUSES: frozenset[str] = frozenset({"open", "closing-soon"})

# Hard cap on Provider rows pulled before filtering by open-now status.
# Set generously: with hundreds of food/drink Providers and a long-tail
# of unparseable hours, we need a fat pre-filter slice to fill 12 cards.
_EAT_FETCH_MULTIPLIER = 6


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


@lru_cache(maxsize=1)
def _load_eat_photos() -> dict[str, str]:
    """Read and cache the curated eat-row Unsplash photo map.

    Returns ``{slug: image_url}`` or ``{}`` on any file-read failure.
    A missing or corrupt file degrades to no curated photos -- cards
    still render with the gradient placeholder, no error surfaces to
    visitors.
    """
    try:
        with _EAT_PHOTOS_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    photos = data.get("photos") or {}
    if not isinstance(photos, dict):
        return {}
    # Belt-and-suspenders: ensure all values are strings (a JSON typo
    # could leave a number or null in there).
    return {
        str(k): str(v)
        for k, v in photos.items()
        if isinstance(v, str) and v
    }


def _format_rating(value: float | None) -> str | None:
    """Render a Google rating as a single-decimal string, or ``None``.

    Returns ``None`` when there's no rating to display so the template
    can hide the rating span entirely -- never render a bare star with
    no number, and never render "0" or "0.0" (BUILD.md no-zero rule).
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return f"{v:.1f}"


def _build_eat_card(
    provider: Provider,
    *,
    status_class: str,
    status_text: str,
    image_url: str | None,
) -> dict[str, Any]:
    """Shape a Provider row into the scroll_row.html card contract.

    Template-facing keys (Jinja-safe defaults for every field):

    - ``slug``: optional URL slug -- when present, card links to
      ``/provider/{slug}``; otherwise the partial renders a non-link
      ``<div>`` with the same styling (no anchor semantics).
    - ``name``: ``Provider.provider_name`` verbatim.
    - ``image_url``: curated Unsplash URL or ``None``; ``None`` triggers
      the gradient placeholder in CSS.
    - ``neighborhood``: ``Provider.district`` (e.g. "English Village");
      empty string when null so the template can ``{% if %}`` cleanly.
    - ``status``: one of "open" / "closing-soon" (the eat row filters
      to those two values; other classes never reach this builder).
    - ``status_text``: pill copy from ``_hours_status``.
    - ``rating``: pre-formatted single-decimal string, or ``None`` to
      hide the rating span.
    """
    return {
        "slug": provider.slug,
        "name": provider.provider_name,
        "image_url": image_url,
        "neighborhood": provider.district or "",
        "status": status_class,
        "status_text": status_text,
        "rating": _format_rating(provider.google_rating),
    }


def eat_row(
    db: Session | None,
    *,
    now: datetime,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return cards for the Direction C Eat & drink scroll row.

    Live DB query: ``Provider WHERE category IN food/drink slug set
    AND is_active AND NOT draft``, post-filtered by ``_hours_status``
    to keep only currently-open (or closing-soon) rows, sorted by
    ``google_rating`` desc with NULLs last, capped at ``limit``.

    Photos come from ``app/home/curated_eat_photos.json`` keyed by
    ``Provider.slug``. Missing photos render as a gradient -- the row
    still shows the live name, neighborhood, status, and rating.

    Args:
        db: SQLAlchemy session. Pass ``None`` to short-circuit to an
            empty list (test seam; tests that don't need DB rows
            shouldn't have to wire one up).
        now: Datetime to evaluate ``_hours_status`` against. Required
            (unlike ``discover_grid``) because the entire filter hinges
            on "open now."
        limit: Max cards to return. Default 12 matches the mockup; 8-12
            is the spec band.

    Returns:
        List of card dicts shaped for ``components/scroll_row.html``.
        Empty list when no rows match (DB has no eat/drink Providers,
        nothing is open, DB is unreachable, etc.). The template's
        ``{% if eat_cards %}`` gate handles the empty case.

    Never raises: a single bad Provider row or DB hiccup must not 500
    the home page. Errors swallow into an empty list.
    """
    if db is None:
        return []
    if limit <= 0:
        return []

    try:
        candidates: list[Provider] = (
            db.query(Provider)
            .filter(
                Provider.category.in_(_FOOD_DRINK_CATEGORIES),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .order_by(Provider.google_rating.desc().nullslast())
            .limit(limit * _EAT_FETCH_MULTIPLIER)
            .all()
        )
    except Exception:
        # Defensive: a DB outage or schema drift should leave the row
        # empty (template hides the section) rather than 500 the home.
        return []

    if not candidates:
        return []

    photos = _load_eat_photos()
    cards: list[dict[str, Any]] = []
    for provider in candidates:
        try:
            status_class, status_text = _hours_status(provider, now=now)
        except Exception:
            # One malformed hours_structured row should never poison
            # the entire row -- skip and continue.
            continue
        if status_class not in _OPEN_NOW_STATUSES:
            continue
        image_url = photos.get(provider.slug) if provider.slug else None
        cards.append(
            _build_eat_card(
                provider,
                status_class=status_class,
                status_text=status_text,
                image_url=image_url,
            )
        )
        if len(cards) >= limit:
            break

    return cards


def reset_cache() -> None:
    """Clear the curated-JSON LRU caches. Test-only seam.

    Defensive against tests that ``monkeypatch.setattr`` the cached
    loaders to plain lambdas: ``cache_clear`` only exists on lru_cache-
    wrapped callables, so we look it up tolerantly. Without this, a
    test that mocks the loader will pass its assertions but blow up
    the autouse fixture's teardown call.
    """
    for fn in (_load_curated, _load_eat_photos):
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()
