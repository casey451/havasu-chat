from __future__ import annotations

from app.bootstrap_env import ensure_dotenv_loaded

# Force redeploy 2026-04-16
from app.core.templates import make_templates

ensure_dotenv_loaded()

import asyncio
import logging
import logging.config
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.admin.provider_approval import router as admin_provider_approval_router
from app.admin.provider_merge_review import router as admin_provider_merge_review_router
from app.admin.router import router as admin_router
from app.admin.sponsor_surface import merchant_upgrade_router
from app.admin.v1_overview import router as admin_v1_overview_router
from app.admin_portal.router import portal_router as admin_portal_router
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
from app.billing.router import router as billing_router
from app.categories.router import router as direction_c_categories_router
from app.chat.entity_matcher import refresh_entity_matcher
from app.core.build_info import build_sha
from app.core.event_quality import friendly_errors
from app.core.feature_flags import business_surfaces_enabled
from app.core.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.db.database import SessionLocal, get_db, init_db
from app.db.jobs_store import count_stale_running, requeue_stale_claims
from app.db.models import AuthSession, Event
from app.digest.routes import router as digest_router

# Event permalink feature (/events, /events/{id}, .ics) lives in
# app/events/permalink.py. The tested render helpers are re-exported below under
# their historical private names so app.main._event_is_past etc. resolve unchanged.
from app.events.permalink import (
    _display_date,  # noqa: F401 — re-export
    _event_is_past,  # noqa: F401 — re-export
    _event_link_html,  # noqa: F401 — re-export
    _format_event_datetime,  # noqa: F401 — re-export
    _link_domain,  # noqa: F401 — re-export
    _link_label,  # noqa: F401 — re-export
    _truncate_for_og,  # noqa: F401 — re-export
    _venue_profile_url,  # noqa: F401 — re-export
)
from app.events.permalink import router as events_permalink_router
from app.feedback.routes import router as feedback_router
from app.home.calendar_route import router as calendar_page_router
from app.home.chat_route import router as new_chat_ui_router
from app.home.router import router as home_router
from app.home.static_pages import router as static_pages_router

# Static legal/policy pages (/privacy, /terms). The renderer + doc-path names are
# re-exported below under their historical private names so existing callers/tests
# resolve app.main._render_doc_markdown_to_html / app.main._TOS_MD_PATH unchanged.
from app.legal_docs import (
    _PRIVACY_MD_PATH,  # noqa: F401 — re-export for back-compat
    _TOS_MD_PATH,  # noqa: F401 — re-export for back-compat
    _render_doc_markdown_to_html,  # noqa: F401 — re-export
)
from app.legal_docs import router as legal_docs_router
from app.movies.router import router as movies_router
from app.news.router import router as news_router
from app.photos.routes import router as photos_router
from app.photos.sweep import run_stuck_photo_sweep
from app.portal.media_routes import router as creative_media_router
from app.portal.router import router as portal_router
from app.programs.router import router as programs_router
from app.providers.router import router as providers_router
from app.search.routes import router as search_router

# robots.txt + sitemap.xml routes live in app/seo/site_routes.py. The sitemap
# builders + cache are re-exported below under their historical private names so
# app.main._build_sitemap_pages_xml / the sitemap tests' _sitemap_cache reset
# resolve unchanged.
from app.seo.site_routes import (
    _SITEMAP_BUILDERS,  # noqa: F401 — re-export
    _build_sitemap_events_xml,  # noqa: F401 — re-export
    _build_sitemap_pages_xml,  # noqa: F401 — re-export
    _build_sitemap_providers_xml,  # noqa: F401 — re-export
    _sitemap_cache,  # noqa: F401 — re-export
)
from app.seo.site_routes import router as seo_router
from app.v1.routes import router as v1_master_spec_router


def _configure_logging() -> None:
    """OPS-8 (audit :218-221): single ``dictConfig`` for the whole app.

    Without it there is no handler anywhere, so app-level ``logger.info(...)``
    (e.g. "Sentry initialized", the janitor's reaper warnings) never reaches
    prod logs — Python's last-resort handler is WARNING+. One stdout handler
    on root, idempotent (dictConfig replaces root handlers, so re-imports
    can't stack duplicates). uvicorn's own loggers keep their handlers and
    don't propagate, so access logs aren't double-printed.
    ``LOG_LEVEL`` env knob (default INFO); unknown values fall back to INFO.
    ``disable_existing_loggers=False`` keeps module-level loggers created
    before this call (and pytest's caplog) fully working.
    """
    level = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "app": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "app",
                },
            },
            "root": {"level": level, "handlers": ["stdout"]},
        }
    )


