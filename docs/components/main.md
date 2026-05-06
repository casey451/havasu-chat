# main

`app/main.py` (~402 lines, post-Slice-51 Jinja2 extraction)

## Purpose

The FastAPI app entry point. Six things happen here:

1. **`.env` bootstrap** before any other `app.*` import (load-bearing for env-reading modules).
2. **Sentry init** with chat-body scrubbing in the `before_send` / `before_breadcrumb` hooks.
3. **App construction** with a `lifespan` context manager that runs `init_db()` and starts the hourly expired-review-cleanup background task.
4. **Exception handlers** for `RateLimitExceeded` (429 with `RATE_LIMIT_MESSAGE`) and `RequestValidationError` (422 with `friendly_errors`).
5. **Router includes and the `/static` mount** — every chat / admin / programs / contribute surface attaches here.
6. **Six top-level routes** for the static UI, legal pages, health probe, and event endpoints, plus a custom Markdown-subset parser that renders `docs/privacy.md` and `docs/tos.md` into HTML through Jinja2 templates.

## Public surface

**`app: FastAPI`** — The module-level FastAPI instance. ASGI entry for uvicorn / Railway. `app.state.limiter` is the shared slowapi `Limiter` from `app/core/rate_limit.py`.

**`scrub_sentry_event(event, hint)` / `scrub_sentry_breadcrumb(crumb, hint)`** — Sentry `before_send` / `before_breadcrumb` hooks. Strip request bodies and breadcrumb data fields when the event refers to `/api/chat` or carries an HTTP body. Tested directly by the test suite.

**`run_expired_review_cleanup() -> int`** — Marks `Event.status='deleted'` for any event whose `admin_review_by` deadline has passed while still in `pending_review`. Returns the count. Called once per hour by the lifespan task; exported so tests can invoke it directly.

The other module-level functions (`_render_doc_markdown_to_html`, `_render_static_doc`, `_render_not_found_response`, `_render_permalink_response`, `_format_event_datetime`, `_truncate_for_og`, `_init_sentry`, `_hourly_cleanup_loop`, `_privacy_inline_formats`, `lifespan`) are private helpers but several are referenced from tests by name.

## Route inventory (routes declared on `app` directly)

| Method | Path | Handler | Notes |
|---|---|---|---|
| GET | `/` | `serve_chat_ui` | `FileResponse(_STATIC_DIR / "index.html")`. Single-page chat shell. |
| GET | `/privacy` | `privacy_page` | Renders `docs/privacy.md` through `_render_static_doc` + `privacy_doc.html` template. |
| GET | `/terms` | `terms_page` | Renders `docs/tos.md` through the same template. |
| GET | `/health` | `health_check` | JSON `{"status": "ok", "db_connected": bool, "event_count": int}`. Catches DB exceptions and returns the false/zero shape rather than raising — Railway's health probe must always 200. |
| GET | `/events` | `list_events` | `list[EventRead]`. Newest `created_at` first; no filters. |
| GET | `/events/{event_id}` | `event_permalink` | HTML event permalink (or `event_not_found.html` 404 when missing or `pending_review`). |

## Exception handlers

| Exception | Handler | Behavior |
|---|---|---|
| `RateLimitExceeded` (slowapi) | `rate_limit_handler` | 429 JSON `{"message": RATE_LIMIT_MESSAGE}` (`"Slow down a sec! Try again in a minute 😅"`). |
| `RequestValidationError` (FastAPI) | `request_validation_handler` | 422 JSON `{"message": friendly_errors(exc.errors())}`. The friendly-error pretty-printer lives in `app/core/event_quality.py`. |

## Routers included (mount layout)

In include order (lines 276–281):

| Module | Prefix | Doc |
|---|---|---|
| `app.api.routes.chat` | (none — full paths in module) | `docs/components/chat_route.md` |
| `app.api.routes.contribute` | (none) | `docs/components/contribute_route.md` |
| `app.admin.router` | `/admin` | `docs/components/admin_router.md` |
| `app.api.routes.admin_contributions` | `/admin/api` (set in module) | `docs/components/admin_contributions_route.md` |
| `app.api.routes.admin_mentions` | `/admin/api` (set in module) | `docs/components/admin_mentions_route.md` |
| `app.programs.router` | (none) | `docs/components/programs_router.md` |

## Mounts

| Mount | Path | Source |
|---|---|---|
| `/static` | `_STATIC_DIR = Path(__file__).parent / "static"` | `StaticFiles(name="static")` — serves the chat UI's JS / CSS bundles split out by Slices 61 / 63. |

## Internal structure

The module reads top-down:

