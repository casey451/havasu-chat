# contribute_route

`app/api/routes/contribute.py` (~285 lines)

## Purpose

Public **HTML contribution form** at `GET /contribute` and the corresponding `POST /contribute` submit handler (Phase 5.4). This is the user-facing intake surface — `index.html` links here from the chat shell. Operators triage submissions in the cookie-gated admin queue (`/admin/contributions`); the route here is the "anyone can suggest something" entry point.

Despite living under `app/api/routes/`, this module renders **HTML** (with a hand-built `<form>` and inline CSS) — not JSON. The directory placement is historical; the request/response is browser-form-shaped, with field-level error rendering and form-state preservation across validation failures.

## Public surface

**`router: APIRouter`** — Sole export. Tagged `contribute`. No prefix; routes are literal `/contribute`. Mounted from `app/main.py` via `app.include_router(contribute_router)`.

There is no Python callable API beyond the HTTP handlers.

## Route inventory

| Route | Method | Rate limit | Purpose |
|---|---|---|---|
| `/contribute` | GET | (none) | Render the submission form (also handles the post-submit success banner via `?submitted=1`). |
| `/contribute` | POST | **custom DB-tracked IP-hash** (1 submission / hour) | Validate `Form(...)` fields → `ContributionCreate` Pydantic → `create_contribution` → background `enrich_contribution`. Redirects to `/contribute?submitted=1` on success; re-renders form with banners + field errors otherwise. |

The rate limit is **NOT** slowapi. It's a custom check (`_rate_limited`) that hashes the request's remote address and counts submissions in the last hour via `count_submissions_since_by_ip_hash`. Disable behavior is shared with slowapi via `is_rate_limit_disabled()` from `app/core/rate_limit.py`, but the counting and enforcement are independent.

## Inputs and outputs

**`GET /contribute`** — Optional `submitted: int | None` query parameter; when truthy, renders the success banner above the form. Otherwise renders an empty form. Always returns `HTMLResponse`.

**`POST /contribute` form fields** (all `Form(...)`):

- `entity_type: str` — Required. One of `provider | program | event | tip` (validated; invalid → 400 + form re-render with field error).
- `submission_name: str` — Required.
- `submission_url: str | None` — Optional except for `provider` and `program` (those require a URL).
- `category_hint: str | None`, `description: str | None` — Optional. Description capped at `_MAX_NOTES = 2000` characters.
- `event_date`, `event_start_time`, `event_end_time: str | None` — Optional. Used only for `entity_type=event`. Times accept `HH:MM` (5-char short form, expanded internally) or `HH:MM:SS`.
- `submitter_email: str | None` — Optional.

**Response:**

- Success → `RedirectResponse("/contribute?submitted=1", status_code=302)`.
- Rate-limited → 429 `HTMLResponse` with the banner `_RATE_MSG = "Thanks for your enthusiasm — please wait an hour between submissions."` and form fields preserved.
- Duplicate URL (already in `pending` or `approved`) → 200 `HTMLResponse` with `_DUP_MSG = "We already have this in our review queue. Thanks though!"` banner.
- Thin submission (no URL **and** no notes) → 200 `HTMLResponse` with `_THIN_MSG = "Please add a short description or a URL — something so we know what this is about."`.
- Validation failure (entity-type, URL-required-for-provider/program, malformed dates/times, Pydantic errors) → 200 `HTMLResponse` with field-error list and preserved form values.

**Side effect on success:** A new `Contribution` row with `source="user_submission"` and `submitter_ip_hash` set; a `BackgroundTasks.add_task(enrich_contribution, row.id, SessionLocal)` schedules URL fetch + Places enrichment.

## Internal structure

The module is six conceptual blocks:

1. **Constants and helpers** (top of file). `_MAX_NOTES`, the four message strings (`_RATE_MSG`, `_DUP_MSG`, `_THIN_MSG`, `_SUCCESS_INTRO`), `_esc` (XSS escape), `_ip_hash` (SHA-256 of the remote address), `_rate_limited` (DB-counted), `_parse_optional_date`, `_parse_optional_time`.
2. **`_render_contribute_page`** — Single rendering function. Takes optional `submitted`, `error_banner`, `field_errors` dict, `preserve` dict (form values to re-populate), and `status_code`. Returns `HTMLResponse` with the inline-CSS-and-JS form. The form's entity-type radio drives JavaScript-side visibility of event-only fields (`event_date`, `event_start_time`, `event_end_time`).
3. **`get_contribute`** (~3 lines) — Renders the form; handles the success banner case.
4. **`post_contribute`** — The submit pipeline:
   1. Build the `preserve` dict from raw form fields (used by every error branch).
   2. Rate-limit check (`_rate_limited`) — return 429 if hit.
   3. Description length check.
   4. Entity-type validation.
   5. URL-required-for-provider/program check.
   6. Thin-submission check (URL or notes required).
   7. URL duplicate check via `normalize_submission_url` + `has_pending_or_approved_duplicate_url`.
   8. Event-only date/time parsing (only when `entity_type == "event"`).
   9. `ContributionCreate` Pydantic validation — `ValidationError` → re-render with per-field errors keyed by Pydantic `loc`.
   10. `create_contribution(db, body, submitter_ip_hash=...)`.
   11. `BackgroundTasks.add_task(enrich_contribution, row.id, SessionLocal)`.
   12. Redirect to success URL.

