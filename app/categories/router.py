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
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.categories import leaf_pages
from app.categories import queries as cat_queries
from app.categories import subcategories as subcats
from app.categories import trades as trade_pages
from app.categories.queries import CategoryFacets
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import Provider
from app.home import sandstone as home_sandstone
from app.home import sponsor_store
from app.home.queries import _provider_image_url
from app.home.router import _utility_chips as _home_utility_chips
from app.seo.urls import absolute_url
from app.v1.categories import BUCKET_SLUG_REDIRECTS

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["categories"])

# Renamed tier-1 route slugs -> their canonical destination. ``professional``
# became ``professional-services`` when WP-9 split the 13th canonical category
# out of public-civic; old bookmarks/links 301 to the new page.
ROUTE_SLUG_ALIASES: dict[str, str] = {
    "professional": "/categories/professional-services",
}


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
_FALLBACK_BLURB = "Local picks in Lake Havasu."

# Per BUILD.md no-zero rule: a card with count==0 never says "0 listings";
# it shows this short editorial note instead.
_EMPTY_BLURB = "Coming soon."


def reset_index_cache() -> None:
    """Drop the cached /categories payload. Test seam."""
    global _index_cache  # noqa: PLW0603 -- module-level cache by design
    _index_cache = None


def _category_count(db: Session, route_slug: str) -> int:
    """Count active non-draft providers that belong on ``route_slug`` (pivot).

    Uses ``route_provider_filter`` (subcategory-primary, legacy fallback) so the
    count matches the listing. Returns 0 on any DB hiccup or empty route.
    """
    if not route_slug:
        return 0
    try:
        from sqlalchemy import func as sa_func

        row = (
            db.query(sa_func.count(Provider.id))
            .filter(
                cat_queries.route_provider_filter(route_slug),
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


def _peek_provider(db: Session, route_slug: str) -> Provider | None:
    """Top-rated active non-draft provider on ``route_slug``, or None.

    Returns None on any DB hiccup; empty route short-circuits.
    """
    if not route_slug:
        return None
    try:
        return (
            db.query(Provider)
            .filter(
                cat_queries.route_provider_filter(route_slug),
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
    first, then the D4 tile routes. Per-row shape:

      slug          URL segment ("eat-drink", "auto-rv-fuel", ...)
      label         display name from CATEGORY_DISPLAY
      blurb         short one-liner from CATEGORY_DISPLAY
      count         int >= 0
      peek_images   list of {url, name} -- 0 or 1 entries today
      empty_blurb   editorial copy shown when count == 0
    """
    rows: list[dict[str, Any]] = []
    for slug in cat_queries.CATEGORY_FILTERS:
        display = cat_queries.CATEGORY_DISPLAY.get(slug)
        if display is not None:
            label, blurb = display
        else:
            label = slug.replace("-", " ").capitalize()
            blurb = _FALLBACK_BLURB

        count = _category_count(db, slug)

        peek_images: list[dict[str, str]] = []
        if count > 0:
            peek = _peek_provider(db, slug)
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

    Identity is preserved across cache hits -- callers within the TTL
    window get the exact same list object.
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


def _facets_from_query(
    *,
    subcategory: str | None,
    open_now: str | None,
    rating: str | None,
    sort: str | None,
    late: str | None = None,
    weekends: str | None = None,
    cuisine: str | None = None,
) -> CategoryFacets:
    """Parse raw query params into a validated CategoryFacets."""

    def _flag(val: str | None) -> bool:
        # Truthy unless explicitly empty/zero/false — so both ``open=1`` and the
        # threshold-style ``rating=4`` toggle on.
        return val is not None and str(val).strip().lower() not in {"", "0", "false", "no"}

    sort_key = (sort or "").strip().lower()
    # Default = volume-weighted "Locals' favorites" (01_UI_BUILD_GUIDE.md §4.8),
    # so institutions outrank thin 5.0/3-review outliers out of the box.
    if sort_key not in {"closest", "alpha", "favorites"}:
        sort_key = "favorites"
    sub = (subcategory or "").strip().lower() or None
    if sub and subcats.subcategory_by_slug(sub) is None:
        sub = None
    cui = (cuisine or "").strip().lower() or None
    if cui and cui not in subcats.cuisine_slugs_in_order():
        cui = None
    return CategoryFacets(
        subcategory=sub,
        cuisine=cui,
        open_now=_flag(open_now),
        top_rated=_flag(rating),
        open_late=_flag(late),
        open_weekends=_flag(weekends),
        sort=sort_key,
    )


_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("default", "Featured"),
    ("closest", "Closest"),
    ("alpha", "A–Z"),
)


def _page_summary(*, page: int, per_page: int, total: int) -> str:
    """Human "Showing 1-60 of 308" line for a paged grid (M-20)."""
    if total <= 0:
        return ""
    first = (page - 1) * per_page + 1
    last = min(page * per_page, total)
    if first > total:  # page past the end -> empty window
        return f"Showing 0 of {total}"
    return f"Showing {first}-{last} of {total}"


def _render_category_page(
    request: Request,
    db: Session,
    *,
    route_slug: str,
    facets: CategoryFacets,
    label: str,
    one_liner: str,
    chip_bucket_id: str | None,
    active_subcategory: str | None,
    active_tab: str,
    page: int = 1,
    extra_context: dict[str, Any] | None = None,
) -> HTMLResponse:
    """Shared render for the plural mega-page and the subcategory SEO landing.

    ``route_slug`` is the ``CATEGORY_FILTERS`` route providers are drawn from;
    ``active_subcategory`` (when set) both filters and highlights its chip.
    """
    now = now_lake_havasu()
    page = max(int(page), 1)
    per_page = cat_queries._DEFAULT_CARD_LIMIT
    cards, total = cat_queries.category_listing(
        db, route_slug, now=now, facets=facets, limit=per_page, page=page
    )

    # C8/N-16: chips are generated from subtypes ACTUALLY present (ordered by
    # count, zero-member omitted) rather than the static curated bucket list, so
    # a route with no live subtypes renders no chip row at all.
    chips = cat_queries.subcategory_chips_for_route(db, route_slug)
    # C-2: cuisine drill-down — a second-level chip row, only populated on routes
    # whose providers carry cuisine signals (Food & Drink). Empty elsewhere.
    cuisine_chips = cat_queries.available_cuisines_for_route(db, route_slug)

    def facet_href(**changes: str | None) -> str:
        """Current path with facet params toggled; drops falsy values.

        Always drops ``page`` on a facet change -- a narrower result set
        invalidates the old page index -- while preserving every OTHER active
        query param (the DL-20 "All"-chip param-preservation rule).
        """
        q = {k: v for k, v in request.query_params.items()}
        q.pop("page", None)
        for key, val in changes.items():
            if val in (None, "", False):
                q.pop(key, None)
            else:
                q[key] = str(val)
        tail = urlencode(sorted(q.items()))
        return request.url.path + ("?" + tail if tail else "")

    def page_href(target_page: int) -> str:
        """Current URL with ``page`` set (or dropped for page 1) -- preserves all
        active facet params on paged views (M-20)."""
        q = {k: v for k, v in request.query_params.items()}
        if target_page <= 1:
            q.pop("page", None)
        else:
            q["page"] = str(target_page)
        tail = urlencode(sorted(q.items()))
        return request.url.path + ("?" + tail if tail else "")

    total_pages = max((total + per_page - 1) // per_page, 1) if total else 1
    prev_url = page_href(page - 1) if page > 1 else None
    next_url = page_href(page + 1) if page < total_pages else None

    # DL-20: the subtype "All" chip clears the subcategory narrowing but PRESERVES
    # every other active param (open / rating / sort / cuisine). It always targets
    # the plural bucket route -- on the /lake-havasu/{sub} landing the subcategory
    # lives in the path, so "All" walks up to /categories/{route_slug}.
    def _all_chip_url() -> str:
        q = {
            k: v
            for k, v in request.query_params.items()
            if k not in ("sub", "page")
        }
        tail = urlencode(sorted(q.items()))
        return f"/categories/{route_slug}" + ("?" + tail if tail else "")

    all_chip_url = _all_chip_url()

    # DL-20 / item 32: the sort-explainer must describe the ACTIVE sort, not a
    # static favorites blurb. Closest/A-Z carry their own one-liner.
    sort_notes = {
        "favorites": "Favorites = rating weighted by review volume, so institutions rank first.",
        "default": "Favorites = rating weighted by review volume, so institutions rank first.",
        "closest": "Closest = nearest to the Lake Havasu City civic center first.",
        "alpha": "Sorted A to Z by name.",
    }
    sort_note = sort_notes.get(facets.sort, sort_notes["favorites"])

    # DL-20 C7: a single honest active-filter summary line. Lists the narrowing
    # facets (subcategory / cuisine / open-now) with the result count and a
    # param-preserving clear link back to the bare route.
    active_filter_labels: list[str] = []
    if active_subcategory:
        sub_obj = subcats.subcategory_by_slug(active_subcategory)
        active_filter_labels.append(sub_obj.label if sub_obj else active_subcategory)
    elif facets.subcategory:
        sub_obj = subcats.subcategory_by_slug(facets.subcategory)
        active_filter_labels.append(sub_obj.label if sub_obj else facets.subcategory)
    if facets.cuisine:
        cui_label = subcats.cuisine_label(facets.cuisine)
        active_filter_labels.append(cui_label or facets.cuisine)
    if facets.open_now:
        active_filter_labels.append("Open now")

    context: dict[str, Any] = {
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "category_slug": route_slug,
            "category_label": label,
            "category_one_liner": one_liner,
            "category_count": total,
            "category_cards": cards,
            "active_tab": active_tab,
            "subcat_chips": chips,
            "active_subcategory": active_subcategory,
            "cuisine_chips": cuisine_chips,
            "active_cuisine": facets.cuisine,
            "facets": facets,
            "sort_options": _SORT_OPTIONS,
            "facet_href": facet_href,
            "page_href": page_href,
            # Pagination context (M-20).
            "page": page,
            "total_pages": total_pages,
            "per_page": per_page,
            "page_summary": _page_summary(page=page, per_page=per_page, total=total),
            "prev_url": prev_url,
            "next_url": next_url,
            # DL-20 sort/filter honesty context.
            "sort_note": sort_note,
            "active_filter_labels": active_filter_labels,
            # The subtype "All" chip drops only ``sub`` (and page) but PRESERVES
            # every other active param (open / rating / sort / cuisine) -- DL-20.
            "all_chip_url": all_chip_url,
            # A full reset link for the active-filter "clear" control: bare route.
            "clear_filters_url": f"/categories/{route_slug}",
            # One labeled sponsored slot (≤1, real-or-omit). active_promoted is the
            # single page-wide promoted row; None -> no slot (never a fake sponsor).
            "sponsored": sponsor_store.active_promoted(db),
            "primary_nav": home_sandstone.primary_nav(),
            "mega_columns": home_sandstone.mega_columns(db),
            "utility_chips": _home_utility_chips(db),
        }
    if extra_context:
        context.update(extra_context)
    return templates.TemplateResponse(
        request=request,
        name="category_sandstone.html",
        context=context,
    )


@router.get("/categories/{slug}", response_class=HTMLResponse, response_model=None)
def serve_category(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    subcategory: str | None = Query(None, alias="sub"),
    open_now: str | None = Query(None, alias="open"),
    rating: str | None = Query(None),
    sort: str | None = Query(None),
    late: str | None = Query(None),
    weekends: str | None = Query(None),
    cuisine: str | None = Query(None),
    trade: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse | RedirectResponse:
    """Render a single category page with subcategory chips + faceted filters.

    Master-bucket slugs (``food-drink``, ``events``, …) 301 to their
    mapped Tier-1 ``/categories/{slug}`` page. Returns 404 when the
    slug is neither a known route nor a master bucket.
    """
    normalised = (slug or "").strip().lower()
    if not cat_queries.is_valid_category_slug(normalised):
        alias_dest = ROUTE_SLUG_ALIASES.get(normalised)
        if alias_dest:
            return RedirectResponse(url=alias_dest, status_code=301)
        bucket_dest = BUCKET_SLUG_REDIRECTS.get(normalised)
        if bucket_dest:
            return RedirectResponse(url=bucket_dest, status_code=301)
        # B.2: a taxonomy department (level-0 with child leaves) renders its
        # landing page (child leaves + counts), distinct from the flat routes.
        dept = leaf_pages.resolve_department(db, normalised)
        if dept is not None:
            return _render_department_page(request, db, dept)
        raise HTTPException(status_code=404, detail="unknown_category")

    label, one_liner = cat_queries.CATEGORY_DISPLAY[normalised]
    facets = _facets_from_query(
        subcategory=subcategory,
        open_now=open_now,
        rating=rating,
        sort=sort,
        late=late,
        weekends=weekends,
        cuisine=cuisine,
    )

    # P2.1: on the trades parent, link the dedicated trade pages (gate-clearing
    # trades only), and when a promoted ``?trade=`` facet value is present,
    # canonicalize to the dedicated trade page instead of the clean category
    # URL. Unpromoted ``?trade=`` values keep the existing behavior
    # (canonical_url drops the query string -> clean category canonical).
    extra_context: dict[str, Any] = {}
    if normalised == trade_pages.TRADE_PARENT_SLUG:
        qualifying = trade_pages.qualifying_trades(db)
        extra_context["trade_links"] = [
            {
                "label": t.label,
                "count": n,
                "url": f"/categories/{trade_pages.TRADE_PARENT_SLUG}/{t.slug}",
            }
            for t, n in qualifying
        ]
        promoted = trade_pages.trade_by_slug(trade)
        if promoted is not None and any(t.slug == promoted.slug for t, _ in qualifying):
            extra_context["canonical_override"] = absolute_url(
                f"/categories/{trade_pages.TRADE_PARENT_SLUG}/{promoted.slug}"
            )

    return _render_category_page(
        request,
        db,
        route_slug=normalised,
        facets=facets,
        label=label,
        one_liner=one_liner,
        chip_bucket_id=subcats.bucket_for_category_route(normalised),
        active_subcategory=None,
        page=page,
        active_tab=cat_queries.active_tab_for(normalised),
        extra_context=extra_context,
    )


@router.get(
    "/categories/{parent}/{trade}", response_class=HTMLResponse, response_model=None
)
def serve_trade_page(
    request: Request,
    parent: str,
    trade: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Dedicated server-rendered department/leaf landing page.

    Two resolvers, in order:

    1. **Curated home-services trades** (SEO P2.1/P2.2) — the ten promoted
       trades under ``home-property-services``, with their rich curated intro /
       FAQ copy and Provider needle-matching. Unchanged behavior.
    2. **Generalized A.3 taxonomy leaves** (Workstream B.1) — any
       ``/categories/{department}/{leaf}`` resolving to a ``level = 1`` leaf
       whose parent is the named ``level = 0`` department, listed by the leaf's
       ``category_id`` via the ``entity_categories.is_primary`` join.

    Unknown parent/leaf -> 404. Thin-page gate (shared): below
    ``*_MIN_PROVIDERS`` active listings the page 404s and is kept out of the
    sitemap / never linked (Google scaled-content rule).

    JSON-LD per DECISION D4 (Casey, final): BreadcrumbList + ItemList only —
    NO AggregateRating structured data anywhere on these pages.
    """
    parent_key = (parent or "").strip().lower()

    # 1. Curated trade under the home-services parent (existing behavior).
    if parent_key == trade_pages.TRADE_PARENT_SLUG:
        trade_obj = trade_pages.trade_by_slug(trade)
        if trade_obj is not None:
            return _render_trade_page(request, db, trade_obj)

    # 2. Generalized taxonomy leaf (B.1).
    leaf = leaf_pages.resolve_leaf(db, parent_key, trade)
    if leaf is not None:
        return _render_leaf_page(request, db, leaf)

    raise HTTPException(status_code=404, detail="unknown_category")


def _render_trade_page(
    request: Request, db: Session, trade_obj: trade_pages.Trade
) -> HTMLResponse:
    """Render a curated home-services trade page (the original P2.1/P2.2 path)."""
    now = now_lake_havasu()
    cards, total, providers = trade_pages.trade_listing(db, trade_obj, now=now)
    if total < trade_pages.TRADE_PAGE_MIN_PROVIDERS:
        # Scaled-content gate: below the minimum the page does not exist.
        raise HTTPException(status_code=404, detail="trade_below_minimum")

    parent_label, _ = cat_queries.CATEGORY_DISPLAY[trade_pages.TRADE_PARENT_SLUG]
    page_path = f"/categories/{trade_pages.TRADE_PARENT_SLUG}/{trade_obj.slug}"

    breadcrumb_jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": absolute_url("/home"),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": parent_label,
                "item": absolute_url(f"/categories/{trade_pages.TRADE_PARENT_SLUG}"),
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": trade_obj.label,
                "item": absolute_url(page_path),
            },
        ],
    }
    # D4: a plain ItemList of the listed businesses — names + URLs only, no
    # nested LocalBusiness payloads and explicitly NO AggregateRating.
    itemlist_jsonld = _itemlist_jsonld(
        f"{trade_obj.label} in Lake Havasu City, AZ", total, providers
    )

    label_lower = trade_obj.label.lower()
    faqs = [
        (
            q.format(
                n=total,
                label=trade_obj.label,
                label_lower=label_lower,
                singular=trade_obj.singular,
            ),
            a.format(
                n=total,
                label=trade_obj.label,
                label_lower=label_lower,
                singular=trade_obj.singular,
            ),
        )
        for q, a in trade_obj.faqs
    ]

    return templates.TemplateResponse(
        request=request,
        name="category_trade.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "parent_slug": trade_pages.TRADE_PARENT_SLUG,
            "parent_label": parent_label,
            "parent_href": f"/categories/{trade_pages.TRADE_PARENT_SLUG}",
            "trade_slug": trade_obj.slug,
            "trade_label": trade_obj.label,
            "trade_count": total,
            "trade_intro": trade_obj.intro,
            "trade_faqs": faqs,
            "category_cards": cards,
            "breadcrumb_jsonld": breadcrumb_jsonld,
            "itemlist_jsonld": itemlist_jsonld,
            "active_tab": cat_queries.active_tab_for(trade_pages.TRADE_PARENT_SLUG),
            "primary_nav": home_sandstone.primary_nav(),
            "mega_columns": home_sandstone.mega_columns(db),
            "utility_chips": _home_utility_chips(db),
        },
    )


