# Cursor Dispatch Prompt — Phase 4.4 (Phase 4 close-out: operator runbook + Railway-cron-service template + image-processing retry-wrapper integration + master plan SHIPPED header + STATE.md refresh + close-out tests)

> Short paste-into-Cursor prompt for Phase 4.4 dispatch — the **close-out sub-phase** of Phase 4 of the master build plan. **This is the SHIPPED-header gate for Phase 4 overall.** When 4.4 commits + pushes, Phase 4 transitions from 🟡 IN FLIGHT (the state added in session-23's `a75cfe8` docs commit + extended in 4.2's `997cdc3`) to ✅ SHIPPED on the master plan. Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI) becomes the next dispatchable major lane. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_4_background_jobs_scrape.md` (read end-to-end, especially §0 + §3 + §7 + §8 + §9 + §10 + §11 + §12). Phase 4.4 ships: new `docs/operations/railway_scheduled_jobs_runbook.md` (operator-facing) + new `docs/operations/scrape_logs_template.md` (per-run summary template) + anchored Edit on the image-processing call site to wrap in `with_retry` (from 4.1) + anchored Edit on master plan §4 Phase 4 to append SHIPPED 2026-05-XX header alongside the four-sub-phase incremental list + anchored Edit on STATE.md Production block + Recently shipped §1 + new test file `tests/test_phase4_close_out.py` (~5-10 tests). **No new layer clients, no new migration, no chat-surface changes, no Railway service stand-up** (operator action per the runbook; not gating Phase 4 SHIPPED).
>
> **Gating dependency:** Phase 4.3 of the master build plan COMPLETE on origin (commit `2f87211` substantive + any chore/docs follow-ups). Phase 4.3 ships the `app/contrib/osm_overpass_client.py` Layer-2 minimal client + `app/contrib/ingest_reconciler.py` cross-layer dedupe + `scripts/osm_overpass_pull.py` script + ~25-32 new tests across `tests/test_phase4_osm_client.py` + `tests/test_phase4_ingest_reconciler.py` + anchored Edit on `app/contrib/google_places_scraper.py` to call `reconcile_hit()` before each ORM write. **Phase 4.4 cannot dispatch until 4.3 closes out** — the master plan SHIPPED header in 4.4 requires the 4.3 ship-line to exist underneath it. Verify 4.3 close-out on origin before pasting this prompt (operator commits Cursor's 4.3 work, push to origin, then dispatch 4.4 in a fresh session).
>
> **Operator prereq for Phase 4.4** (deferred-to-operator, NOT blocking the §13 acceptance gate but should land before the close-out narrative claims it): stand up the first Railway scheduled-job service per the new runbook. Recommended: spin up `outbox_redrive` (5-minute cadence per design memo §6.2) as the smoke-test target — it's a small, self-contained, no-API-key job that exercises the runbook's full setup path. Alternative: spin up `places_discovery --category eat-drink` (6-hour cadence per the existing `parks-rec-scrapes.yml` cron precedent at `15 */6 * * *`) as a real-data scrape on the Layer-1 client. Either way, the Railway action is operator UI work + not a Cursor deliverable — Cursor flags it deferred in §13.
>
> **No operator decision-lock BEFORE paste.** All brief §9 deviation invitations for 4.4 (optional anchored edits on `scan_and_save_mentions` + `enrich_contribution`, `docs/operations/` directory creation if it doesn't yet exist, image-processing retry-wrapper integration deferred-or-shipped) are "flag in §13" style. Recommendations baked in below: (a) SHIP the optional anchored edits on `scan_and_save_mentions` + `enrich_contribution` (deferred from 4.1 close-out per brief §4.3 — clarity-only improvement; lands naturally alongside the image-processing wrapper); (b) SHIP the image-processing retry-wrapper integration (brief §7.3 deliverable); (c) defer the Railway-cron-service stand-up to post-commit operator action.
>
> **Author note:** this prompt was authored at session-23-extension close alongside the Phase 4.3 dispatch prompt artifact. The §0 baseline values reference the post-Phase-4.3 state — `git log --oneline -10` top SHA after 4.3 ships will be Cursor's 4.3 substantive ship + any chore/docs follow-ups (SHA-patch the `2f87211` slot at paste time per the session-19+20+21+22+23 SHA-patch-at-paste rhythm); alembic head likely stays at `0a1b2c3d4e5f` (Phase 4.3 deferred the `entities.sources` migration per brief §6.5 + the SHA-patched operator decision-lock in the 4.3 dispatch prompt — unless Cursor shipped the migration as a §13-flagged deviation, in which case the head is the new revision and 4.4 inherits it without further change; SHA-patch the actual head into the `0a1b2c3d4e5f` slot); pytest baseline after 4.3 will be **1749 + 25-32 net-new = ~1774-1781** (SHA-patch the actual count from Cursor's 4.3 §13 report into the `1784` slot).

---

```
Read outputs/cursor_brief_phase_4_background_jobs_scrape.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3 (sub-phase
boundaries), §7 (Phase 4.4 deliverable list -- the close-out sub-
phase), §8 (locked vs open), §9 (acceptable deviations), §10 (risk
register), §11 (what NOT to do), §12 (final report format).

