# Admin Portal

Unified admin portal at `/admin/portal`: dashboard, moderation hub, users & access,
chat insights, ops (jobs/outbox), audit log. Full plan: `docs/ADMIN_PORTAL_PLAN.md`.

**Current state: wired** (Track E, 2026-06-10):

- `app/main.py` registers the router (imported as `admin_portal_router` — the
  merchant portal at `app/portal` owns the bare `portal_router` name there).
- The `admin_audit_log` table ships via alembic `e9b5d7f3a1c6` (promoted from
  the pre-wiring `migrations_draft/`, removed at promotion). The portal degrades
  gracefully if the table is absent: the audit page shows a setup notice and
  audit writes are skipped.
- The classic admin nav (`app/admin/nav_html.py`) links to the portal.
- Smoke tests live in `tests/test_admin_portal_smoke.py` (CI-collected).

Auth: reuses the existing admin cookie (`app/admin/auth.py`) — log in once at
`/admin/login`, the portal just works. Unauthenticated portal requests 303 there.

## Layout

- `router.py` — aggregator + dashboard + moderation hub + audit page (prefix `/admin/portal`)
- `users.py` — user search/detail, role change, de/reactivate (audited writes)
- `chat_insights.py` — ChatLog rollups: volume, tiers, cache hit-rate, tokens/cost,
  intents, unmatched queries, slowest turns (`?days=7|30|90`)
- `ops.py` — jobs + outbox monitors with requeue/retry (audited writes)
- `queues.py` — shared pending-count cards (deep-link to existing admin screens)
- `guard.py` — admin-cookie gate; `shared.py` — templates env + helpers
- `audit_models.py` — `AdminAuditLog` on its own Base (kept off shared metadata so
  alembic autogenerate never picks it up by accident)
- `templates/` — self-contained Jinja2 (inline CSS; no static-mount changes)

## Cost estimate note

`chat_insights.INPUT_COST_PER_M` / `OUTPUT_COST_PER_M` are display-only pricing
constants, set for the prod Tier-3 model (gpt-4.1-mini). Adjust when the model
or its pricing changes.
