# Cursor Dispatch Prompt — Phase 4.1 (background-jobs scaffold: app/core/background.py + retry-wrapper + optional Outbox table)

> Short paste-into-Cursor prompt for Phase 4.1 dispatch — the background-jobs scaffold sub-phase of Phase 4 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_4_background_jobs_scrape.md` (read end-to-end, especially §0 + §3 + §4 + §8 + §9 + §10 + §11 + §12). Phase 4.1 is the plumbing sub-phase: new `app/core/background.py` module with `with_retry()` helper + Sentry breadcrumb integration + (operator-locked) Outbox(Base) table + magic-link send wrapping + ~15-25 new tests. **No layered-scrape work, no new in-process loops, no Railway-cron-service config, no chat-surface changes** — all of that is 4.2 / 4.3 / 4.4.
>
> **Gating dependency:** Phase 3 of the master build plan COMPLETE on origin (3.1 at `7925a14`; 3.2 at `5dbde39`; close-out at `294567b`) AND DEPLOYED to Railway production (`d5e9b71` deploy 2026-05-13; six-migration walk to `e1f2a3b4c5d6` clean). Phase 1D circular-import bug fix at `5faa37c` MUST be on origin/main + cron MUST be re-enabled per `18a4100`. The 4.1 prompt depends on `register_catalog_dual_write_hooks` being centralized at `app/db/__init__.py` (the session-22 fix) — Phase 4 scrape clients in 4.2/4.3 plug into this seam.
>
> **No operator prereq beyond the Phase 3 close-out + production deploy + circular-import fix.** Phase 4.1 has no Cloudflare / Resend / external-service prereq. Resend was wired in Phase 2A.2 (`714ca52`); 4.1 wraps the existing send in `with_retry()` without changing the email outcome.
>
> **Operator decision-lock BEFORE paste:** Outbox(Base) table in Phase 4.1 OR defer to Phase 4.5 / V1.5. **Recommendation: ship Outbox now** (magic-link is must-not-lose; deferring means accepting "magic-link emails may occasionally fail silently" through V1 user signups; Outbox is M-effort per design memo §10 = ~100 lines + 1 migration + tests). Alternative: ship 4.1 without Outbox; add later when traffic surfaces a failure. **SHA-patch the chosen answer below at the `<OUTBOX_DECISION>` marker before paste.**
>
> **Author note:** this prompt was authored at session-23 alongside the Phase 4 brief. The §0 baseline values reference the session-22 close-out state — `git log --oneline -10` top SHA is whichever session-22 close-out chore landed; alembic head is `e1f2a3b4c5d6`; pytest baseline is `1703`. SHA-patch the session-22 close-out tip into the `<SESSION_22_CLOSE_OUT_SHA>` slot at paste time per the session-19+20+21 SHA-patch-at-paste rhythm.

---

```
Read outputs/cursor_brief_phase_4_background_jobs_scrape.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3 (sub-phase
boundaries), §4 (Phase 4.1 deliverable list -- the background-jobs
scaffold sub-phase), §8 (locked vs open), §9 (acceptable deviations),
§10 (risk register), §11 (what NOT to do), §12 (final report format).

Phase 3 of the master build plan is COMPLETE on origin AND DEPLOYED
to Railway production at d5e9b71 (six-migration walk b2c3d4e5f6a7 ->
e1f2a3b4c5d6 clean on 2026-05-13). Phase 1D circular-import fix
landed at 5faa37c (session-22) -- this matters for Phase 4 because
the centralized register_catalog_dual_write_hooks() at
app/db/__init__.py:36-38 is the seam Phase 4 scrape clients plug
into in 4.2/4.3. Run `git log --oneline -10` and report the top
SHAs. Pytest collect baseline going in is **1703**
tests (1702 passed + 1 skipped + 30 subtests). Alembic head is
**e1f2a3b4c5d6** (Phase 3.2 data pass; the production-deployed tip).

Ship Phase 4.1 ONLY per §3 + §4 of the brief -- new
app/core/background.py module + with_retry helper + Sentry breadcrumb
integration + (conditional) Outbox(Base) table + magic-link send
wrapping + ~15-25 new tests. **No layered-scrape work, no new
in-process loops, no Railway-cron-service config, no chat-surface
changes** -- 4.2 + 4.3 + 4.4 close out the rest.