_configure_logging()
logger = logging.getLogger(__name__)

# make_templates() runs both registrars (CLUSTER-08 clean_name filter + the Q5
# Plausible ``plausible_domain`` global that gates _partials/plausible.html), so
# every render resolves them regardless of which router built the instance.
# (Legal-doc paths moved to app/legal_docs.py, re-exported in the import block.)
templates = make_templates()
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


def _janitor_int_env(name: str, default: int) -> int:
    """Optional integer janitor knob: unset/blank/garbage falls back to the default."""
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def run_stale_job_requeue() -> int:
    """OPS-4: requeue jobs stuck in ``claimed`` (worker died between claim and run).

    Threshold via ``JOBS_STALE_CLAIM_MINUTES`` (default 60 — claim→running is
    normally seconds, so an hour-old claim is a dead worker, not a slow one).
    Also warns on ``running`` rows older than ``JOBS_STUCK_RUNNING_WARN_HOURS``
    (default 6) WITHOUT requeueing them — double-run risk for side-effectful
    job types; the portal's manual requeue covers those after inspection.
    Returns the number of jobs requeued.
    """
    minutes = _janitor_int_env("JOBS_STALE_CLAIM_MINUTES", 60)
    warn_hours = _janitor_int_env("JOBS_STUCK_RUNNING_WARN_HOURS", 6)
    with SessionLocal() as db:
        requeued = requeue_stale_claims(db, older_than_minutes=minutes)
        if requeued:
            logger.warning(
                "stale-claim reaper requeued %d job(s): %s",
                len(requeued),
                ", ".join(f"{j.job_type}:{j.id}" for j in requeued),
            )
        stuck = count_stale_running(db, older_than_hours=warn_hours)
        if stuck:
            logger.warning(
                "%d job(s) stuck in 'running' > %dh — inspect/requeue in the portal ops page",
                stuck,
                warn_hours,
            )
        return len(requeued)


def run_news_pull() -> None:
    """Refresh the local-news cache (home ticker + /news) so it stays fresh
    without an external cron (Casey 2026-06-30). Best-effort: a failure is logged
    and retried the next hour. pull_local_news already isolates per-source feed
    failures internally, so this only catches a hard DB/transport error."""
    from app.news.store import pull_local_news

    try:
        with SessionLocal() as db:
            count = pull_local_news(db)
            db.commit()
        logger.info("news pull refreshed %s headline(s)", count)
    except Exception:
        logger.warning("news pull failed; retrying next hour", exc_info=True)


async def _hourly_cleanup_loop() -> None:
    # OPS-3: one transient failure (DB blip, etc.) must not kill the janitor
    # for the process lifetime — run_stuck_photo_sweep is the safety net for
    # fire-and-forget photo processing. CancelledError is a BaseException, so
    # ``except Exception`` never swallows lifespan shutdown.
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(run_news_pull)
            await asyncio.to_thread(run_expired_review_cleanup)
            await asyncio.to_thread(run_stuck_photo_sweep)
            await asyncio.to_thread(run_stale_job_requeue)
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


# ThemeMiddleware was deleted 2026-07-02 (audit flag-collapse): lake has been
# the only theme since the desert lineage was deleted 2026-06-24, so the
# per-request ?theme=/cookie/THEME_DEFAULT resolution could only ever produce
# "lake". Templates hardcode data-theme="lake" in the two base layouts.


class AdminLakeSkinMiddleware(BaseHTTPMiddleware):
    """Skin the admin/portal pages. The admin surface is three rendering families
    (inline-HTML _nav_shell pages, the Jinja .d-admin templates, and the CSS-var-
    driven admin_portal) — each builds its own <head>+<style>, so this is the
    single uniform injection point: for an /admin HTML response, append the
    self-contained lake_admin.css link (which overrides those styles) + noindex
    before </head>.

    This is the LAST body-rewriting middleware: it survives the 2026-07-02
    flag-collapse only because the admin shells are ~15 separate hand-built
    <head>s; the planned admin-shell consolidation bakes this link into the one
    shared shell and deletes this class. (v4.6 PR-2: the .d-admin Jinja templates
    now extend base_plain.html, so the old base_lake reskin injection —
    lake_redesign_site.css + data-redesign — was dropped; lake_admin.css is
    self-contained with its own --la-* tokens.)
    """

    _INJECT = (
        '<link rel="stylesheet" href="/static/styles/lake_admin.css">'
        '<meta name="robots" content="noindex">'
    )

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        if not (
            request.url.path.startswith("/admin")
            and "text/html" in (response.headers.get("content-type") or "")
        ):
            return response
        body = b"".join([section async for section in response.body_iterator])
        text = body.decode("utf-8", "replace")
        if "</head>" in text:
            text = text.replace("</head>", self._INJECT + "</head>", 1)
        data = text.encode("utf-8")
        keep = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(
            content=data,
            status_code=response.status_code,
            headers=keep,
            background=response.background,
        )