def _itemlist_jsonld(name: str, total: int, providers: list[Provider]) -> dict[str, Any]:
    """D4 ItemList: business names + URLs only — no nested LocalBusiness, no
    AggregateRating. Shared by trade and leaf pages."""
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "numberOfItems": total,
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": idx,
                "name": prov.provider_name,
                "url": absolute_url(f"/provider/{prov.slug}"),
            }
            for idx, prov in enumerate(providers, start=1)
            if prov.slug
        ],
    }


# A generic, honest intro for a leaf page until B.2 adds per-leaf curated copy.
# No fabricated specifics — just the ranking-transparency line the whole site
# uses. ``{name}`` is the leaf's display noun (e.g. "Plumbing", "Restaurants").
_LEAF_INTRO_TEMPLATE = (
    "{name} in Lake Havasu City, AZ. The {n} listings below are ranked by a "
    "volume-weighted rating, so a business with a strong rating across many "
    "reviews ranks above one with a perfect score from only a couple. Ratings "
    "and review counts come from real public reviews — Ask Hava never "
    "fabricates a rating, and any sponsored placement is clearly labeled."
)


def _render_leaf_page(
    request: Request, db: Session, leaf: leaf_pages.Leaf
) -> HTMLResponse:
    """Render a generalized A.3 taxonomy leaf page (B.1).

    Lists the leaf's primary-linked Providers, applies the shared thin-page
    gate, and reuses ``category_trade.html``. Per-leaf curated intro/FAQ copy
    and the department-landing breadcrumb link land in B.2 — here the breadcrumb
    shows the department as plain text (``parent_href`` omitted) and the FAQ
    block is empty.
    """
    now = now_lake_havasu()
    cards, total, providers = leaf_pages.leaf_listing(db, leaf, now=now)
    if total < leaf_pages.LEAF_PAGE_MIN_PROVIDERS:
        raise HTTPException(status_code=404, detail="leaf_below_minimum")

    page_path = f"/categories/{leaf.department_slug}/{leaf.slug}"
    dept_path = f"/categories/{leaf.department_slug}"
    # Three-level breadcrumb (Home › department › leaf) — the department landing
    # exists as of B.2, so the crumb links to it.
    breadcrumb_jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": absolute_url("/home"),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": leaf.department_name,
                "item": absolute_url(dept_path),
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": leaf.name,
                "item": absolute_url(page_path),
            },
        ],
    }
    itemlist_jsonld = _itemlist_jsonld(
        f"{leaf.name} in Lake Havasu City, AZ", total, providers
    )

    return templates.TemplateResponse(
        request=request,
        name="category_trade.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "parent_slug": leaf.department_slug,
            "parent_label": leaf.department_name,
            "parent_href": dept_path,
            "trade_slug": leaf.slug,
            "trade_label": leaf.name,
            "trade_count": total,
            "trade_intro": _LEAF_INTRO_TEMPLATE.format(name=leaf.name, n=total),
            "trade_faqs": [],
            "category_cards": cards,
            "breadcrumb_jsonld": breadcrumb_jsonld,
            "itemlist_jsonld": itemlist_jsonld,
            "active_tab": cat_queries.active_tab_for(leaf.department_slug),
            "primary_nav": home_sandstone.primary_nav(),
            "mega_columns": home_sandstone.mega_columns(db),
            "utility_chips": _home_utility_chips(db),
        },
    )