OPERATOR DECISION-LOCK (per brief §2 row "Outbox table in Phase 4
vs Phase 5"): SHIP OUTBOX NOW (locked at session-23 dispatch
authoring, 2026-05-13 -- magic-link is must-not-lose; deferring
means accepting silent V1 user-signup failures).

Phase 4.1 therefore adds a single alembic migration advancing head
by one (outbox table per brief §4.2 schema). Magic-link send call
site writes Outbox row in the same transaction as the request,
commits, then background_tasks.add_task(deliver_outbox_row,
outbox_row.id) per brief §4.2 "After (Phase 4.1 with Outbox)"
snippet. New scripts/outbox_redrive.py thin script polls Outbox
for state=pending older than 30s + calls deliver_outbox_row per
row + respects --max-rows.

ORDER MATTERS WITHIN PHASE 4.1:
1. First: read the docs + source files in brief §0 step 6 + step 7.
   Critical reads: app/main.py end-to-end (lifespan at :259,
   _hourly_cleanup_loop at :251 -- DO NOT touch the existing loop);
   app/db/__init__.py end-to-end (37 lines; the centralized Phase 1D
   hook registration site; gotcha #17 explainer in its docstring);
   app/contrib/rate_limiter.py end-to-end (the SourceLimiter shape
   that with_retry mirrors); existing BackgroundTasks consumers
   at app/api/routes/chat.py:62 + app/contrib/enrichment.py:18 (do
   NOT modify in 4.1 unless brief §4.3 invitation accepted with
   §13 flag); the Resend magic-link send call site (Grep
   `Resend|send_magic_link|magic_link_email` to locate exactly).
2. Then: new app/core/background.py per brief §4.1. with_retry
   (sync) + with_retry_async (async sibling) + Sentry breadcrumb
   integration. **CRITICAL: do NOT import from app/db/models at
   module top.** Lazy-import inside deliver_outbox_row if Outbox
   path is chosen. Prevents reintroducing the gotcha #17 cycle
   pattern.
3. Then (Outbox path only): new alembic migration
   <rev>_phase4_outbox.py chaining off e1f2a3b4c5d6. op.create_table
   for outbox per brief §4.2 schema. CHECK constraints on state +
   kind. Indexes on (state, created_at) + (kind).
4. Then (Outbox path only): append Outbox(Base) ORM class at the
   tail of app/db/models.py per the same append discipline as
   Phase 3.1 + 3.2. Do NOT add module-import-time hooks for Outbox
   in models.py -- if any before_flush / after_insert semantics are
   needed, registration goes in app/db/__init__.py (NOT models.py
   leaf module).
5. Then (Outbox path only): append deliver_outbox_row function to
   app/core/background.py per brief §4.2. State transitions
   pending -> in_flight -> delivered (success) OR pending ->
   in_flight -> pending + attempts += 1 (transient failure) OR
   pending -> failed at attempts >= 5 (exhaustion). Wraps the
   handler call in with_retry.
6. Then (Outbox path only): new scripts/outbox_redrive.py thin
   script. Polls Outbox for state=pending older than 30s; calls
   deliver_outbox_row per row; respects --max-rows.
7. Then: anchored Edit on magic-link send call site (located in
   step 1). Wrap in with_retry (defer path) OR write Outbox row
   first then background_tasks.add_task(deliver_outbox_row, ...)
   (ship-now path). Preserve same email body + recipient + Resend
   API call semantics; texture rule from brief §1.
8. Then: new tests per brief §4.4 in tests/test_phase4_background.py
   (~15-25 tests):
     - with_retry happy path / exhaustion / retry-then-success /
       backoff timing / fatal_on bypass
     - Sentry breadcrumb on retry + exhaustion
     - with_retry does NOT re-raise (returns None)
     - with_retry_async happy path / exhaustion / uses asyncio.sleep
     - (Outbox-conditional) Outbox model + migration cycle +
       CHECK constraints + defaults + deliver_outbox_row state
       transitions + idempotency + redrive script behavior
     - Magic-link integration test with mocked Resend (retry-then-
       success path; bounded retry behavior)
     - **Import-chain test**: `from app.core.background import
       with_retry` succeeds without importing app.db.models at
       module top (subprocess import test mirroring
       tests/test_phase1d_dual_write.py::test_scraper_entry_point_
       import_chain_does_not_cycle shape)
9. After all of the above: confirm full pytest stays green, ruff
   clean, that (Outbox path only) `python -m alembic upgrade head`
   against a fresh dev DB reaches the new revision cleanly +
   alembic head advances by one + `python -m alembic downgrade -1
   && python -m alembic upgrade head` cycles cleanly. No required
   manual smoke from Cursor in 4.1 (magic-link end-to-end smoke
   deferred-to-operator; flag in §13).

POSTGRES COMPATIBILITY (carried forward from brief §11 + every
prior phase brief):
- The bash sandbox + tests run SQLite; production runs Postgres.
- Phase 2A.1 (92ce4899dc08_account_lite_v01.py) + Phase 2B.2
  (c8d9e0f1a2b3_entities_fts_pgtrgm.py) + Phase 2B.1 photos +
  Phase 3.1 + Phase 3.2 are recent portable-migration precedents.
  Mirror their shape.
- Use sa.true() / sa.false() (NOT sa.text("1") / sa.text("0")) for
  Boolean server_default values.
- Use sa.func.now() (NOT sa.text("CURRENT_TIMESTAMP")) for default
  timestamps.
- For JSON columns: sa.JSON() is portable; both dialects support it.
- For enum-like columns: VARCHAR + CHECK constraint is portable.
  Native ENUM type is NOT (Postgres-only). Mirror Phase 2A.1's
  users.role shape + Phase 3.1's heat_exposure shape.
- No raw SQL inside op.execute() unless verified portable across
  both dialects.

DEVIATION INVITATIONS (per brief §9 Phase 4.1):
- with_retry Sentry breadcrumb shape -- brief specifies
  category="background-jobs" + level="warning" per retry + level=
  "error" on exhaustion. If existing app/contrib/rate_limiter.py
  Sentry shape differs (likely different category name), flag in
  §13. Consistency with existing Sentry usage more important than
  the exact string.
- with_retry_async vs sync-only -- brief ships both. If skipping
  the async variant simplifies the module, flag in §13.
  (Recommendation: ship both for forward-compat; async variant is
  ~30 lines at no real cost.)
- Anchored edits on existing BackgroundTasks call sites
  (scan_and_save_mentions + enrich_contribution) -- recommend
  defer-to-4.4. If Cursor takes 4.1 with bandwidth to spare,
  wrapping is acceptable; flag rationale in §13.
- Outbox redrive idle threshold (30s) -- brief specifies 30s per
  design memo §6.2. Tighter or looser threshold acceptable with
  rationale.
- Outbox.state enum values (4 states: pending / in_flight /
  delivered / failed). 5th state (e.g., "paused") acceptable for
  operator-paused redrive but recommendation is 4 states for V1.
- Outbox.payload TypedDict vs free-form dict -- brief uses
  free-form. Typed per-kind aliases acceptable upgrade if Cursor
  finds it cleaner.

WHAT NOT TO DO (per brief §10 + §11):
- Don't add new in-process asyncio loops to app/main.py:lifespan
  in 4.1. _hourly_cleanup_loop stays put; cache warming + alerts
  dispatcher are Phase 5/8 -- they pick up the documented pattern
  when they ship.
- Don't touch _hourly_cleanup_loop at app/main.py:251. It's the
  canonical reference; not a refactor target.
- Don't add new Python dependencies. sentry-sdk already present;
  httpx already present.
- Don't add Celery / Redis / Dramatiq / RQ. Option B is the
  migration path per design memo §7; not in scope.
- Don't register before_flush / module-import-time hooks anywhere
  except app/db/__init__.py. Gotcha #17 is the canonical lesson.
- Don't import from app/db/models.py at module top in
  app/core/background.py. Lazy-import inside deliver_outbox_row
  if needed. Prevents reintroducing the gotcha #17 cycle pattern.
- Don't modify chat-route response shape. Phase 4 ships zero
  user-visible surface changes.
- Don't modify magic-link email body / recipient address / Resend
  API call semantics. Phase 4.1 wraps the existing send in retries;
  outcome unchanged.
- Don't add admin-form surfaces for Outbox visibility. V1.5+.
- Don't add layered-scrape work. That's 4.2 + 4.3.
- Don't propose Option B in 4.1. Not in scope.
- Don't add ENUM types (Postgres-only). VARCHAR + CHECK is portable.
- Don't use sa.text("1") / sa.text("0") for Boolean defaults.
  Phase 1A's 5132162 hotfix is the canonical lesson.
- Don't modify existing tables beyond outbox (IF Outbox path
  chosen). Touching ENTITY columns, providers, events, programs,
  photos, districts, alert_subscriptions, etc. requires a separate
  brief.
