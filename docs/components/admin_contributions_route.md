# admin_contributions_route

`app/api/routes/admin_contributions.py` (~133 lines)

## Purpose

Admin-gated **JSON API** for the contribution review queue (Phase 5.1 + 5.2 enrichment). Five endpoints under `/admin/api/contributions*` — list, single fetch, create (admin direct path), status update, and re-enrich. The HTML surface at `app/admin/contributions_html.py` (`/admin/contributions*`) is the operator-facing page; this module is the JSON-shaped sibling that powers programmatic clients (and any HTML buttons that submit XHR rather than full-form posts).

The route module is intentionally thin — auth via the cookie, request validation via Pydantic, dispatch to `app/db/contribution_store.py` and `app/contrib/enrichment.py`. No business logic of its own beyond branching on Pydantic validation outcomes.

## Public surface

**`router: APIRouter`** — Sole export. **Prefix `/admin/api`**, tag `admin-contributions`. Mounted from `app/main.py` via `app.include_router(admin_contributions_router)`.

**`require_admin(request: Request) -> None`** — Module-local dependency. Reads the admin cookie from `request.cookies.get(COOKIE_NAME)` and validates via `app/admin/auth.verify_admin_cookie`. Raises `HTTPException(401)` on missing or invalid cookie. Wired into every handler via the `AdminAuth` annotation.

The mention-route module (`admin_mentions.py`) defines its own `require_admin` with the same body. Shared cookie-gate via `app/admin/auth.COOKIE_NAME` + `verify_admin_cookie`; the dependency function is duplicated, not shared.

## Route inventory

| Route | Method | Status | Purpose |
|---|---|---|---|
| `/admin/api/contributions` | POST | **201** | Admin direct create. Body `ContributionCreate`; calls `create_contribution(submitter_ip_hash=None)` and schedules `enrich_contribution`. Returns `ContributionResponse`. |
| `/admin/api/contributions` | GET | 200 | List with filters: `status`, `entity_type`, `source`, `limit` (1–200, default 50), `offset` (≥0, default 0). Returns `list[ContributionResponse]`. |
| `/admin/api/contributions/{contribution_id}` | GET | 200 / 404 | Single contribution by integer id. Returns `ContributionResponse` or `HTTPException(404)`. |
| `/admin/api/contributions/{contribution_id}/status` | PATCH | 200 / 400 / 404 | Body `ContributionStatusUpdate` (`status`, optional `review_notes`, `rejection_reason`). Calls `update_contribution_status`; `ValueError` → 400 with the message; missing row → 404. |
| `/admin/api/contributions/{contribution_id}/enrich` | POST | **202 Accepted** | Schedules `enrich_contribution` background task; returns `{"contribution_id": ..., "enrichment": "scheduled"}` JSON. 404 if the row is missing. |

## Inputs and outputs

**Auth:** Every route is gated by `Depends(require_admin)` (via the `AdminAuth = Annotated[None, Depends(require_admin)]` alias). No cookie → 401 `{"detail": "Admin authentication required"}`. Login is via `POST /admin/login` (the HTML surface) which sets the cookie this module verifies.

**Request bodies and query params:** All Pydantic-validated. The list endpoint uses `Query(...)` with explicit bounds (`ge=1`, `le=200` on `limit`; `ge=0` on `offset`) so out-of-range values return FastAPI's standard 422.

