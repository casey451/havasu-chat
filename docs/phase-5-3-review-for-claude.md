# Phase 5.3 — Review handoff for Claude

Operator review UI for the contribution queue: HTML admin at `/admin/contributions*`, approval creates `Provider` / `Program` / `Event` rows, JSON API moved under `/admin/api/contributions` to avoid path clash.

**Commit status:** Implementation is complete; **owner has not yet approved commit**. When approved, commit message (verbatim):

`Phase 5.3: Operator review UI + approval creates catalog rows`

---

## Scope delivered

| Area | What shipped |
|------|----------------|
| List | `GET /admin/contributions` — filters `status` (default `pending`), `entity_type`, `source`, `limit`, `offset`; pagination; flash query params |
| Detail | `GET /admin/contributions/{id}` — submission, enrichment (URL + Places + hours formatter), actions or frozen review state |
| Approve | `GET` + `POST /admin/contributions/{id}/approve` — provider/program/event forms; category `<datalist>` from distinct DB values; redirect + flash on success |
| Reject | `GET` + `POST /admin/contributions/{id}/reject` — reason dropdown + optional notes |
| Needs info | `GET` + `POST /admin/contributions/{id}/needs-info` — required notes |
| Tips | Approve returns **400** with message to use Needs Info (no tip catalog in 5.3) |
| Re-enrich | Detail page POSTs to existing endpoint at **`/admin/api/contributions/{id}/enrich`** |
| JSON API | All contribution JSON under **`/admin/api`** prefix (see table below) |
| Service | `app/contrib/approval_service.py` — single `commit`; rollback on failure; `enrichment_suggests_verified()` drives `verified` on catalog rows |
| Schemas | `ProviderApprovalFields`, `ProgramApprovalFields`, `EventApprovalFields` in `app/schemas/contribution.py` |

**Out of scope (unchanged):** `Contribution` model shape, enrichment workers (`url_fetcher`, `places_client`, `enrichment.py`), Tier 1/2/3, user-facing submit form, tip approval.

---

## Pre-flight (all passed before implementation)

1. **5.2 in history:** `f5c4463` — `Phase 5.2: URL validation + Google Places integration`
2. **HTML admin pattern:** No Jinja2 in repo; admin uses **inline HTML** in Python (`app/admin/router.py`). Phase 5.3 matches that in `app/admin/contributions_html.py` (no new dependency).
3. **Catalog models:** `Provider`, `Program`, `Event` in `app/db/models.py` — UUID string PKs; `Contribution.id` is integer autoincrement.
4. **Category seeds:** Distinct `providers.category` / `programs.activity_category` used for datalist (small enum-like sets from seed data).

---

## Route map

### HTML (cookie session; unauthenticated → `302` `/admin/login`; use `follow_redirects=False` in tests for auth assertions)

| Method | Path |
|--------|------|
| GET | `/admin/contributions` |
| GET | `/admin/contributions/{id}` |
| GET/POST | `/admin/contributions/{id}/approve` |
| GET/POST | `/admin/contributions/{id}/reject` |
| GET/POST | `/admin/contributions/{id}/needs-info` |

FastAPI: routes use `response_model=None` where return type is `HTMLResponse | RedirectResponse`.

### JSON (same admin cookie as HTML; unauthenticated → **401**)

| Method | Path |
|--------|------|
| POST | `/admin/api/contributions` |
| GET | `/admin/api/contributions` |
| GET | `/admin/api/contributions/{id}` |
| PATCH | `/admin/api/contributions/{id}/status` |
| POST | `/admin/api/contributions/{id}/enrich` |

---

## Key files

| Path | Role |
|------|------|
| `app/admin/contributions_html.py` | HTML builders + `register_contribution_html_routes(router)` |
| `app/admin/router.py` | Calls `register_contribution_html_routes(router)` at module end |
| `app/contrib/approval_service.py` | Approve three entity types + helpers |
| `app/schemas/contribution.py` | Approval Pydantic models |
| `app/api/routes/admin_contributions.py` | `prefix="/admin/api"` |
| `app/db/contribution_store.py` | `count_contributions()` for list pagination |
| `tests/test_approval_service.py` | Service + verified + rollback + mismatch |
| `tests/test_admin_contributions_html.py` | HTML flows + enrich form target |
| `tests/test_admin_contributions_api.py` | URLs updated to `/admin/api/...` |
| `scripts/smoke_phase52_contributions.py` | JSON URLs updated |

---

## Verification (last run on implementation machine)

- **`pytest`:** 601 passed (full suite).
- **Track A:** `scripts/run_query_battery.py` → **116 / 120** (script’s hardcoded production `BASE`; threshold in spec was ≥ 116).

---

## Review checklist for Claude

1. **Security / privacy:** Detail view shows submitter email and **truncated IP hash** (first 8 + ellipsis); no new logging of raw PII called out in code paths.
2. **Transactions:** Approval path commits once; `except` → `rollback()` in `approval_service`.
3. **Double approve:** POST approve on non-pending → **400** HTML error page.
4. **Program validation:** `ProgramCreate` enforces schedule times `HH:MM`, `schedule_days` full day names, description length, optional phone rules — empty phone is OK.
5. **Event validation:** `EventCreate` / `Event.from_create` — URL normalization and description min length apply.
6. **JSON vs HTML:** No duplicate route on same method+path; list **HTML** and list **JSON** are different paths.
7. **Tip deferral:** Approve GET/POST for `entity_type == tip"` returns 400 with explicit copy.

---

## Optional manual smoke

1. Set `ADMIN_PASSWORD`, run app, `POST /admin/login`, then open `/admin/contributions`.
2. Create a provider via `POST /admin/api/contributions` with `submission_url`, open detail, use **Re-run enrichment**, then **Approve** and confirm row in `providers` and `contributions.created_provider_id`.

---

## Owner workflow (do not skip)

Per phase instructions: **no commit** until owner replies `approved` in chat; then one commit with the verbatim subject above and one push to `main`. No amend, no hook bypass, leave `Made-with: Cursor` trailer as-is.
