"""Hava -- ``GET /categories/{slug}`` route + ``GET /categories`` index.

Direction C category-page lane (PR D5). Sister surface to
``app/home/router.py`` -- shares the dark cinematic chrome from
``home_c.html`` but renders a category-specific grid below a slim
header (no full hero). The 12 D4 service tiles and the 4 home_c
mega-tab anchors all resolve here.

Two category surfaces live in the codebase. PR D6 (2026-05-26)
resolved them as a *deliberate editorial split*, not duplicates to
reconcile:

  /categories/{slug}  (THIS module, plural)
    Chrome-driven nav. Tap a topbar tab on /home -> land here.
    5 mega-category routes (today / eat-drink / on-the-water /
    things-to-do / services) that aggregate multiple
    Provider.category slugs into a single editorial grid. No filter
    chips per BUILD.md's "no filters in chrome / chat" rule.
    Provider.category-backed, ~77 LoC template.

  /category/{slug}    (app/api/routes/category_pages.py, singular)
    SEO landing pages and intent-led narrowing. ~12 Tier-1 slugs
    (plumbers, electricians, eat-drink, on-the-water, pets, ...)
    with filter chips and sub-trade refinement. Entity / EntityCategory
    backed, ~1150 LoC template, ranked by closest_now / editorial_pick.

When the slugs overlap (eat-drink, on-the-water, pets, etc.) the
two routes intentionally serve different UX -- the funnel is:
chrome tab -> /categories/services -> tap a tile -> /category/plumbers.

Q2 (v48, 2026-05-29): also serves ``GET /categories`` -- an index page
listing every key in ``CATEGORY_FILTERS`` with provider counts and a
single peek image per card. v48 audit CLUSTER-07 surfaced that the
topbar exposes only 4 of 15 routes; this index gives mobile users and
search crawlers a real path to the full set. The payload is cached
in-process for an hour (counts move on the order of days, not minutes)
via a wall-clock ``(timestamp, payload)`` tuple -- same pattern as
``app.main._sitemap_cache``. ``reset_index_cache()`` is the test seam.
"""

from __future__ import annotations

import time as _time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import Provider
from app.home.queries import _provider_image_url

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["categories"])


# ---------------------------------------------------------------------------
# /categories index: cached payload (Q2)
# ---------------------------------------------------------------------------
#
# Walks ``CATEGORY_FILTERS`` and runs one COUNT + one top-rated provider
# fetch per route. Aggregate cost: ~30 small queries on a cold cache.
# The cache key is global -- no per-request variance -- so a single
# ``(timestamp, payload)`` tuple is enough. Mirrors
# ``app.main._sitemap_cache``. ``reset_index_cache()`` is the canonical
# test seam; tests should never poke ``_index_cache`` directly.
_INDEX_TTL_SECONDS = 3600
_index_cache: tuple[float, list[dict[str, Any]]] | None = None

# Defensive fallback blurb for any slug missing from CATEGORY_DISPLAY.
# CATEGORY_FILTERS / CATEGORY_DISPLAY share keys today and an existing
# invariant test pins that; this is strictly a safety net.
_FALLBACK_BLURB = "Local picks in Lake Havasu."

# Per BUILD.md no-zero rule: a card with count==0 never says "0 listings";
# it shows this short editorial note instead.
_EMPTY_BLURB = "Coming soon."


def reset_index_cache() -> None:
    """Drop the cached /categories payload.

    Test seam. Tests autouse this between cases (mirroring
    ``tests/test_robots_and_sitemap.py::_clear_sitemap_cache``) so a
    stale list built against one fixture's DB state doesn't leak into
    the next test.
    """
    global _index_cache  # noqa: PLW0603 -- module-level cache by design
    _index_cache = None