# HomeRedesignSkinMiddleware was deleted 2026-07-02 (audit flag-collapse) and the
# base_lake reskin path was deleted 2026-07-04 (v4.6 PR-2): every page is now on
# the standalone v4 shell (base_redesign / base_plain → lake_redesign.css), so no
# response-body reskinning remains except the admin lake_admin.css injection above.
app.add_middleware(AdminLakeSkinMiddleware)


# ---------------------------------------------------------------------------
# Business-surfaces kill switch (BUSINESS_SURFACES_ENABLED, default off).
# ---------------------------------------------------------------------------
#
# While the flag is off the consumer site is fully live but the advertiser /
# business-owner side is hidden: the header/footer/homepage/category/provider CTAs
# are gated in the templates (via the ``business_surfaces_enabled()`` global), and
# the OWNER-FACING ROUTES below are intercepted here to serve ONE friendly
# "coming soon" page (200, noindex, contact mailto) instead of their real content.
# No 404s — an owner who lands on /portal or /sponsor from word-of-mouth gets a
# way to reach us, not a wall. Flag ON passes every request straight through, so
# re-enabling the whole business side is a single config flip.
#
# Prefix match is boundary-safe (``== p`` or ``startswith(p + "/")``) so an
# unrelated path like ``/sponsorships-guide`` could never be swept in. ``/billing``
# is intentionally NOT listed — it is separately dormant behind
# STRIPE_BILLING_ENABLED (Stripe work is on hold).
_BUSINESS_ROUTE_PREFIXES = ("/portal", "/sponsor", "/advertise", "/claim", "/merchant")


def _is_business_route(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _BUSINESS_ROUTE_PREFIXES)


