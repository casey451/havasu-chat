from __future__ import annotations

# Force redeploy 2026-04-16
from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

import asyncio
import html
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.admin.provider_approval import router as admin_provider_approval_router
from app.admin.provider_merge_review import router as admin_provider_merge_review_router
from app.admin.router import router as admin_router
from app.admin.sponsor_surface import merchant_upgrade_router
from app.admin.v1_overview import router as admin_v1_overview_router
from app.api.routes.account_alerts import router as account_alerts_router
from app.api.routes.admin_contributions import router as admin_contributions_router
from app.api.routes.admin_jobs import router as admin_jobs_router
from app.api.routes.admin_mentions import router as admin_mentions_router
from app.api.routes.calendar_feed import router as calendar_feed_router
from app.api.routes.captures import router as captures_router
from app.api.routes.category_pages import router as category_pages_router
from app.api.routes.chat import router as concierge_chat_router
from app.api.routes.conditions import router as conditions_router
from app.api.routes.contribute import router as contribute_router
from app.api.routes.gas import router as gas_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.ingest_jobs import router as ingest_jobs_router
from app.api.routes.ingest_publish import router as ingest_publish_router
from app.api.routes.map_data import router as map_data_router
from app.api.routes.micro_ad import router as micro_ad_router
from app.api.routes.themed_groups import router as themed_groups_router
from app.api.routes.today import router as today_router
from app.auth.routes import router as auth_router
from app.auth.session import COOKIE_NAME, SessionMiddleware, cookie_secure_in_prod
from app.categories.router import router as direction_c_categories_router
from app.chat.entity_matcher import refresh_entity_matcher
from app.core.event_quality import friendly_errors
from app.core.provider_name import (
    register_template_filters as _register_template_filters,
)
from app.core.provider_name import (
    register_template_globals as _register_template_globals,
)
from app.core.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal, get_db, init_db
from app.db.models import AuthSession, Event, Provider
from app.digest.routes import router as digest_router
from app.events.time_labels import is_time_tbd
from app.home.chat_route import router as new_chat_ui_router
from app.home.router import router as home_router
from app.home.static_pages import router as static_pages_router
from app.photos.routes import router as photos_router
from app.photos.sweep import run_stuck_photo_sweep
from app.portal.router import router as portal_router
from app.programs.router import router as programs_router
from app.providers.router import router as providers_router
from app.search.routes import router as search_router
from app.v1.routes import router as v1_master_spec_router

logger = logging.getLogger(__name__)

_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
_PRIVACY_MD_PATH = _DOCS_DIR / "privacy.md"
_TOS_MD_PATH = _DOCS_DIR / "tos.md"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
# CLUSTER-08 name hygiene: ``clean_name`` strips vendor marketing tails
# (everything from the first ``|`` onward) at render time so dirty Google
# Places names never reach the page. The codebase has ~10 ``Jinja2Templates``
# instances (one per router module); each must call the shared registrar so
# the filter resolves regardless of which router rendered the template.
_register_template_filters(templates)
# Q5 Plausible analytics: ``plausible_domain`` Jinja global gates the
# ``_partials/plausible.html`` include in every page <head>. Unset env var
# → global is ``None`` → script tag never renders (local dev no-op).
_register_template_globals(templates)
_SENSITIVE_EVENT_KEYS = frozenset({"query", "message", "normalized_query"})


def _is_chat_post_request_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.rstrip("/") or "/"
    except Exception:
        path = url
    return path.endswith("/api/chat")


def _scrub_mapping_keys_inplace(d: dict[str, Any]) -> None:
    for k in list(d.keys()):
        if str(k).lower() in _SENSITIVE_EVENT_KEYS:
            d[k] = "<scrubbed>"