1. **Bootstrap** (lines 1–6). `from app.bootstrap_env import ensure_dotenv_loaded` then `ensure_dotenv_loaded()`. The "Force redeploy" comment is a Railway dirty-deploy lever. Everything below this is conventional `app.*` imports — they read env at import time and rely on `.env` already being loaded.

2. **Stdlib + third-party imports + module constants** (lines 8–46). `_DOCS_DIR`, `_PRIVACY_MD_PATH`, `_TOS_MD_PATH`, `_TEMPLATES_DIR`, the Jinja2 `templates` instance, and `_SENSITIVE_EVENT_KEYS` (the scrub allowlist).

3. **Sentry scrubbers** (lines 49–93). `_is_chat_post_request_url` checks whether a Sentry-captured URL is the `/api/chat` POST. `_scrub_mapping_keys_inplace` walks `_SENSITIVE_EVENT_KEYS` and replaces values with `"<scrubbed>"`. `scrub_sentry_event` and `scrub_sentry_breadcrumb` are the two `before_send` / `before_breadcrumb` hooks Sentry calls per event/crumb.

4. **Markdown-subset parser** (lines 96–184). `_privacy_inline_formats` handles `**bold**`, bare HTTPS links, and `[label](/path)` link syntax. `_render_doc_markdown_to_html` is a hand-rolled line scanner supporting `# h1`, `## h2`, `<!-- comments -->`, `- ` lists, and paragraphs. Deliberately minimal — only the constrained subset used by `docs/privacy.md` / `docs/tos.md`.

5. **Static-doc rendering helper** (lines 187–194). `_render_static_doc` reads the markdown file, runs it through the parser, and returns `templates.TemplateResponse(name="privacy_doc.html", ...)`.

6. **Sentry init** (lines 197–221). `_init_sentry` reads `SENTRY_DSN`; when present, imports `sentry_sdk` and the FastAPI / Starlette integrations and calls `sentry_sdk.init` with `traces_sample_rate=0.1`, `before_send=scrub_sentry_event`, `before_breadcrumb=scrub_sentry_breadcrumb`. Best-effort: any exception from the import or init is logged at WARNING and swallowed (monitoring must never break startup). `_init_sentry()` is invoked once at module load.

7. **Hourly cleanup task** (lines 224–246). `run_expired_review_cleanup` scans for `pending_review` events past their `admin_review_by` deadline and flips them to `deleted`. `_hourly_cleanup_loop` is an `asyncio` task that calls the cleanup every 3600 seconds.

8. **Lifespan + app construction** (lines 249–266). The `@asynccontextmanager` `lifespan` logs the `ADMIN_PASSWORD` presence (boolean only — never the value), runs `init_db()`, and spawns the hourly cleanup task. On shutdown, it cancels the task and awaits its `CancelledError`. `app = FastAPI(title="Havasu Chat", lifespan=lifespan)` then `app.state.limiter = limiter` wires the shared slowapi limiter.

9. **Exception handlers** (lines 268–273, 375–380). Two handlers, registered via `@app.exception_handler(...)`. Both return JSON.

10. **Router includes + static mount** (lines 276–284). Six `app.include_router(...)` calls in the order listed above, then the `/static` mount.

11. **Permalink rendering helpers** (lines 287–353). `_format_event_datetime` (12-hour clock with day name + month + day), `_truncate_for_og` (Open Graph description trim at 160 chars), `_render_not_found_response` (404 HTML via `event_not_found.html`), `_render_permalink_response` (200 HTML via `event_permalink.html`, with hand-built contact / event-link / tags HTML fragments). The permalink route reads through these to keep the route handler thin.

12. **App-level routes** (lines 356–402). The six routes from the inventory above, plus the `RequestValidationError` handler near the middle.

## Conventions

**`ensure_dotenv_loaded()` is the first executable line.** The per-file E402 ignore in `pyproject.toml` exists exclusively to allow this ordering; reorganizing the module top is load-bearing. See `docs/components/bootstrap_env.md`.

**Three Jinja2 templates, three responses.** Templates live in `app/templates/`: `privacy_doc.html` (used for both `/privacy` and `/terms`), `event_not_found.html`, `event_permalink.html`. Adding a fourth response type means adding a template, not extending the markdown parser — the parser is intentionally minimal.

**`/health` never raises.** Railway's health probe must reliably return 200; the handler catches all DB exceptions and returns `{"db_connected": False, "event_count": 0}` rather than letting an outage trip the probe and mask the underlying issue.

**Sentry scrubbing is mandatory, not opportunistic.** Every chat-body field that could contain user PII is replaced with `<scrubbed>` before upload. The hook list (`_SENSITIVE_EVENT_KEYS = {"query", "message", "normalized_query"}`) plus the `/api/chat` URL check covers the known risk surface. New PII-bearing fields require updating the allowlist.