def _render_department_page(
    request: Request, db: Session, dept: Any
) -> HTMLResponse:
    """Render a taxonomy department landing (B.2): the department's gate-clearing
    child leaves with live counts + links, aggregated from the leaf join."""
    now = now_lake_havasu()
    pairs = leaf_pages.department_leaves(db, dept)
    if not pairs:
        # Every child leaf is sub-gate — nothing shippable, so the landing does
        # not exist (anti-thin-content, same spirit as the leaf gate).
        raise HTTPException(status_code=404, detail="department_no_shippable_leaves")
    leaves = [
        {
            "name": leaf.name,
            "count": count,
            "url": f"/categories/{leaf.department_slug}/{leaf.slug}",
        }
        for leaf, count in pairs
    ]
    listing_total = sum(count for _, count in pairs)
    dept_path = f"/categories/{dept.slug}"

    breadcrumb_jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": absolute_url("/home"),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": dept.name,
                "item": absolute_url(dept_path),
            },
        ],
    }
    # ItemList of the child leaf PAGES (names + URLs) — no AggregateRating (D4).
    itemlist_jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{dept.name} categories in Lake Havasu City, AZ",
        "numberOfItems": len(leaves),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": idx,
                "name": leaf["name"],
                "url": absolute_url(leaf["url"]),
            }
            for idx, leaf in enumerate(leaves, start=1)
        ],
    }

    return templates.TemplateResponse(
        request=request,
        name="category_department.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "department_slug": dept.slug,
            "department_label": dept.name,
            "leaves": leaves,
            "leaf_total": len(leaves),
            "listing_total": listing_total,
            "breadcrumb_jsonld": breadcrumb_jsonld,
            "itemlist_jsonld": itemlist_jsonld,
            "active_tab": cat_queries.active_tab_for(dept.slug),
            "primary_nav": home_sandstone.primary_nav(),
            "mega_columns": home_sandstone.mega_columns(db),
            "utility_chips": _home_utility_chips(db),
        },
    )