def scrub_sentry_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip chat bodies from Sentry events before upload."""
    req = event.get("request")
    if isinstance(req, dict) and _is_chat_post_request_url(str(req.get("url") or "")):
        req["data"] = "<scrubbed>"
        if "json" in req:
            req["json"] = "<scrubbed>"
    for bag in ("extra", "contexts"):
        bagv = event.get(bag)
        if isinstance(bagv, dict):
            _scrub_mapping_keys_inplace(bagv)
    crumbs = event.get("breadcrumbs")
    if isinstance(crumbs, dict):
        values = crumbs.get("values")
        if isinstance(values, list):
            for c in values:
                if isinstance(c, dict):
                    scrub_sentry_breadcrumb(c, hint)
    return event


def scrub_sentry_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Remove bodies from HTTP-related breadcrumbs that may echo POST payloads."""
    data = crumb.get("data")
    if isinstance(data, dict):
        for k in ("body", "data", "json", "state"):
            if k in data:
                data[k] = "<scrubbed>"
    return crumb


def _privacy_inline_formats(text: str) -> str:
    parts = re.split(r"(\*\*.+?\*\*)", text)
    chunks: list[str] = []
    for p in parts:
        if len(p) >= 4 and p.startswith("**") and p.endswith("**"):
            inner = html.escape(p[2:-2])
            chunks.append(f"<strong>{inner}</strong>")
        else:
            chunks.append(html.escape(p))
    s = "".join(chunks)

    def _link(m: re.Match[str]) -> str:
        u = m.group(1)
        safe = html.escape(u, quote=True)
        return f'<a href="{safe}" rel="noopener noreferrer">{html.escape(u)}</a>'

    s = re.sub(r"(https?://[^\s<>]+)", _link, s)

    def _path_link(m: re.Match[str]) -> str:
        label, path = m.group(1), m.group(2)
        p = html.escape(path, quote=True)
        return f'<a href="{p}">{html.escape(label)}</a>'

    return re.sub(r"\[([^\]]+)\]\((/[^)]+)\)", _path_link, s)


def _render_doc_markdown_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    in_ul = False
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith("<!--") and "-->" in stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(stripped)
            i += 1
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
            i += 1
            continue
        if stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
            i += 1
            continue
        if stripped.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = stripped[2:].lstrip()
            out.append(f"<li>{_privacy_inline_formats(item)}</li>")
            i += 1
            continue
        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            i += 1
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        para_parts: list[str] = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                break
            if lines[i].lstrip().startswith("- ") or lines[i].lstrip().startswith("##"):
                break
            if lines[i].strip().startswith("<!--"):
                break
            para_parts.append(nxt)
            i += 1
        out.append(f"<p>{_privacy_inline_formats(' '.join(para_parts))}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def _render_static_doc(request: Request, *, path: Path, head_title: str) -> HTMLResponse:
    md = path.read_text(encoding="utf-8")
    body = _render_doc_markdown_to_html(md)
    return templates.TemplateResponse(
        request=request,
        name="privacy_doc.html",
        context={"head_title": head_title, "body": body},
    )


def _init_sentry() -> None:
    """Initialize Sentry if SENTRY_DSN is set. Never raise — monitoring is best-effort."""
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        environment = "production" if os.getenv("RAILWAY_ENVIRONMENT") else "development"
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=0.1,
            integrations=[FastApiIntegration(), StarletteIntegration()],
            before_send=scrub_sentry_event,
            before_breadcrumb=scrub_sentry_breadcrumb,
        )
        logger.info("Sentry initialized (environment=%s)", environment)
    except Exception as exc:  # pragma: no cover — best-effort init
        logger.warning("Sentry initialization failed: %s", exc)


_init_sentry()