**Response models:** `ContributionResponse` for the four data-bearing routes; the enrich endpoint returns a literal JSON object (it doesn't fetch and serialize the row — the work is async and not yet visible). The `model_validate(row)` call converts SQLAlchemy ORM rows to Pydantic responses.

**Status filter alias.** The list query parameter is exposed as `?status=...` (alias for the in-Python name `status_filter`). The alias avoids shadowing the imported `fastapi.status` symbol.

## Internal structure

This module is mostly a series of decorated handlers, all with the same shape:

1. `Depends(require_admin)` (via `AdminAuth` annotation) — guard.
2. `Depends(get_db)` (via `DbSession` annotation) — request-scoped session.
3. Optional `BackgroundTasks` — for the create and enrich routes.
4. Path / query / body parameters.
5. Direct dispatch to `contribution_store` / `enrichment` helpers.
6. `HTTPException` on missing rows or bad transitions; otherwise return the validated response model.

Two `Annotated` aliases pull the boilerplate out:

- `AdminAuth = Annotated[None, Depends(require_admin)]` — applied as the **first** parameter on every handler (named `_` because the guard's return value is unused).
- `DbSession = Annotated[Session, Depends(get_db)]` — applied as a request-scoped DB session.

The `update_contribution_status` call wraps `ValueError` and converts to `HTTPException(400)` with the original message. The store raises `ValueError` for invalid status transitions; the route doesn't try to enumerate them — the message is opaque-ish and operator-readable.

## Conventions

**`/admin/api` prefix is set on the router itself.** The router declares `APIRouter(prefix="/admin/api", tags=["admin-contributions"])`; routes inside the file use the bare path (e.g., `/contributions`). Cross-checking with `docs/maintainability/http_api.md` is the way to confirm the full URL.

**Cookie auth, not bearer/header.** Same cookie as the HTML admin (`POST /admin/login`). The pair docs (`admin_contributions_html.md` + this file) describe the same operator surface from two angles.

**`require_admin` is local, not imported.** The helper is duplicated in `admin_mentions.py`. Consolidating into `app/admin/auth.py` is on the table whenever someone touches both modules at once; the duplication is small.

**Enrich returns 202, not 200.** The work is async. 202 Accepted is the correct semantic — request acknowledged, not yet complete. Clients that want completion confirmation must poll the GET endpoint.

**`submitter_ip_hash=None` on admin direct create.** Operator submissions don't carry a public IP; setting `None` distinguishes admin direct creates from `source="user_submission"` rows in queries that count submissions per IP.

**`ContributionResponse.model_validate(row)`.** Pydantic v2 idiom for ORM → response model. Don't replace with `from_orm` (deprecated).

**404 vs ValueError vs ValidationError.** Missing rows → `HTTPException(404, "Not found")`. Bad status transitions → `HTTPException(400, str(e))`. Pydantic body validation → FastAPI 422. The three layers stay distinct.

## Known limitations and design notes

**Pairs with the HTML surface.** This route is not the only contribution-management surface; `app/admin/contributions_html.py` does the bulk of the operator review work (approve/reject/needs-info forms, enrichment panels, category datalists). The JSON API is for programmatic clients and the small subset of HTML actions that POST via XHR (the `enrich` button on the detail page is one).

**No bulk operations.** Each handler operates on a single contribution. Bulk approve / bulk reject would require either repeated calls or a new endpoint.

**No pagination metadata.** The list endpoint returns the rows but no total-count envelope. Clients infer "more" by checking whether the returned slice is full. If pagination metadata is ever needed, the response shape needs to change (or a sibling `/count` endpoint added).

**No CSRF token.** Cookie auth + JSON body. Same posture as the rest of the admin surface; the threat model assumes single-admin operation.

**No rate limit.** Cookie auth is the gate. If a compromised admin cookie is the threat, rate-limiting won't help.

**`require_admin` duplication.** Shared via copy-paste with `admin_mentions.py`. A single dependency in `app/admin/auth.py` would consolidate, but the duplication is two-line.

**Status update accepts the full new status in the body.** The store validates the transition; the route doesn't enumerate transitions in code. If a new status is added (`Contribution.status` literals), the schema is the source of truth — verify both files are updated.

## Configuration

No environment configuration. `ADMIN_PASSWORD` (used during cookie minting at login) is documented under `admin_auth.md`.

## Related

**Direct callers:** `app/main.py` mounts the router. The HTML surface (`contributions_html.py`) embeds an XHR POST form to `/admin/api/contributions/{id}/enrich` for the re-enrich button.

**Direct dependencies:**

- `app/admin/auth.py` — `COOKIE_NAME`, `verify_admin_cookie` (cookie validation).
- `app/db/contribution_store.py` — `create_contribution`, `get_contribution`, `list_contributions`, `update_contribution_status`.
- `app/contrib/enrichment.py` — `enrich_contribution` (background task).
- `app/db/database.py` — `SessionLocal` (background-task factory), `get_db`.
- `app/schemas/contribution.py` — `ContributionCreate`, `ContributionResponse`, `ContributionStatusUpdate`.

**Cross-references:**

- `docs/components/admin_contributions_html.md` — the HTML pair: operator review forms, approve/reject/needs-info handlers, enrichment panels.
- `docs/components/admin_auth.md` — cookie threat model and login flow.
- `docs/components/contribution_store.md` — store-layer helpers this route dispatches to.
- `docs/components/enrichment.md` — what `enrich_contribution` does on the background-task side.
- `docs/components/schema_contribution.md` — request/response Pydantic shapes.
- `docs/components/approval_service.md` — referenced from `update_contribution_status`'s downstream side when status transitions to `approved`.
- `docs/maintainability/http_api.md` — full admin JSON API inventory.
- `docs/components/admin_mentions_route.md` — sibling JSON API; mirror structure with the same auth pattern.