class BusinessSurfacesGateMiddleware(BaseHTTPMiddleware):
    """Serve the "coming soon" stub on owner-facing routes while the flag is off.

    Sits INSIDE ``SecurityHeadersMiddleware`` (added just before it) so the stub
    response still gets the standard no-store + security headers on the way out.
    Any method is answered with the same 200 stub — a stray POST from a bookmarked
    form lands softly rather than erroring."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if business_surfaces_enabled() or not _is_business_route(request.url.path):
            return await call_next(request)
        response = templates.TemplateResponse(
            request=request,
            name="business_coming_soon_lake.html",
            context={"active_tab": ""},
        )
        # Belt-and-suspenders with the <meta robots> in the template: a header
        # keeps the stub out of the index even for non-HTML crawlers.
        response.headers["X-Robots-Tag"] = "noindex, follow"
        return response


app.add_middleware(BusinessSurfacesGateMiddleware)


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
            # ``no-store`` (not just ``no-cache``) — the 2026-07-07 stale-day-view
            # was a Cloudflare edge copy frozen at one PoP. no-store tells every
            # cache to never STORE the HTML, so a broad "cache everything" rule
            # can't silently freeze a per-URL copy again. (A CF rule with "override
            # origin" still wins, but the standing config now correctly signals
            # uncacheable; the deploy/data-op CDN purge is the active backstop.)
            response.headers.setdefault(
                "Cache-Control", "no-store, no-cache, max-age=0, must-revalidate"
            )
            # Launch hardening (audit M1): start CSP in Report-Only to inventory
            # inline scripts/styles + image sources, then rename the header to
            # "Content-Security-Policy" to enforce. Report-Only blocks nothing.
            response.headers.setdefault(
                "Content-Security-Policy-Report-Only",
                "default-src 'self'; img-src 'self' data: https:; "
                "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'none'; base-uri 'self'",
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
_LEGACY_HOSTS = frozenset(
    {"havasu-chat-production.up.railway.app", "www.askhava.com"}
)


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

# Host-header allowlist (audit L9; A1 Cloudflare-readiness) — defense-in-depth
# alongside the Starlette 1.0.1 BadHost fix. OFF by default (no behavior change
# on deploy); enable by setting TRUSTED_HOSTS (comma-separated) once confirmed,
# e.g. "askhava.com,*.askhava.com,*.up.railway.app" — include the Railway host
# so health probes and the legacy-host redirect still pass. With Cloudflare in
# front (Track A1) the Host header is preserved end to end, so the same origin
# hostnames apply; recommended to enable alongside the CF cutover so only
# Cloudflare-proxied hostnames are accepted at the origin.
_trusted_hosts_env = (os.getenv("TRUSTED_HOSTS") or "").strip()
if _trusted_hosts_env:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[h.strip() for h in _trusted_hosts_env.split(",") if h.strip()],
    )
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
app.include_router(feedback_router)
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
app.include_router(legal_docs_router)
app.include_router(seo_router)
app.include_router(events_permalink_router)
app.include_router(news_router)
app.include_router(calendar_feed_router)
app.include_router(ingest_router)
app.include_router(ingest_jobs_router)
app.include_router(ingest_publish_router)
app.include_router(captures_router)
app.include_router(admin_router)
# Unified admin portal (/admin/portal — Track E wiring, 2026-06-10). Named
# admin_portal_router here because the MERCHANT portal (app/portal) already
# owns the bare portal_router name.
app.include_router(admin_portal_router)
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
app.include_router(movies_router)
# Lake Ink & Brass redesign (Phase 2b): the /calendar discovery page — the
# concierge intent-router's destination for discovery queries.
app.include_router(calendar_page_router)
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
# C10: serve uploaded ad-creative images from the Railway volume.
app.include_router(creative_media_router)
# F4 billing (Stripe). Dormant: every /billing/* route 404s until the operator
# sets STRIPE_BILLING_ENABLED + keys and adds `stripe` to requirements.
app.include_router(billing_router)


class CachedStaticFiles(StaticFiles):
    """``StaticFiles`` that emits an explicit ``Cache-Control`` (UI plan 1.9).

    Starlette's ``StaticFiles`` already sends ``ETag`` + ``Last-Modified``
    validators, so correctness was never at risk — but it sent *no* ``max-age``,
    so browsers issued a conditional request for every asset on every
    navigation (a round-trip each, even though the answer is almost always a
    304). The ``/static`` mount therefore shipped with no freshness lifetime at
    all. This subclass adds one:

    * **Fingerprinted** requests (any ``?v=`` query, e.g.
      ``/static/styles/desert.css?v=ab12cd``) → ``max-age`` of one year +
      ``immutable``. The URL changes whenever the bytes change, so a pinned
      copy can never go stale. Templates do not fingerprint their asset URLs
      yet — threading a ``static_url()`` helper through the shared Jinja
      registrar is the 1.9b follow-up — and when they do, **no change here is
      needed**: the immutable branch simply starts applying.
    * **Bare** requests (no ``?v=``) → a short ``max-age`` so an
      un-fingerprinted asset still skips most revalidations yet self-heals
      within minutes of a deploy (the ``ETag`` keeps it correct on the next
      conditional request after expiry).

    HTML is unaffected: it is served by routes, not this mount, and
    ``SecurityHeadersMiddleware`` keeps every ``text/html`` response
    ``no-cache``.
    """

    def __init__(
        self,
        *args: Any,
        versioned_max_age: int = 31_536_000,  # 1 year
        default_max_age: int = 300,  # 5 minutes
        **kwargs: Any,
    ) -> None:
        self._versioned_max_age = versioned_max_age
        self._default_max_age = default_max_age
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        # Stamp cacheable bodies (200/206) and validator replies (304); leave
        # 404/405 alone so a cache never pins a miss.
        if response.status_code in (200, 206, 304):
            query = scope.get("query_string", b"") or b""
            fingerprinted = any(
                part.split(b"=", 1)[0] == b"v" for part in query.split(b"&") if part
            )
            if fingerprinted:
                response.headers["Cache-Control"] = (
                    f"public, max-age={self._versioned_max_age}, immutable"
                )
            else:
                response.headers["Cache-Control"] = (
                    f"public, max-age={self._default_max_age}"
                )
        return response


_STATIC_DIR = Path(__file__).resolve().parent / "static"
# Mount the more-specific /static/biz-photos BEFORE the broad /static mount.
# Starlette matches mounts in registration order; if /static is registered first
# it shadows /static/biz-photos (the request resolves against app/static -> 404).
_BIZ_PHOTOS_DIR = Path("/data/biz-photos")
if _BIZ_PHOTOS_DIR.is_dir():
    app.mount(
        "/static/biz-photos",
        CachedStaticFiles(directory=str(_BIZ_PHOTOS_DIR)),
        name="biz_photos",
    )
app.mount("/static", CachedStaticFiles(directory=_STATIC_DIR), name="static")

_CONTRIB_UPLOADS = Path(__file__).resolve().parents[1] / "data" / "contrib_uploads"
if _CONTRIB_UPLOADS.is_dir():
    app.mount(
        "/data/contrib_uploads",
        CachedStaticFiles(directory=str(_CONTRIB_UPLOADS)),
        name="contrib_uploads",
    )


from app.seo.urls import _coerce_https  # noqa: F401 — re-export for back-compat/tests
from app.seo.urls import base_url as _base_url


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> FileResponse:
    """Serve the multi-size .ico at the root path browsers request by default
    (the static mount only covers /static/...). Binary generated by
    scripts/gen_favicon_assets.py from app/static/img/favicon.svg."""
    return FileResponse(
        _STATIC_DIR / "img" / "favicon.ico", media_type="image/x-icon"
    )


@app.get("/")
def serve_chat_ui() -> RedirectResponse:
    # 307 (temporary) so browsers do NOT permanently cache the bare-root
    # redirect. The previous 301 (permanent) was cached indefinitely by
    # browsers; once a stale/broken target got cached, the bare root appeared
    # to "not load" for that visitor even after the server was fixed, while
    # /home and www.* kept working. SEO consolidation is handled by the
    # self-canonical <link> on /home, so we don't need a permanent redirect
    # here. (Bare / is already excluded from the sitemap.)
    return RedirectResponse(url="/home", status_code=307)


@app.get("/advertise")
def advertise_redirect() -> RedirectResponse:
    # DL-13: /advertise is the colloquial entry point advertisers type; the
    # actual sponsor landing (the public rate card) lives at /sponsor. 301 so the
    # canonical URL is the one that ranks. (There is no /portal/advertise route —
    # the merchant dashboard is /portal/placements, behind login; WS3 will make
    # /advertise itself the canonical rate card and 301 /sponsor onto it.)
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
        name="not_found_lake.html",
        context={},
        status_code=404,
    )


@app.get("/health")
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        count = db.query(Event).count()
    except Exception:
        # OPS-1: a process that can't reach the database must FAIL the
        # healthcheck (Railway healthcheckPath gates deploys on this), not
        # report 200-ok and let a dead deploy go live.
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db_connected": False, "event_count": 0},
        )
    return JSONResponse(
        {
            "status": "ok",
            "db_connected": True,
            "event_count": count,
            # The running build's commit SHA — the cold-cache canary compares this
            # (the ACTUAL running app) against each page's <meta name="build-sha">,
            # so a stale/edge render from an older build is caught.
            "build_sha": build_sha(),
            # Cluster fingerprint so the web-app/internal-host path can be proven
            # the SAME Postgres as the Actions/public-proxy path (scripts/
            # db_identity_probe.py). system_identifier is initdb-unique per cluster
            # and non-sensitive. Best-effort: a failure here never affects the
            # deploy healthcheck gate above.
            "db_identity": _db_identity(db),
        }
    )


def _db_identity(db: Session) -> dict[str, object | None]:
    """Read-only cluster fingerprint for the /health identity check. Never raises;
    an unreadable probe yields a null field, not a 503. Each probe rolls back on
    failure so a permission-denied ``pg_control_system()`` (which aborts the
    transaction) doesn't poison the ``inet_server_*`` fallbacks after it."""
    from sqlalchemy import text as _sql_text

    identity: dict[str, object | None] = {}
    for label, sql in (
        ("system_identifier", "SELECT system_identifier FROM pg_control_system()"),
        ("database", "SELECT current_database()"),
        ("server_port", "SELECT inet_server_port()"),
        ("server_version", "SELECT current_setting('server_version')"),
    ):
        try:
            value = db.execute(_sql_text(sql)).scalar()
            identity[label] = str(value) if label == "system_identifier" and value is not None else value
        except Exception:
            identity[label] = None
            try:
                db.rollback()
            except Exception:
                pass
    return identity