def run_expired_review_cleanup() -> int:
    """Mark expired pending_review events as deleted. Returns number of rows updated."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        expired = (
            db.query(Event)
            .filter(
                Event.status == "pending_review",
                Event.admin_review_by.isnot(None),
                Event.admin_review_by < now,
            )
            .all()
        )
        for ev in expired:
            ev.status = "deleted"
        db.commit()
        return len(expired)


async def _hourly_cleanup_loop() -> None:
    # OPS-3: one transient failure (DB blip, etc.) must not kill the janitor
    # for the process lifetime — run_stuck_photo_sweep is the safety net for
    # fire-and-forget photo processing. CancelledError is a BaseException, so
    # ``except Exception`` never swallows lifespan shutdown.
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(run_expired_review_cleanup)
            await asyncio.to_thread(run_stuck_photo_sweep)
        except Exception as exc:
            logger.warning("hourly cleanup pass failed; retrying next hour", exc_info=True)
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            except Exception:
                pass  # monitoring is best-effort — never let it kill the loop


def _warm_entity_matcher() -> None:
    """Build the chat entity-matcher index before the first request.

    The index rebuilds on demand with a 5-minute TTL; without warming, the
    first chat request in each fresh process pays the ~50-150ms rebuild.
    Failure is non-fatal — the on-demand path remains the fallback.
    """
    try:
        with SessionLocal() as db:
            refresh_entity_matcher(db)
    except Exception:
        logger.warning("entity-matcher warm failed; first request will rebuild", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("ADMIN_PASSWORD loaded: %s", bool(os.getenv("ADMIN_PASSWORD")))
    init_db()
    await asyncio.to_thread(_warm_entity_matcher)
    task = asyncio.create_task(_hourly_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Havasu Chat", lifespan=lifespan)
app.add_middleware(SessionMiddleware)


# Launch hardening (v48): minimal security headers on HTML responses. CSP is
# deliberately deferred — it requires a full audit of inline scripts/styles
# and image sources, and is tracked in a separate PR. /health and /api/*
# routes skip these headers: Railway probes only need a 200, and JSON API
# clients don't benefit from frame/permissions policies.
_SECURITY_HEADER_SKIP_EXACT = frozenset({"/health"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to HTML responses.

    Skips ``/health`` (Railway liveness probe) and any path beginning with
    ``/api/`` (JSON endpoints — keeps the API contract minimal). HSTS is
    only emitted when the request scheme is HTTPS so dev/local traffic
    doesn't get a long-lived enforcement record.

    Also stamps ``Cache-Control: no-cache`` on every HTML response (P0
    stale-serving fix, 2026-06-07): the dynamic pages are date-stamped
    ("Today" / "This Weekend" buckets, conditions chips) but previously
    shipped with NO freshness directives, leaving browsers, proxies and the
    Railway edge free to apply heuristic caching and replay a days-old
    render — the live ``/events-ui`` served a June 2 "Today" on June 7
    while ``/home`` was fresh (SITE_AUDIT_LIVE_2026-06-03 theme T2/B-04).
    ``no-cache`` forces revalidation on every use; ``setdefault`` lets a
    route opt into a different policy explicitly. Static assets are not
    ``text/html`` and keep their normal validator-based caching.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path in _SECURITY_HEADER_SKIP_EXACT or path.startswith("/api/"):
            return response
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        content_type = (response.headers.get("content-type") or "").lower()
        if content_type.startswith("text/html"):
            response.headers.setdefault(
                "Cache-Control", "no-cache, max-age=0, must-revalidate"
            )
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Canonical-host 301 (SEO, 2026-06): askhava.com is the one public origin.
# ---------------------------------------------------------------------------
#
# Requests arriving on a legacy alias host (the Railway-generated domain)
# permanently redirect to the same path + query on the canonical origin, so
# ranking signals consolidate on askhava.com and the old domain never serves
# duplicate content. Scope is deliberately an explicit alias SET — never a
# blanket "host != canonical" rule — so localhost, the TestClient's
# ``testserver``, and any future preview domains pass through untouched.
#
# Exemptions / safety:
#   * ``/health`` — Railway's liveness probe hits the service domain and must
#     keep getting a 200, not a 301.
#   * Loop guard — if ``BASE_URL`` still points at a legacy host (stale env),
#     redirecting would loop; we pass through instead.
#   * Non-GET/HEAD methods get 308 (preserves method + body); GET/HEAD get
#     the classic 301 search engines consolidate on.
_LEGACY_HOSTS = frozenset({"havasu-chat-production.up.railway.app"})


class CanonicalHostRedirectMiddleware(BaseHTTPMiddleware):
    """301/308 legacy-host traffic to the canonical origin (askhava.com)."""

    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").split(":", 1)[0].strip().lower()
        if host in _LEGACY_HOSTS and request.url.path != "/health":
            canonical = _base_url()
            canonical_host = canonical.split("://", 1)[-1].split("/", 1)[0].lower()
            if canonical_host != host:  # loop guard for a stale BASE_URL env
                dest = canonical + request.url.path
                if request.url.query:
                    dest = f"{dest}?{request.url.query}"
                code = 301 if request.method in ("GET", "HEAD") else 308
                return RedirectResponse(url=dest, status_code=code)
        return await call_next(request)


# Added AFTER SecurityHeadersMiddleware so it sits OUTERMOST in the stack
# (Starlette middleware is LIFO): a legacy-host request redirects before any
# session or header work happens.
app.add_middleware(CanonicalHostRedirectMiddleware)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, __: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"message": RATE_LIMIT_MESSAGE},
    )


app.include_router(v1_master_spec_router)
app.include_router(concierge_chat_router)
app.include_router(contribute_router)
app.include_router(auth_router)
app.include_router(photos_router)
app.include_router(search_router)
app.include_router(category_pages_router)
# PR D6 (2026-05-26): deliberate editorial split — both surfaces ship.
# /categories/{slug} = chrome funnel (mega-tabs); /category/{slug} =
# SEO filter landing (Tier-1 slugs). See category_pages + categories routers.
app.include_router(direction_c_categories_router)
app.include_router(themed_groups_router)
app.include_router(map_data_router)
app.include_router(conditions_router)
app.include_router(today_router)
app.include_router(gas_router)
app.include_router(static_pages_router)
app.include_router(calendar_feed_router)
app.include_router(ingest_router)
app.include_router(ingest_jobs_router)
app.include_router(ingest_publish_router)
app.include_router(captures_router)
app.include_router(admin_router)
app.include_router(admin_v1_overview_router)
app.include_router(admin_contributions_router)
app.include_router(admin_jobs_router)
app.include_router(admin_mentions_router)
app.include_router(admin_provider_approval_router)
app.include_router(admin_provider_merge_review_router)
app.include_router(programs_router)
# BUILD.md step 1: new /home page lives alongside the existing static / chat
# UI during dogfooding. Cuts over to / once we're confident.
app.include_router(home_router)
app.include_router(account_alerts_router)
app.include_router(digest_router)
# Directory pivot V1 (2026-05-13): per-provider profile page at
# /provider/<slug>. Gates the Verified Presence sponsor package.
app.include_router(providers_router)
# BUILD.md step 5: new /chat surface that renders chat turns by
# component.type. Lives alongside the existing static / chat UI
# during dogfooding.
app.include_router(new_chat_ui_router)
# Phase A4 ad-surface activation: loading micro-ad payload + merchant
# featured-listing upgrade funnel (admin review routes live on admin_router).
app.include_router(micro_ad_router)
app.include_router(merchant_upgrade_router)
app.include_router(portal_router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
# Mount the more-specific /static/biz-photos BEFORE the broad /static mount.
# Starlette matches mounts in registration order; if /static is registered first
# it shadows /static/biz-photos (the request resolves against app/static -> 404).
_BIZ_PHOTOS_DIR = Path("/data/biz-photos")
if _BIZ_PHOTOS_DIR.is_dir():
    app.mount(
        "/static/biz-photos",
        StaticFiles(directory=str(_BIZ_PHOTOS_DIR)),
        name="biz_photos",
    )
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

_CONTRIB_UPLOADS = Path(__file__).resolve().parents[1] / "data" / "contrib_uploads"
if _CONTRIB_UPLOADS.is_dir():
    app.mount(
        "/data/contrib_uploads",
        StaticFiles(directory=str(_CONTRIB_UPLOADS)),
        name="contrib_uploads",
    )


def _format_event_datetime(event: Event) -> str:
    weekday = event.date.strftime("%A")
    month = event.date.strftime("%B")
    day = event.date.day
    if is_time_tbd(event.start_time, event.end_time):
        # WP-4 allows NULL times at ingest (never fabricate noon), and a bare
        # 00:00 start with no real end is the aggregator-ingest "no time given"
        # fallback, not a real midnight event — show the date only. The single
        # definition of that contract lives in app/events/time_labels.py.
        return f"{weekday}, {month} {day}"
    hour_24 = event.start_time.hour
    minute = event.start_time.minute
    suffix = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12 or 12
    return f"{weekday}, {month} {day}, {hour_12}:{minute:02d} {suffix}"


def _event_is_past(event: Event) -> bool:
    # Drives the "This event has passed" banner on the detail page. A recurring
    # series (rdate) is never "passed" while it still recurs, so only flag genuine
    # one-offs. Compare against Lake Havasu local time. A date-only event (NULL
    # time) is past only once the whole day is over -- never mid-day -- so a
    # same-day all-day event is not prematurely buried.
    if event.rdate:
        return False
    now = now_lake_havasu()
    end_d = event.end_date or event.date
    if end_d < now.date():
        return True
    if end_d > now.date():
        return False
    last_time = event.end_time or event.start_time
    return last_time is not None and last_time < now.time()


def _truncate_for_og(value: str, limit: int = 160) -> str:
    # og:description should never cut a word in half ("...Lake Hav"). Collapse
    # whitespace, then if we're over the limit trim back to the last word
    # boundary inside the budget and append an ellipsis. Falls back to a hard
    # slice only when a single token is longer than the limit.
    clean = " ".join(value.split()).strip()
    if len(clean) <= limit:
        return clean
    head = clean[:limit].rstrip()
    cut = head.rfind(" ")
    if cut > 0:
        head = head[:cut].rstrip()
    return head + "..."


def _render_not_found_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="event_not_found.html",
        context={},
        status_code=404,
    )


def _render_permalink_response(
    request: Request, *, event: Event, permalink_url: str
) -> HTMLResponse:
    contact_html = ""
    if event.contact_name or event.contact_phone:
        parts = [html.escape(p) for p in [event.contact_name, event.contact_phone] if p]
        contact_html = f"<p><strong>Contact:</strong> {' | '.join(parts)}</p>"

    event_link_html = ""
    if event.event_url:
        escaped_url = html.escape(event.event_url)
        event_link_html = (
            f"<p><strong>Event Link:</strong> "
            f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_url}</a></p>'
        )

    tags_html = ""
    if event.tags:
        tag_nodes = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in event.tags)
        tags_html = f'<div class="tags"><h2>Tags</h2><div class="tag-wrap">{tag_nodes}</div></div>'

    return templates.TemplateResponse(
        request=request,
        name="event_permalink.html",
        context={
            "event_title": event.title,
            "og_description": _truncate_for_og(event.description),
            "og_url": permalink_url,
            "image_url": event.image_url,
            "formatted_datetime": _format_event_datetime(event),
            "is_past": _event_is_past(event),
            "location_name": event.location_name,
            "description": event.description,
            "contact_html": contact_html,
            "event_link_html": event_link_html,
            "tags_html": tags_html,
        },
    )


# --------------------------------------------------------------------------
# robots.txt + sitemap.xml (launch hardening v48)
# --------------------------------------------------------------------------
#
# robots.txt is fully static. sitemap.xml enumerates the home page, static
# legal/contribute pages, every taxonomy department + gate-clearing leaf, every
# active non-draft provider profile, and every live event. The XML is
# cached in-process for one hour because regeneration walks providers +
# events tables (thousands of rows). The cache is a simple
# (timestamp, xml) tuple rather than functools.lru_cache so it correctly
# expires by wall-clock time and is easy to reason about under tests.
# Canonical base-URL helpers live in app/seo/urls.py (P1.0 — single source of
# truth, shared with templates via the canonical_url Jinja global). Re-exported
# here under their historical private names so existing callers/tests resolve
# ``app.main._base_url`` / ``app.main._coerce_https`` unchanged.
from app.seo.urls import _coerce_https  # noqa: F401 — re-export for back-compat/tests
from app.seo.urls import base_url as _base_url

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


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> PlainTextResponse:
    body = f"User-agent: *\nAllow: /\n\nSitemap: {_base_url()}/sitemap.xml\n"
    return PlainTextResponse(body)


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
        "/events-ui",
        "/categories",
        "/privacy",
        "/terms",
        "/contribute",
        "/about",
        "/help",
        "/contact",
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
    entries: list[str] = []
    try:
        with SessionLocal() as db:
            events = db.query(Event.id, Event.created_at).filter(Event.status == "live").all()
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


@app.get("/sitemap.xml")
def sitemap_xml() -> Response:
    return Response(
        content=_get_cached_sitemap_xml("index"),
        media_type="application/xml",
    )


@app.get("/sitemap-{section}.xml")
def sitemap_section_xml(section: str) -> Response:
    if section not in _SITEMAP_SECTIONS:
        raise HTTPException(status_code=404, detail="unknown_sitemap")
    return Response(
        content=_get_cached_sitemap_xml(section),
        media_type="application/xml",
    )


@app.get("/")
def serve_chat_ui() -> RedirectResponse:
    # 301 (permanent) so search engines fold link equity into /home and stop
    # re-crawling the bare root. Was 307 (temporary) which kept / canonical.
    return RedirectResponse(url="/home", status_code=301)


@app.get("/advertise")
def advertise_redirect() -> RedirectResponse:
    # DL-13: /advertise is the colloquial entry point advertisers type; the
    # actual sponsor landing lives at /sponsor. 301 so the canonical URL is the
    # one that ranks. (The ad *catalog* is a separate page at /portal/advertise.)
    return RedirectResponse(url="/sponsor", status_code=301)


@app.get("/logout")
def logout_get(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    # GET /logout is what a plain <a href="/logout"> link hits. Auth's canonical
    # logout is POST /logout; without this, the link 405s. Mirror the POST's
    # behavior: drop the AuthSession row and clear the session cookie, then send
    # the user home.
    sess = getattr(request.state, "current_session", None)
    if sess is not None:
        row = db.get(AuthSession, sess.id)
        if row is not None:
            db.delete(row)
            db.commit()
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=cookie_secure_in_prod(),
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request) -> HTMLResponse:
    return _render_static_doc(request, path=_PRIVACY_MD_PATH, head_title="Privacy — Hava")


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request) -> HTMLResponse:
    return _render_static_doc(request, path=_TOS_MD_PATH, head_title="Terms — Hava")


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"message": friendly_errors(exc.errors())},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> HTMLResponse | JSONResponse:
    # Styled Hava-branded 404 page for unmatched HTML routes.
    # JSON clients and /api/* paths still get the default JSON shape.
    if exc.status_code != 404:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    accept = (request.headers.get("accept") or "").lower()
    wants_json = (
        "application/json" in accept and "text/html" not in accept
    ) or request.url.path.startswith("/api/")
    if wants_json:
        return JSONResponse(
            status_code=404,
            content={"detail": exc.detail or "Not Found"},
        )
    return templates.TemplateResponse(
        request=request,
        name="not_found.html",
        context={},
        status_code=404,
    )


@app.get("/health")
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        count = db.query(Event).count()
        return JSONResponse({"status": "ok", "db_connected": True, "event_count": count})
    except Exception:
        # OPS-1: a process that can't reach the database must FAIL the
        # healthcheck (Railway healthcheckPath gates deploys on this), not
        # report 200-ok and let a dead deploy go live.
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db_connected": False, "event_count": 0},
        )


@app.get("/events")
def events_redirect() -> RedirectResponse:
    # /events used to serve the raw EventRead JSON dump (leaking embedding,
    # source, and internal columns to any caller). The public JSON contract now
    # lives at /api/events (app/v1/routes/events.py, scrubbed serializer); the
    # human-facing list is /events-ui. 301 so the old JSON path folds into the
    # browsable UI for crawlers.
    return RedirectResponse(url="/events-ui", status_code=301)


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_permalink(event_id: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        return _render_not_found_response(request)
    # ED-5: build a canonical https URL from the configured base (request.url is
    # http behind Railway's proxy when X-Forwarded-Proto isn't honored).
    permalink_url = f"{_base_url()}/events/{event.id}"
    return _render_permalink_response(request, event=event, permalink_url=permalink_url)
