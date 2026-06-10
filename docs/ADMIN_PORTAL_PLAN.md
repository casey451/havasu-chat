# Admin Portal — Plan & Build Notes (2026-06-10)

Goal: one coherent, user-friendly admin portal that consolidates everything Casey needs to run
Ask Hava day-to-day. Built as an **isolated, unwired package** at `app/admin_portal/` so it can
land in the repo while other sessions work the codebase. Nothing is registered in `app/main.py`
and no migration is applied until we're ready (see `app/admin_portal/README.md` for the wiring
steps — it's a 2-line change).

## What already exists (audit summary)

The current `/admin` area (cookie gate via `ADMIN_PASSWORD`, `app/admin/auth.py`) already covers:

- Event queue + approve/reject/edit (`/admin?tab=queue`, `app/admin/router.py`)
- Provider approval (`/admin/providers/pending`), duplicate merge review (`/admin/providers/duplicates`)
- Contributions review, mentioned entities, categories, miscategorized patrol
- Claims verify/reject (`/admin/claims`), upgrade requests, sponsors inventory, ad reservations
- Jobs page (create scraper-pipeline jobs), analytics page, feedback, demand
- Batch ops: `/admin/reembed-all`, `/admin/retag-all`

Gaps the portal fills:

1. **No unified home.** Counts and queues are scattered across ~20 pages with a hardcoded nav.
2. **No user management UI.** Promoting a user to admin is SQL-only (model docstring, `User`).
   No way to search users, see roles, deactivate accounts.
3. **Thin chat observability.** `ChatLog` records tier_used, cache_status, latency_ms,
   llm_input/output_tokens, feedback_signal, timing_ms — but there's no rollup view
   (cost, cache hit-rate, slow turns, unmatched queries).
4. **No ops visibility.** `jobs` and `outbox` tables have no monitoring UI (failed outbox rows =
   lost magic links; no retry button).
5. **No audit trail.** Admin actions (approve/reject/role changes) aren't recorded anywhere.

## Portal design

Mounted at **`/admin/portal`** (no collision with existing routes). Reuses the existing admin
cookie (`app/admin/auth.verify_admin_cookie`) — same login, immediately works once wired.
Self-contained Jinja2 templates with a persistent sidebar; styling inlined in the base template
(no static-mount changes needed).

| Page | Route | What it does |
|---|---|---|
| Dashboard | `/admin/portal` | Action-first home: every pending queue as a card with live count + deep link; system health (jobs, outbox, failures); chat-at-a-glance (7-day volume, latency, cache hit-rate) |
| Moderation hub | `/admin/portal/moderation` | All review queues in one table — providers, events, claims, contributions, duplicates, upgrade requests, ad reservations, capture inbox — with counts and links to the existing screens |
| Users & access | `/admin/portal/users` | Search/filter users, detail view with claims, change role (end_user/merchant/admin), activate/deactivate — replaces SQL-only admin promotion |
| Chat insights | `/admin/portal/chat` | Daily volume, tier breakdown, cache hit-rate, top intents, latency, token usage + est. cost, feedback signals, recent unmatched queries (7/30/90-day windows) |
| Ops | `/admin/portal/ops` | Jobs monitor (queued/claimed/running/done/failed, requeue failed), Outbox monitor (pending/in_flight/delivered/failed, retry failed), capture inbox counts |
| Audit log | `/admin/portal/audit` | Trail of admin actions. Table created by a **draft** migration (not applied); page degrades gracefully until then; portal writes audit rows only when the table exists |

## Isolation guarantees (until "ready")

- Zero edits to existing files. `app/main.py`, `app/admin/*`, models, alembic — untouched.
- `app/admin_portal/` is imported by nothing; FastAPI never sees the router.
- `AdminAuditLog` uses its **own** declarative Base — it does not join the shared
  `app.db.models.Base` metadata, so alembic autogenerate won't pick it up by accident.
- Draft migration lives at `app/admin_portal/migrations_draft/` — outside `alembic/versions`,
  so `alembic upgrade head` (and Railway preDeploy) never runs it.
- `pytest.ini` restricts collection to `tests/`; the portal's smoke test
  (`app/admin_portal/smoke_test.py`) is opt-in by explicit path.

## Wiring (when ready — Casey's call, via PR)

1. `app/main.py`: `from app.admin_portal.router import portal_router` + `app.include_router(portal_router)`
2. Move `migrations_draft/0001_create_admin_audit_log.py` into `alembic/versions/`, set
   `down_revision` to current head, dry-run, then apply per prod-ops rules.
3. Optional: add a "Portal" link to `app/admin/nav_html.py`.

## Phased rollout suggestion

- **Phase 1 (wire now-able):** Dashboard + Moderation hub + Ops (read-mostly, low risk).
- **Phase 2:** Users & access + audit migration (write paths, wants the audit table first).
- **Phase 3:** Chat insights cost tuning (pricing constants), then retire/redirect the old
  scattered nav to the portal.

## Future candidates (not built)

- Per-admin accounts (move off the shared password; `User.role='admin'` + magic-link is already
  in place to support it), CSRF tokens on portal POST forms, entity editor for the unified
  Entity table, sponsor revenue reporting, Plausible embed on the dashboard.
