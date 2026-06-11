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

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.liveness import DAMPENER_FLOOR
from app.db.models import Provider
from app.home.queries import _hours_status, _provider_image_url

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
    attr = raw.get("image_attribution")
    image_attribution: dict[str, str] | None = None
    if isinstance(attr, dict):
        photographer = attr.get("photographer")
        profile_url = attr.get("profile_url")
        if photographer and profile_url:
            image_attribution = {
                "photographer": str(photographer),
                "profile_url": str(profile_url),
            }

    return {
        "slug": raw.get("slug"),
        "name": raw["name"],
        "where": raw.get("where") or "",
        "image_url": raw["image_url"],
        "image_attribution": image_attribution,
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

    # Drop cards that claim a slug but have no matching Provider row.
    # Without this guard, a stale curated entry (typo, deleted provider,
    # provider not yet seeded) renders a link to /provider/<slug> that
    # returns 404 -- the single highest-traffic broken link on /home.
    # Landmark cards (slug=None) are kept; the template renders them as
    # non-link divs.
    filtered: list[dict[str, Any]] = []
    for card in cards:
        slug = card.get("slug")
        if slug and slug not in by_slug:
            # Slug present but no Provider row -- skip rather than render
            # a broken link. Editorial decision: better to show 9 cards
            # than 10 with a guaranteed 404.
            continue
        filtered.append(card)
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

    return filtered


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
    return {str(k): str(v) for k, v in photos.items() if isinstance(v, str) and v}


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


# Minimum Google review count before a star rating is credible enough to
# show. A 5.0 from a single review is noise -- it floats junk to the top of
# rating-sorted grids and reads as fake. Below this floor we hide the rating
# entirely (the card still renders name/status/photo) and sort the provider
# after the credibly-rated ones.
MIN_RATING_REVIEWS = 5


def _rating_display(
    rating: float | None, review_count: int | None
) -> tuple[str | None, int | None]:
    """Return ``(rating_str, review_count)`` for a card, or ``(None, None)``.

    Hides the rating when there's no rating OR fewer than
    ``MIN_RATING_REVIEWS`` reviews behind it, so a 1-review 5.0 never renders
    as a credibility signal. When shown, the review count rides along so the
    template can print "4.3 (1,862)" instead of a bare star.
    """
    formatted = _format_rating(rating)
    if formatted is None:
        return None, None
    try:
        n = int(review_count) if review_count is not None else 0
    except (TypeError, ValueError):
        n = 0
    if n < MIN_RATING_REVIEWS:
        return None, None
    return formatted, n


def _rating_sort_key(db):
    """SQL ordering by Bayesian-shrunk rating (WS-2), volume-weighted.

    ``(R*n + m*C)/(n + C)`` (``app.core.rating_prior``, C=25, live
    review-weighted ``m``) replaces the old two-tier sort (hard
    ``MIN_RATING_REVIEWS`` cutoff, then raw rating). The prior does the same
    job continuously: a single-review 5.0 shrinks to ≈``m`` and cannot top a
    grid, while review-rich heads keep their raw order (calibrated on the
    2026-06-10 prod export — top-20 identical at C=25). ``MIN_RATING_REVIEWS``
    still gates rating *display* (cards), just no longer the sort.

    The score is scaled by the liveness dampener (``FLOOR + (1 - FLOOR) *
    COALESCE(liveness_score, 1)`` — SQL mirror of
    :func:`app.core.liveness.liveness_dampener`), so a stale-but-once-popular
    listing sinks instead of riding its old rating forever (bury, never
    remove). NULL liveness leaves the ordering unchanged; NULL ratings still
    sort last.
    """
    from app.core.rating_prior import bayesian_rating_expr, global_mean_rating

    dampener = DAMPENER_FLOOR + (1.0 - DAMPENER_FLOOR) * func.coalesce(
        Provider.liveness_score, 1.0
    )
    score = bayesian_rating_expr(global_mean_rating(db))
    return (
        (score * dampener).desc().nullslast(),
        Provider.google_review_count.desc().nullslast(),
    )


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
    rating, review_count = _rating_display(
        provider.google_rating, getattr(provider, "google_review_count", None)
    )
    return {
        "slug": provider.slug,
        "name": provider.provider_name,
        "image_url": image_url,
        "neighborhood": provider.district or "",
        "status": status_class,
        "status_text": status_text,
        "rating": rating,
        "review_count": review_count,
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
            .order_by(*_rating_sort_key(db))
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
        if not image_url:
            # Fall back to the provider's Google photo so the home row stops
            # rendering letter-tile placeholders for everything not in the
            # small curated file. Mirrors the category page resolver. Guarded
            # so a malformed photo column degrades to the gradient rather than
            # 500-ing the home (eat_row's "never raises" contract).
            try:
                image_url = _provider_image_url(provider)
            except Exception:
                image_url = None
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


# ============================================================
# PR D4: Service icon grid 6-up
# ============================================================
#
# Renders a 6-column-by-2-row icon grid below the eat row. Each
# tile represents one ``/categories/{route}`` destination page
# and counts real active non-draft Providers across all legacy
# ``Provider.category`` slugs that map to that route.
#
# Tile set covers the top 12 D5 category routes, excluding the
# ``eat-drink`` route (the D3 Eat row above already surfaces
# food/drink providers).
#
# The tile↔count↔page chain is anchored on ``route``:
#
#     tile.route  ->  CATEGORY_FILTERS[route]  ->  Provider.category set
#
# This means a tile's count is always the same arithmetic as the
# slim header count on ``/categories/{route}`` -- no drift between
# what the visitor reads on /home and what they see after a click.
# When the catalog grows or shifts, ``CATEGORY_FILTERS`` in
# ``app/categories/queries.py`` is the single edit site for the
# slug set; this constant just picks which 12 routes to surface.
#
# Per BUILD.md "no zero counts": tiles with count == 0 hide the
# count line but still render the tile (icon + name + tap target).
#
# Icon SVG paths are inlined per-tile (no Lucide / CDN). They use
# ``viewBox="0 0 24 24"`` and CSS-strokable single-path shapes.
# When the design lane wants different icons, edit ``svg_path``.


_SERVICE_TILES: tuple[dict[str, Any], ...] = (
    {
        "name": "Health & wellness",
        "route": "health-wellness-care",
        "svg_path": "M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.5-7 10-7 10z",
    },
    {
        "name": "Home & property",
        "route": "home-property-services",
        "svg_path": "M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1V11z",
    },
    {
        "name": "Shopping & retail",
        "route": "shopping-essentials",
        "svg_path": "M6 7h12l-1 13H7L6 7zM9 7V5a3 3 0 0 1 6 0v2",
    },
    {
        "name": "On the water",
        "route": "on-the-water",
        "svg_path": "M2 17c2-2 4-2 6 0s4 2 6 0 4-2 6 0M2 13c2-2 4-2 6 0s4 2 6 0 4-2 6 0M5 10l7-6 7 6",
    },
    {
        "name": "Professional",
        "route": "professional-services",
        "svg_path": "M3 8h18v12H3zM9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18",
    },
    {
        "name": "Beauty & care",
        "route": "beauty-care",
        "svg_path": "M6 4l8 8M6 20l8-8M10 12a4 4 0 1 1-4-4 4 4 0 0 1 4 4zM18 6a2 2 0 1 1-2-2 2 2 0 0 1 2 2zM18 18a2 2 0 1 1-2-2 2 2 0 0 1 2 2z",
    },
    {
        "name": "Auto, RV & fuel",
        "route": "auto-rv-fuel",
        "svg_path": "M5 16h14M5 16l1-5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2l1 5M5 16v3M19 16v3M8 16a1.5 1.5 0 1 1-3 0M19 16a1.5 1.5 0 1 1-3 0",
    },
    {
        "name": "Community",
        "route": "public-civic-resources",
        "svg_path": "M9 11a3 3 0 1 1 6 0 3 3 0 0 1-6 0zM3 21v-1a5 5 0 0 1 5-5h8a5 5 0 0 1 5 5v1",
    },
    {
        "name": "Fitness & sports",
        "route": "classes-sports-recreation",
        "svg_path": "M3 12h2M19 12h2M7 8v8M17 8v8M7 12h10",
    },
    {
        "name": "Attractions",
        "route": "attractions",
        "svg_path": "M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5L12 3z",
    },
    {
        "name": "Lodging",
        "route": "lodging-vacation-rentals",
        "svg_path": "M3 18V8M21 18v-5a3 3 0 0 0-3-3H8M3 13h18M3 18h18M7 10a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z",
    },
    {
        "name": "Pets",
        "route": "pets",
        "svg_path": "M5 11a2 2 0 1 1-2-2 2 2 0 0 1 2 2zM21 11a2 2 0 1 1-2-2 2 2 0 0 1 2 2zM9 6a2 2 0 1 1-2-2 2 2 0 0 1 2 2zM17 6a2 2 0 1 1-2-2 2 2 0 0 1 2 2zM7 17a5 5 0 0 1 10 0 3 3 0 0 1-3 3h-4a3 3 0 0 1-3-3z",
    },
)


def services_grid(db: Session) -> list[dict[str, Any]]:
    """Service icon grid -- 12 category tiles with real counts.

    Each tile counts active non-draft Providers across the full slug
    tuple in ``CATEGORY_FILTERS[tile['route']]``. This guarantees the
    tile count on /home matches the slim-header count on the
    ``/categories/{route}`` destination page -- no drift between
    surfaces. The slug-set source of truth lives in
    ``app/categories/queries.py``; this function imports it lazily to
    avoid an import cycle (``categories.queries`` already imports
    ``queries_c`` for ``_format_rating`` / ``_load_eat_photos``).

    Per BUILD.md "no zero counts" rule: tiles with 0 providers still
    render (icon + name + tap target) but the count line is suppressed.
    The template reads ``card["count"]`` -- ``None`` means hide the
    count line, an ``int`` means render "{n} listed". A tile is never
    omitted from the output.

    Args:
        db: SQLAlchemy session. ``None`` returns the 12 tiles with all
            counts as ``None`` -- defensive for tests / DB outages.

    Returns:
        List of 12 card dicts shaped for ``components/services_grid.html``.
        Each card has: ``name`` (display), ``route`` (D5 URL path
        segment), ``svg_path`` (inline SVG), ``count`` (int|None),
        ``count_label`` ("N listed" or ""), ``href``
        ("/categories/{route}").

    Never raises: a DB hiccup must not 500 /home. Errors swallow into
    "all counts None" so the grid still renders.
    """
    # Lazy import: ``app.categories.queries`` imports ``_format_rating``
    # and ``_load_eat_photos`` from this module at import time, so a
    # top-level import here would create a cycle. Importing inside the
    # function body is the cleanest break -- runtime cost is negligible
    # and CPython caches the module after the first call.
    from sqlalchemy import func as sa_func

    from app.categories.queries import route_provider_filter

    # S4 reconciliation: count each tile with the SAME ``route_provider_filter``
    # the ``/categories/{route}`` page uses (subcategory-primary, legacy fallback),
    # so the tile count on /home equals the slim-header count on the destination
    # page — no drift. One small COUNT per tile (12 total).
    cards: list[dict[str, Any]] = []
    for tile in _SERVICE_TILES:
        count_value: int | None = None
        if db is not None:
            try:
                total = (
                    db.query(sa_func.count(Provider.id))
                    .filter(
                        route_provider_filter(tile["route"]),
                        Provider.is_active.is_(True),
                        Provider.draft.is_(False),
                    )
                    .scalar()
                )
                total = int(total or 0)
                # 0 collapses to None per the no-zero rule; >0 renders the line.
                count_value = total if total > 0 else None
            except Exception:
                # A DB hiccup leaves the tile in "no count" state — surface
                # still renders, count line just hides.
                count_value = None
        cards.append(
            {
                "name": tile["name"],
                "route": tile["route"],
                "svg_path": tile["svg_path"],
                "count": count_value,
                "count_label": f"{count_value} listed" if count_value else "",
                "href": f"/categories/{tile['route']}",
            }
        )
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