def _category_count(db: Session, slugs_for_route: tuple[str, ...]) -> int:
    """Count active non-draft providers in the slug set.

    Returns 0 on any DB hiccup so a transient outage degrades the card
    to its empty-state copy rather than 500-ing the page. The empty-tuple
    guard short-circuits without touching the DB.
    """
    if not slugs_for_route:
        return 0
    try:
        from sqlalchemy import func as sa_func

        row = (
            db.query(sa_func.count(Provider.id))
            .filter(
                Provider.category.in_(slugs_for_route),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .scalar()
        )
    except Exception:
        return 0
    if row is None:
        return 0
    try:
        return max(int(row), 0)
    except (TypeError, ValueError):
        return 0


def _peek_provider(db: Session, slugs_for_route: tuple[str, ...]) -> Provider | None:
    """Top-rated active non-draft provider in the slug set, or None.

    Returns None on any DB hiccup -- the template falls through to the
    CSS gradient placeholder when there's no peek image. Empty-tuple
    short-circuits without touching the DB.
    """
    if not slugs_for_route:
        return None
    try:
        return (
            db.query(Provider)
            .filter(
                Provider.category.in_(slugs_for_route),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .order_by(Provider.google_rating.desc().nullslast())
            .first()
        )
    except Exception:
        return None


def _build_index_payload(db: Session) -> list[dict[str, Any]]:
    """Compute the /categories index rows from scratch.

    Walks ``CATEGORY_FILTERS`` in declaration order so mega-tabs render
    first, then the D4 tile routes -- matches the visual hierarchy in
    Casey's brief. Per-row shape:

      slug          URL segment ("eat-drink", "auto-rv-fuel", ...)
      label         display name from CATEGORY_DISPLAY
      blurb         short one-liner from CATEGORY_DISPLAY
      count         int >= 0
      peek_images   list of {url, name} -- 0 or 1 entries today;
                    list shape so a future "2-3 collage" expansion is
                    non-breaking
      empty_blurb   editorial copy shown when count == 0
    """
    rows: list[dict[str, Any]] = []
    for slug, slugs_for_route in cat_queries.CATEGORY_FILTERS.items():
        display = cat_queries.CATEGORY_DISPLAY.get(slug)
        if display is not None:
            label, blurb = display
        else:
            label = slug.replace("-", " ").capitalize()
            blurb = _FALLBACK_BLURB

        count = _category_count(db, slugs_for_route)

        peek_images: list[dict[str, str]] = []
        if count > 0:
            peek = _peek_provider(db, slugs_for_route)
            if peek is not None:
                image_url = _provider_image_url(peek)
                if image_url:
                    peek_images.append(
                        {
                            "url": image_url,
                            "name": peek.provider_name or "",
                        }
                    )

        rows.append(
            {
                "slug": slug,
                "label": label,
                "blurb": blurb,
                "count": count,
                "peek_images": peek_images,
                "empty_blurb": _EMPTY_BLURB,
            }
        )
    return rows


def _get_index_payload(db: Session) -> list[dict[str, Any]]:
    """Return the cached /categories payload, rebuilding if stale.

    The TTL gate compares wall-clock seconds. Identity is preserved
    across cache hits -- callers within the TTL window get the exact
    same list object (the cache test asserts ``first is second``).
    """
    global _index_cache  # noqa: PLW0603 -- module-level cache by design
    now_ts = _time.time()
    cached = _index_cache
    if cached is not None and (now_ts - cached[0]) < _INDEX_TTL_SECONDS:
        return cached[1]
    payload = _build_index_payload(db)
    _index_cache = (now_ts, payload)
    return payload


@router.get("/categories", response_class=HTMLResponse)
def serve_categories_index(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render the /categories index page.

    Route declared *before* ``/categories/{slug}`` so FastAPI's exact-path
    priority matches this handler first; slug catches anything else.
    """
    now = now_lake_havasu()
    categories = _get_index_payload(db)
    return templates.TemplateResponse(
        request=request,
        name="categories_index.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "categories": categories,
            "active_tab": "all-categories",
        },
    )


@router.get("/categories/{slug}", response_class=HTMLResponse)
def serve_category(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render a single category page.

    Returns 404 when the slug is not in
    ``app.categories.queries.CATEGORY_FILTERS``. Otherwise, renders
    ``category_c.html`` with a filtered Provider list, a slim header,
    and the shared topbar with the right tab marked active.
    """
    normalised = (slug or "").strip().lower()
    if not cat_queries.is_valid_category_slug(normalised):
        raise HTTPException(status_code=404, detail="unknown_category")

    now = now_lake_havasu()
    label, one_liner = cat_queries.CATEGORY_DISPLAY[normalised]
    count = cat_queries.category_count(db, normalised)
    cards = cat_queries.category_cards(db, normalised, now=now)
    active_tab = cat_queries.active_tab_for(normalised)

    return templates.TemplateResponse(
        request=request,
        name="category_c.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "category_slug": normalised,
            "category_label": label,
            "category_one_liner": one_liner,
            "category_count": count,
            "category_cards": cards,
            "active_tab": active_tab,
        },
    )