- Don't dispatch Phase 4.2 / 4.3 / 4.4 in the same Cursor session.
  HALT at the §3 Phase 4.1 boundary.

HALT at the §3 Phase 4.1 boundary. After 4.1 ships + commits, halt
for operator re-dispatch in a fresh session for Phase 4.2 (layered-
scrape client interface + Google Places refactor). Phase 4.2
dispatches only after Phase 4.1 ships + commits + pushes to origin.

Same constraints as Phase 2 + Phase 3 sub-phases:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 4.1 only

Pre-dispatch checklist (verify before paste):
- Phase 3 SHIPPED + DEPLOYED to Railway production at d5e9b71
- Session-22 circular-import fix at 5faa37c on origin/main
- parks-rec-scrapes cron re-enabled per 18a4100
- e1f2a3b4c5d6 is the current single alembic head (production AND origin)
- Pytest baseline going in is 1703 (or matches reality `python -m
  alembic heads` + `pytest --collect-only` returns)
- Outbox decision locked SHIP-OUTBOX-NOW at session-23 dispatch
  authoring (2026-05-13)
- Session-22 close-out SHAs verified on origin per `git log
  --oneline -10` step at top of this prompt
```

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phases: paste back to the Cowork primary chat, primary reviews against §4.5 acceptance gates + brief §11 scope discipline, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new `app/core/background.py` module
- (Outbox path only) 1 new alembic migration `alembic/versions/<rev>_phase4_outbox.py`
- (Outbox path only) 1 modified `app/db/models.py` (Outbox class appended at file tail)
- (Outbox path only) 1 new `scripts/outbox_redrive.py` script
- 1 modified magic-link send route file (located via Grep at dispatch time)
- 1 new test file `tests/test_phase4_background.py` (~15-25 tests)

Expected pytest delta: +15-25 net-new tests. Pre-existing chat-route + Provider-profile + search + photos + magic-link + Phase 3 tests must all stay green.

Expected effort: 2-3 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations:
1. Sentry breadcrumb category string — flag if differs from existing app/contrib/rate_limiter.py shape
2. `with_retry_async` ship vs skip — flag rationale either way
3. Anchored edits on `scan_and_save_mentions` + `enrich_contribution` in 4.1 vs defer to 4.4 — flag if taken
4. Outbox redrive idle threshold — flag if not 30s
5. `Outbox.state` enum values — flag if 5th state added
6. `Outbox.payload` TypedDict aliases — flag if added

## After Phase 4.1 ships

Update master plan §4 Phase 4 — add a "Shipped (incremental)" subsection (same pattern as Phase 1 / Phase 2 / Phase 3) with the 4.1 ship-line covering `app/core/background.py` + (Outbox path only) the migration + magic-link wrapping + pytest delta + alembic head advancement (if Outbox path). Update STATE.md Production block + "Recently shipped" §1 with the 4.1 close-out narrative.

Phase 4.2 dispatch prompt to be authored after 4.1 ships — chains off whatever 4.1's alembic revision is (or stays at `e1f2a3b4c5d6` if Defer-Outbox path was chosen). 4.2 dispatch is gated on 4.1 close-out.

## After Phase 4.4 ships (Phase 4 close-out)

Phase 4 is COMPLETE. Master plan §4 Phase 4 gets a SHIPPED header. STATE.md Production block + "Recently shipped" §1 capture the close-out narrative. Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI build) becomes the next dispatchable lane.