## Conventions

**HTML, not JSON.** This module is browser-form-oriented; field errors render as HTML banners + inline `<li>` lists. The admin JSON API for contributions lives at `app/api/routes/admin_contributions.py` — a different module with different concerns.

**XSS discipline.** Every interpolation of user-supplied text into the form HTML goes through `_esc(...)` (which is `html.escape(s or "", quote=True)`). The form renders even after validation failure, with the user's own values preserved — `_esc` is the load-bearing safety boundary.

**Form-state preservation.** On every error branch, the `preserve` dict is passed back to `_render_contribute_page` so the operator's typing isn't lost. The entity-type radio is also pinned via the dict so the event-only fields' visibility is consistent on re-render.

**IP-hash, not raw IP.** `_ip_hash` computes SHA-256 of `get_remote_address(request)`. The hash is what's persisted on the `Contribution` row and what's counted for rate-limiting. Plaintext IPs are never stored.

**Custom rate limiter, not slowapi.** Slowapi's in-memory backend would reset on every worker restart; the DB-tracked counter survives restarts and gives a reliable per-IP / per-hour cap. The custom limiter still respects `RATE_LIMIT_DISABLED` for test isolation.

**`source="user_submission"` is hard-coded.** The admin promote-from-mention flow uses `source="llm_inferred"`; the admin direct-create UI uses `source="admin"`. These three values are the discriminators downstream consumers (admin UI filters, approval policy) rely on.

**Success uses 302 redirect.** Post-Redirect-Get pattern — refreshing the success page won't re-submit. The query param `?submitted=1` triggers the banner on the GET render.

## Known limitations and design notes

**Form HTML is inline.** No Jinja template; the f-string in `_render_contribute_page` carries the entire CSS, the form structure, the JavaScript visibility toggle, and the field error rendering. Same posture as the admin HTML helpers — adding a Jinja layer is its own decision.

**JavaScript-only event-field visibility.** The event-only fields (`event_date`, `event_start_time`, `event_end_time`) are hidden via inline JS based on the entity-type radio. With JavaScript disabled, the fields are visible regardless of selection — the server-side handler ignores them when `entity_type != "event"`, so this is a UX issue not a correctness issue.

**Duplicate check is URL-only.** A submission without a URL bypasses the duplicate gate. Acceptable: text-only submissions are usually tips or one-off events; the admin queue catches duplicates manually.

**No CSRF token.** Public form, public POST. Same posture as `/programs/submit`. The custom rate-limit + validation gating reduces abuse impact; CSRF mitigation would require a session/cookie story this route doesn't currently have.

**Email is opt-in and not validated beyond format.** Submitters can submit anonymously; the email field is for "we'll come back to you with questions" — no verification, no double-opt-in.

**`_RATE_MSG` etc. are hard-coded English.** Same posture as `RATE_LIMIT_MESSAGE` in `app/core/rate_limit.py` — localization would require splitting per locale.

**No structured logging on validation failure.** The route doesn't `logger.info` rejected submissions; the only persistent record of a bad submission is "no row was created." If abuse-pattern visibility is ever needed, this is the place to add it.

## Configuration

- `RATE_LIMIT_DISABLED` (env, shared with slowapi) — when set, `_rate_limited` returns `False` unconditionally. Used in `tests/conftest.py`.
- `_MAX_NOTES = 2000` — character cap for the description field; module-level constant.

## Related

**Direct callers:** `app/main.py` mounts the router. The `index.html` chat shell links to `/contribute`.

**Direct dependencies:**

- `app/core/rate_limit.py` — `is_rate_limit_disabled` (shared disable flag).
- `app/db/contribution_store.py` — `create_contribution`, `count_submissions_since_by_ip_hash`, `has_pending_or_approved_duplicate_url`, `normalize_submission_url`.
- `app/db/database.py` — `SessionLocal` (background-task factory), `get_db`.
- `app/contrib/enrichment.py` — `enrich_contribution` (background URL-fetch + Places lookup).
- `app/schemas/contribution.py` — `ContributionCreate` Pydantic model.
- `slowapi.util.get_remote_address` — used inside `_ip_hash` for the hashing input.

**Cross-references:**

- `docs/components/admin_contributions_html.md` — admin HTML surface that triages these submissions.
- `docs/components/admin_contributions_route.md` — admin JSON API for the same queue.
- `docs/components/contribution_store.md` — DB-side helpers the route uses.
- `docs/components/enrichment.md` — what the background task does to a fresh row.
- `docs/components/schema_contribution.md` — `ContributionCreate` field-level shape.
- `docs/components/rate_limit.md` — shared disable flag and the slowapi limiter (which this module does NOT use, deliberately).
- `docs/maintainability/http_api.md` — full HTTP surface; this route's row notes the custom limiter explicitly.
- `docs/maintainability/end_to_end_creation.md` — Path 1 (public submission) starts here.
