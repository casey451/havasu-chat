"""robots.txt + sitemap.xml routes, extracted from app/main.py (audit 2026-07-01
decomposition). ``app/seo/urls.py`` already owned the canonical base-URL helpers;
this puts the robots + sitemap *builders and routes* in the same package.

Pure move: the routes, paths, cached-XML shape, and output are unchanged. The
router is mounted from ``app.main``; ``app.main`` re-exports the sitemap builders
+ ``_sitemap_cache`` + ``_SITEMAP_BUILDERS`` under their historical private names
so existing callers/tests (``app.main._build_sitemap_pages_xml`` etc.) resolve
unchanged. Imports only leaf modules (``seo.urls`` never imports ``main``), so no
cycle.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, or_

from app.core.rate_limit import limiter, public_html_rate_limit
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Event, Provider
from app.monitoring.canaries import not_canary_clause
from app.seo.urls import base_url as _base_url

logger = logging.getLogger(__name__)

router = APIRouter()

_SITEMAP_TTL_SECONDS = 3600
# P1.6 — /sitemap.xml is a sitemap *index* referencing per-section child
# sitemaps (pages / providers / events) so each section can scale and carry
# honest <lastmod> values:
#   - pages: static surfaces carry no lastmod (they rarely change; advertising
#     "today" every day told crawlers everything churned daily). Category pages
#     use the max Provider.updated_at of their member categories.
#   - providers: Provider.updated_at (as before).
#   - events: Event.created_at (no updated_at column).
# Each section is cached independently for one hour (same TTL/shape rationale
# as the original single-document cache). ``_sitemap_cache`` keys are section
# names; tests reset the whole dict between cases.
_sitemap_cache: dict[str, tuple[float, str]] = {}

_SITEMAP_SECTIONS = ("pages", "providers", "events")


# A3 (anti-scrape): AI training / scraper crawlers blocked from the whole site.
# Search engines (Googlebot, Bingbot, DuckDuckBot, …) are deliberately NOT on
# this list — blocking them would tank the SEO this whole effort is for. These
# are the well-published AI/data-harvest agents that honor robots.txt; the ones
# that don't are Cloudflare/limiter's job (Track A1/A2), not robots'.
_BLOCKED_CRAWLER_AGENTS: tuple[str, ...] = (
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "anthropic-ai",
    "ClaudeBot",
    "Claude-Web",
    "CCBot",
    "Google-Extended",
    "PerplexityBot",
    "Bytespider",
    "Amazonbot",
    "Applebot-Extended",
    "FacebookBot",
    "meta-externalagent",
    "Diffbot",
    "Omgilibot",
    "Omgili",
    "ImagesiftBot",
    "DataForSeoBot",
    "YouBot",
    "cohere-ai",
    "Scrapy",
)

# Paths every crawler (even the allowed ones) should skip: the JSON/data APIs and
# the bulk iCal feed are cheap full-dataset pulls with no SEO value to crawl.
_ROBOTS_DISALLOWED_PATHS: tuple[str, ...] = ("/api/", "/events.ics")


def _build_robots_txt(base: str) -> str:
    """robots.txt body: block AI/scraper agents site-wide, keep the HTML
    directory crawlable for search engines, and steer everyone away from the
    JSON/data endpoints. ``Allow: /`` stays in the wildcard group (default-allow
    semantics + back-compat); the per-path ``Disallow`` wins by longest-match."""
    lines: list[str] = []
    # One grouped block: many ``User-agent`` lines sharing a single ``Disallow: /``
    # rule (valid per the robots spec — a group may name multiple agents).
    for agent in _BLOCKED_CRAWLER_AGENTS:
        lines.append(f"User-agent: {agent}")
    lines.append("Disallow: /")
    lines.append("")
    # Everyone else (incl. search engines): crawl HTML, skip the data endpoints.
    lines.append("User-agent: *")
    for path in _ROBOTS_DISALLOWED_PATHS:
        lines.append(f"Disallow: {path}")
    lines.append("Allow: /")
    lines.append("")
    lines.append(f"Sitemap: {base}/sitemap.xml")
    return "\n".join(lines) + "\n"


@router.get("/robots.txt", response_class=PlainTextResponse)
@limiter.limit(public_html_rate_limit)
def robots_txt(request: Request) -> PlainTextResponse:
    return PlainTextResponse(_build_robots_txt(_base_url()))


def _sitemap_url_entry(loc: str, lastmod: str | None = None) -> str:
    lastmod_line = f"    <lastmod>{lastmod}</lastmod>\n" if lastmod else ""
    return (
        "  <url>\n"
        f"    <loc>{html.escape(loc, quote=False)}</loc>\n"
        f"{lastmod_line}"
        "  </url>\n"
    )


def _format_lastmod(value: datetime | None, *, today_iso: str) -> str:
    if value is None:
        return today_iso
    try:
        return value.date().isoformat()
    except Exception:
        return today_iso


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    try:
        return value.date().isoformat()
    except Exception:
        return None


def _wrap_urlset(entries: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(entries)
        + "</urlset>\n"
    )


def _build_sitemap_pages_xml() -> str:
    base = _base_url()
    entries: list[str] = []

    # Static surfaces. /home is the canonical editorial home; bare / 301s to it
    # and so is intentionally NOT listed. No <lastmod>: these are stable pages
    # and the element is optional — omitting beats fabricating daily churn.
    static_paths = (
        "/home",
        "/chat",
        "/map",
        "/gas",
        "/today",
        "/events-ui",
        "/categories",
        # Editorial guide pages (2026-07-01 master audit §6.5: the strongest
        # editorial content on the site was invisible to crawlers).
        "/lake",
        "/night",
        "/family",
        "/seniors",
        "/privacy",
        "/terms",
        "/contribute",
        "/about",
        "/help",
        "/contact",
        "/portal",
        "/portal/claim",
    )
    for path in static_paths:
        entries.append(_sitemap_url_entry(f"{base}{path}"))

    # The retired flat /categories/{slug} bucket routes 301 to taxonomy
    # departments (A.3 nav rewire) and are deliberately NOT listed — a sitemap
    # should never advertise a redirect. Departments + leaves are enumerated
    # below.

    # P2.1 dedicated trade pages — only trades clearing the thin-page gate
    # (TRADE_PAGE_MIN_PROVIDERS) are listed; under-minimum trades 404 and are
    # excluded here so near-empty templated pages are never exposed to crawlers.
    # lastmod: max updated_at of the trade's matching providers.
    try:
        from app.categories.leaf_pages import (
            LEAF_PAGE_MIN_PROVIDERS,
            leaf_renderable_count,
            resolve_leaf,
        )
        from app.categories.trades import (
            LEAF_TWINS,
            TRADE_LEAF_DEPARTMENT_SLUG,
            TRADE_PARENT_SLUG,
            _trade_provider_rows,
        )
        from app.categories.trades import qualifying_trades as _qualifying_trades

        with SessionLocal() as db:
            for trade_obj, _count in _qualifying_trades(db):
                # PR-B consolidation: a trade whose taxonomy-leaf twin ships
                # 301s to it, so the sitemap lists only the leaf (below).
                twin_slug = LEAF_TWINS.get(trade_obj.slug)
                if twin_slug:
                    twin = resolve_leaf(db, TRADE_LEAF_DEPARTMENT_SLUG, twin_slug)
                    if (
                        twin is not None
                        and leaf_renderable_count(db, twin)
                        >= LEAF_PAGE_MIN_PROVIDERS
                    ):
                        continue
                rows = _trade_provider_rows(db, trade_obj)
                stamps2 = [r.updated_at for r in rows if r.updated_at is not None]
                lastmod = _iso_or_none(max(stamps2)) if stamps2 else None
                entries.append(
                    _sitemap_url_entry(
                        f"{base}/categories/{TRADE_PARENT_SLUG}/{trade_obj.slug}",
                        lastmod,
                    )
                )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("sitemap: trade page enumeration failed: %s", exc)

    # B.2 taxonomy leaf pages + department landings — only gate-clearing leaves
    # (sub-gate leaves 404), and only departments that own at least one such
    # leaf (so a listed landing is never empty). No <lastmod> — the counts move
    # on the order of days and a per-leaf max(updated_at) would be N queries.
    try:
        from app.categories.leaf_pages import qualifying_leaves

        with SessionLocal() as db:
            seen_departments: set[str] = set()
            for leaf, _count in qualifying_leaves(db):
                entries.append(
                    _sitemap_url_entry(
                        f"{base}/categories/{leaf.department_slug}/{leaf.slug}"
                    )
                )
                if leaf.department_slug not in seen_departments:
                    seen_departments.add(leaf.department_slug)
                    entries.append(
                        _sitemap_url_entry(f"{base}/categories/{leaf.department_slug}")
                    )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("sitemap: leaf page enumeration failed: %s", exc)

    # A3 cuisine SEO landings (/lake-havasu/{cuisine}) — only cuisines clearing
    # the thin-page gate (CUISINE_PAGE_MIN_PROVIDERS); thin cuisines 404 and are
    # excluded so near-empty templated pages are never exposed to crawlers.
    try:
        from app.categories.cuisine_pages import qualifying_cuisines

        with SessionLocal() as db:
            for cuisine_slug, _label, _count in qualifying_cuisines(db):
                entries.append(
                    _sitemap_url_entry(f"{base}/lake-havasu/{cuisine_slug}")
                )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("sitemap: cuisine page enumeration failed: %s", exc)

    return _wrap_urlset(entries)


def _build_sitemap_providers_xml() -> str:
    base = _base_url()
    today_iso = datetime.now(timezone.utc).date().isoformat()
    entries: list[str] = []
    try:
        with SessionLocal() as db:
            providers = (
                db.query(Provider.slug, Provider.updated_at)
                .filter(
                    Provider.is_active.is_(True),
                    Provider.draft.is_(False),
                    Provider.slug.isnot(None),
                    # A4: seeded canary listings never enter the sitemap (we don't
                    # want a decoy business indexed by Google).
                    not_canary_clause(),
                )
                .all()
            )
        for slug, updated_at in providers:
            if not slug:
                continue
            entries.append(
                _sitemap_url_entry(
                    f"{base}/provider/{slug}",
                    _format_lastmod(updated_at, today_iso=today_iso),
                )
            )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("sitemap: provider enumeration failed: %s", exc)
    return _wrap_urlset(entries)


def _build_sitemap_events_xml() -> str:
    base = _base_url()
    today_iso = datetime.now(timezone.utc).date().isoformat()
    # Lake Havasu LOCAL date for the past/future split — a July-1 event is not
    # past while it is still July 1 in Arizona, even once UTC rolls over.
    today_local = now_lake_havasu().date()
    entries: list[str] = []
    try:
        with SessionLocal() as db:
            # 2026-07-01 master audit §5.1: never advertise a past event to
            # crawlers — half the event sitemap was past-dated. A one-off stays
            # listed through its (end) date; a recurring series is evergreen
            # (its ``date`` is just the RRULE anchor, often long past).
            events = (
                db.query(Event.id, Event.created_at)
                .filter(
                    Event.status == "live",
                    or_(
                        Event.is_recurring.is_(True),
                        Event.rrule.isnot(None),
                        func.coalesce(Event.end_date, Event.date) >= today_local,
                    ),
                )
                .all()
            )
        for event_id, created_at in events:
            entries.append(
                _sitemap_url_entry(
                    f"{base}/events/{event_id}",
                    _format_lastmod(created_at, today_iso=today_iso),
                )
            )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("sitemap: event enumeration failed: %s", exc)
    return _wrap_urlset(entries)


_SITEMAP_BUILDERS = {
    "pages": _build_sitemap_pages_xml,
    "providers": _build_sitemap_providers_xml,
    "events": _build_sitemap_events_xml,
}


def _build_sitemap_index_xml() -> str:
    base = _base_url()
    refs = "".join(
        f"  <sitemap>\n    <loc>{base}/sitemap-{section}.xml</loc>\n  </sitemap>\n"
        for section in _SITEMAP_SECTIONS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + refs
        + "</sitemapindex>\n"
    )


def _get_cached_sitemap_xml(section: str) -> str:
    now = datetime.now(timezone.utc).timestamp()
    cache = _sitemap_cache.get(section)
    if cache is not None and (now - cache[0]) < _SITEMAP_TTL_SECONDS:
        return cache[1]
    if section == "index":
        xml = _build_sitemap_index_xml()
    else:
        xml = _SITEMAP_BUILDERS[section]()
    _sitemap_cache[section] = (now, xml)
    return xml


@router.get("/sitemap.xml")
@limiter.limit(public_html_rate_limit)
def sitemap_xml(request: Request) -> Response:
    return Response(
        content=_get_cached_sitemap_xml("index"),
        media_type="application/xml",
    )


@router.get("/sitemap-{section}.xml")
@limiter.limit(public_html_rate_limit)
def sitemap_section_xml(request: Request, section: str) -> Response:
    if section not in _SITEMAP_SECTIONS:
        raise HTTPException(status_code=404, detail="unknown_sitemap")
    return Response(
        content=_get_cached_sitemap_xml(section),
        media_type="application/xml",
    )
