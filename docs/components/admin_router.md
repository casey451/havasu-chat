# admin_router

`app/admin/router.py` (~1794 lines)
`app/admin/auth.py` — see `docs/components/admin_auth.md`
`app/admin/contributions_html.py`, `app/admin/categories_html.py`, `app/admin/feedback_html.py`, `app/admin/mentions_html.py`, `app/admin/nav_html.py` — register-style helper modules

## Purpose

Mounts every cookie-gated admin route under `/admin/*`. Renders dashboard, login, event-list, contribution-review, mention-promotion, feedback, and analytics HTML pages. Pairs with `app/api/routes/admin_*` for the JSON-API endpoints (`/admin/api/*`). The HTML helpers (`*_html.py`) are register-style — `router.py` imports each helper module and calls its `register_*_routes(router)` function near the top of the file.

## Public surface

**`router: APIRouter`** — The single exported router. `app/main.py` mounts it via `app.include_router(admin_router)`. Prefix `/admin`, tag `admin`.

There is no other public API; all consumers go through HTTP routes.

## Route inventory (high level)

| Route | Method | Purpose |
|-------|--------|---------|
| `/admin/login` | GET / POST | Login page + form submit. Sets cookie on success. |
| `/admin/logout` | POST | Clears cookie. |
| `/admin` | GET | Dashboard — pending vs live events, sortable tabs. |
| `/admin/event/{id}` | GET / POST | Event detail/edit. |
| `/admin/contributions` | GET | Contribution review queue. |
| `/admin/contributions/{id}` | GET / POST | Contribution review/approve/reject. |
| `/admin/categories` | GET | Category-management UI (registered via `categories_html.py`). |
| `/admin/feedback` | GET | User-feedback view (registered via `feedback_html.py`). |
| `/admin/mentions` | GET | LLM mention queue — promote/skip (registered via `mentions_html.py`). |
| `/admin/analytics` | GET | Top user messages, zero-result queries, daily active sessions, event funnel. |

The exact set may change; the most-current authoritative list is `docs/maintainability/http_api.md` admin-routes section.

## Internal structure

`router.py` is organized as five conceptual sections:

1. **Imports + setup** (lines 1-30). Imports the auth helpers, DB models, and the `*_html` register modules. Constructs `router = APIRouter(prefix="/admin", tags=["admin"])`. Calls `register_*_routes(router)` for each helper module.
2. **Guard + utility helpers** (lines ~30-200). `_guard(request)` returns a `RedirectResponse` to login if the cookie is invalid. Date and analytics-query helpers (`_utc_now`, `_analytics_cutoff`, `_query_top_user_messages`, etc.). HTML rendering helpers (`_table_rows_html`, `_analytics_page_html`, etc.).
3. **Event-card + dashboard rendering** (lines ~290-600). HTML for event cards, dashboard tabs, sort controls. `_login_html`, `_dashboard_html_simple`, `_card_html`.
4. **Login + dashboard routes** (lines ~600-700). `admin_login_page`, `admin_login_submit`, dashboard root `/admin`.
5. **Event detail + edit + analytics routes** (lines ~700-1794). Per-event handlers, contribution-handling routes (proxied to `contributions_html.py` register), analytics page.

The `*_html.py` helper modules each export a `register_*_routes(router)` function that adds routes to the passed-in router. This split keeps `router.py` focused on the dashboard and event-detail flow; large per-feature surfaces (contributions, mentions) live in their own files.

## Conventions

**Every route starts with `_guard(request)`.** The guard returns a `RedirectResponse` to `/admin/login` when the cookie is invalid or absent. Routes invoke this defensively rather than relying on a global middleware so per-route opt-out is possible (e.g., the login page itself, the auth callback). Adding new routes without the guard exposes them to unauthenticated traffic.

**HTML is hand-rendered, not via Jinja.** All admin HTML is produced by Python f-strings and helper functions returning escaped strings. `html.escape` is used systematically for user-supplied data. Adding a Jinja layer is its own decision; current state intentionally avoids the templating dependency.

**Form posts use FastAPI's `Form(...)` dependency.** Multipart not used. Forms are kept simple to keep the rendering logic auditable.

**Database access via `Depends(get_db)`.** Sessions are scoped per request. Direct `SessionLocal()` calls in routes are an anti-pattern; the dependency injection makes test fixtures simpler.

**`_utc_now`, `_analytics_cutoff`, `_chatlog_day_column` are timezone-aware.** Analytics queries use UTC consistently. Display is also UTC unless a future I18n decision changes that.

## Configuration

- `ADMIN_PASSWORD` — required for production; falls back to `"changeme"` in dev (see `admin_auth.md`).
- `DATABASE_URL` — used indirectly via `Depends(get_db)`.

## Known limitations and design notes

**Single-file router is large.** ~1794 lines is at the upper edge of "reasonable for a single FastAPI router." Per-feature splits via `*_html.py` register modules are partial mitigation. Future refactors might fully split (e.g., `admin/dashboard.py`, `admin/events.py`, `admin/analytics.py`) if growth continues.

**Hand-rendered HTML carries XSS risk.** Every user-supplied string MUST go through `html.escape` (or `_escape` helper) before insertion into the output. Code review should call out missing escapes; ruff/lint won't catch this category of bug.

**No CSRF protection.** Form posts rely on the cookie alone; there's no per-request CSRF token. The single-admin threat model is the rationale; if multi-admin or any kind of public surface is added, CSRF mitigation becomes required.

**Analytics queries are computed live.** No caching; each `/admin/analytics` page-load runs the full query battery. Acceptable at current scale (~tens of queries per dashboard load); if analytics becomes a daily review habit, caching becomes worthwhile.

**Dashboard `tab=pending` and `tab=live` filter via SQL `WHERE` on `Event.status`.** Inactive providers/programs aren't surfaced in admin-event flows; that's deliberate (admin reviews catalog status separately).

## Related

**Direct callers:** `app/main.py` mounts the router. No other modules import `router` directly.

**Direct dependencies:**

- `app/admin/auth.py` — cookie verification (see `docs/components/admin_auth.md`).
- `app/admin/contributions_html.py`, `categories_html.py`, `feedback_html.py`, `mentions_html.py`, `nav_html.py` — register-style helper modules.
- `app/db/models.{ChatLog, Event, Program}` — read for dashboard, analytics.
- `app/schemas/program.ProgramCreate` — for program-creation form posts.
- `app/db/database.{DATABASE_URL, get_db}` — DB session.

**Cross-references:**

- `docs/maintainability/http_api.md` — full admin-route inventory with auth posture.
- `docs/components/admin_auth.md` — auth helper details + threat model.
- `app/api/routes/admin_*` — the JSON API counterparts (separate modules; not covered here).