def render_subcategory_landing(
    request: Request,
    db: Session,
    *,
    subcategory_slug: str,
    open_now: str | None = None,
    rating: str | None = None,
    sort: str | None = None,
    late: str | None = None,
    weekends: str | None = None,
) -> HTMLResponse | None:
    """Render the ``/lake-havasu/{subcategory}`` SEO landing, or None if unknown.

    Draws providers from the subcategory's bucket route, pre-filtered to the
    subcategory, with its own ``<h1>`` headline. Returns None so the caller can
    fall through to the provider-slug alias when the token isn't a subcategory.
    """
    sub = subcats.subcategory_by_slug(subcategory_slug)
    if sub is None:
        return None
    bucket_route = _bucket_route_for_subcategory(sub.bucket_id)
    if bucket_route is None:
        return None
    facets = _facets_from_query(
        subcategory=sub.slug,
        open_now=open_now,
        rating=rating,
        sort=sort,
        late=late,
        weekends=weekends,
    )
    headline = f"{sub.label} in Lake Havasu City"
    try:
        page = max(int(request.query_params.get("page", "1")), 1)
    except (TypeError, ValueError):
        page = 1
    return _render_category_page(
        request,
        db,
        route_slug=bucket_route,
        facets=facets,
        label=headline,
        one_liner=sub.one_liner,
        chip_bucket_id=sub.bucket_id,
        active_subcategory=sub.slug,
        active_tab=cat_queries.active_tab_for(bucket_route),
        page=page,
    )


def _bucket_route_for_subcategory(bucket_id: str) -> str | None:
    """Plural ``CATEGORY_FILTERS`` route that hosts a bucket's providers."""
    dest = BUCKET_SLUG_REDIRECTS.get(bucket_id)
    if not dest:
        return None
    route = dest.rsplit("/", 1)[-1]
    return route if cat_queries.is_valid_category_slug(route) else None
