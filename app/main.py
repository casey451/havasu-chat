from __future__ import annotations

# Force redeploy 2026-04-16
from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

import asyncio
import html
import logging
import logging.config
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
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
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.admin.provider_approval import router as admin_provider_approval_router
from app.admin.provider_merge_review import router as admin_provider_merge_review_router
from app.admin.router import router as admin_router
from app.admin.sponsor_surface import merchant_upgrade_router
from app.admin.url_safety import safe_href
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
from app.core.event_quality import friendly_errors
from app.core.provider_name import (
    register_template_filters as _register_template_filters,
)
from app.core.provider_name import (
    register_template_globals as _register_template_globals,
)
from app.core.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.core.theme import (
    THEME_COOKIE,
    VALID_THEMES,
    resolve_request_theme,
)
from app.core.timezone import now_lake_havasu, occurrence_end_dt, to_lake_naive
from app.db.database import SessionLocal, get_db, init_db
from app.db.jobs_store import count_stale_running, requeue_stale_claims
from app.db.models import AuthSession, Event, Provider
from app.digest.routes import router as digest_router
from app.events.event_type_tags import event_type_label
from app.events.recurrence import _event_is_recurring, next_occurrence
from app.events.tag_display import public_event_tags
from app.events.time_labels import is_time_tbd
from app.events.title_clean import clean_event_title
from app.feedback.routes import router as feedback_router
from app.home import flags as home_redesign_flags
from app.home.calendar_route import router as calendar_page_router
from app.home.chat_route import router as new_chat_ui_router
from app.home.lake_preview import router as lake_preview_router
from app.home.router import router as home_router
from app.home.static_pages import router as static_pages_router
from app.monitoring.canaries import not_canary_clause
from app.movies.router import router as movies_router
from app.photos.routes import router as photos_router
from app.photos.sweep import run_stuck_photo_sweep
from app.portal.media_routes import router as creative_media_router
from app.portal.router import router as portal_router
from app.programs.router import router as programs_router
from app.providers.router import router as providers_router
from app.search.routes import router as search_router
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
            # Source comments are for editors, not the public page source —
            # the live /terms shipped its "Drafted by AI … needs attorney
            # review" note to anyone who hit View Source. Drop them.
            if in_ul:
                out.append("</ul>")
                in_ul = False
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
            # A markdown bullet hard-wraps across source lines; the
            # continuation lines are indented and belong to the SAME <li>.
            # The old line-by-line pass closed the list and emitted each
            # continuation as an orphan <p>, splitting every wrapped bullet
            # mid-sentence on the live /privacy page.
            item_parts = [stripped[2:].lstrip()]
            i += 1
            while i < len(lines):
                cont_raw = lines[i]
                cont = cont_raw.strip()
                if (
                    not cont
                    or not cont_raw[:1].isspace()
                    or cont.startswith("- ")
                    or cont.startswith("#")
                    or cont.startswith("<!--")
                ):
                    break
                item_parts.append(cont)
                i += 1
            out.append(f"<li>{_privacy_inline_formats(' '.join(item_parts))}</li>")
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


