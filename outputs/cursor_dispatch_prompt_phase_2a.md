# Cursor Dispatch Prompt — Phase 2A.1 (account-lite schema + ORM + Resend scaffold)

> Short paste-into-Cursor prompt for Phase 2A.1 dispatch — the first sub-phase of Lane 2A (account-lite v0.1) of Phase 2 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_2a_account_lite.md` (read it before §0 — especially §3 + §4 + §5 + §9 + §10 + §11 + §12). After 2A.3 ships, Lane 2A of Phase 2 is complete and Lane 2B (image storage + search) becomes the next dispatchable lane.
>
> **Operator gate:** do not paste this prompt to Cursor until Casey has confirmed the Resend operator-side prereq is complete — sender domain verified (or sandbox-only is acceptable for V1) + `RESEND_API_KEY` + `RESEND_FROM_ADDRESS` + `AUTH_MAGIC_LINK_BASE_URL` env vars present in Railway. See `outputs/operator_prereqs_phase_2.md` §1 for the 30-min setup walkthrough. For local dev, `AUTH_DEV_MODE=1` in `.env` skips the Resend call entirely.

---

```
Read outputs/cursor_brief_phase_2a_account_lite.md end-to-end.

Phase 1 of the master build plan is SHIPPED on origin per master plan §4 Phase 1
"Shipped (incremental)" list — 1A (ff9832d), 1B (d475b06), 1C (e0417c8), 1D
(3f3628e) all landed, plus the 5132162 production hotfix for Postgres boolean
defaults. Origin/main HEAD should top at 4a5ee246 ("docs(outputs): patch
session-17 boot prompt SHAs to current origin head") — run git log --oneline -5
and confirm. Pytest collect baseline going in is **1518** tests. Alembic head
is f8e9d0c1b2a3 (Phase 1D legacy entity_id NOT NULL flip).

Ship Phase 2A.1 ONLY per §3 + §5 of the brief — schema additive migration + new
ORM models (User, MagicLinkToken, Session, UserFavorite, Claim) + Resend module
scaffold (app/auth/__init__.py + app/auth/email_sender.py with the dev-mode
fallback). **Zero app-layer route changes. Zero behavior change for any viewer.**

ORDER MATTERS WITHIN PHASE 2A.1:
1. First: read all five docs listed in brief §0 step 6 + all the source files
   listed in §0 step 7. The brief's line offsets are accurate as of authoring
   (session-17 boot, 2026-05-14/15) but recent commits may have shifted them by
   a few lines — verify before anchoring edits.
2. Then: anchored Edit on app/db/models.py appending the five new model
   classes (brief §4.1 through §4.5; classes go at the bottom of the file
   after the existing Phase 1 Entity + extension classes + the
   _register_provider_slug_listeners function). DO NOT full-file Write — the
   models.py file is shared with Phase 1 work and a full-file overwrite is a
   dispatch_protocol Rule 1+6 violation. Verify the necessary imports
   (CheckConstraint, true/false from sqlalchemy.sql) are present at the top of
   the file; add if needed via anchored Edit.
3. Then: hand-write a new alembic migration via `alembic revision -m
   "account_lite_v01"` (NOT --autogenerate — autogen often mis-orders
   constraints and may emit Postgres-incompatible Boolean defaults). Chain off
   f8e9d0c1b2a3. Five op.create_table calls + indexes + CHECK constraints per
   §4. Generate a fresh revision id; do NOT reuse a placeholder.
4. Then: new app/auth/__init__.py + app/auth/email_sender.py per brief §5.1 +
   §5.2. The email_sender module has the dev-mode fallback (logs the magic-
   link URL when AUTH_DEV_MODE is truthy; mirrors RATE_LIMIT_DISABLED
   convention at app/core/rate_limit.py:17-19). No auth routes wired yet.
5. Then: new tests/test_account_lite_schema.py + tests/test_email_sender.py
   per brief §5.5 + §5.6. ~10-14 net-new tests.
6. After all of the above: confirm full pytest stays green, ruff clean, and
   that `python -m alembic upgrade head` against a fresh dev DB applies the
   new migration cleanly. Then ALSO confirm
   `python -m alembic downgrade -1 && python -m alembic upgrade head` cycles
   cleanly (the migration must be reversible per brief §4.6 + §13 step 9).

POSTGRES COMPATIBILITY (per brief §9, session-15 lesson at 5132162):
- The bash sandbox + tests run SQLite; production runs Postgres.
- Use sa.true() / sa.false() (NOT sa.text("1") / sa.text("0")) for Boolean
  server_default values. The Phase 1 Entity class at app/db/models.py:648 is
  the precedent (server_default=true()).
- Use sa.func.now() (NOT sa.text("CURRENT_TIMESTAMP")) for timestamp defaults
  if the migration needs server-side time. For most timestamp columns, default
  via the Python lambda `default=lambda: datetime.now(UTC)` at app-layer is
  already the convention — server_default isn't required.
- Verify any raw SQL inside op.execute() works on Postgres, not just SQLite.
- The Phase 1D migration f8e9d0c1b2a3_legacy_entity_id_not_null.py is the
  most recent precedent for a clean Postgres-portable additive migration —
  mirror that shape.

ENTITY FK NOTE (per brief §2 + §4):
The design memo at docs/maintainability/account_lite_v01_design.md is slightly
stale on this point — it specifies a polymorphic (entity_type, entity_id)
shape with FK to providers / places separately. The master plan §4 Phase 2
Lane 2A explicitly amended this to "user_favorites (now points to entities.id),
claims (now points to entities.id)" because Phase 1 unified everything into
the entities table with its own entity_type discriminator. So:
- UserFavorite.entity_id: String, ForeignKey("entities.id", ondelete="CASCADE")
- Claim.entity_id: String, ForeignKey("entities.id", ondelete="CASCADE")
- NO separate entity_type column on UserFavorite or Claim — entities row carries it.
- App-layer validation (in Phase 2A.3) checks entity.entity_type at insert
  time. Favoritable: commercial/place/event. Claimable: commercial/place.

DEVIATION INVITATION:
Per brief §10, you may register a before_flush Session listener if you find
that test fixtures create User rows directly without going through the
magic-link callback flow and you want a safety net for default-field fill
(role, created_at). This mirrors the Phase 1D pattern in
app/db/database.py::_register_orm_listeners + the older slug-listener
precedent at app/db/seed_helpers.py::register_provider_slug_hooks (session-13
commit d967568). Flag in §13 if you do this. Optional — only if it's a clean
fit.

HALT at the §3 Phase 2A.1 boundary. After 2A.1 ships + commits, halt for
operator re-dispatch in a fresh session for 2A.2 (auth flow + middleware +
login UI). Do NOT start 2A.2 in the same session.

Same constraints as the Phase 1 lane:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits — Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 2A.1 only

Operator note: AUTH_DEV_MODE=1 should be set in the local .env before running
the full pytest suite locally so test_email_sender.py paths don't try to call
Resend. tests/conftest.py may already set RATE_LIMIT_DISABLED=1; consider
setting AUTH_DEV_MODE=1 in the same fixture to keep auth tests hermetic.
```

---

## After Cursor returns with the §12 report

Same rhythm as Phase 1: paste back to the Cowork primary chat, primary reviews against §5.7 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 2 new files in `app/auth/` (`__init__.py`, `email_sender.py`)
- 1 modified `app/db/models.py` (5 new ORM classes appended at bottom; possible import addition at top)
- 1 new alembic migration (`alembic/versions/<rev>_account_lite_v01.py`; chains off `f8e9d0c1b2a3`)
- 2 new test files (`tests/test_account_lite_schema.py`, `tests/test_email_sender.py`)

Expected pytest delta: +10-14 net-new tests (the brief specifies ~10 schema-pin tests + ~4 email-sender tests; reality usually trends within this range for additive schema sub-phases).

Expected effort: 2-3 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations: (a) `before_flush` safety-net listener if test-fixture coverage benefits from it; (b) folding magic-link-token / session cleanup into `_hourly_cleanup_loop` may surface naturally during the migration test pass (deferrable to 2A.2 if cleaner there); (c) the model class `Session` may need rename to `AuthSession` if a real SQLAlchemy collision surfaces — Cursor should flag this explicitly rather than silently rename.

## After Phase 2A.1 ships

Update master plan §4 Phase 2 with a "Shipped (incremental)" list (same pattern as §4 Phase 1) and append the 2A.1 ship-line. Then re-dispatch for 2A.2 with a fresh dispatch prompt (`outputs/cursor_dispatch_prompt_phase_2a_2.md` — author after 2A.1 lands so the prompt can cite the actual SHA + pytest delta). Lane 2B (image storage + search) is parallelizable per dispatch_protocol Rule 3 once the operator has the R2 prereq locked — Casey can hold or dispatch in parallel.

## After Phase 2A.3 (full Lane 2A) ships

Phase 2 Lane 2A is COMPLETE. Update master plan §4 Phase 2 header to mark Lane 2A as SHIPPED with overall pytest delta + total commit chain. Standby for Lane 2B dispatch (separate brief authoring required — `outputs/cursor_brief_phase_2b_image_storage_search.md`, mirrors this brief's shape scoped to R2 + Pillow + Postgres FTS + pg_trgm).