Phase 4.3 of the master build plan COMPLETE on origin at
`2f87211` (the OSM Overpass client + cross-layer
reconciler sub-phase; ships app/contrib/osm_overpass_client.py
OsmOverpassClient + app/contrib/ingest_reconciler.py reconcile_hit
+ scripts/osm_overpass_pull.py + tests/test_phase4_osm_client.py
+ tests/test_phase4_ingest_reconciler.py + anchored Edit on
app/contrib/google_places_scraper.py to call reconcile_hit before
each ORM write). Run `git log --oneline -10` and report the top
SHAs. Pytest collect baseline going in is
**1784** tests (1749 from session-23-
extension + 4.3's net-new ~25-32). Alembic head is
**0a1b2c3d4e5f** (likely 0a1b2c3d4e5f -- 4.3 deferred
the entities.sources migration per its operator decision-lock;
if Cursor shipped that migration anyway as a §13-flagged deviation
the slot is the new revision).

Ship Phase 4.4 ONLY per §3 + §7 of the brief -- the close-out
sub-phase. **This is the SHIPPED-header gate for Phase 4 overall.**
When 4.4 commits + pushes, master plan §4 Phase 4 transitions from
🟡 IN FLIGHT (added in session-23's a75cfe8 docs commit; extended
in 4.2's 997cdc3 + 4.3's docs close-out) to ✅ SHIPPED. **No new
layer clients, no new migration, no chat-surface changes, no
Railway service stand-up** (operator action per the new runbook;
deferred-to-operator and flagged in §13).

NO OPERATOR DECISION-LOCK (per brief §9 -- all Phase 4.4 deviation
invitations are "flag in §13 if you deviate" style). Three
recommendations baked in:
- SHIP the optional anchored edits on the existing BackgroundTasks
  call sites (app/api/routes/chat.py:62 `scan_and_save_mentions` +
  app/contrib/enrichment.py:18 `enrich_contribution`) per brief §4.3
  -- they were deferred from Phase 4.1 close-out + this is the right
  time to land them alongside the image-processing wrapper.
- SHIP the image-processing retry-wrapper integration per brief §7.3
  -- wrap the existing Pillow processing call in `with_retry` from
  app.core.background. Locate via Grep (`Pillow|PIL|process_uploaded
  _photo|photo_processing`) before anchoring.
- DEFER the Railway-cron-service stand-up to post-commit operator
  action -- Cursor does NOT have Railway credentials; the runbook
  is the deliverable + operator stands up the first service per
  the runbook on their own time.

ORDER MATTERS WITHIN PHASE 4.4:
1. First: read the docs + source files in brief §0 step 6 + step 7
   PLUS the Phase 4.1-4.3 ship surface. Critical reads: brief §7
   end-to-end (the 7 sub-deliverable blocks); app/core/background.py
   (the with_retry helper from 4.1 -- consumer in step 4); 
   app/api/routes/chat.py:62 (scan_and_save_mentions BackgroundTasks
   call site -- anchored Edit target in step 4); 
   app/contrib/enrichment.py:18 (enrich_contribution call site -- 
   same); image-processing call site (Grep to locate -- 
   `app/photos/processor.py` is the canonical Phase 2B.1 surface 
   per master plan §4 Phase 2 Lane 2B; `process_uploaded_photo` is 
   the BackgroundTasks entry-point); `.github/workflows/parks-rec-
   scrapes.yml` (the existing GitHub-Actions cron precedent; informs
   the Railway-cron template's cadence + env-var shape); 
   docs/maintainability/background_job_infrastructure_decision.md
   §6.1 + §6.2 (the design-memo's runbook scaffolding); 
   docs/maintainability/layered_scrape_strategy.md §5 (per-layer
   cadences); docs/STATE.md current Production block (the anchor
   point for STATE.md refresh in step 7); 
   docs/maintainability/master_build_plan.md §4 Phase 4 (the 
   anchor point for the SHIPPED header in step 6).
2. Then: new `docs/operations/railway_scheduled_jobs_runbook.md`
   per brief §7.1. Operator-facing runbook. 
   - When to use section (Railway scheduled jobs for cron-like 
     surface; FastAPI BackgroundTasks for event-triggered already 
     wired in 4.1)
   - Pre-checks section (script operator-runnable end-to-end; env 
     vars listed in .env.example + Railway Variables; idempotency 
     verified)
   - Steps section (Railway dashboard -> create service -> source
     from GitHub repo -> set start command -> set cron schedule
     `15 */6 * * *` cadence matches parks-rec-scrapes precedent
     -> Variables -> Deploy -> verify first run + Logs -> verify
     DB writes via Postgres Query console)
   - Monitoring section (Sentry tag `background-jobs` captures 
     retry breadcrumbs from app/core/background.py::with_retry; 
     per-run markdown summary at docs/scrape_logs/<source>_<YYYY-
     MM-DD>.md; failure alert if 0 new rows OR > 50% errors -> 
     Sentry breadcrumb fires)
   - Cost section (Railway scheduled-job services bill at standard
     rate; per-category vs parameterized trade-off)
   - Rollback section (Cron schedule -> empty pauses; Suspend; 
     push fix to main + re-enable when verified)
   - Reference section (links to the design memo + strategy memo
     + app/core/background.py + parks-rec-scrapes.yml precedent)
3. Then: new `docs/operations/scrape_logs_template.md` per brief
   §7.2. Per-run summary template -- markdown shape for operator
   to copy to docs/scrape_logs/<source>_<YYYY-MM-DD>.md per scrape
   run. Sections: Run identification (source / run timestamp UTC /
   triggered by / script); Counts (queries / discovered / new / 
   updated / skipped / errors / sample errors first 3); Duration
   (run elapsed time); Notes (free-form operator).
4. Then: anchored Edit on the image-processing call site per brief
   §7.3. Locate via Grep -- `app/photos/processor.py::process_
   uploaded_photo` is the BackgroundTasks entry-point per Phase 
   2B.1 ship (master plan §4 Phase 2 Lane 2B). Wrap the existing
   Pillow processing in `with_retry` from app.core.background.
   Texture rule from brief §1: same Photo row outcome (status 
   transitions to live on success, flagged/decode_failed on
   persistent failure); the wrapper adds bounded retry + Sentry
   breadcrumb + structured log on retry/exhaustion.
   Also per brief §4.3 + §7.4 baked-in recommendation: anchored
   Edits on `app/api/routes/chat.py:62` (`scan_and_save_mentions`
   BackgroundTasks call) + `app/contrib/enrichment.py:18`
   (`enrich_contribution` BackgroundTasks call). Wrap both in
   `with_retry`. Same texture-rule preservation -- both consumers
   were already silently fault-tolerant; wrapping adds Sentry
   breadcrumbs + structured logging without changing the user-
   visible outcome.
5. Then: new test file tests/test_phase4_close_out.py per brief
   §7.7 (~5-10 tests):
     - `app/core/background.py::with_retry` is wired into the
       magic-link send path (grep verification on app/auth/routes.py
       OR check that the request_link route uses enqueue_outbox + 
       deliver_outbox_row from Phase 4.1)
     - `app/core/background.py::with_retry` is wired into the
       image-processing path (grep verification on app/photos/
       processor.py)
     - `app/core/background.py::with_retry` is wired into the
       scan_and_save_mentions path (grep verification on app/api/
       routes/chat.py)
     - `app/core/background.py::with_retry` is wired into the
       enrich_contribution path (grep verification on app/contrib/
       enrichment.py)
     - `_hourly_cleanup_loop` at `app/main.py:251` still exists +
       signature unchanged (regression: Phase 4.4 does NOT touch
       the existing loop)
     - `app/main.py:lifespan` still schedules `_hourly_cleanup_loop`
       via `asyncio.create_task`
     - `docs/operations/railway_scheduled_jobs_runbook.md` exists +
       is non-empty
     - `docs/operations/scrape_logs_template.md` exists + is non-empty
     - Import-chain regression: `from app.core.background import
       with_retry` + `from app.contrib.google_places_scraper import
       GooglePlacesClient` + `from app.contrib.osm_overpass_client
       import OsmOverpassClient` + `from app.contrib.ingest_reconciler
       import reconcile_hit` all succeed without gotcha #17 cycle
       (subprocess test mirroring the Phase 4.1 + 4.2 + 4.3 import-
       chain regression test shape)
6. Then: anchored Edit on docs/maintainability/master_build_plan.md
   §4 Phase 4 per brief §7.5. Append SHIPPED 2026-05-XX header
   (replace the 🟡 IN FLIGHT status added in session-23's a75cfe8
   docs commit). Pattern matches Phase 1 / Phase 2 / Phase 3 
   SHIPPED + DEPLOYED headers. Append the Phase 4.4 ship-line to
   the "Shipped (incremental)" subsection (Phase 4.1 + 4.2 + 4.3 
   already there from prior close-out commits). **Total Phase 4
   pytest delta + alembic head walk + ship-line narrative** at
   the end of the Shipped (incremental) list.
7. Then: anchored Edit on docs/STATE.md per brief §7.6. Production
   block refresh: HEAD SHA, Build phase narrative ("Phase 4 SHIPPED
   on origin (NOT yet deployed unless operator has redeployed); 
   Phase 4.1 + 4.2 + 4.3 + 4.4 close-out chain complete"), pytest
   count, alembic head (likely 0a1b2c3d4e5f unchanged from 4.1).
   Recently shipped §1 prepend: Session-N entry with Phase 4.4
   ship-line covering operator runbook + scrape-logs template +
   image-processing wrapper + scan_and_save_mentions + enrich_
   contribution wrappers + close-out tests + master plan SHIPPED
   header.
8. After all of the above: confirm full pytest stays green
   (1784 floor + 5-10 net-new in close-out
   tests), ruff clean. Manual smoke deferred-to-operator:
   - magic-link request still works end-to-end with Resend (Phase
     4.1 path unchanged)
   - photo upload retry-wrapper integration works (Phase 2B.1
     path with Phase 4.4 wrapper added)
   - `python -m scripts.places_discovery --category eat-drink 
     --dry-run` produces same log output as pre-4.2-refactor
     (Phase 4.2 + 4.3 ingest_reconciler hook integration)
   - `python -m scripts.osm_overpass_pull --tag leisure --value 
     dog_park --dry-run` returns parseable Overpass response
     (Phase 4.3 surface)
   - stand up first Railway scheduled-job service per the new 
     runbook (operator decides when; not gating Phase 4 SHIPPED)

POSTGRES COMPATIBILITY (carried forward from brief §11 + every
prior phase brief):
- NO migration in Phase 4.4 (close-out is application code +
  docs only).
- alembic head stays unchanged from 4.3 (likely 0a1b2c3d4e5f).

DEVIATION INVITATIONS (per brief §9 Phase 4.4):
- Optional anchored edits on `scan_and_save_mentions` + 
  `enrich_contribution` -- BAKED IN as ship-it recommendation 
  per brief §4.3 + §7.4. If you find these wrappers cause flaky
  behavior (e.g., retry storms on a malformed input), flag in §13.
- `docs/operations/` directory creation -- brief creates two new
  docs there. If the directory doesn't yet exist (`Glob 
  docs/operations/`), Cursor creates it. If a different naming 
  pattern is in use elsewhere in `docs/`, flag in §13. 
  Recommendation: `docs/operations/` is the right naming convention
  alongside `docs/maintainability/` for design-memo + strategy
  artifacts.
- Image-processing retry-wrapper integration -- BAKED IN as ship-
  it recommendation. If the image-processing path needs significant
  refactor to accept `with_retry` cleanly (e.g., the existing
  process_uploaded_photo signature doesn't fit), flag in §13 + 
  defer to a follow-up commit. The 4.4 close-out doesn't gate on
  this; SHIPPED header can land without the image-processing
  wrapper if the integration is messier than expected.
- `_hourly_cleanup_loop` modification -- DO NOT MODIFY per brief
  §11. The loop stays at app/main.py:251. Phase 4 explicitly
  documented it as the canonical reference, not a refactor target.
  If you find an unrelated reason to touch app/main.py:lifespan
  during this session, flag in §13.
- Sentry breadcrumb integration for the new wrapper call sites --
  expect each wrapper call to fire breadcrumbs per the Phase 4.1
  with_retry shape (category="background-jobs"). If the integration
  fires breadcrumbs at unexpected rates (e.g., every successful
  call), flag in §13.
- master plan SHIPPED header date -- use 2026-05-XX with XX = today
  (most likely 2026-05-13 if all of 4.1-4.4 shipped same day, OR
  2026-05-14+ if multi-day). Match the actual ship-date for the
  4.4 commit.

WHAT NOT TO DO (per brief §10 + §11):
- Don't stand up Railway scheduled-job services. Cursor doesn't 
  have Railway credentials; operator stands up services per the
  runbook on their own time. Cursor flags it as deferred-to-
  operator in §13.
- Don't ship Phase 5 deliverables. Phase 5 (Tier 1 data gathering)
  is the next dispatchable major lane after Phase 4 close-out.
  Phase 5 is operator-driven scrape-and-curate work, not 
  engineering deliverables.
- Don't modify `_hourly_cleanup_loop`. It's the canonical reference
  documented in app/core/background.py's module docstring; not a
  refactor target.
- Don't delete or refactor any of the Phase 4.1/4.2/4.3 modules in
  4.4 close-out. They're committed in earlier sub-phases; 4.4 only
  adds + documents.
- Don't add new Python dependencies. The image-processing wrapper
  uses `with_retry` from app/core/background.py which is already
  shipped in Phase 4.1.
- Don't change the user-visible outcome of any wrapped call site:
  - magic-link send: same email body / recipient / Resend API call
    (unchanged from Phase 4.1)
  - image processing: same Photo row transitions (status='live' on
    success, status='flagged' with processing_error on persistent
    failure; the wrapper adds retry semantics in between, not new
    states)
  - scan_and_save_mentions: same mention-row insertion semantics
    (wrapper adds breadcrumb + structured log on retry, no row
    behavior change)
  - enrich_contribution: same contribution-row enrichment 
    semantics (wrapper adds breadcrumb + structured log on retry,
    no row behavior change)
- Don't add admin-form surfaces in Phase 4. Outbox visibility,
  scrape log inspection, operator-review queue for reconciler 
  "ambiguous" -- all Phase 5 + V1.5 territory.
- Don't add module-import-time hooks anywhere except 
  app/db/__init__.py. Gotcha #17 cure carries forward.
- Don't dispatch Phase 5 in the same Cursor session. HALT at the
  §3 Phase 4.4 boundary. Phase 5 dispatches in a fresh session
  after Phase 4 SHIPPED.

HALT at the §3 Phase 4.4 boundary. After 4.4 ships + commits +
pushes, **Phase 4 is COMPLETE**. Master plan §4 Phase 4 gets the
SHIPPED header. STATE.md Production block + Recently shipped §1
capture the close-out narrative. Phase 5 (Tier 1 data gathering,
parallel with Phase 6 UI build) becomes the next dispatchable
major lane -- see the pre-positioned prereq checklist at 
`outputs/phase5_prereq_checklist.md` (if it exists; the session-23-
extension Phase 5 prereq audit sub-agent reported writing this
doc but the write did not propagate to Windows-authoritative disk
-- if the doc is missing, Cowork primary re-authors during 
between-sessions docs work OR at Phase 5 dispatch authoring time)
for the operator decisions to lock + external data-source 
verifications to complete before Phase 5 paste.

Same constraints as Phase 4.1 + Phase 4.2 + Phase 4.3 + Phase 2 +
Phase 3 sub-phases:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 4.4 only

Pre-dispatch checklist (verify before paste):
- Phase 4.3 SHIPPED on origin (`2f87211`)
- alembic head matches `0a1b2c3d4e5f` (likely 
  0a1b2c3d4e5f unchanged from 4.1; if 4.3 shipped the entities.
  sources migration as a §13-flagged deviation, the slot is the 
  new revision)
- Pytest baseline going in matches Phase 4.3 §13 report's final
  count (SHA-patch the 1784 slot)
- No operator decision-lock required for 4.4
- Three recommendations baked in: SHIP scan_and_save_mentions +
  enrich_contribution wrappers, SHIP image-processing wrapper,
  DEFER Railway-cron-service stand-up to operator
- session-23 + 4.2 + 4.3 close-out chain verified on origin per
  `git log --oneline -10` step at top of this prompt
```

---

## After Cursor returns with the §12 report

Same rhythm as Phase 4.1 + Phase 4.2 + Phase 4.3 + every prior sub-phase: paste back to the Cowork primary chat, primary reviews against §7.8 acceptance gates + brief §11 scope discipline, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new `docs/operations/railway_scheduled_jobs_runbook.md` (operator-facing runbook)
- 1 new `docs/operations/scrape_logs_template.md` (per-run summary template)
- 1 modified image-processing call site (likely `app/photos/processor.py::process_uploaded_photo` per Phase 2B.1 shape — Grep to locate)
- 1 modified `app/api/routes/chat.py:62` (`scan_and_save_mentions` wrapped in `with_retry`)
- 1 modified `app/contrib/enrichment.py:18` (`enrich_contribution` wrapped in `with_retry`)
- 1 modified `docs/maintainability/master_build_plan.md` §4 Phase 4 (SHIPPED header + Phase 4.4 ship-line under Shipped (incremental))
- 1 modified `docs/STATE.md` (Production block refresh + Recently shipped §1 prepend)
- 1 new test file `tests/test_phase4_close_out.py` (~5-10 tests)

Expected pytest delta: +5-10 net-new tests in `tests/test_phase4_close_out.py`. Pre-existing tests from Phase 4.1 + 4.2 + 4.3 must remain green. Pre-existing magic-link, photo upload, chat, contribution tests must remain green (the new wrappers preserve outcomes; only retry + breadcrumb semantics added).

Expected effort: 1-2 day brief estimate; one Cursor session realistically. Phase 4.4 is lighter than 4.1/4.2/4.3 because it's mostly docs + anchored Edits + smoke tests, not new architectural surfaces.

Expected pragmatic deviations:
1. Image-processing wrapper integration — flag if `process_uploaded_photo` signature doesn't fit `with_retry` cleanly; defer to follow-up commit acceptable
2. `scan_and_save_mentions` + `enrich_contribution` wrapper integration — flag if either causes flaky behavior (retry storms on malformed input)
3. `docs/operations/` directory creation — flag if a different naming pattern is in use
4. master plan SHIPPED header date — match actual 4.4 ship-date
5. Sentry breadcrumb fire rate — flag if wrappers fire breadcrumbs at unexpected rates (e.g., every successful call)

## After Phase 4.4 ships (Phase 4 close-out)

**Phase 4 is COMPLETE.** Master plan §4 Phase 4 has the SHIPPED header (replaces the 🟡 IN FLIGHT status). STATE.md Production block + Recently shipped §1 capture the close-out narrative. **Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI build) becomes the next dispatchable major lane.**

Operator post-4.4 actions (deferred-to-operator, not blocking SHIPPED):
1. Stand up the first Railway scheduled-job service per the new `docs/operations/railway_scheduled_jobs_runbook.md`. Recommended first target: `outbox_redrive` (5-minute cadence, self-contained, no-API-key smoke).
2. (Optional) Run the manual smoke list from §13 to validate the Phase 4 deploy: magic-link request, photo upload, places_discovery dry-run, osm_overpass_pull dry-run.
3. Plan Phase 5 dispatch — open `outputs/phase5_prereq_checklist.md` (if it exists; re-author if missing per session-23-extension lesson) and chip away at the 11 operator decisions + 10 external data-source verifications during the Phase 5 lead-up.

Phase 5 dispatch prompt to be authored at Phase 5 dispatch authoring time (not pre-positioned here — Phase 5 is operator-driven scrape-and-curate work spanning 4-8 weeks; the dispatch artifact for Phase 5 is more sub-phase-than-monolith and benefits from being authored fresh against the Phase 4 SHIPPED + DEPLOYED state).

## Phase 4 done. Next major lane: Phase 5.

After this Cursor session returns + the operator commits Phase 4.4 + pushes, the master plan ledger reads:
- Phase 1 SHIPPED + DEPLOYED (2026-05-14 / 2026-05-13)
- Phase 2 SHIPPED + DEPLOYED (2026-05-12 / 2026-05-13)
- Phase 3 SHIPPED + DEPLOYED (2026-05-12 / 2026-05-13)
- Phase 4 SHIPPED (2026-05-XX) — production redeploy pending operator action

That's three major phases LIVE + one SHIPPED-on-origin awaiting redeploy. Phase 5 (Tier 1 data gathering) becomes the active major lane. The Phase 4 background-jobs + layered-scrape infrastructure built across 4.1 → 4.4 is the runtime under Phase 5's operator-driven scrape-and-curate workflows. The session-23 + session-23-extension chain is the structural foundation Phase 5 builds on.