def _render_static_doc(
    request: Request, *, path: Path, head_title: str, meta_description: str | None = None
) -> HTMLResponse:
    md = path.read_text(encoding="utf-8")
    body = _render_doc_markdown_to_html(md)
    return templates.TemplateResponse(
        request=request,
        name="privacy_doc_lake.html",
        context={
            "head_title": head_title,
            "body": body,
            "meta_description": meta_description,
        },
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


# Lake Ink & Brass redesign (Phase 0): resolve the active theme per request and
# stamp it on ``request.state.theme`` so routes pick the base layout / CSS bundle
# and templates read ``request.state.theme`` directly. Order of precedence lives
# in app/core/theme.py: ?theme= query → theme cookie → THEME_DEFAULT env →
# "desert". Stays dark (desert) the whole build; the flip sets THEME_DEFAULT=lake.
class ThemeMiddleware(BaseHTTPMiddleware):
    """Resolve + persist the redesign theme flag on every request."""

    async def dispatch(self, request: Request, call_next):
        query_theme = request.query_params.get("theme")
        cookie_theme = request.cookies.get(THEME_COOKIE)
        theme = resolve_request_theme(query_theme, cookie_theme)
        request.state.theme = theme
        response = await call_next(request)
        # Persist a valid ?theme= override so QA click-through keeps the skin
        # without re-appending the query string on every link.
        normalized_q = (query_theme or "").strip().lower()
        if normalized_q in VALID_THEMES and normalized_q != (cookie_theme or "").lower():
            response.set_cookie(
                THEME_COOKIE,
                theme,
                max_age=2_592_000,  # 30 days
                path="/",
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
        return response


class AdminLakeSkinMiddleware(BaseHTTPMiddleware):
    """Phase 6: reskin the admin/portal pages to Lake Ink & Brass behind the THEME
    flag. The admin surface is three rendering families (inline-HTML _nav_shell
    pages, the Jinja .d-admin templates, and the CSS-var-driven admin_portal) —
    each builds its own <head>+<style>, so this is the single uniform injection
    point: for an /admin HTML response when the flag resolves to lake, append the
    lake_admin.css link (which overrides those styles) + noindex before </head>.
    Dark behind the flag: desert admin is byte-identical (no injection)."""

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


class HomeRedesignSkinMiddleware(BaseHTTPMiddleware):
    """Sitewide v4 reskin (home_redesign, dark rollout).

    When the flag resolves on, stamp ``data-redesign="1"`` on the <html> element
    and inject the ``lake_redesign_site.css`` override link into every HTML
    response (public + portal + admin) — the single uniform injection point, the
    same technique :class:`AdminLakeSkinMiddleware` uses for lake_admin.css. The
    CSS is fully scoped under ``html[data-redesign="1"]`` so a flag-off render is
    byte-identical (instant rollback). The standalone v4 home/calendar already
    ship their own ``lake_redesign.css`` (they extend base_redesign), so they are
    skipped to avoid double-skinning.
    """

    _LINK = '<link rel="stylesheet" href="/static/styles/lake_redesign_site.css">'

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        if "text/html" not in (response.headers.get("content-type") or ""):
            return response
        if not home_redesign_flags.home_redesign_enabled(request):
            return response
        body = b"".join([section async for section in response.body_iterator])
        text = body.decode("utf-8", "replace")
        # The standalone v4 home/calendar already carry lake_redesign.css — leave
        # them untouched (but still rebuild the response since the iterator is
        # consumed; also persist a preview cookie if a ?home_redesign= override
        # was used).
        already_v4 = "lake_redesign.css" in text
        if not already_v4 and "data-redesign" not in text:
            if 'data-theme="lake"' in text:
                text = text.replace(
                    'data-theme="lake"', 'data-theme="lake" data-redesign="1"', 1
                )
            else:
                text = text.replace("<html", '<html data-redesign="1"', 1)
            if "</head>" in text:
                text = text.replace("</head>", self._LINK + "</head>", 1)
        data = text.encode("utf-8")
        keep = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        new_response = Response(
            content=data,
            status_code=response.status_code,
            headers=keep,
            background=response.background,
        )
        home_redesign_flags.apply_preview_cookie(request, new_response)
        return new_response


app.add_middleware(AdminLakeSkinMiddleware)
app.add_middleware(ThemeMiddleware)
# Outermost of the skin middlewares: runs LAST on the response so it injects the
# sitewide override after AdminLakeSkin's lake_admin.css (source order → wins).
app.add_middleware(HomeRedesignSkinMiddleware)


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

# Host-header allowlist (audit L9) — defense-in-depth alongside the Starlette
# 1.0.1 BadHost fix. OFF by default (no behavior change on deploy); enable by
# setting TRUSTED_HOSTS (comma-separated) once confirmed, e.g.
# "askhava.com,*.askhava.com,*.up.railway.app" — include the Railway host so
# health probes and the legacy-host redirect still pass.
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
# Lake Ink & Brass redesign (Phase 0): the noindex /lake-styleguide gallery —
# the CI a11y/SEO sample target on the new base_lake layout.
app.include_router(lake_preview_router)
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


def _display_date(event: Event) -> date:
    """The date to SHOW on the detail page. For a recurring series ``event.date``
    is just the RRULE anchor (often a 2024 "Monday, January 1" seed), so show the
    next upcoming occurrence instead — matching the live day/index listing and
    killing the N1 "January 1 / This event has passed" contradiction. One-offs
    keep their own date."""
    if _event_is_recurring(event):
        nxt = next_occurrence(event, on_or_after=now_lake_havasu().date())
        if nxt is not None:
            return nxt
    return event.date


def _format_event_datetime(event: Event) -> str:
    display = _display_date(event)
    weekday = display.strftime("%A")
    month = display.strftime("%B")
    day = display.day
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
    # series is "passed" only when it has NO future occurrence left (e.g. an
    # RRULE whose UNTIL is in the past) -- never while it still recurs. The old
    # guard only checked ``event.rdate``, so RRULE-only series (the senior-center
    # rows: rrule set, rdate NULL, anchored at 2024-01-01) fell through and wore
    # a false "passed" banner while listed live all week (N1). Compare against
    # Lake Havasu local time. A date-only one-off (NULL time) is past only once
    # the whole day is over -- never mid-day -- so a same-day all-day event is
    # not prematurely buried.
    if _event_is_recurring(event):
        return next_occurrence(event, on_or_after=now_lake_havasu().date()) is None
    now = now_lake_havasu()
    end_d = event.end_date or event.date
    if end_d < now.date():
        return True
    if end_d > now.date():
        return False
    if event.end_time is not None:
        # Shared end-moment resolution: an end_time of 00:00 (or any time at/
        # before the start) means the event runs PAST midnight, so it is not
        # "passed" earlier the same day (live bug: 1 PM "Motor Madness" stored
        # with a 00:00 end read as passed at 08:54 AM). Compare in Phoenix
        # wall-clock, consistent with the feed and /events-ui.
        end_dt = occurrence_end_dt(end_d, event.start_time, event.end_time)
        if end_dt is not None:
            return to_lake_naive(now) > end_dt
    # No end time on file (whether or not a start time is known): a same-day
    # event is NOT "passed" until the local day is over. The old 3-hour-run
    # assumption flipped a morning event to "passed" mid-morning (live bug: the
    # 9:00 AM Board of Adjustment meeting wore "This event has passed" at 9:07
    # AM). end_d == now.date() here (the earlier date checks handled past/future
    # days), so the event still has the rest of the day to run.
    return False


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


def _link_domain(url: str | None) -> str:
    """Bare hostname for a URL (no leading ``www.``), or ``""`` when unparseable."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _link_label(url: str | None) -> str:
    """Friendly link text — the site's domain, else a generic fallback."""
    return _link_domain(url) or "Visit event page"


def _event_link_html(event_url: str | None, source_url: str | None) -> str:
    """The 'Event Link' block for the detail page.

    Shows a friendly domain label rather than the raw URL string, and — when we
    hold a distinct ``source_url`` (where the listing was found) — a quiet
    provenance byline. Falls back to ``source_url`` as the primary link when no
    ``event_url`` is stored, so a source-only event still links somewhere.
    ``safe_href`` strips dangerous schemes (the URLs are scraped/unvalidated and
    this is a public page; audit M2).
    """
    primary = (event_url or source_url or "").strip()
    if not primary:
        return ""
    safe_url = html.escape(safe_href(primary))
    label = html.escape(_link_label(primary))
    out = (
        f"<p><strong>Event Link:</strong> "
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{label}</a></p>'
    )
    src = (source_url or "").strip()
    if src and _link_domain(src) and _link_domain(src) != _link_domain(primary):
        src_safe = html.escape(safe_href(src))
        src_label = html.escape(_link_domain(src))
        out += (
            f'<p class="ev-source"><small>Source: '
            f'<a href="{src_safe}" target="_blank" rel="noopener noreferrer">{src_label}</a>'
            f"</small></p>"
        )
    return out


def _render_not_found_response(request: Request, *, gone: bool = False) -> HTMLResponse:
    """Render the event error page. ``gone=True`` → 410 (the event was removed:
    status ``deleted``); otherwise 404 (missing or not-yet-public)."""
    return templates.TemplateResponse(
        request=request,
        name="event_not_found_lake.html",
        context={"gone": gone},
        status_code=410 if gone else 404,
    )


def _venue_profile_url(db: Session, event: Event) -> str | None:
    """Internal ``/provider/<slug>`` link for the event's venue, when that venue
    has a live directory page — so the event detail links back to the place
    (site review §1). Returns None when the venue has no published profile.
    """
    prov: Provider | None = None
    if event.provider_id:
        prov = db.query(Provider).filter(Provider.id == event.provider_id).first()
    if prov is None and event.entity_id:
        prov = db.query(Provider).filter(Provider.entity_id == event.entity_id).first()
    if prov is None or not prov.slug or prov.draft or prov.is_active is False:
        return None
    return f"/provider/{prov.slug}"


def _render_permalink_response(
    request: Request, *, event: Event, permalink_url: str, venue_url: str | None = None
) -> HTMLResponse:
    contact_html = ""
    if event.contact_name or event.contact_phone:
        parts = [html.escape(p) for p in [event.contact_name, event.contact_phone] if p]
        contact_html = f"<p><strong>Contact:</strong> {' | '.join(parts)}</p>"

    event_link_html = _event_link_html(event.event_url, event.source_url)

    tags_html = ""
    display_tags = public_event_tags(event.tags)
    if display_tags:
        tag_nodes = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in display_tags)
        tags_html = f'<div class="tags"><h2>Tags</h2><div class="tag-wrap">{tag_nodes}</div></div>'

    # Event JSON-LD (SEO audit §2.7: zero Event schema on a hyperlocal events
    # product — a free rich-results win). Built as a dict here so missing
    # fields are OMITTED, never emitted as ``"key": null``. Arizona ignores
    # DST: the offset is -07:00 year-round.
    # Schema.org wants the upcoming date, so a recurring series advertises its
    # next occurrence (not the 2024 RRULE anchor) — same source as the visible
    # date, keeping the rich result and the page in agreement.
    disp_date = _display_date(event)
    if is_time_tbd(event.start_time, event.end_time):
        start_iso = disp_date.isoformat()
    else:
        start_iso = (
            f"{disp_date.isoformat()}T{event.start_time.strftime('%H:%M')}:00-07:00"
        )
    event_jsonld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.title,
        "startDate": start_iso,
        "url": permalink_url,
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@type": "Place",
            "name": event.location_name or "Lake Havasu City",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Lake Havasu City",
                "addressRegion": "AZ",
                "addressCountry": "US",
            },
        },
    }
    if event.end_time is not None and not is_time_tbd(event.start_time, event.end_time):
        end_d = disp_date if _event_is_recurring(event) else (event.end_date or event.date)
        event_jsonld["endDate"] = (
            f"{end_d.isoformat()}T{event.end_time.strftime('%H:%M')}:00-07:00"
        )
    if event.description:
        event_jsonld["description"] = _truncate_for_og(event.description, limit=300)
    if event.image_url and str(event.image_url).startswith("http"):
        event_jsonld["image"] = [event.image_url]

    return templates.TemplateResponse(
        request=request,
        name="event_permalink_lake.html",
        context={
            "event_title": clean_event_title(event.title, location_name=event.location_name),
            "og_description": _truncate_for_og(event.description),
            "og_url": permalink_url,
            "image_url": event.image_url,
            "formatted_datetime": _format_event_datetime(event),
            "is_past": _event_is_past(event),
            # P2: the type folded into the detail eyebrow ("Live Music"/"Comedy").
            "type_label": event_type_label(event.title, event.tags, event.location_name),
            "location_name": event.location_name,
            "venue_url": venue_url,
            "description": event.description,
            "cost": getattr(event, "cost", None),
            "cost_description": getattr(event, "cost_description", None),
            "host": getattr(event, "host", None),
            "contact_html": contact_html,
            "event_link_html": event_link_html,
            "tags_html": tags_html,
            "event_jsonld": event_jsonld,
            "ics_url": f"/events/{event.id}.ics",
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


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> FileResponse:
    """Serve the multi-size .ico at the root path browsers request by default
    (the static mount only covers /static/...). Binary generated by
    scripts/gen_favicon_assets.py from app/static/img/favicon.svg."""
    return FileResponse(
        _STATIC_DIR / "img" / "favicon.ico", media_type="image/x-icon"
    )


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
    return _render_static_doc(
        request,
        path=_PRIVACY_MD_PATH,
        head_title="Privacy — Ask Hava",
        meta_description=(
            "How Hava handles your data: what we store, who processes it, "
            "and the choices you have. No ads, no profiles, no data sales."
        ),
    )


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request) -> HTMLResponse:
    return _render_static_doc(
        request,
        path=_TOS_MD_PATH,
        head_title="Terms — Ask Hava",
        meta_description=(
            "The terms for using Ask Hava — Lake Havasu City's free local "
            "guide, directory, and AI concierge."
        ),
    )


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


@app.get("/events/{event_id}.ics", include_in_schema=False)
def event_ics(event_id: str, db: Session = Depends(get_db)) -> Response:
    """Per-event iCalendar download (UX-4 "Add to calendar"). Registered before
    the HTML permalink so ``/events/{id}.ics`` matches this route, not the
    ``{event_id}`` catch-all."""
    from app.api.routes.calendar_feed import build_single_event_ics

    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        raise HTTPException(status_code=404, detail="event_not_found")
    return Response(
        content=build_single_event_ics(event),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="event-{event.id}.ics"'},
    )


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_permalink(event_id: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        return _render_not_found_response(request)
    # SEO: a removed event (status "deleted") is permanently gone — return 410,
    # not the full page (a soft-404/served-removed-content bug). Only the literal
    # "deleted" status takes this path, so a live event is never mistakenly gone.
    if event.status == "deleted":
        return _render_not_found_response(request, gone=True)
    # ED-5: build a canonical https URL from the configured base (request.url is
    # http behind Railway's proxy when X-Forwarded-Proto isn't honored).
    permalink_url = f"{_base_url()}/events/{event.id}"
    venue_url = _venue_profile_url(db, event)
    return _render_permalink_response(
        request, event=event, permalink_url=permalink_url, venue_url=venue_url
    )
