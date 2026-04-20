# Phase 5.4 — Completion report (pre-commit)

Phase **5.4 is implemented** (not committed, per workflow). This document mirrors the handoff summary from implementation.

---

## Pre-flight

```
Pre-flight checks:
  Check 1 (5.3 commit in history): PASS — 7fa2630 "Phase 5.3: Operator review UI + approval creates catalog rows" in last 20 commits
  Check 2 (gap_template location): PASS — `_GAP_TAIL` + `_catalog_gap_response()` in `app/chat/unified_router.py` (~40–57); three variants (HOURS / LOCATION / DATE prefix + shared tail)
  Check 3 (rate limiter pattern): PASS — `slowapi` `Limiter` in `app/core/rate_limit.py` with `get_remote_address`, `RATE_LIMIT_DISABLED`; routes use `@limiter.limit(...)`. POST `/contribute` uses **DB + IP hash**: `count_submissions_since_by_ip_hash` + same `get_remote_address` + `is_rate_limit_disabled()` so tests stay stable when the global limiter is disabled (no new infra).
  Check 4 (public routes): PASS — `app/main.py` `app.include_router(contribute_router)` alongside chat routers; `GET /` still `FileResponse` static.
```

---

## What shipped

| Item | Detail |
|------|--------|
| **Routes** | `GET` / `POST /contribute` in `app/api/routes/contribute.py` — inline HTML + ~40 lines inline JS (entity fields, URL `required`) |
| **Success** | `302` → `/contribute?submitted=1` + success banner |
| **Validation** | `ContributionCreate` + route rules: provider/program URL required; min content = URL **or** notes; notes max 2000 |
| **Duplicates** | `normalize_submission_url` + `has_pending_or_approved_duplicate_url` in `contribution_store.py` — only `pending` / `approved` |
| **Rate limit** | 1 submission per IP per rolling hour when `RATE_LIMIT_DISABLED` is off |
| **Enrichment** | `BackgroundTasks` → `enrich_contribution` + `SessionLocal` (same as admin) |
| **gap_template** | `_GAP_TAIL` updated (see below) |
| **Prompt** | `prompts/system_prompt.txt` catalog-gap bullet extended with `/contribute` |
| **Chat UI** | `app/static/index.html` — “Add to catalog →” under composer |
| **Tests** | `tests/test_contribute_public.py`, `tests/test_gap_template_contribute_link.py`; `tests/test_phase38_gap_and_hours.py` asserts `/contribute` |

---

## gap_template wording (before → after)

**Shared tail (`_GAP_TAIL`)**

- **Before:** `Havasu Chat grows from what locals contribute — share the name and a link (Google Business page or official site) and I'll add it.`
- **After:** `Add it at /contribute or share the name and a link (Google Business page or official site) — either works.`

**Full lines (prefix unchanged, tail replaced)**

- HOURS: `I don't have those business hours in the catalog yet. ` + new tail  
- LOCATION: `I don't have that place in the catalog yet. ` + new tail  
- DATE: `I don't have that event or program in the catalog yet. ` + new tail  

---

## Rate limiting (for reviewers)

- **Library:** `slowapi` (`Limiter` in `app/core/rate_limit.py`) remains the standard for `/api/chat` etc.  
- **`/contribute` POST:** **No** `@limiter.limit` on this route (avoids JSON-only `RateLimitExceeded` handler and avoids coupling to a process-wide disabled limiter in pytest). Instead: **`get_remote_address`**, **SHA-256 IP hash**, **`count_submissions_since_by_ip_hash`** on `contributions.submitted_at` (last hour), skipped when **`is_rate_limit_disabled()`** is true (same env as Phase 3.8).

---

## HTML escaping

All echoed user input on error/success paths goes through **`_esc()`** (`html.escape(..., quote=True)`) in `contribute.py`, including preserve dict, banners, and field-error list.

---

## Verification

| Check | Result |
|--------|--------|
| **pytest** | **614 passed** |
| **Track A** (`scripts/run_query_battery.py`) | **116 / 120** |

---

## Files touched

**New:** `app/api/routes/contribute.py`, `tests/test_contribute_public.py`, `tests/test_gap_template_contribute_link.py`  

**Modified:** `app/main.py`, `app/db/contribution_store.py`, `app/chat/unified_router.py`, `prompts/system_prompt.txt`, `app/static/index.html`, `tests/test_phase38_gap_and_hours.py`

---

## Representative form HTML (shape)

The page is built in `_render_contribute_page()` in `contribute.py`: intro paragraph, optional success/error banners, `<form method="post" action="/contribute">` with radios for entity type, text/url/textarea fields, event-only block `#event-fields`, submit button, link back to `/`. Open that function in the repo for the full template.

---

## STOP-and-ask

None. No changes to `Contribution` ORM, enrichment, approval service, or admin JSON/HTML from 5.3 beyond shared `contribution_store` helpers.

---

## Commit / push

**Not committed** (per Phase 5.4 instructions). When the owner replies **`approved`**, commit with **verbatim**:

`Phase 5.4: Public user contribution form`

then one `git push` to `main`.