**Background tasks survive process shutdown via cancel + await.** The lifespan teardown explicitly catches `CancelledError` so the task's cleanup runs cleanly. Don't `task.cancel()` without `await task` — the task's `await asyncio.sleep(3600)` would be cancelled mid-iteration and could leave a half-rolled-back DB session.

**Per-route HTML helpers, not inline strings.** After Slice 51's Jinja2 extraction, only the small contact / event-link / tags fragments inside `_render_permalink_response` are still hand-built strings (with `html.escape`). The full HTML pages live in templates.

**Router include order is documented but not load-bearing.** FastAPI matches the most specific path; mount order doesn't change routing. The order in this file is read as "chat + public flows first, then admin, then programs."

## Known limitations and design notes

**`run_expired_review_cleanup` runs only on hourly tick.** A pending-review event whose deadline passes between ticks stays `pending_review` for up to 60 minutes. Acceptable: the deadline window is on the order of days, not minutes.

**`_hourly_cleanup_loop` is single-process.** With multiple uvicorn workers, multiple processes would each run the loop. Idempotent (each cleanup commits its own row updates and concurrent updates settle correctly), but redundant.

**Markdown subset is intentional.** Bold, italic-via-no-bold, lists, headings, comments, hyperlinks, and `[label](/path)` links. No tables, no code blocks, no nested lists. Adding any of those means extending `_render_doc_markdown_to_html` — the parser is positioned to grow if needed but not over-engineered now.

**`/health` exposes `event_count`.** Drift after catalog changes is expected; this isn't a billing surface.

**`/events` has no pagination, filtering, or auth.** All public events; full table read. Acceptable at current catalog size; would need rework at scale.

**`_truncate_for_og` is character-based, not word-aware.** Open Graph descriptions can end mid-word. Fine for OG previews.

**Sentry init swallows all exceptions.** A misconfigured DSN logs WARNING and continues — monitoring is never load-bearing for startup.

**Two parallel `/admin/api` mounts.** `admin_contributions_route` and `admin_mentions_route` both set their own `prefix="/admin/api"` on their `APIRouter`. The HTTP-API doc (`docs/maintainability/http_api.md`) lists both under the same prefix.

## Configuration

| Env var | Effect |
|---|---|
| `SENTRY_DSN` | If set and non-empty, initializes Sentry with the FastAPI + Starlette integrations. |
| `RAILWAY_ENVIRONMENT` | Used only to set Sentry's `environment` label (`"production"` if set, `"development"` otherwise). |
| `ADMIN_PASSWORD` | Read by `app/admin/auth.py` at import; lifespan logs presence only. |
| `RATE_LIMIT_DISABLED` | Toggles the slowapi limiter (process-wide). See `docs/components/rate_limit.md`. |

The `.env` file at the repo root supplies these in dev; Railway injects them in production.

## Related

**Direct callers:** `uvicorn` (Railway / local dev) imports `app.main:app`. The test suite imports the same `app` for `TestClient` instantiation.

**Direct dependencies:**

- `app/bootstrap_env.py` — `ensure_dotenv_loaded` (load-bearing first call).
- `app/core/rate_limit.py` — shared `limiter` and `RATE_LIMIT_MESSAGE`.
- `app/core/event_quality.py` — `friendly_errors` for the validation handler.
- `app/db/database.py` — `SessionLocal`, `get_db`, `init_db`.
- `app/db/models.py` — `Event` (used in `/health`, `/events`, and the cleanup task).
- `app/schemas/event.py` — `EventRead`.
- `app/admin/router.py`, `app/api/routes/{chat,contribute,admin_contributions,admin_mentions}.py`, `app/programs/router.py` — six included routers.
- `app/templates/` — three Jinja2 templates.
- `app/static/` — single-page chat shell (mounted at `/static`).

**Cross-references:**

- `docs/components/bootstrap_env.md` — why the `.env` loader sits at the top.
- `docs/components/rate_limit.md` — the shared slowapi `Limiter`.
- `docs/components/admin_router.md`, `docs/components/admin_contributions_route.md`, `docs/components/admin_mentions_route.md`, `docs/components/chat_route.md`, `docs/components/contribute_route.md`, `docs/components/programs_router.md` — every router this file mounts.
- `docs/maintainability/http_api.md` — full HTTP API surface (the cross-cutting view this file's mount layout feeds).
- `docs/maintainability/railway_layout.md` — env-var matrix and `/health` contract.
- `pyproject.toml` — `[tool.ruff.lint.per-file-ignores]` exempts this file from E402 because of the bootstrap-ordering imports.
