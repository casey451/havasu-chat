<!--
PURPOSE: Single reference for Hava's HTTP API surface — every route, its
mount path, auth posture, and rate limit. Consolidates information
previously spread across app/main.py, app/api/routes/*, app/admin/router.py,
app/programs/router.py, and ad-hoc grepping.

AUDIENCE: Anyone integrating with the API, debugging a request, or adding
a new route who wants to see the surface holistically. For per-route
field-level schemas see `app/schemas/`; for handler internals see the
route module source.
-->

# HTTP API sketch

## Mount layout

| Source | Prefix | Tags | Purpose |
|---|---|---|---|
| `app/main.py` (`@app.X`) | (no prefix) | — | Static UI, health, legal pages, event endpoints |
| `app/api/routes/chat.py` | (no prefix; full paths) | concierge | `/api/chat` + onboarding + feedback |
| `app/api/routes/contribute.py` | (no prefix) | contribute | Public contribute form + submit |
| `app/programs/router.py` | (no prefix) | (untagged) | Program list/detail/submit + admin program create |
| `app/admin/router.py` (with `categories_html`, `contributions_html`, `feedback_html`, `mentions_html`) | `/admin` | admin | Admin HTML UI (cookie-gated) |
| `app/api/routes/admin_contributions.py` | `/admin/api` | admin-contributions | Admin JSON API for contributions queue |
| `app/api/routes/admin_mentions.py` | `/admin/api` | admin-mentions | Admin JSON API for mentions queue |

## Public routes (no auth)

### Chat

| Method | Path | Rate limit | Schema / notes |
|---|---|---|---|
| POST | `/api/chat` | 120/min | req `ConciergeChatRequest` → resp `ConciergeChatResponse`. Sole chat entry; routes through tier 1/2/3 (`docs/components/unified_router.md`). |
| POST | `/api/chat/onboarding` | 120/min | resp `ChatOnboardingResponse`. Captures session hints. |
| POST | `/api/chat/feedback` | (none) | resp `ChatFeedbackResponse`. Logs feedback per turn. |

### UI / static / legal

| Method | Path | Notes |
|---|---|---|
| GET | `/` | HTML chat single-page app (`app/static/index.html`). |
| GET | `/privacy` | HTML — privacy policy. |
| GET | `/terms` | HTML — terms of service. |

### Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | JSON `{status, db_connected, event_count}`. See `docs/maintainability/railway_layout.md`. |

### Events (public read + 1 public write)

| Method | Path | Rate limit | Notes |
|---|---|---|---|
| POST | `/events` | 5/min | req `EventCreate` → resp `EventOut`. Publicly accepts event creates (rate-limited; verify intent). |
| GET | `/events` | (none) | List events. |
| GET | `/events/{event_id}` | (none) | Event permalink (HTML). |

### Contribute

| Method | Path | Rate limit | Notes |
|---|---|---|---|
| GET | `/contribute` | (none) | HTML — submission form. |
| POST | `/contribute` | DB-tracked IP hash (custom; see `_rate_limited` in `contribute.py`, not slowapi) | HTML response after submit. |

### Programs

| Method | Path | Rate limit | Notes |
|---|---|---|---|
| GET | `/programs` | (none) | List public programs. |
| GET | `/programs/{program_id}` | (none) | Single program view. |
| GET | `/programs/submit` | (none) | HTML — submission form. |
| POST | `/programs/submit` | 3/min | Submit a program (public-facing). |
| POST | `/programs` | 5/min | Create program (admin-flavored; see also `/admin/programs` below). |

## Admin HTML routes (`/admin/*`, cookie-gated via `verify_admin`)

Cookie set by `POST /admin/login` if password matches `ADMIN_PASSWORD` env var. Without the cookie, gated routes redirect to login.

### Auth + dashboard

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/admin/login` | — | HTML form. NOT gated. |
| POST | `/admin/login` | — | Sets cookie if password matches. NOT gated. |
| GET | `/admin/debug-pw` | — | Debug helper (verify production posture). |
| GET | `/admin/` | gated | Dashboard. |
| GET | `/admin/analytics` | gated | Analytics view. |

### Contributions queue

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/contributions` | Queue list. |
| GET | `/admin/contributions/{contribution_id}` | Detail. |
| GET / POST | `/admin/contributions/{contribution_id}/approve` | Form + handler. |
| GET / POST | `/admin/contributions/{contribution_id}/needs-info` | Form + handler. |
| GET / POST | `/admin/contributions/{contribution_id}/reject` | Form + handler. |

### Events admin

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/event/{event_id}/approve` | Approve event. |
| POST | `/admin/event/{event_id}/reject` | Reject event. |
| POST | `/admin/event/{event_id}/delete` | Delete event. |
| POST | `/admin/review/{event_id}` | Review action via JSON. |

### Programs admin

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/programs/new` | New program form. |
| POST | `/admin/programs` | Create program (HTML form path). |
| GET | `/admin/programs/{program_id}/edit` | Edit form. |
| POST | `/admin/programs/{program_id}/update` | Update. |
| POST | `/admin/programs/{program_id}/activate` | Activate. |
| POST | `/admin/programs/{program_id}/deactivate` | Deactivate. |

### Mentions queue

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/mentioned-entities` | List. |
| GET | `/admin/mentioned-entities/{mention_id}` | Detail. |
| GET / POST | `/admin/mentioned-entities/{mention_id}/dismiss` | Form + handler. |
| GET / POST | `/admin/mentioned-entities/{mention_id}/promote` | Form + handler (creates Provider). |

### Categories + feedback + bulk ops

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/categories` | Category management UI. |
| GET | `/admin/feedback` | View chat feedback rows. |
| POST | `/admin/reembed-all` | Bulk re-embed. |
| POST | `/admin/retag-all` | Bulk re-tag. |

## Admin JSON API (`/admin/api/*`, cookie-gated via `Depends(require_admin)`)

### Contributions

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/api/contributions` | List with filters. |
| POST | `/admin/api/contributions` | Direct create (admin-side). |
| GET | `/admin/api/contributions/{contribution_id}` | Single. |
| POST | `/admin/api/contributions/{contribution_id}/enrich` | Schedule background enrichment task. |
| PATCH | `/admin/api/contributions/{contribution_id}/status` | Status update. |

### Mentions

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/api/mentioned-entities` | List. |
| GET | `/admin/api/mentioned-entities/{mention_id}` | Single. |
| POST | `/admin/api/mentioned-entities/{mention_id}/dismiss` | Dismiss. |
| POST | `/admin/api/mentioned-entities/{mention_id}/promote` | Promote (creates Provider row). |

## Auth posture summary

- **Public** (no auth): chat (3), contribute (2), programs (5), events read + 1 public write (3), UI/static/legal (3), health (1) — **17 routes**.
- **Admin HTML** (cookie via `verify_admin`): all under `/admin/*` except `/admin/login` (GET+POST) and `/admin/debug-pw` — **~30 routes**.
- **Admin JSON API** (cookie via `Depends(require_admin)`): all under `/admin/api/*` — **9 routes**.

Cookie auth: see `app/admin/auth.py`. Login at `POST /admin/login` validates against `ADMIN_PASSWORD` env var (per `docs/maintainability/railway_layout.md`).

## Rate limits

slowapi `@limiter.limit` decorators (see `app/core/rate_limit.py`):

| Route | Limit |
|---|---|
| POST `/api/chat` | 120/min |
| POST `/api/chat/onboarding` | 120/min |
| POST `/events` | 5/min |
| POST `/programs` | 5/min |
| POST `/programs/submit` | 3/min |

Custom rate limit (DB-tracked IP hash, NOT slowapi): `POST /contribute` via `_rate_limited()` in `app/api/routes/contribute.py`.

`RATE_LIMIT_DISABLED=true` env var disables the slowapi limiter process-wide; `tests/conftest.py` uses this for test isolation. The custom contribute limiter is separate and not affected by that flag.

## Schemas

Canonical request/response Pydantic models live in `app/schemas/`:

- `chat.py` — `ConciergeChatRequest`, `ConciergeChatResponse`, `ChatOnboardingResponse`, `ChatFeedbackResponse`
- `contribution.py` — contribution create/read shapes
- `event.py` — `EventCreate`, `EventOut`, list response
- `program.py` — program create/read shapes
- `llm_mention.py` — mention / promote shapes

Pydantic v2; validation errors return 422 with FastAPI's standard envelope (some transformed via `friendly_errors` in `app/main.py`).

## What this doc does NOT cover

- **Per-route field-level schemas.** See `app/schemas/` source.
- **Per-route handler internals.** See route module source; `docs/components/unified_router.md` covers `POST /api/chat`.
- **WebSocket / streaming endpoints.** None currently.
- **OpenAPI / Swagger UI.** FastAPI's built-in `/docs` may or may not be mounted in production; verify before relying.
- **Background tasks per route** (e.g., chat's mention scanning, the enrich endpoint's background work). Per-handler detail lives in source.
- **Whether `POST /events` and `/admin/debug-pw` should exist as currently configured.** Doc describes the surface; whether the surface is correct is out of scope.

## Related docs

- `app/api/routes/`, `app/admin/`, `app/programs/`, `app/main.py` — source of truth.
- `app/schemas/` — request/response Pydantic models.
- `docs/maintainability/railway_layout.md` — env vars (`ADMIN_PASSWORD`, `RATE_LIMIT_DISABLED`), `/health` JSON detail.
- `docs/components/unified_router.md` — `POST /api/chat` handler internals.
- `docs/runbook.md` — operational playbooks (some endpoints have ops notes).
