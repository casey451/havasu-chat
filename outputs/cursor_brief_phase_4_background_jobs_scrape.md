# Cursor Brief — Phase 4: background-jobs scaffold + layered scrape infrastructure

> **Operator note:** paste this brief to a fresh Cursor chat. **This is Phase 4 of the master build plan** (`docs/maintainability/master_build_plan.md` §4 Phase 4). Phase 3 is COMPLETE on origin (`5dbde39` 3.2 + `7925a14` 3.1; Phase 3 ship close-out at `294567b`) and DEPLOYED to Railway production at `d5e9b71` on 2026-05-13 (six-migration walk `b2c3d4e5f6a7 → e1f2a3b4c5d6` clean). Phase 4 is the **plumbing** lane: it scaffolds the background-jobs infrastructure (Option A from `docs/maintainability/background_job_infrastructure_decision.md` — Railway scheduled jobs + FastAPI `BackgroundTasks` + optional Outbox) and lays the layered-scrape framework (per `docs/maintainability/layered_scrape_strategy.md` — shared client interface + Layer 1 Google Places refactor + reference Layer 2 OSM client + cross-layer reconciler). **Phase 4 does NOT populate the directory** — Phase 5 fills the framework with real scrapers per category. The seam between Phase 4 framework and Phase 5 fill-up is the locked Layer-1/2/3/4 abstraction.
>
> The brief is structured around **four explicit sub-phase boundaries** — **Phase 4.1 background-jobs scaffold** (the `app/core/background.py` retry-wrapper module + Outbox table + `_hourly_cleanup_loop` reference doc + BackgroundTasks retry integration), **Phase 4.2 layered-scrape client interface + Google Places refactor** (extract shared scrape lib from `places_discovery.py` + `places_enrichment.py`; define `BaseIngestClient` abstract interface; map clients to Phase 1D dual-write helpers; types mapping table), **Phase 4.3 second client + cross-layer reconciler** (minimal OSM Overpass client conforming to the interface + `app/contrib/ingest_reconciler.py` for cross-source dedupe — the parallel-eligibility proof per master plan §4 Phase 4 effort estimate), and **Phase 4.4 Phase 4 close-out** (scheduled-jobs operator runbook + Railway cron-service scaffolding template + master plan ship-line + STATE.md refresh). Each is independently committable + pytest-green. **You are expected to HALT and report after each sub-phase** so the operator can commit before you proceed. Each sub-phase is sized to one Cursor session.
>
> Authored by Cowork primary at session-23, 2026-05-13, after the Phase 3 production deploy + Phase 1D circular-import bug fix landed. Source documents absorbed:
> - `docs/maintainability/master_build_plan.md` §4 Phase 4 — the deliverables checklist (background jobs + layered scrape sources + reconciler + operator monitoring)
> - `docs/maintainability/background_job_infrastructure_decision.md` end-to-end — Option A locked recommendation, scheduled-jobs inventory §2, event-triggered-jobs inventory §2.2, the `BackgroundTasks` + retry-wrapper + Outbox pattern §6, the migration path §7 to Option B
> - `docs/maintainability/layered_scrape_strategy.md` end-to-end — the 5-layer pattern, per-layer client modules, reconciliation logic §4, sequencing §5 for initial population + ongoing
> - `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules)
> - `docs/maintainability/dispatch_channels.md` (17 gotchas; especially #7 bash mount staleness, #15 bash mount index.lock corruption, #16 PowerShell embedded-double-quote, #17 module-import-time hook registration cycle + companion confirm-via-log/repro lesson)
> - `outputs/cursor_brief_phase_3_v11_schema_pass.md` — brief-shape precedent (structure + Postgres portability checklist + deviation guardrails + risk register + final report format)
> - `outputs/cursor_brief_phase_2b_lane.md` + `outputs/cursor_brief_phase_2a_account_lite.md` — additional brief-shape precedents
> - `outputs/cursor_dispatch_prompt_phase_3_1.md` — dispatch-prompt shape precedent (for the 4.1 dispatch prompt that accompanies this brief)
> - `app/main.py:251 _hourly_cleanup_loop` + `app/main.py:259 lifespan` — the canonical in-process asyncio loop pattern Phase 4.1 promotes to documented reference
> - `app/contrib/rate_limiter.py` — the existing `SourceLimiter` + `GOOGLE_PLACES_LIMITER` used by Layer-1 scrapers; Phase 4 reuses it directly, no rewrites
> - `app/db/__init__.py` + `app/db/entity_dual_write.py` — the Phase 1D dual-write hook + `register_catalog_dual_write_hooks()` + `create_provider_and_entity` / `create_event_and_entity` / `create_program_and_entity` helpers that Phase 4 scrape clients write through, NOT around
> - `scripts/places_discovery.py` + `scripts/places_enrichment.py` — the existing operator-runnable Layer-1 scrapers; Phase 4.2 extracts their shared logic into a library module without behavior change
> - `.github/workflows/parks-rec-scrapes.yml` — the existing GitHub-Actions cron precedent for the parks-rec scraper (cron `15 */6 * * *` + workflow_dispatch + Postgres write via `DATABASE_URL` secret); informs Phase 4.4 Railway-cron-service template
>
> **No operator prereq for Phase 4.1.** Phase 4.1 is the background-jobs scaffold — pure application code. No new Railway services, no new env vars, no Resend changes (Resend was wired in Phase 2A.2). Phase 4.2/4.3 also no prereq (refactor + reconciler). **Phase 4.4 close-out has an operator action:** stand up the first Railway scheduled-job service when the framework lands. That's a Railway-UI action, not engineering work, and lives in the §13 follow-up checklist.
>
> **Texture rule reminder (carried forward from every prior brief):** every existing chat-route response, every Provider profile render, every Tier 2 catalog lookup, every search-bar query, every Photo upload must produce **equivalent output** after Phase 4 as before. Phase 4 is plumbing; no user-visible surface changes. The `BackgroundTasks` integration for Resend (Phase 2A.2 already wired the send; Phase 4.1 adds the retry wrapper around it) must not change the magic-link email outcome — the same email body, the same recipient address, the same delivery semantics, just with bounded retries on transient failure. The Google Places scrape refactor in Phase 4.2 must be a pure refactor — same DB rows produced, same rate-limit semantics, same idempotency posture. Cursor's §13 report must call out any change that breaks the equivalent-output rule.

---

## §0 Baseline confirmation (do this FIRST and report before touching code)

Before any edits, confirm and report:

1. **`git log --oneline -10`** — origin/main should top at the Phase 3 ship + production deploy + Phase 1D circular-import fix chain. Floor SHA chain (pre-Phase-4 dispatch): `7925a14` (3.1 schema additions, session-20) → `81a83a1` (3.1 docs) → `38abbcb` (session-19 SHA-patch chore) → `c4fdc69` (session-20 close-out SHA-patch) → `540efbd` (Phase 3.2 district UX reality check) → `3bf9f66` (gotcha #16 docs) → `5dbde39` (Phase 3.2 substantive ship) → `bd9b00f` (3.2 dispatch prompt chore) → `294567b` (Phase 3 SHIPPED docs) → `43b5f8f` (session-21 close-out) → `59521dd` (cron pause) → `d5e9b71` (session-21 SHA-patch chore; PRODUCTION DEPLOY TIP) → `18a4100` (cron re-enable) → `5faa37c` (Phase 1D circular-import fix) → `d506b5a` (session-22 docs) → `81b6f55` (session-22 close-out) → SHA-patch-at-session-22-close. Treat the chain as soft; material divergence (top SHA not derivable from this chain, or Phase 3 not SHIPPED + DEPLOYED) is the halt trigger. **Report actual top-10 SHAs.**
2. **`git status`** — should be clean.
3. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — collected count should be **≥1703** tests (session-22 Windows-side baseline; +1 net-new from `tests/test_phase1d_dual_write.py::test_scraper_entry_point_import_chain_does_not_cycle`). The 1 skipped is the Postgres-only FTS execution path from `tests/test_search_fts.py` under `skip-unless-postgres`. Treat 1703 as soft floor; report actual.
4. **`python -m alembic heads`** — single head. Floor at authoring: `e1f2a3b4c5d6` (Phase 3.2 data pass; the production-deployed tip). Phase 4.1 is pure application code; **no new alembic migration in 4.1**. Phase 4.2 + 4.3 are also application-code-only — no migrations. Phase 4.4 close-out **MAY** add a single migration ONLY if 4.1's optional Outbox(Base) table is included in this Phase (see §2 row "Outbox table in Phase 4 vs Phase 5"); otherwise alembic head stays at `e1f2a3b4c5d6` through all of Phase 4.
5. **`python -m alembic current`** — should match head when local SQLite is clean. SQLite drift gotchas per `docs/maintainability/dispatch_channels.md` gotcha #10 — chain-walk down_revision before alarming. If local dev DB has drift, operator can drop + recreate Windows-side; Phase 4 tests don't depend on local DB state beyond fresh-SQLite migration cycles.
6. **Read these docs end-to-end before writing any code:**
   - `docs/maintainability/master_build_plan.md` §4 Phase 4 (the deliverables checklist + L (10-15 days dispatch) estimate)
   - `docs/maintainability/background_job_infrastructure_decision.md` end-to-end — Option A locked; §2 job-type inventory; §6 implementation pattern; §7 migration path to Option B; §8 Resend integration; §9 open questions (Q4 Railway cron pricing was operator-confirmed pre-session-23; not a blocker)
   - `docs/maintainability/layered_scrape_strategy.md` end-to-end — 5 layers; per-layer client modules; §4 reconciliation logic; §5 sequencing; §6 per-category coverage estimates
   - `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules — anchored Edit on shared files; no `git add` until explicit report; sequential lanes when files overlap)
   - `docs/maintainability/dispatch_channels.md` (17 gotchas as of session-22; especially #4 bash mount staleness + #7 Linux mount serves stale view of edits + #10 alembic mergepoint diagnostic + #14 reflog forensics + #15 bash mount index.lock corruption + #16 PowerShell embedded double-quote + **#17 module-import-time hook registration cycle** — this is the most-recent + most-relevant for Phase 4 because Phase 4 adds new modules under `app/` that may need cross-module hook registration; the cure is to put any such registration in the package `__init__.py`, not a leaf module)
7. **Read these source files** so you have current line offsets for the anchored edits in §4 + §5 + §6 + §7:
   - `app/main.py` end-to-end (~700+ lines; lifespan at `:259`, `_hourly_cleanup_loop` at `:251`, `run_expired_review_cleanup` at `:232`, `run_stuck_photo_sweep` referenced at `:255`; you'll add new background-loop registrations alongside `_hourly_cleanup_loop` in the lifespan task list if Phase 4.1 ships any new in-process loops — recommendation per §4 below is **NO new in-process loops in 4.1**; the goal is to formalize the existing one as a documented pattern in `app/core/background.py`, not to add more)
   - `app/core/__init__.py` — empty or near-empty; you'll add `app/core/background.py` as a sibling module in 4.1
   - `app/contrib/rate_limiter.py` end-to-end (~200 lines; `class SourceLimiter` at `:39`, `GOOGLE_PLACES_LIMITER: Final` at `:158`; you'll reuse this directly in Phase 4.2 — no rewrites; the `SourceLimiter` interface is stable across Option A → Option B per its own docstring)
   - `app/contrib/places_client.py` — the Google Places HTTP client; you'll consume this from the refactored library module in Phase 4.2, no rewrites
   - `scripts/places_discovery.py` end-to-end (~100-200 lines; module docstring at `:10-13` describes operator-runnable shape; the discovery loop + pagination + dedupe-on-google-place-id logic is the extraction target for Phase 4.2)
   - `scripts/places_enrichment.py` end-to-end (~100-200 lines; module docstring at `:13-15`; the resume-safe `load_processed_ids` pattern at `:89-100` per the design memo — preserve this exact shape in the refactored library)
   - `app/contrib/__init__.py` — package init (likely empty or minimal); for Phase 4.2, if you add cross-module hook registration to `app/contrib/`, it goes in the package `__init__.py` per gotcha #17 (the Phase 1D lesson). **For Phase 4.2 specifically, no cross-module hook registration is required** — clients write via the existing Phase 1D `register_catalog_dual_write_hooks()` already centralized in `app/db/__init__.py:36-38`; new Provider/Event/Program ORM rows from Layer-1/2 clients flow through the same `before_flush` hook automatically.
   - `app/db/__init__.py` end-to-end (37 lines; **this is the centralized Phase 1D hook registration site** — read the full docstring, it explains gotcha #17 in detail; if Phase 4 adds any new ORM models that need `before_flush` hooks, the registration goes here, NOT in a leaf module)
   - `app/db/entity_dual_write.py` end-to-end (~500 lines; `create_provider_and_entity` at ~`:50-100`, `create_event_and_entity` at ~`:150-200`, `create_program_and_entity` at ~`:250-300`, `register_catalog_dual_write_hooks` at `:401-423`, `sync_provider_entity_from_legacy` at `:426+`; **scrape clients in Phase 4.2/4.3 write via the helpers OR via the existing `before_flush` hook on raw ORM `session.add(Provider(...))` calls — either path lands an Entity row + extensions; do NOT bypass either**)
   - `app/api/routes/chat.py:62` + `app/contrib/enrichment.py:18` — existing `BackgroundTasks` consumers (`scan_and_save_mentions` + `enrich_contribution`); Phase 4.1 adds the retry-wrapper helper but does NOT modify these call sites in 4.1 unless brief §4.4 below explicitly invites — they already prove the pattern; the new helper is for new consumers (Resend send already wired in Phase 2A.2, image processing if/when externalized)
   - `app/auth/*.py` — the magic-link send path from Phase 2A.2 (`5fea2ce` lane); Resend integration is already in place. **Phase 4.1 wraps the existing Resend send in the retry helper without changing the email outcome.** Locate the exact call site via Grep (`Resend|send_magic_link|magic_link_email`) before anchoring edits.
   - `app/photos/*.py` — the photo upload pipeline from Phase 2B.1 (`1c57c73`); BackgroundTasks integration for image processing is brief §4.5 scope but **Phase 4.1 ships the wrapper ONLY** — image-processing retry-wrapper integration lands as a tiny anchored edit in 4.1 close-out OR is deferred to Phase 4.4 close-out per Cursor's call (flag in §13 either way)
   - `tests/conftest.py` — fixtures for new test files (`tests/test_phase4_background.py` in 4.1; `tests/test_phase4_ingest_client_interface.py` in 4.2; `tests/test_phase4_osm_client.py` + `tests/test_phase4_ingest_reconciler.py` in 4.3)
   - `requirements.txt` — Phase 4 adds **NO new Python dependencies** in 4.1/4.2/4.3 per Option A locked decision; if Phase 4.3's OSM client needs an HTTP client beyond what's already there, **first check** if `httpx` (already present per `app/contrib/places_client.py`) suffices; if so, no new deps. If a real new dep is needed (e.g., `overpy` for Overpass QL convenience), flag in §13 deviation list — do NOT add silently.
8. Report all baseline values + confirm reads complete. Only then proceed to §1.

If any baseline value mismatches, any file has materially moved from these descriptions, the Phase 3 production deploy hasn't held, or the Phase 1D circular-import fix hasn't been verified green via the workflow_dispatch run from session-22, **HALT and report** before proceeding.

---

## §1 Why this lane exists

Phase 1 unified the catalog under `entities` with a discriminator column. Phase 2 gave the directory authentication (Lane 2A) + photo storage + search (Lane 2B). Phase 3 lit up the operator-curated fields (heat_exposure, crowd_notes, boat_access, seasonal_hours, district_id, featured), the categories taxonomy rewrite (12 slugs in Tier 1/2/3 order), and the 10-district seed (as backend tag per session-20 reality-check; paragraph landing pages deferred to V1.5). **Phase 4 is the data-ingestion-pipeline plumbing**: it builds the framework that Phase 5 fills with real scrapers per category, and it builds the background-jobs infrastructure that the magic-link send + image processing + (eventually) alert dispatcher + cache warming all depend on.

The audit memo at `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.7 flagged "background-job infrastructure" as Gap #3. The design memo at `docs/maintainability/background_job_infrastructure_decision.md` locked Option A — Railway scheduled jobs (cron-like) + FastAPI `BackgroundTasks` (event-triggered) + optional Outbox (must-not-lose) — over Option B (Celery + Redis) and Option C (in-app asyncio only). The strategy memo at `docs/maintainability/layered_scrape_strategy.md` locked the five-layer scrape pattern (Google Places + OpenStreetMap + city/state open data + specialized regulatory APIs + manual recovery) with the per-layer client interface + cross-layer reconciler shape.

Repo-wide grep confirms what's missing:

- **No `app/core/background.py` module.** The `_hourly_cleanup_loop` at `app/main.py:251` is the ONE durable background pattern in the codebase. The design memo recommends formalizing it as the documented reference (alongside a retry-wrapper helper for `BackgroundTasks` consumers). Without the module, every new `BackgroundTasks` consumer reinvents retry/backoff/Sentry-breadcrumb wiring inline.
- **No retry wrapper for `BackgroundTasks` consumers.** The two existing consumers (`scan_and_save_mentions` at `app/api/routes/chat.py:62` + `enrich_contribution` at `app/contrib/enrichment.py:18`) silently swallow exceptions. Adding the Phase 2A.2 Resend magic-link send + the eventual image-processing pipeline on top of bare `BackgroundTasks` means a transient Resend 429 silently drops a user signup. **Mitigation:** bounded retry + Sentry breadcrumb on exhaustion via the new `app/core/background.py::with_retry()` helper.
- **No Outbox(Base) table for must-not-lose jobs.** Magic-link send is the canonical must-not-lose job — a silently-dropped magic-link email costs a user signup. The design memo §6.2 specifies an Outbox table paired with a redrive cron service for must-not-lose semantics. **Operator decision:** ship the Outbox table in Phase 4.1 (recommended) OR defer to Phase 4.5 / V1.5 once magic-link traffic actually surfaces failures (alternative). Flag in §2 row "Outbox table in Phase 4 vs Phase 5".
- **No layered-scrape client interface.** The existing Layer-1 scrapers (`scripts/places_discovery.py` + `scripts/places_enrichment.py`) embed the scrape loop + pagination + dedupe + rate-limit + retry logic inline. Adding Layer 2 (OSM) + Layer 3 (city/state open data) + Layer 4 (NPI, USAPickleball, PDGA, etc.) means N independent reimplementations of the same plumbing. **Mitigation:** extract the shared logic into `app/contrib/google_places_scraper.py` library + define `BaseIngestClient` abstract interface in `app/contrib/ingest_base.py`; each layer's client subclasses + overrides the source-specific parts (HTTP client, response parsing, dedupe key derivation).
- **No `app/contrib/ingest_reconciler.py`.** Multiple layers will return the same entity (Lake Havasu Aquatic Park appears in Google Places, OSM, AND the City Parks & Rec list). The strategy memo §4 specifies dedupe-at-ingest-time logic (geo proximity + normalized name + stable IDs) with operator-typed-fields-win field-merge priority. Without the reconciler, three layers create three rows.
- **No Railway-cron-service template.** The existing `.github/workflows/parks-rec-scrapes.yml` is the GitHub-Actions precedent for the parks-rec scraper (cron `15 */6 * * *` + workflow_dispatch + Postgres write via `DATABASE_URL` secret). Per the design memo §6.1, the Railway scheduled-jobs pattern is a sibling service that runs a one-shot command on a cron schedule. Phase 4.4 close-out ships the template (a runbook + Railway service config) so Phase 5 can spin up per-category scrapers without re-inventing the deploy shape each time.

And the existing scrape scripts are structurally entangled:

- `scripts/places_discovery.py` + `scripts/places_enrichment.py` share ~80% of their HTTP-client + pagination + rate-limit + dedupe + log-shape logic but each has its own copy. Adding a `--category` filter (per design memo §6.1 step 1) or a Layer-2 OSM equivalent multiplies the duplication.
- `app/contrib/places_client.py` is the Google Places HTTP client; it's parameterized for Provider scrapes but doesn't generalize to Places (per the strategy memo §3.1 Layer 1 extension — Phase 5 territory) or to OSM Overpass QL.
- The dedupe logic inside the existing scripts is Google-Place-ID-only; cross-layer dedupe (Google entity matches OSM entity by lat/lng proximity + name normalization) doesn't exist.

**Texture rule reminder:** Phase 4 ships **zero user-visible surface changes**. The chat-route response shape is unchanged. The home page renders the same. The provider profile renders the same. The /api/search response is unchanged. The photo upload routes are unchanged. The magic-link auth flow lands the same email body in the same recipient inbox. The Google Places scrape produces the same DB rows. The only user-visible signal that Phase 4 shipped is operational — Sentry breadcrumbs on retry events, the new Railway scheduled-job service running on cadence, the new `Outbox(Base)` rows landing in production Postgres if 4.1 ships the table.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Option A locked over Option B + Option C | LOCKED per `background_job_infrastructure_decision.md` §5. Railway scheduled jobs (cron-like) + FastAPI `BackgroundTasks` (event-triggered) + optional Outbox(Base) (must-not-lose). NO Celery / NO Redis / NO Dramatiq in Phase 4. Migration path to Option B documented at memo §7; not in scope for Phase 4. | Decision memo §5 + §7 |
| Layered scrape strategy: 5 layers, shared interface | LOCKED per `layered_scrape_strategy.md` §2 + §3. Each layer's output writes to the same `entities` + extensions table with a `source` field tracking provenance. Phase 4 framework supports Layer 1 (Google Places) + Layer 2 (OSM) implementations + the shared interface; Layers 3 + 4 per-source implementations are Phase 5 + V1.5 territory. | Strategy memo §2 + §3 |
| All scrape clients write via Phase 1D dual-write helpers | LOCKED per Phase 1D ship (`3f3628e`) + Session-22 fix (`5faa37c`). Clients add new Provider/Event/Program ORM rows via `session.add(...)`; the centralized `register_catalog_dual_write_hooks()` registered in `app/db/__init__.py:36-38` auto-promotes to Entity + extensions on `before_flush`. **Phase 4 scrape clients MUST NOT bypass this pattern.** Direct entity-table inserts are forbidden — they break the legacy-table + Entity-table consistency the entire Phase 1 lane was built to enforce. | Phase 1D + Session-22 |
| Hook registration belongs in package `__init__.py`, NOT leaf modules | LOCKED per gotcha #17 (Session-22 lesson). If Phase 4 adds any new ORM models needing `before_flush` / `after_flush` / `before_insert` / etc. hooks, registration goes in the package `__init__.py` (`app/db/__init__.py` for ORM-level hooks; `app/contrib/__init__.py` if there's a contrib-only hook surface), NOT in a leaf module. End-of-file in `models.py` is REJECTED — that pattern broke under alternate entry points. | Gotcha #17 + `app/db/__init__.py` docstring |
| No new Python dependencies in Phase 4.1/4.2/4.3 | LOCKED per Option A. `requirements.txt` is unchanged through Phase 4.1/4.2/4.3. If Phase 4.3's OSM client genuinely needs `overpy` or similar, flag in §13 deviation list — Cursor does NOT add silently. `httpx` is already present (used by `app/contrib/places_client.py`); reuse it for OSM. | Decision memo §3.1 cons + Option A pros |
| Outbox table in Phase 4.1 vs defer to Phase 4.5 / V1.5 | **LOCKED 2026-05-13 at session-23 dispatch authoring: SHIP OUTBOX IN PHASE 4.1.** Magic-link send is the canonical must-not-lose job; deferring the Outbox means accepting "magic-link emails may occasionally fail silently" through V1 user signups. The Outbox is M-effort per decision memo §10 (~100 lines of code + 1 migration + tests). Phase 4.1 therefore adds one new alembic migration advancing the head by one (off `e1f2a3b4c5d6`). The dispatch prompt at `outputs/cursor_dispatch_prompt_phase_4_1.md` reflects this lock. | §9 deviation list + decision memo §6.2 + §10 |
| BackgroundTasks retry wrapper pattern | LOCKED per decision memo §6.2. `app/core/background.py::with_retry(fn, *args, max_attempts=3, backoff_initial_s=1.0, **kwargs)` — bounded retries on transient failure; Sentry breadcrumb on exhaustion; tasks must be idempotent. Caller call sites: `background_tasks.add_task(with_retry, send_magic_link_email, email, token)`. The signature mirrors the existing `app.contrib.rate_limiter.SourceLimiter` retry shape so the two retry surfaces feel consistent. | Decision memo §6.2 |
| `_hourly_cleanup_loop` stays at `app/main.py:251` | LOCKED — Phase 4.1 does NOT move the existing loop. It's referenced as the canonical in-process asyncio loop pattern from `app/core/background.py` docstring (a comment block + import), but the loop itself stays put. No new in-process loops added in Phase 4.1 (cache warming + alerts dispatcher are Phase 5/8 — they pick up the documented pattern when they ship). | §4 below |
| Layered-scrape client base interface in `app/contrib/ingest_base.py` | LOCKED per strategy memo §4 (`app/contrib/ingest_reconciler.py` referenced; sibling `ingest_base.py` is the natural home for the abstract `BaseIngestClient`). Abstract methods: `discover(query) -> list[RawHit]`, `enrich(hit) -> EnrichedHit`, `dedupe_key(hit) -> str`, `to_entity_payload(hit) -> EntityPayload`. Per-layer subclasses live in `app/contrib/google_places_scraper.py`, `app/contrib/osm_overpass_client.py`, etc. Each client owns its HTTP layer + parsing; the base owns the orchestration loop + reconciler hand-off. | Strategy memo §3 + §4 |
| Reconciler shape: shared module + 3 match strategies | LOCKED per strategy memo §4. Match by `google_place_id` (definitive when both source + existing have it) → match by geo proximity (50m default; operator-tunable) → match by normalized name (`slugify(name)`). Field-merge priority: operator-typed > Google > OSM > city > specialized. Output: "insert new row" OR "update existing row id X with these new fields, preserving operator-typed fields." | Strategy memo §4 |
| Source provenance: JSON array column on entity row | LOCKED per strategy memo §8 Q4 recommendation. `entities.sources: list[str]` — already a candidate column or attribute via the existing `entity.source` field (singular string). **Phase 4.3 reconciler updates `entity.source` to a comma-separated multi-source string or migrates to a JSON-array column.** Cursor's call which shape — if migration required (e.g., column doesn't already exist or is the wrong type), flag in §13 and either author the migration in 4.3 (advancing alembic head by one) OR defer to Phase 4.5 / Phase 5 fill-in. Recommended: comma-separated string in `entity.source` for V1 (no migration); JSON-array column when query patterns force it (Phase 5 / V1.5). | Strategy memo §8 Q4 |
| Operator monitoring: per-run log files + Sentry breadcrumbs | LOCKED per master plan §4 Phase 4 + decision memo §9 Q6 floor recommendation. Each scrape run writes a markdown summary to `docs/scrape_logs/<source>_<YYYY-MM-DD>.md` OR a `scrape_run_log` DB table. Phase 4 ships the file-based path (no migration); the DB table is V1.5 if query patterns force it. Sentry tag `background-jobs` + retry-exhaustion breadcrumbs ship in Phase 4.1's `with_retry` helper. | Master plan §4 Phase 4 + decision memo §9 Q6 |
| Manual recovery (Layer 5) is operator workflow, NOT engineering | LOCKED per strategy memo §3.5. The `docs/maintainability/manual_recovery_checklist.md` exists; Phase 4 does NOT touch it. Phase 5 + 6 may add an admin form surface for manual-recovery entry; Phase 4 doesn't. | Strategy memo §3.5 |

---

## §3 Sub-phase boundaries (HALT etiquette)

Phase 4 splits into **four** sub-phases. Each is independently committable + pytest-green. **HALT and report between sub-phases** so the operator can commit + push before you proceed.

### Phase 4.1 — Background-jobs scaffold

**Scope:**
- New `app/core/background.py` module: `with_retry()` helper + Sentry breadcrumb integration + docstring documenting the `_hourly_cleanup_loop` reference pattern (no behavior change to the existing loop).
- (IF operator locks "ship Outbox now" at §2 row): new alembic migration adding `Outbox(Base)` table + `app/db/models.py` Outbox ORM class + `app/core/background.py::deliver_outbox_row()` + `scripts/outbox_redrive.py` script.
- Anchored edit on the Phase 2A.2 magic-link send call site to wrap in `with_retry()`. Locate via Grep before anchoring; preserve the same email body + recipient + Resend API call semantics.
- New test file `tests/test_phase4_background.py` (~15-25 tests): retry-wrapper happy path, bounded-retry exhaustion, Sentry breadcrumb fires on exhaustion, idempotency contract documented, magic-link integration test (mocked Resend) verifies retry-on-429 + final-success outcome. If Outbox ships in 4.1, add Outbox migration cycle test + redrive script idempotency test + state-transition test.

**No new in-process loops in 4.1.** `_hourly_cleanup_loop` stays at `app/main.py:251` unchanged. Cache warming + alerts dispatcher are Phase 5/8 — they pick up the documented pattern when they ship.

**No layered-scrape work in 4.1.** That's 4.2 + 4.3.

**No Railway-cron-service config in 4.1.** That's 4.4 close-out.

**Acceptance gates for 4.1:**
- Pytest stays green (~1703 + ~15-25 net-new tests in `tests/test_phase4_background.py`)
- Ruff clean
- If Outbox ships in 4.1: `python -m alembic upgrade head` against fresh SQLite reaches the new revision cleanly; `python -m alembic downgrade -1 && python -m alembic upgrade head` cycles cleanly (reversibility verified)
- Manual smoke: magic-link request → email landed (operator-runnable; Cursor doesn't execute; flag in §13 as deferred-to-operator)
- No raw SQL in `op.execute()` unless verified portable (Postgres + SQLite both) — applies only if Outbox migration ships
- No `sa.text("1")` / `sa.text("0")` for Boolean defaults — applies only if Outbox migration ships
- `app/core/background.py` does NOT import from `app/db/models.py` at module top (avoids reintroducing the gotcha #17 cycle); any model-related logic in the Outbox path uses lazy-import or session-time imports

**Report at §13 format. HALT.**

### Phase 4.2 — Layered-scrape client interface + Google Places refactor

**Scope:**
- New `app/contrib/ingest_base.py`: abstract `BaseIngestClient` class with `discover()`, `enrich()`, `dedupe_key()`, `to_entity_payload()` methods. Type aliases for `RawHit`, `EnrichedHit`, `EntityPayload`. Docstring documenting the layered-scrape pattern + the Phase 1D dual-write seam (`session.add(Provider(...))` lands the Entity + extensions via the centralized `before_flush` hook).
- New `app/contrib/google_places_scraper.py` library module: extract the shared scrape loop + pagination + rate-limit + retry + dedupe-on-google-place-id logic from `scripts/places_discovery.py` + `scripts/places_enrichment.py`. The library module conforms to `BaseIngestClient`. The two existing scripts become thin wrappers that instantiate the library client + call its `run_discovery()` / `run_enrichment()` methods.
- New `app/contrib/google_types_mapping.py`: dictionary mapping Google Places `types` array values → `Category.slug` + `place_type` discriminator. Operator-maintainable. Per strategy memo §3.1.
- Anchored edits on `scripts/places_discovery.py` + `scripts/places_enrichment.py`: replace inline logic with library-module calls. Pure refactor — same DB rows produced, same log lines, same rate-limit semantics.
- (Optional, design memo §6.1 step 1): add `--category` flag to `places_discovery.py`. The strategy memo locks this as a Phase 4 deliverable; the design memo notes it as a precondition for Railway-cron-service scheduling. Recommended for Phase 4.2 inclusion.
- New test file `tests/test_phase4_ingest_client_interface.py` (~10-15 tests): `BaseIngestClient` abstract-method enforcement (subclass must implement all 4 methods); `google_places_scraper.GooglePlacesClient` conforms to the interface; types-mapping returns expected slug + place_type for canonical Google `types` values (5-10 examples); refactored-script smoke: discovery + enrichment produce same DB rows as pre-refactor (use mocked Google response fixtures from the existing test surface if present, or new fixtures).

**No new layer-2/3/4 clients in 4.2.** OSM is 4.3. Layers 3 + 4 are Phase 5.

**No reconciler in 4.2.** That's 4.3.

**No alembic migration in 4.2.** Pure application code.

**Acceptance gates for 4.2:**
- Pytest stays green (+10-15 net-new tests in `tests/test_phase4_ingest_client_interface.py` + existing places-scraper tests must remain green)
- Ruff clean
- Manual smoke: operator-runnable `python -m scripts.places_discovery --dry-run` + `python -m scripts.places_enrichment --dry-run` produce same log output as pre-refactor (operator-runnable; Cursor doesn't execute; flag in §13 as deferred-to-operator)
- No new Python dependencies in `requirements.txt`
- `app/contrib/google_places_scraper.py` does NOT bypass Phase 1D dual-write helpers — verify by tracing the write path: it calls `session.add(Provider(...))` (or equivalent for Event/Program); the centralized `before_flush` hook from `app/db/__init__.py` auto-promotes to Entity + extensions
- `BaseIngestClient` import chain does NOT trigger gotcha #17 — verify with a one-line subprocess import test in the test file (mirror `tests/test_phase1d_dual_write.py::test_scraper_entry_point_import_chain_does_not_cycle` shape)

**Report at §13 format. HALT.**

### Phase 4.3 — Second client + cross-layer reconciler (parallel-eligibility proof)

**Scope:**
- New `app/contrib/osm_overpass_client.py`: minimal OSM Overpass-QL client conforming to `BaseIngestClient` (from 4.2). Overpass QL query for a single category (recommendation: `leisure=dog_park` per strategy memo §3.2 — small, well-mapped category, fast to verify). Returns `RawHit` objects with name + lat/lng + tags + OSM stable ID. `dedupe_key` derives from OSM stable ID. `to_entity_payload` maps OSM tags → entity columns + extension records (`Location.lat`/`Location.lng` + `Feature.ada_accessible` from `wheelchair=yes/no/limited` + `Feature.free` from inverted `fee=yes/no` per strategy memo §3.2).
- New `scripts/osm_overpass_pull.py`: thin wrapper that instantiates the OSM client + runs discovery for a configurable category list.
- New `app/contrib/ingest_reconciler.py`: cross-layer dedupe module. Three match strategies in priority order: (1) `google_place_id` exact match → definitive; (2) geo proximity (50m default; operator-tunable constant `GEO_PROXIMITY_THRESHOLD_M = 50`); (3) normalized name match (`slugify(name)`). Field-merge priority: operator-typed > Google > OSM > city > specialized. Returns `ReconcileResult(action="insert" | "update", existing_id: str | None, merge_fields: dict)`.
- Anchored edit on `app/contrib/google_places_scraper.py` (from 4.2) to call `ingest_reconciler.reconcile_hit()` before each ORM `session.add(Provider(...))`. Same hook for the OSM client.
- (IF operator locks JSON-array `sources` column at §2 row "Source provenance"): alembic migration adding `entities.sources: JSON` column + backfill from `entity.source` singular string. **Recommendation: defer to V1.5 unless 4.3 reconciler surfaces real multi-source matches; for V1, comma-separated string in `entity.source` is sufficient.**
- New test file `tests/test_phase4_osm_client.py` (~8-12 tests): Overpass QL query construction; mocked Overpass response → `RawHit` parsing; OSM stable ID dedupe key; OSM tag → entity payload mapping for `wheelchair` + `fee` + `name` + `lat/lng`.
- New test file `tests/test_phase4_ingest_reconciler.py` (~15-20 tests): `google_place_id` exact match returns "update"; geo-proximity-within-50m + matching name returns "update"; geo-proximity-within-50m + mismatched name returns "ambiguous" (operator-review queue); name-only match without geo returns "ambiguous"; field-merge priority — operator-typed wins; field-merge — same-priority later run wins (most-recent update); reconcile-then-add for a brand-new entity returns "insert"; ingest_reconciler is idempotent (same hit twice produces the same result).

**No layer-3/4 clients in 4.3.** Phase 5.

**No new Python dependencies in 4.3** unless operator approves at §13. `httpx` (already present) handles Overpass HTTP.

**No production cutover in 4.3.** OSM client is wired but not yet on a Railway cron. That's 4.4 close-out + Phase 5 fill-in.

**Acceptance gates for 4.3:**
- Pytest stays green (+25-32 net-new tests across both test files)
- Ruff clean
- If `sources` column migration ships in 4.3: `python -m alembic upgrade head` against fresh SQLite reaches the new revision cleanly; `python -m alembic downgrade -1 && python -m alembic upgrade head` cycles cleanly; **otherwise** alembic head stays at 4.1's level
- Manual smoke (deferred-to-operator): `python -m scripts.osm_overpass_pull --category dog_park --dry-run` produces parseable Overpass response + maps to expected entity payloads
- Reconciler is idempotent (proven in `test_phase4_ingest_reconciler.py`)
- OSM + Google Places clients both share the `BaseIngestClient` interface — verify via abstract-method conformance test (mirror 4.2's shape)
- No raw SQL in any new `op.execute()` calls unless verified portable
- No `sa.text("1")` / `sa.text("0")` for Boolean defaults

**Report at §13 format. HALT.**

### Phase 4.4 — Phase 4 close-out (operator runbook + Railway cron template + docs ship-line)

**Scope:**
- New `docs/operations/railway_scheduled_jobs_runbook.md`: operator-facing runbook for spinning up a Railway scheduled-job service. Step-by-step: create service from main repo; set service command (e.g., `python -m scripts.places_discovery --category $CATEGORY`); set cron schedule; set env vars (`DATABASE_URL`, `GOOGLE_PLACES_API_KEY`, etc.); verify first run + post-run log inspection.
- New `docs/operations/scrape_logs_template.md`: per-run summary markdown template (total queries, total discovered, total new, total updated, total errors, sample errors, run duration, source name, run timestamp).
- Anchored edit on `docs/maintainability/master_build_plan.md` §4 Phase 4: append SHIPPED 2026-05-XX (Phase 4.4 ship date) header + four-sub-phase shipped-incremental list.
- Anchored edit on `docs/STATE.md`: Production block + Recently shipped §1 prepend with Phase 4 narrative.
- Anchored edit on `app/photos/*.py` (or wherever image processing fires) to wrap the existing Pillow processing in `with_retry()` (from 4.1). Locate via Grep before anchoring; this is the second `BackgroundTasks` retry-wrapper integration per design memo §6.4 V1 cut.
- Anchored edit on `app/api/routes/chat.py:62` + `app/contrib/enrichment.py:18` — wrap the existing `scan_and_save_mentions` + `enrich_contribution` BackgroundTasks calls in `with_retry()` for consistency. OPTIONAL — flag in §13 if you skip; current shape is best-effort which already matches `with_retry`'s exhaustion-is-silent semantics.
- New test file `tests/test_phase4_close_out.py` (~5-10 tests): smoke that all wrapper integrations are wired (grep verification + import-chain test); regression that `_hourly_cleanup_loop` at `app/main.py:251` still exists + unchanged.

**No new layer clients in 4.4.** Phase 5.

**No new alembic migration in 4.4.** Pure docs + anchored edits.

**Acceptance gates for 4.4:**
- Pytest stays green (+5-10 net-new tests in `tests/test_phase4_close_out.py`)
- Ruff clean
- `docs/operations/railway_scheduled_jobs_runbook.md` exists + is operator-readable (no internal jargon; numbered steps; copy-paste-able shell commands)
- `docs/operations/scrape_logs_template.md` exists with clear placeholder markers
- Master plan §4 Phase 4 has a SHIPPED 2026-05-XX header
- STATE.md Production block + Recently shipped §1 reflect the Phase 4 ship
- `with_retry()` is wired into image-processing call site (deferred image-processing retry integration is acceptable if flagged + rationale)
- Manual smoke (deferred-to-operator): stand up the first Railway scheduled-job service per the new runbook (operator decides when; not gating Phase 4 close-out)

**Report at §13 format.** After 4.4 ships + commits, **Phase 4 is COMPLETE**. Master plan §4 Phase 4 gets a SHIPPED header; Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI) becomes the next dispatchable lane.

---

## §4 Phase 4.1 deliverables (in dispatch order)

Author the background-jobs scaffold + (optional) Outbox table in a single Cursor session. The session has one large new module (`app/core/background.py`), one optional new migration + ORM class, one anchored edit on the magic-link send call site, and one large new test file.

### §4.1 New `app/core/background.py` module

```
app/core/background.py
"""Background-jobs scaffold for Option A (Railway scheduled jobs + FastAPI
BackgroundTasks + optional Outbox).

This module is the centralized retry + Sentry + logging surface for all
background work in the codebase. Two patterns it supports:

1. Event-triggered tasks via FastAPI BackgroundTasks (the common case):
       background_tasks.add_task(with_retry, send_magic_link_email, email, token)
   `with_retry` wraps the call with bounded retry + exponential backoff
   + Sentry breadcrumb on exhaustion. Tasks MUST be idempotent.

2. In-process scheduled loops via asyncio.create_task in lifespan (the
   `_hourly_cleanup_loop` pattern at app/main.py:251):
       async def _cache_warm_loop() -> None:
           while True:
               await asyncio.sleep(900)
               await asyncio.to_thread(warm_llm_response_cache)
   Wired into `lifespan` alongside the existing loop. Each loop is
   best-effort and idempotent; process restart re-starts the loop with
   the next sleep window. Cap: do NOT use this pattern for any job
   longer than ~5 seconds or any job with strict timing requirements.
   For longer + scheduled work, use a Railway scheduled-job service
   per docs/operations/railway_scheduled_jobs_runbook.md (shipping in
   Phase 4.4).

Option A migration path to Option B (Celery + Redis) is documented in
docs/maintainability/background_job_infrastructure_decision.md §7.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

import sentry_sdk

logger = logging.getLogger(__name__)
T = TypeVar("T")


def with_retry(
    fn: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    backoff_initial_s: float = 1.0,
    backoff_multiplier: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    fatal_on: tuple[type[Exception], ...] = (),
    **kwargs: Any,
) -> T | None:
    """Execute fn with bounded retries on transient failure.

    On exhaustion, log to Sentry breadcrumb + return None (do not raise).
    Tasks must be idempotent — re-running on retry must produce the same
    side effects (or no incremental side effects).

    Parameters:
    - fn: callable to execute
    - *args, **kwargs: passed to fn
    - max_attempts: total attempts including initial (default 3)
    - backoff_initial_s: initial backoff in seconds (default 1.0)
    - backoff_multiplier: backoff scaling factor (default 2.0 -> 1s, 2s, 4s)
    - retry_on: exception types that trigger retry (default Exception)
    - fatal_on: exception types that exit immediately, no retry (e.g.,
                4xx validation errors; subset of retry_on by convention)

    Returns the function's return value on success; None on retry
    exhaustion. Caller is responsible for any return-value semantics.
    """
    last_exc: Exception | None = None
    backoff = backoff_initial_s
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except fatal_on as exc:
            sentry_sdk.add_breadcrumb(
                category="background-jobs",
                message=f"{fn.__name__} fatal exception: {type(exc).__name__}",
                level="error",
            )
            logger.error(
                "background_jobs fatal", extra={"fn": fn.__name__, "exc_type": type(exc).__name__, "attempt": attempt}
            )
            return None
        except retry_on as exc:
            last_exc = exc
            sentry_sdk.add_breadcrumb(
                category="background-jobs",
                message=f"{fn.__name__} attempt {attempt} failed: {type(exc).__name__}",
                level="warning",
            )
            logger.warning(
                "background_jobs retry",
                extra={"fn": fn.__name__, "exc_type": type(exc).__name__, "attempt": attempt, "max_attempts": max_attempts},
            )
            if attempt < max_attempts:
                time.sleep(backoff)
                backoff *= backoff_multiplier
    sentry_sdk.add_breadcrumb(
        category="background-jobs",
        message=f"{fn.__name__} exhausted retries: {type(last_exc).__name__ if last_exc else 'unknown'}",
        level="error",
    )
    logger.error(
        "background_jobs exhausted",
        extra={"fn": fn.__name__, "exc_type": type(last_exc).__name__ if last_exc else "unknown", "max_attempts": max_attempts},
    )
    return None


async def with_retry_async(
    fn: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    backoff_initial_s: float = 1.0,
    backoff_multiplier: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    fatal_on: tuple[type[Exception], ...] = (),
    **kwargs: Any,
) -> Any:
    """Async variant of with_retry for awaitable fn. Same semantics."""
    last_exc: Exception | None = None
    backoff = backoff_initial_s
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except fatal_on as exc:
            sentry_sdk.add_breadcrumb(
                category="background-jobs",
                message=f"{fn.__name__} fatal exception: {type(exc).__name__}",
                level="error",
            )
            logger.error(
                "background_jobs fatal", extra={"fn": fn.__name__, "exc_type": type(exc).__name__, "attempt": attempt}
            )
            return None
        except retry_on as exc:
            last_exc = exc
            sentry_sdk.add_breadcrumb(
                category="background-jobs",
                message=f"{fn.__name__} attempt {attempt} failed: {type(exc).__name__}",
                level="warning",
            )
            logger.warning(
                "background_jobs retry async",
                extra={"fn": fn.__name__, "exc_type": type(exc).__name__, "attempt": attempt, "max_attempts": max_attempts},
            )
            if attempt < max_attempts:
                await asyncio.sleep(backoff)
                backoff *= backoff_multiplier
    sentry_sdk.add_breadcrumb(
        category="background-jobs",
        message=f"{fn.__name__} exhausted retries: {type(last_exc).__name__ if last_exc else 'unknown'}",
        level="error",
    )
    logger.error(
        "background_jobs exhausted async",
        extra={"fn": fn.__name__, "exc_type": type(last_exc).__name__ if last_exc else "unknown", "max_attempts": max_attempts},
    )
    return None
```

Notes for Cursor:

- The sync `with_retry` is the common case (Resend `send` is a sync httpx call; Pillow processing is sync; existing `BackgroundTasks` consumers like `scan_and_save_mentions` + `enrich_contribution` are sync).
- The async variant is for any future awaitable BackgroundTasks consumer; ships as a sibling for consistency.
- `sentry_sdk.add_breadcrumb` is already imported elsewhere (`app/main.py` uses sentry-sdk per `_init_sentry()` at `:205`); verify via Grep that `sentry-sdk` is in `requirements.txt` already (it is — Phase 0/Phase 1 dep). If not, do NOT add it; flag in §13.
- Logger uses the structured-logging shape from `app/contrib/rate_limiter.py:33` (`logger = logging.getLogger(__name__)`).
- Do NOT use `print()` for any background-jobs telemetry. Logger + Sentry breadcrumb are the two channels.

### §4.2 Outbox(Base) table (CONDITIONAL — operator decision-lock at §2 row)

**If operator locks "ship Outbox now":**

New alembic migration `alembic/versions/<rev>_phase4_outbox.py` chains off `e1f2a3b4c5d6`:

```
outbox:
  id            VARCHAR(36) PRIMARY KEY  (uuid)
  kind          VARCHAR(32) NOT NULL CHECK IN ('magic_link', 'sponsor_notification', 'image_processing', 'other')
  payload       JSON NOT NULL                              (serialized task arguments; idempotency contract: caller derives a stable hash)
  state         VARCHAR(20) NOT NULL CHECK IN ('pending', 'in_flight', 'delivered', 'failed') DEFAULT 'pending'
  attempts      INTEGER NOT NULL DEFAULT 0
  last_attempt_at TIMESTAMP NULL
  last_error    VARCHAR(500) NULL
  created_at    TIMESTAMP NOT NULL default sa.func.now()
  updated_at    TIMESTAMP NOT NULL default sa.func.now()
  delivered_at  TIMESTAMP NULL

INDEX ix_outbox_state_created_at (state, created_at)      -- for redrive-poll selectivity
INDEX ix_outbox_kind
```

`app/db/models.py`: append `Outbox(Base)` model class at file tail (mirror Phase 3.1 + 3.2 append discipline; goes AFTER all existing classes). Do NOT add any module-import-time hook for Outbox — gotcha #17 cure. If `before_flush` semantics are needed, register in `app/db/__init__.py` (NOT in models.py or in a leaf module).

`app/core/background.py`: append `deliver_outbox_row(row_id: str) -> bool` function. Picks up `Outbox` row by ID; transitions `pending → in_flight`; invokes the appropriate handler based on `kind`; on success transitions `in_flight → delivered` + sets `delivered_at`; on transient failure transitions back to `pending` + increments `attempts` + sets `last_error`; on `attempts >= 5` transitions to `failed`. Wraps the handler call in `with_retry`.

`scripts/outbox_redrive.py`: new script. Polls `Outbox` for rows in state `pending` older than `30s` (avoid racing the hot-path `BackgroundTasks` invocation that runs right after row insertion). For each row, calls `deliver_outbox_row()`. Stops when batch is empty or `--max-rows` reached. Operator-runnable; Phase 4.4 wires it to a Railway scheduled-job service running every 5 minutes per design memo §6.2.

Anchored edit on the magic-link send path (Phase 2A.2 territory; Grep `Resend|send_magic_link|magic_link_email` to locate exactly):

```python
# Before (Phase 2A.2 shape):
@router.post("/api/auth/request-link")
async def request_link(email: str, background_tasks: BackgroundTasks, db: Session):
    token = create_token(email)
    background_tasks.add_task(send_magic_link_email, email, token)
    return {"status": "sent"}

# After (Phase 4.1 with Outbox):
@router.post("/api/auth/request-link")
async def request_link(email: str, background_tasks: BackgroundTasks, db: Session):
    token = create_token(email)
    outbox_row = Outbox(
        kind="magic_link",
        payload={"email": email, "token": token},
        state="pending",
    )
    db.add(outbox_row)
    db.commit()
    background_tasks.add_task(deliver_outbox_row, outbox_row.id)
    return {"status": "sent"}
```

**If operator locks "defer Outbox":**

Skip the migration + the Outbox ORM class + `scripts/outbox_redrive.py`. The magic-link send call site still gets the `with_retry()` wrapping:

```python
# After (Phase 4.1 without Outbox):
@router.post("/api/auth/request-link")
async def request_link(email: str, background_tasks: BackgroundTasks):
    token = create_token(email)
    background_tasks.add_task(with_retry, send_magic_link_email, email, token, max_attempts=3)
    return {"status": "sent"}
```

The trade-off is the explicit decision-lock at §2 row "Outbox table in Phase 4 vs Phase 5".

### §4.3 Anchored edits on existing `BackgroundTasks` call sites

OPTIONAL — flag in §13 if you skip. Brief invitation per decision memo §6.4. Wrapping existing best-effort consumers in `with_retry` adds Sentry breadcrumbs + structured logging without changing the outcome (both consumers are already silently fault-tolerant per their original shape).

- `app/api/routes/chat.py:62` — `scan_and_save_mentions`. Anchored edit:
  ```python
  # Before:
  background_tasks.add_task(scan_and_save_mentions, ...)
  # After:
  background_tasks.add_task(with_retry, scan_and_save_mentions, ..., max_attempts=2)
  ```
- `app/contrib/enrichment.py:18` — `enrich_contribution`. Same pattern.

**Recommendation:** ship in Phase 4.4 close-out alongside the image-processing retry-wrapper integration, NOT in 4.1. Phase 4.1's scope discipline is the new module + Outbox + magic-link call site only. If Cursor takes Phase 4.1 with bandwidth to spare, the close-out edits are acceptable but flag in §13.

### §4.4 New tests for Phase 4.1

New test file `tests/test_phase4_background.py` (~15-25 tests):

1. `with_retry` happy path: fn returns value on first attempt; returned unchanged
2. `with_retry` exhaustion: fn always raises; returns None after `max_attempts`
3. `with_retry` retry-then-success: fn raises on attempt 1, returns value on attempt 2
4. `with_retry` backoff timing: backoff escalates per `backoff_multiplier`
5. `with_retry` fatal_on bypasses retry: fn raises a fatal exception; returns None immediately + Sentry breadcrumb tag = fatal
6. `with_retry` Sentry breadcrumb fires on every retry attempt
7. `with_retry` Sentry breadcrumb fires on exhaustion with `exhausted` category
8. `with_retry` does NOT re-raise the underlying exception (returns None)
9. `with_retry_async` happy path
10. `with_retry_async` exhaustion
11. `with_retry_async` uses `asyncio.sleep` not `time.sleep`
12. (Outbox-conditional) `Outbox(Base)` model class is importable + has the expected columns
13. (Outbox-conditional) Migration upgrade + downgrade + upgrade cycle on fresh SQLite
14. (Outbox-conditional) `Outbox.state` CHECK constraint rejects invalid state values
15. (Outbox-conditional) `Outbox.kind` CHECK constraint rejects invalid kind values
16. (Outbox-conditional) `Outbox.attempts` defaults to 0
17. (Outbox-conditional) `deliver_outbox_row` happy path: pending → in_flight → delivered
18. (Outbox-conditional) `deliver_outbox_row` transient failure: pending → in_flight → pending; attempts += 1
19. (Outbox-conditional) `deliver_outbox_row` exhaustion at attempts=5: pending → failed
20. (Outbox-conditional) `deliver_outbox_row` is idempotent: calling on a `delivered` row is a no-op
21. (Outbox-conditional) `scripts/outbox_redrive` picks up only rows in `pending` state + older than 30s
22. (Outbox-conditional) `scripts/outbox_redrive` respects `--max-rows`
23. Magic-link integration test (mocked Resend): request triggers Outbox row insert + BackgroundTasks delivery + Resend send. (Operator-runnable end-to-end smoke deferred; this test mocks the Resend call.)
24. Magic-link integration test transient-failure path: mocked Resend raises on attempt 1, succeeds on attempt 2; Outbox transitions through expected states
25. Import-chain test: `from app.core.background import with_retry` succeeds without importing `app.db.models` (gotcha #17 cure — `app/core/background.py` must NOT import from models at module top; lazy-import or session-time imports for any model-touching logic in the Outbox path)

### §4.5 What NOT to do in Phase 4.1

- DO NOT add new in-process asyncio loops to `app/main.py:lifespan`. The existing `_hourly_cleanup_loop` stays put; cache warming + alerts dispatcher pick up the documented pattern when they ship in Phase 5/8.
- DO NOT touch the existing `_hourly_cleanup_loop` at `app/main.py:251`. It's the canonical reference, referenced by docstring in `app/core/background.py`, but not refactored.
- DO NOT add new Python dependencies. `sentry-sdk` is already present; `httpx` is already present.
- DO NOT add Celery / Redis / Dramatiq / RQ. Option B is documented as the migration path; not in scope.
- DO NOT register any `before_flush` / module-import-time hooks anywhere except `app/db/__init__.py`. Gotcha #17 is the canonical lesson; the cure is centralized package-init registration.
- DO NOT import from `app/db/models.py` at module top in `app/core/background.py`. Lazy-import inside `deliver_outbox_row` if needed. Prevents reintroducing the gotcha #17 cycle pattern.
- DO NOT modify the chat-route response shape. Phase 4 is plumbing; zero user-visible surface changes.
- DO NOT modify the magic-link email body, recipient address, or Resend API call semantics. Phase 4.1 wraps the existing send in retries; the email outcome is unchanged.
- DO NOT add admin-form surfaces for Outbox visibility. Phase 5 + V1.5 can add an admin page for must-not-lose-job inspection; Phase 4.1 is scaffold only.
- DO NOT add layered-scrape work. That's 4.2 + 4.3.
- DO NOT propose moving to Option B. The locked decision is Option A; the migration path is documented in the design memo §7 and triggers when job failure rates / latency / observability needs / horizontal scaling forces the issue — not on speculation.

---

## §5 Phase 4.2 deliverables (in dispatch order)

Author the layered-scrape client interface + Google Places refactor in a single Cursor session. The session has one new abstract base module, one large new library module (extracted from existing scripts), one new mapping module, anchored edits on two existing scripts, and one new test file.

### §5.1 New `app/contrib/ingest_base.py`

```
app/contrib/ingest_base.py
"""Layered-scrape framework: abstract base + type aliases.

Each scrape layer (Google Places, OSM, city open data, specialized APIs)
implements a subclass of BaseIngestClient. The base owns the orchestration
loop + reconciler hand-off; subclasses own the source-specific HTTP layer
+ response parsing + dedupe-key derivation + entity-payload mapping.

Locked design context: docs/maintainability/layered_scrape_strategy.md
end-to-end. Phase 4 ships the framework + Layer 1 (Google Places refactor)
+ Layer 2 (OSM Overpass minimal); Phase 5 fills Layers 3 + 4 per category.

All clients write via Phase 1D dual-write helpers — i.e., `session.add(
Provider(...))` (or Event/Program) triggers the centralized `before_flush`
hook registered in `app/db/__init__.py`, which auto-promotes the row to
an Entity + extensions. Clients MUST NOT bypass this pattern by directly
inserting into `entities` or extension tables.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawHit:
    """Raw response data from a single source (one entity per hit)."""
    source: str                                    # e.g., "google_places", "osm"
    source_stable_id: str                          # source-specific stable identifier (google_place_id, OSM stable ID, etc.)
    name: str
    lat: float | None = None
    lng: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)  # source-specific full response payload


@dataclass
class EnrichedHit:
    """RawHit + enrichment fetch (full detail beyond the discovery response)."""
    raw_hit: RawHit
    enriched: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityPayload:
    """Source-agnostic entity payload, ready for ORM dual-write."""
    name: str
    entity_type: str                               # "commercial" | "place" | "event" | "program"
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    description: str | None = None
    category_slug: str | None = None
    google_place_id: str | None = None
    source: str = "unknown"
    extension_payloads: dict[str, Any] = field(default_factory=dict)  # Location / ContactPoint / Hours / etc.


class BaseIngestClient(ABC):
    """Abstract base for all layered-scrape clients.

    Subclasses implement the four abstract methods; the base provides
    discover_and_enrich() + reconcile-then-write orchestration.
    """

    source_name: str = "unknown"  # subclass override

    @abstractmethod
    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        """Source-specific discovery call. Returns list of raw hits."""
        ...

    @abstractmethod
    def enrich(self, hit: RawHit) -> EnrichedHit:
        """Source-specific enrichment fetch (e.g., Google Places details).

        For sources where discover() already returns full detail (e.g.,
        Overpass), subclass returns EnrichedHit(raw_hit=hit) — no-op enrich.
        """
        ...

    @abstractmethod
    def dedupe_key(self, hit: RawHit) -> str:
        """Source-specific stable dedupe key (e.g., google_place_id, OSM ID)."""
        ...

    @abstractmethod
    def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
        """Map enriched-hit data into source-agnostic EntityPayload."""
        ...

    def run(self, query: dict[str, Any]) -> list[EntityPayload]:
        """Orchestration: discover -> enrich -> payload-list.

        Reconciler hand-off + ORM write happen in the calling script
        (Phase 4.3 adds the reconciler; Phase 4.4 wires the write).
        """
        hits = self.discover(query)
        enriched = [self.enrich(h) for h in hits]
        return [self.to_entity_payload(e) for e in enriched]
```

### §5.2 New `app/contrib/google_places_scraper.py`

Extract the shared logic from `scripts/places_discovery.py` + `scripts/places_enrichment.py`:

```
app/contrib/google_places_scraper.py
"""Google Places API Layer-1 client conforming to BaseIngestClient.

Refactored from scripts/places_discovery.py + scripts/places_enrichment.py.
Same DB write semantics; same rate-limit posture (uses
app.contrib.rate_limiter.GOOGLE_PLACES_LIMITER); same idempotency contract
(load_processed_ids resume-safe pattern preserved).

The two thin script wrappers (places_discovery.py + places_enrichment.py)
now instantiate this client + call run_discovery() / run_enrichment().
"""

from typing import Any

from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload, RawHit
from app.contrib.places_client import GooglePlacesHttpClient  # existing client; reuse
from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER
from app.contrib.google_types_mapping import map_google_types_to_slug_and_place_type


class GooglePlacesClient(BaseIngestClient):
    source_name = "google_places"

    def __init__(self, http_client: GooglePlacesHttpClient | None = None) -> None:
        self.http = http_client or GooglePlacesHttpClient()

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        # Per scripts/places_discovery.py orchestration: paginated discovery
        # against Google Places Text Search or Nearby Search, gated by
        # GOOGLE_PLACES_LIMITER for QPS pacing + retry on 429/5xx.
        # Implementation: extract from scripts/places_discovery.py lines
        # [grep-anchored at dispatch time]
        ...

    def enrich(self, hit: RawHit) -> EnrichedHit:
        # Per scripts/places_enrichment.py: detail fetch via place_id.
        # Same GOOGLE_PLACES_LIMITER gating.
        ...

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id  # google_place_id

    def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
        # Map Google's response to source-agnostic payload.
        # category_slug derived from google_types via mapping table.
        types = hit.raw_hit.raw.get("types", [])
        category_slug, place_type = map_google_types_to_slug_and_place_type(types)
        return EntityPayload(
            name=hit.raw_hit.name,
            entity_type="commercial",  # most Google Places hits are commercial; place_type discriminator routes
            lat=hit.raw_hit.lat,
            lng=hit.raw_hit.lng,
            address=hit.raw_hit.raw.get("formattedAddress"),
            phone=hit.enriched.get("nationalPhoneNumber"),
            website=hit.enriched.get("websiteUri"),
            description=hit.enriched.get("editorialSummary", {}).get("text") if hit.enriched.get("editorialSummary") else None,
            category_slug=category_slug,
            google_place_id=hit.raw_hit.source_stable_id,
            source=self.source_name,
            extension_payloads={"place_type": place_type},  # consumed by Layer-1 script when calling create_provider_and_entity
        )

    def run_discovery(self, category: str, dry_run: bool = False) -> list[EntityPayload]:
        """Thin wrapper called by scripts/places_discovery.py.

        Filters discovery by category. If dry_run, returns payloads
        without writing to DB. Otherwise, calls session.add(Provider(...))
        for each new payload, letting Phase 1D dual-write promote to
        Entity + extensions.
        """
        ...

    def run_enrichment(self, dry_run: bool = False) -> list[EntityPayload]:
        """Thin wrapper called by scripts/places_enrichment.py.

        Iterates over rows with last_verified_at in aged band; enriches each.
        """
        ...
```

### §5.3 New `app/contrib/google_types_mapping.py`

Operator-maintainable mapping table per strategy memo §3.1:

```
app/contrib/google_types_mapping.py
"""Google Places `types` array → (Category.slug, place_type) mapping.

Operator-maintainable. New Google types should be added here as discovered
during Phase 5 + 6 data-gathering passes.
"""

# Maps Google's `types[0]` (primary type) to (category_slug, place_type)
# place_type is "commercial" | "place" | None
_PRIMARY_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "restaurant": ("eat-drink", "commercial"),
    "cafe": ("eat-drink", "commercial"),
    "bar": ("eat-drink", "commercial"),
    "bakery": ("eat-drink", "commercial"),
    "plumber": ("home-property-services", "commercial"),
    "electrician": ("home-property-services", "commercial"),
    "hvac_contractor": ("home-property-services", "commercial"),
    "general_contractor": ("home-property-services", "commercial"),
    "doctor": ("health-wellness-care", "commercial"),
    "dentist": ("health-wellness-care", "commercial"),
    "hospital": ("health-wellness-care", "commercial"),
    "pharmacy": ("health-wellness-care", "commercial"),
    "lodging": ("lodging-vacation-rentals", "commercial"),
    "rv_park": ("lodging-vacation-rentals", "commercial"),
    "store": ("shopping-essentials", "commercial"),
    "supermarket": ("shopping-essentials", "commercial"),
    "grocery_or_supermarket": ("shopping-essentials", "commercial"),
    "gas_station": ("auto-rv-fuel", "commercial"),
    "car_repair": ("auto-rv-fuel", "commercial"),
    "car_dealer": ("auto-rv-fuel", "commercial"),
    "park": ("outdoors-parks-trails", "place"),
    "dog_park": ("outdoors-parks-trails", "place"),
    "marina": ("on-the-water", "place"),
    "beach": ("on-the-water", "place"),
    "veterinary_care": ("pets", "commercial"),
    "pet_store": ("pets", "commercial"),
    "school": ("classes-sports-recreation", "commercial"),
    "gym": ("health-wellness-care", "commercial"),
    "library": ("public-civic-resources", "place"),
    "city_hall": ("public-civic-resources", "place"),
    # ... more per Phase 5 fill-in
}


def map_google_types_to_slug_and_place_type(types: list[str]) -> tuple[str | None, str | None]:
    """Given a Google Places `types` array, return (category_slug, place_type).

    Tries primary type first, then fallback through the rest. Returns
    (None, None) if no type matches — operator queue surface for review.
    """
    for t in types:
        if t in _PRIMARY_TYPE_MAP:
            return _PRIMARY_TYPE_MAP[t]
    return (None, None)
```

### §5.4 Anchored edits on `scripts/places_discovery.py` + `scripts/places_enrichment.py`

Replace inline orchestration with library-module calls:

```
scripts/places_discovery.py
"""Operator-runnable Layer-1 discovery script (Google Places).

Thin wrapper around app.contrib.google_places_scraper.GooglePlacesClient.
"""

import argparse
from app.contrib.google_places_scraper import GooglePlacesClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True)  # NEW in Phase 4.2
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    client = GooglePlacesClient()
    payloads = client.run_discovery(category=args.category, dry_run=args.dry_run)
    print(f"Discovered {len(payloads)} payloads")


if __name__ == "__main__":
    main()
```

Same shape for `scripts/places_enrichment.py`.

### §5.5 New tests for Phase 4.2

New test file `tests/test_phase4_ingest_client_interface.py` (~10-15 tests):

1. `BaseIngestClient` is abstract — instantiating directly raises TypeError
2. Subclass with missing `discover` raises TypeError
3. Subclass with missing `enrich` raises TypeError
4. Subclass with missing `dedupe_key` raises TypeError
5. Subclass with missing `to_entity_payload` raises TypeError
6. `GooglePlacesClient` is a `BaseIngestClient` subclass
7. `GooglePlacesClient.source_name == "google_places"`
8. `GooglePlacesClient.dedupe_key()` returns `google_place_id` exactly
9. `map_google_types_to_slug_and_place_type` for `["restaurant"]` returns `("eat-drink", "commercial")`
10. `map_google_types_to_slug_and_place_type` for `["dog_park", "park"]` returns `("outdoors-parks-trails", "place")` (primary type wins)
11. `map_google_types_to_slug_and_place_type` for unknown types returns `(None, None)`
12. `GooglePlacesClient.to_entity_payload` produces an `EntityPayload` with `source="google_places"` + correct `category_slug`
13. Refactor regression: `scripts/places_discovery.py --dry-run` produces the same log output as pre-refactor (use a fixture if available, or skip with deferred-to-operator note)
14. Import-chain regression: `from app.contrib.google_places_scraper import GooglePlacesClient` does not trigger gotcha #17 cycle (subprocess import test mirroring `tests/test_phase1d_dual_write.py::test_scraper_entry_point_import_chain_does_not_cycle`)
15. `GooglePlacesClient` calls `GOOGLE_PLACES_LIMITER` for rate-limiting (verify via attribute introspection or via patching the limiter and asserting `.acquire()` was called)

### §5.6 What NOT to do in Phase 4.2

- DO NOT add new layer clients (OSM is 4.3; Layers 3/4 are Phase 5).
- DO NOT modify `app/contrib/rate_limiter.py`. It's the stable interface per its own docstring.
- DO NOT bypass Phase 1D dual-write. Every new Provider/Event/Program row goes via `session.add(...)`.
- DO NOT modify `app/contrib/places_client.py` (the Google HTTP client). It's parameterized for Provider scrapes and stays as-is.
- DO NOT change the DB rows produced by `places_discovery` + `places_enrichment` pre-refactor. Pure refactor.
- DO NOT add module-import-time hooks. Gotcha #17.
- DO NOT add new Python dependencies.
- DO NOT propose moving to Option B in 4.2 either. Same scope discipline.

---

## §6 Phase 4.3 deliverables (in dispatch order)

Author the minimal OSM Overpass client + cross-layer reconciler in a single Cursor session.

### §6.1 New `app/contrib/osm_overpass_client.py`

Minimal Overpass-QL client (single-category proof) conforming to `BaseIngestClient`:

```
app/contrib/osm_overpass_client.py
"""OpenStreetMap Overpass-QL Layer-2 client.

Lake Havasu bounding box per strategy memo §3.2:
  south=34.43, west=-114.41, north=34.59, east=-114.30

Phase 4.3 ships a single-category proof (default: leisure=dog_park).
Phase 5 fills additional categories per the strategy memo §3.2
category table.
"""

import httpx
from typing import Any

from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload, RawHit
from app.contrib.rate_limiter import SourceLimiter

OSM_OVERPASS_LIMITER = SourceLimiter("osm_overpass", qps=0.5)  # Overpass public is generous; 0.5 QPS is comfortable
OSM_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
LHC_BOUNDING_BOX = (34.43, -114.41, 34.59, -114.30)  # (south, west, north, east)


def build_query(tag: str, value: str) -> str:
    s, w, n, e = LHC_BOUNDING_BOX
    return f"""[out:json][timeout:60];
(
  node["{tag}"="{value}"]({s},{w},{n},{e});
  way["{tag}"="{value}"]({s},{w},{n},{e});
);
out body geom;
"""


class OsmOverpassClient(BaseIngestClient):
    source_name = "osm"

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        tag = query.get("tag", "leisure")
        value = query.get("value", "dog_park")
        q = build_query(tag, value)
        with httpx.Client(timeout=90.0) as http:
            response = OSM_OVERPASS_LIMITER.request(
                http, "POST", OSM_OVERPASS_ENDPOINT, data={"data": q}
            )
        if response.status_code != 200:
            return []
        elements = response.json().get("elements", [])
        return [self._element_to_raw_hit(el) for el in elements if el.get("tags", {}).get("name")]

    def _element_to_raw_hit(self, el: dict[str, Any]) -> RawHit:
        tags = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        return RawHit(
            source=self.source_name,
            source_stable_id=f"osm_{el.get('type')}_{el.get('id')}",
            name=tags.get("name", ""),
            lat=lat,
            lng=lng,
            raw={"element": el, "tags": tags},
        )

    def enrich(self, hit: RawHit) -> EnrichedHit:
        # Overpass discovery returns full detail; no separate enrichment fetch.
        return EnrichedHit(raw_hit=hit)

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id  # e.g., "osm_node_12345"

    def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
        tags = hit.raw_hit.raw.get("tags", {})
        category_slug = "outdoors-parks-trails"  # default for Phase 4.3 single-category proof
        # Extension payload: Feature record with ada_accessible + free derived from OSM tags
        extensions: dict[str, Any] = {}
        wheelchair = tags.get("wheelchair")
        if wheelchair in ("yes", "limited"):
            extensions["ada_accessible"] = True
        elif wheelchair == "no":
            extensions["ada_accessible"] = False
        fee = tags.get("fee")
        if fee == "no":
            extensions["free"] = True
        elif fee == "yes":
            extensions["free"] = False
        return EntityPayload(
            name=hit.raw_hit.name,
            entity_type="place",
            lat=hit.raw_hit.lat,
            lng=hit.raw_hit.lng,
            category_slug=category_slug,
            source=self.source_name,
            extension_payloads=extensions,
        )
```

### §6.2 New `scripts/osm_overpass_pull.py`

Thin script wrapper:

```
scripts/osm_overpass_pull.py
"""Operator-runnable Layer-2 OSM Overpass discovery script.

Phase 4.3 proof: single-category run (default leisure=dog_park).
"""

import argparse
from app.contrib.osm_overpass_client import OsmOverpassClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="leisure")
    parser.add_argument("--value", default="dog_park")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    client = OsmOverpassClient()
    payloads = client.run({"tag": args.tag, "value": args.value})
    print(f"Discovered {len(payloads)} {args.tag}={args.value} payloads from OSM")
    if args.dry_run:
        for p in payloads[:5]:
            print(f"  {p.name} @ ({p.lat}, {p.lng})")


if __name__ == "__main__":
    main()
```

### §6.3 New `app/contrib/ingest_reconciler.py`

Cross-layer dedupe logic per strategy memo §4:

```
app/contrib/ingest_reconciler.py
"""Cross-layer ingest reconciler.

Each new EntityPayload from any layer (Google / OSM / city / specialized)
is reconciled against existing entities before write. Three match
strategies in priority order:

1. google_place_id exact match (definitive when both source + existing
   have it)
2. Geo proximity (within GEO_PROXIMITY_THRESHOLD_M, default 50m;
   operator-tunable)
3. Normalized name match (slugify)

Field-merge priority: operator-typed > Google > OSM > city > specialized.

Returns ReconcileResult(action, existing_id, merge_fields).
"""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any

from sqlalchemy.orm import Session

from app.contrib.ingest_base import EntityPayload
from app.db.models import Entity, Location

GEO_PROXIMITY_THRESHOLD_M = 50.0  # operator-tunable per strategy memo §8 Q3
SOURCE_PRIORITY = {
    "operator": 0,
    "google_places": 1,
    "osm": 2,
    "lhc_open_data": 3,
    "az_roc": 3,
    "npi_registry": 4,
    "usapickleball": 4,
}


@dataclass
class ReconcileResult:
    action: str                                # "insert" | "update" | "ambiguous"
    existing_id: str | None = None
    merge_fields: dict[str, Any] | None = None
    reason: str | None = None                  # debug breadcrumb


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0  # Earth radius in meters
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def reconcile_hit(db: Session, payload: EntityPayload) -> ReconcileResult:
    # Strategy 1: google_place_id exact match
    if payload.google_place_id:
        existing = db.query(Location).filter(Location.google_place_id == payload.google_place_id).first()
        if existing:
            return ReconcileResult(
                action="update",
                existing_id=existing.entity_id,
                merge_fields=_compute_merge_fields(db, existing.entity_id, payload),
                reason="google_place_id exact match",
            )

    # Strategy 2: geo proximity
    if payload.lat is not None and payload.lng is not None:
        candidates = db.query(Location).filter(
            Location.lat.isnot(None),
            Location.lng.isnot(None),
        ).all()
        for cand in candidates:
            if haversine_m(payload.lat, payload.lng, cand.lat, cand.lng) <= GEO_PROXIMITY_THRESHOLD_M:
                cand_entity = db.get(Entity, cand.entity_id)
                if cand_entity and slugify(cand_entity.name) == slugify(payload.name):
                    return ReconcileResult(
                        action="update",
                        existing_id=cand.entity_id,
                        merge_fields=_compute_merge_fields(db, cand.entity_id, payload),
                        reason="geo within 50m + name match",
                    )
                return ReconcileResult(
                    action="ambiguous",
                    existing_id=cand.entity_id,
                    reason="geo within 50m but name differs",
                )

    # Strategy 3: normalized name only (last resort)
    slug = slugify(payload.name)
    candidates = db.query(Entity).filter(Entity.name.isnot(None)).all()
    for cand in candidates:
        if slugify(cand.name) == slug:
            return ReconcileResult(
                action="ambiguous",
                existing_id=cand.id,
                reason="name match only (no geo)",
            )

    return ReconcileResult(action="insert", reason="no match")


def _compute_merge_fields(db: Session, existing_id: str, payload: EntityPayload) -> dict[str, Any]:
    """Field-merge priority: operator-typed > Google > OSM > city > specialized."""
    ent = db.get(Entity, existing_id)
    if not ent:
        return {}
    new_source_priority = SOURCE_PRIORITY.get(payload.source, 99)
    existing_source_priority = SOURCE_PRIORITY.get(ent.source or "", 99)
    # If existing source is operator-typed, preserve all operator fields
    if ent.source == "operator":
        return {}  # operator wins; no fields overwritten
    # Otherwise, merge: prefer fields from the higher-priority source
    if new_source_priority < existing_source_priority:
        return {"name": payload.name, "description": payload.description, "source": payload.source}
    # Lower priority: only update missing fields
    merge = {}
    if not ent.description and payload.description:
        merge["description"] = payload.description
    return merge
```

### §6.4 New tests for Phase 4.3

New test files:

`tests/test_phase4_osm_client.py` (~8-12 tests):
1. `build_query` produces valid Overpass-QL for `leisure=dog_park`
2. `OsmOverpassClient` is a `BaseIngestClient` subclass
3. `OsmOverpassClient.source_name == "osm"`
4. Mocked Overpass response → 3 `RawHit` objects with names + lat/lng
5. `dedupe_key` returns `"osm_node_12345"` shape
6. `wheelchair=yes` → `extension_payloads["ada_accessible"]=True`
7. `wheelchair=no` → `extension_payloads["ada_accessible"]=False`
8. `fee=no` → `extension_payloads["free"]=True`
9. `fee=yes` → `extension_payloads["free"]=False`
10. Empty Overpass response (no elements) → empty `RawHit` list
11. Overpass 5xx → empty `RawHit` list (no raise; per `with_retry` pattern)
12. OSM rate-limiter integration: `OSM_OVERPASS_LIMITER` is a `SourceLimiter`

`tests/test_phase4_ingest_reconciler.py` (~15-20 tests):
1. `haversine_m` returns ~0 for identical points
2. `haversine_m` returns ~111000 for 1-degree-latitude separation
3. `slugify("English Village") == "english-village"`
4. `slugify("Lake Havasu Aquatic Park!") == "lake-havasu-aquatic-park"`
5. `reconcile_hit` empty DB → "insert"
6. `reconcile_hit` existing entity with same `google_place_id` → "update"
7. `reconcile_hit` existing entity within 50m + matching name → "update"
8. `reconcile_hit` existing entity within 50m + mismatched name → "ambiguous"
9. `reconcile_hit` existing entity > 50m + matching name → "ambiguous" (name only; no geo)
10. `reconcile_hit` no match anywhere → "insert"
11. `_compute_merge_fields` operator-typed entity → no overwrites (empty merge)
12. `_compute_merge_fields` Google source over existing OSM source → name + description + source updated
13. `_compute_merge_fields` OSM source over existing Google source (lower priority) → only fill missing description
14. Idempotency: same hit twice → first inserts, second updates with empty merge (no field changes)
15. `GEO_PROXIMITY_THRESHOLD_M = 50.0` is the documented constant
16. `SOURCE_PRIORITY` priority order: operator < google_places < osm < city < specialized
17. Edge case: payload missing lat/lng skips strategy 2
18. Edge case: payload missing google_place_id skips strategy 1
19. Slugify handles unicode + punctuation cleanly
20. Reconciler does not bypass Phase 1D — it returns metadata; caller writes via `session.add(...)`

### §6.5 What NOT to do in Phase 4.3

- DO NOT ship OSM cron service in 4.3. Phase 4.4 close-out has the Railway-cron-service runbook; actual Railway service stand-up is operator action.
- DO NOT add Layer 3 / Layer 4 clients. Phase 5.
- DO NOT add new Python dependencies (no `overpy`, no `geopy`, etc.). `httpx` (existing) handles Overpass HTTP; haversine is ~10 lines of inline math.
- DO NOT migrate `entity.source` from singular string to JSON array in 4.3 unless operator approves at §2 row "Source provenance". Comma-separated string is V1 sufficient.
- DO NOT bypass Phase 1D dual-write. Reconciler returns metadata; caller (script) does `session.add(Provider(...))` for "insert" actions + `session.merge()` style for "update" actions.
- DO NOT change `GEO_PROXIMITY_THRESHOLD_M` based on speculation. 50m is the strategy memo §8 Q3 recommendation; operator tunes after real data lands.

---

## §7 Phase 4.4 deliverables (in dispatch order)

Author the operator runbook + close-out anchored edits + master plan ship-line + STATE.md refresh.

### §7.1 New `docs/operations/railway_scheduled_jobs_runbook.md`

Operator-facing runbook. Step-by-step:

```
docs/operations/railway_scheduled_jobs_runbook.md
# Railway Scheduled Jobs — Operator Runbook

> Spinning up a new Railway scheduled-job service for a scrape or
> background task. Sized for solo-founder operator workflow.

## When to use

Per `docs/maintainability/background_job_infrastructure_decision.md` §6.1,
Railway scheduled jobs handle the cron-like surface (scrape sweeps, aged-
row refresh, weekly re-verification flag passes, outbox redrive). For
event-triggered jobs (magic-link email, image processing), use FastAPI
BackgroundTasks (already wired in Phase 4.1).

## Pre-checks

1. Confirm the script you're scheduling is operator-runnable end-to-end
   from your local Windows venv. E.g.,
   `python -m scripts.places_discovery --category eat-drink --dry-run`
2. Confirm any env vars the script needs are listed in `.env.example`
   AND in Railway Variables (production). E.g., `GOOGLE_PLACES_API_KEY`,
   `DATABASE_URL`.
3. Confirm the script is idempotent — re-running on the same day must
   not produce duplicate rows. The Layer-1 dedupe-on-google-place-id +
   `app.contrib.ingest_reconciler.reconcile_hit` covers most cases.

## Steps

1. Railway dashboard -> create a new service in the same project as the
   main app
2. Source: connect to the same GitHub repo as the main app
3. Settings -> Service -> set the start command:
   `python -m scripts.places_discovery --category $CATEGORY` (or
   whatever script + flags)
4. Settings -> Cron schedule:
   `15 */6 * * *` (every 6h at minute 15 — matches the existing parks-
   rec-scrapes cadence from `.github/workflows/parks-rec-scrapes.yml`).
   See [crontab.guru](https://crontab.guru) for cron syntax.
5. Variables -> set service-specific env vars; the shared DATABASE_URL
   from the main service can be shared via Railway variable references
6. Click Deploy
7. Wait for first scheduled run; check Logs tab for any errors
8. Verify DB writes via Railway Postgres Query console:
   `SELECT COUNT(*) FROM entities WHERE source = '<source_name>' AND
   created_at > NOW() - INTERVAL '1 day'`

## Monitoring

- Sentry: tag `background-jobs` captures retry breadcrumbs from
  `app/core/background.py::with_retry` (Phase 4.1)
- Per-run summary: each scrape writes a markdown summary to
  `docs/scrape_logs/<source>_<YYYY-MM-DD>.md`. Operator reviews weekly
- Failure alert: if a scrape returns 0 new rows OR > 50% errors,
  Sentry breadcrumb fires; operator gets email digest

## Cost

Railway scheduled-job services bill at the standard service rate. Per-
category cron services = N services = N bill lines. Operator decides
per-category vs parameterized-with-env (one service driven by $JOB_NAME):
- Per-category: clearer logs, finer-grained control, more bill lines
- Parameterized: one bill line, harder to debug per-category failures

## Rollback

If a scheduled job is misbehaving:
1. Railway dashboard -> Service -> Settings -> Cron schedule -> set to
   empty (pauses the cron; keeps the service)
2. Or: Service -> Settings -> Suspend
3. Push fix to main; re-enable cron when verified

## Reference

- `docs/maintainability/background_job_infrastructure_decision.md` (Option A)
- `docs/maintainability/layered_scrape_strategy.md` (per-layer cadences)
- `app/core/background.py` (retry-wrapper + Sentry breadcrumbs)
- `.github/workflows/parks-rec-scrapes.yml` (GitHub-Actions cron precedent)
```

### §7.2 New `docs/operations/scrape_logs_template.md`

Per-run summary template:

```
docs/operations/scrape_logs_template.md
# Scrape Run Log Template

Copy to `docs/scrape_logs/<source>_<YYYY-MM-DD>.md` per scrape run.

## Run identification

- Source: <google_places | osm | lhc_open_data | az_roc | ...>
- Run timestamp (UTC): <ISO 8601>
- Triggered by: <cron schedule | manual operator | workflow_dispatch>
- Script: <scripts/places_discovery.py --category ...>

## Counts

- Total queries issued: <N>
- Total rows discovered: <N>
- Total rows new (inserted): <N>
- Total rows updated (reconciler matched existing): <N>
- Total rows skipped (dedupe within same run): <N>
- Total errors: <N>
- Sample errors (first 3):
  - <error 1>
  - <error 2>
  - <error 3>

## Duration

- Run elapsed time: <HH:MM:SS>

## Notes

<free-form operator notes; anomalies; rate-limit hits; etc.>
```

### §7.3 Anchored edit on image-processing call site

Locate via Grep (`Pillow|PIL|process_uploaded_photo|photo_processing`); wrap in `with_retry`. Same shape as Phase 4.1 magic-link integration.

### §7.4 (Optional, flag in §13) Anchored edits on remaining BackgroundTasks call sites

`app/api/routes/chat.py:62` + `app/contrib/enrichment.py:18` per §4.3 above. Skip is acceptable; flag rationale in §13.

### §7.5 Anchored edit on `docs/maintainability/master_build_plan.md` §4 Phase 4

Append SHIPPED 2026-05-XX header + four-sub-phase incremental list per Phase 1 / Phase 2 / Phase 3 precedent.

### §7.6 Anchored edit on `docs/STATE.md`

Production block: refresh `Current main HEAD (origin)` + `Currently deployed in production` + `Build phase` + `Pytest` + `Alembic head` lines per Phase 4 ship. Recently shipped §1: prepend the Phase 4 narrative.

### §7.7 New tests for Phase 4.4

New test file `tests/test_phase4_close_out.py` (~5-10 tests):
1. `app/core/background.py::with_retry` is wired into the magic-link send path (grep verification)
2. `app/core/background.py::with_retry` is wired into the image-processing path
3. `_hourly_cleanup_loop` at `app/main.py:251` still exists + signature unchanged
4. `app/main.py:lifespan` still schedules `_hourly_cleanup_loop` via `asyncio.create_task`
5. `docs/operations/railway_scheduled_jobs_runbook.md` exists + is non-empty
6. `docs/operations/scrape_logs_template.md` exists + is non-empty
7. Import-chain regression: `from app.core.background import with_retry` + `from app.contrib.google_places_scraper import GooglePlacesClient` + `from app.contrib.osm_overpass_client import OsmOverpassClient` + `from app.contrib.ingest_reconciler import reconcile_hit` all succeed without gotcha #17 cycle

### §7.8 What NOT to do in Phase 4.4

- DO NOT spin up Railway services in 4.4. Cursor doesn't have Railway credentials; operator stands up services per the runbook.
- DO NOT ship Phase 5 deliverables in 4.4. Phase 4.4 is close-out; Phase 5 is the next dispatchable lane.
- DO NOT modify `_hourly_cleanup_loop`. It's the canonical reference.
- DO NOT delete or refactor any of the Phase 4.1/4.2/4.3 modules in 4.4 close-out. They're committed in earlier sub-phases; 4.4 only adds + documents.

---

## §8 What's already locked vs what's not

Locked (do not relitigate):
- Option A over Option B/C (background-jobs decision memo §5)
- 5-layer scrape strategy (strategy memo §2)
- All scrape clients write via Phase 1D dual-write helpers (Phase 1D + Session-22)
- Hook registration in package `__init__.py` (gotcha #17)
- No new Python dependencies in 4.1/4.2/4.3
- BackgroundTasks retry wrapper signature (`with_retry(fn, *args, max_attempts=3, backoff_initial_s=1.0, **kwargs)`)
- `_hourly_cleanup_loop` stays at `app/main.py:251`
- `BaseIngestClient` abstract interface (4 methods)
- Reconciler 3-strategy match order (google_place_id → geo proximity → name)
- Field-merge priority: operator > Google > OSM > city > specialized
- GEO_PROXIMITY_THRESHOLD_M = 50.0 default
- Operator monitoring: file-based scrape logs + Sentry breadcrumbs

Open (must lock BEFORE Phase 4.1 dispatches — see §9):
- (none — Outbox table decision locked SHIP-OUTBOX-NOW at session-23 dispatch authoring per §2 row)

Open (deferred to Phase 5 / V1.5):
- Layer-3 city/state open data clients (LHC Parks & Rec, AZ ROC, Mohave County GIS, AZ Office of Tourism)
- Layer-4 specialized API clients (NPI extension, USAPickleball, PDGA, AMA, etc.)
- Cache warming asyncio loop
- Outbox admin form (visibility into must-not-lose jobs)
- `entities.sources` JSON-array column (if comma-separated string proves insufficient)
- Per-source scrape_run_log DB table (if file-based logs prove insufficient)

---

## §9 Acceptable deviations (open-doors for Cursor)

### Phase 4.1

- **Outbox table in 4.1 vs defer — LOCKED SHIP-OUTBOX-NOW at session-23.** No deviation invitation here; the migration + ORM class + redrive script + magic-link Outbox-row wrap are all in 4.1 scope. See §2 row for context.
- **`with_retry` Sentry breadcrumb shape.** Brief specifies category=`"background-jobs"` + level=`"warning"` per retry + level=`"error"` on exhaustion. If Cursor finds the existing `app/contrib/rate_limiter.py` Sentry shape differs (e.g., different category name), flag in §13. Consistency with existing Sentry usage in this codebase is more important than the exact category string.
- **`with_retry_async` vs sync-only.** Brief ships both. If Cursor finds no current async consumer + skipping the async variant simplifies the module, flag in §13. (Recommendation: ship both for forward-compat; the async variant is ~30 lines and ships at no real cost.)
- **Anchored edits on existing BackgroundTasks call sites in 4.1 vs defer to 4.4.** Brief recommends defer-to-4.4. If Cursor takes 4.1 with bandwidth to spare, wrapping `scan_and_save_mentions` + `enrich_contribution` is acceptable; flag rationale in §13.
- **Outbox redrive idle threshold (30s) vs different value.** Brief specifies 30s per design memo §6.2. If Cursor finds a tighter or looser threshold makes more sense given Resend's typical latency, flag in §13.
- **`Outbox.state` enum values.** Brief specifies `pending | in_flight | delivered | failed`. If Cursor wants a 5th state (e.g., `paused`) for operator-paused redrive, flag in §13. (Recommendation: 4 states is V1 sufficient.)
- **`Outbox.payload` JSON shape.** Per-kind shape varies; brief specifies a free-form JSON column with caller-derived idempotency hash. If Cursor wants type aliases per kind (e.g., `MagicLinkPayload` TypedDict), flag in §13 — likely worth it for clarity; the migration is unchanged.

### Phase 4.2

- **`BaseIngestClient` abstract-method count.** Brief specifies 4 methods (`discover`, `enrich`, `dedupe_key`, `to_entity_payload`). If Cursor finds a fifth method (e.g., `validate_payload` for pre-write validation) is unavoidable, flag in §13. Recommendation: 4 is sufficient; validation can live on the caller side.
- **`run_discovery` + `run_enrichment` orchestration method names.** Brief specifies these names per the existing scripts. If Cursor finds a cleaner single `run(query)` method on the base + per-subclass override is cleaner, flag in §13. (Recommendation: split is clearer for the Google Places pattern; OSM has no separate enrichment so its `run` would be discovery-only.)
- **`EntityPayload.extension_payloads` shape.** Brief uses free-form `dict[str, Any]`. If Cursor finds typed extension payloads (e.g., `LocationExtension`, `ContactPointExtension`) cleaner, flag in §13. Recommendation: free-form for V1; type aliases as Phase 5 fill-in adds new layer-specific shapes.
- **`google_types_mapping.py` initial coverage.** Brief shows ~28 types. If Cursor wants to expand to match the full Google Places type list, flag in §13. Recommendation: ship the initial subset + grow incrementally; not every Google type maps to our 12 categories.
- **`scripts/places_discovery.py --category` flag.** Brief invites the flag. If Cursor finds the existing script's discovery is already category-aware via some other mechanism, flag in §13.
- **Refactor scope of `places_client.py`.** Brief says don't refactor it. If Cursor finds the refactor naturally extends into `places_client.py` (e.g., a method needs to move from `places_client.py` to `google_places_scraper.py`), flag in §13.

### Phase 4.3

- **OSM single-category default.** Brief recommends `leisure=dog_park`. If Cursor wants a different single-category proof, flag in §13. Recommendation: dog_park is small + well-mapped + low risk; perfect for the proof-of-concept.
- **Lake Havasu bounding box.** Brief uses `(34.43, -114.41, 34.59, -114.30)` per strategy memo §3.2. If Cursor finds a tighter or different box more accurate (e.g., excludes Topock + Havasu Landing), flag in §13. Recommendation: strategy memo box is the locked one; tuning is V1.5+ operator concern.
- **`ingest_reconciler.py` strategy order.** Brief specifies `google_place_id → geo → name`. If Cursor wants a different order or different criteria (e.g., OSM stable ID also serves as definitive match), flag in §13. Recommendation: stay with brief order; OSM stable ID is layer-2-only and doesn't generalize.
- **`SOURCE_PRIORITY` table.** Brief specifies 5 sources. If Cursor wants explicit "unknown" or "manual" entries, flag in §13.
- **`entities.sources` migration.** Brief recommends defer (comma-separated string in `entity.source` suffices for V1). If Cursor finds a reason to migrate now (e.g., reconciler logic gets too tangled with comma-separated parsing), flag in §13 — migration is acceptable but adds ~1 day.

### Phase 4.4

- **Optional Anchored edits on `scan_and_save_mentions` + `enrich_contribution`.** Skip is acceptable; flag rationale.
- **`docs/operations/` directory creation.** Brief creates two new docs there. If the directory doesn't yet exist (`Glob docs/operations/`), Cursor creates it. If a different naming pattern is in use elsewhere in `docs/`, flag in §13.
- **Image-processing retry-wrapper integration in 4.4 vs deferred.** Brief recommends ship-in-4.4. If Cursor finds the image-processing path needs significant refactor to accept `with_retry` cleanly, flag in §13 + defer to a follow-up commit; the 4.4 close-out doesn't gate on this.

---

## §10 Risk register (12 rows + monitoring)

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| 1 | `app/core/background.py` import-time cycle (gotcha #17 reintroduction) | M | H | No `app/db/models` imports at module top; lazy-import in `deliver_outbox_row`; subprocess import test in §4.4 test 25 |
| 2 | `Outbox(Base)` migration fails on Postgres due to JSON column type issue | L | H | Use `sa.JSON()` not Postgres-only `JSONB`; mirror Phase 3.1 `crowd_notes` precedent at `entities` table |
| 3 | `with_retry` swallows exceptions and Caller doesn't know task failed | M | M | Sentry breadcrumb on exhaustion + structured log line + return None; idempotency contract documented in module docstring; caller-side null check encouraged |
| 4 | Magic-link send rate-limit hit (Resend 429) → retry storm | L | M | `with_retry` `max_attempts=3` + exponential backoff (1s, 2s, 4s); Resend's docs say generous limits at launch volume; design memo §8 confirms 100/day free tier well above expected magic-link volume |
| 5 | Layer-1 refactor changes DB row shape unintentionally | M | H | Existing places-scraper tests must remain green; new `test_phase4_ingest_client_interface.py` test 13 (refactor regression) verifies same log output; manual smoke deferred-to-operator |
| 6 | `google_types_mapping` returns `(None, None)` for too many real Google responses | M | M | Operator queue surfaces NULL category_slug; Phase 5 fill-in adds more mappings as discovered |
| 7 | OSM Overpass server unavailable / rate-limited during 4.3 testing | L | M | Tests mock Overpass response (don't hit live API); operator-runnable smoke deferred-to-operator |
| 8 | Reconciler geo-proximity false-positive (two genuinely-different entities within 50m) | M | M | Returns "ambiguous" → operator review queue (admin form surface, Phase 5); does NOT auto-merge; conservative default |
| 9 | Reconciler name-only match across layers wrongly merges entities | M | M | Name-only matches return "ambiguous" by default; only name+geo merges are auto-applied as "update"; conservative default |
| 10 | Reconciler operator-typed-fields-win logic incorrectly applies operator-typed lock to non-operator sources | L | M | `_compute_merge_fields` checks `ent.source == "operator"` exactly; tests cover this case (test 11) |
| 11 | Railway scheduled-job service spins up + immediately fails due to missing env vars | M | L | Operator runbook §pre-checks step 2 calls this out explicitly; service goes red in dashboard; no production impact since main app is unaffected |
| 12 | Background-jobs framework lands but no consumer wires in 4.1/4.4 → dormant infra | L | L | Magic-link integration in 4.1 is the V1 anchor consumer; image processing in 4.4 is the second; both exercise `with_retry` end-to-end |

---

## §11 What NOT to do (Phase 4 overall — design rails)

- DO NOT relitigate the locked decisions in §2.
- DO NOT propose Option B (Celery + Redis) in Phase 4. Migration path is documented; trigger is documented; not in scope until triggered.
- DO NOT add Celery / Redis / Dramatiq / RQ / Beat to `requirements.txt`.
- DO NOT add `overpy` / `geopy` / specialized scraping libraries. `httpx` + a few inline helpers handle 4.3 OSM scope.
- DO NOT bypass Phase 1D dual-write helpers in any scrape client. Every new Provider/Event/Program row goes via `session.add(...)`; the centralized `before_flush` hook auto-promotes to Entity + extensions.
- DO NOT register `before_flush` / module-import-time hooks anywhere except `app/db/__init__.py` (for ORM-level hooks) or `app/contrib/__init__.py` (for contrib-only hooks if any). Gotcha #17 is the canonical lesson.
- DO NOT modify `app/contrib/rate_limiter.py`. Interface is stable; reuse directly.
- DO NOT modify `_hourly_cleanup_loop` at `app/main.py:251`. It's the canonical reference, not a refactor target.
- DO NOT change the magic-link email body, recipient address, or Resend API call semantics. Phase 4 wraps the existing send in retries; outcome is unchanged.
- DO NOT change the DB rows produced by `places_discovery` + `places_enrichment` pre-refactor. 4.2 is pure refactor; same rows out.
- DO NOT touch the chat-route response shape. Phase 4 ships zero user-visible surface changes.
- DO NOT add admin-form surfaces in Phase 4. Outbox visibility, scrape log inspection, operator review queue — all Phase 5 + V1.5 territory.
- DO NOT propose ENUM types (Postgres-only) for any new column. VARCHAR + CHECK constraint per Phase 2A.1 precedent.
- DO NOT use `sa.text("1")` / `sa.text("0")` for Boolean defaults. Phase 1A's `5132162` hotfix is the canonical lesson.
- DO NOT add raw SQL inside `op.execute()` unless verified portable across Postgres + SQLite.
- DO NOT use embedded double-quotes inside `-m '...'` commit body bodies on PowerShell. Gotcha #16; em-dashes or `->` for emphasis.
- DO NOT run `git ...` from the bash sandbox against the working tree. Gotcha #15. Read + Grep + Glob are Windows-authoritative.
- DO NOT push without operator approval. Rules 2 + 12.
- DO NOT modify existing tables beyond the explicit columns/changes in §4 (Outbox table only, IF that path is locked). Touching ENTITY columns, providers, events, programs, photos, districts, alert_subscriptions, alerts_dispatched, external_conditions_cache, peer_recommendations, etc. requires a separate brief.
- DO NOT propose a parallel Phase 4 sub-phase (e.g., Phase 4.5 cache warming) without explicit brief amendment. Phase 4 has four sub-phases; Phase 5 fills the framework.
- DO NOT dispatch sub-agents during 4.1/4.2/4.3/4.4 sessions. Each sub-phase is a single Cursor session.

---

## §12 Final report format (for §13)

After Phase 4.1 OR 4.2 OR 4.3 OR 4.4 ships (HALT and report after EACH), produce a report with:

1. **Sub-phase identifier** (4.1 background-jobs scaffold OR 4.2 layered-scrape interface + Google Places refactor OR 4.3 OSM client + reconciler OR 4.4 close-out)
2. **§0 baseline as observed:**
   - `git log --oneline -10` top SHAs
   - `git status` clean state
   - `python -m alembic heads` single head + revision name
   - `python -m alembic current` (note any drift)
   - pytest collected count (entering)
3. **Files created** — table of `path | role`
4. **Files modified** — table of `path | change description`
5. **Migration:** Revision ID + chain-off ID (4.1 only IF Outbox path chosen; 4.2/4.3 no migration unless `entities.sources` path chosen in 4.3; 4.4 no migration). Postgres-only DDL flagged. CHECK constraints listed. Indexes listed.
6. **Tests added** — file path + brief test list per test file
7. **Final pytest count** (passed / skipped); diff vs entering baseline
8. **`alembic upgrade head` + `alembic downgrade -1 && alembic upgrade head` cycle** results (if migration present)
9. **Ruff** clean status
10. **Manual smoke** (operator-runnable; Cursor doesn't execute):
    - 4.1: magic-link request → email landed
    - 4.2: `python -m scripts.places_discovery --category eat-drink --dry-run` produces same log output as pre-refactor
    - 4.3: `python -m scripts.osm_overpass_pull --tag leisure --value dog_park --dry-run` returns parseable Overpass response
    - 4.4: Stand up first Railway scheduled-job service per runbook (operator decides when)
11. **Pragmatic deviations from §9** — flagged + rationale + impact assessment
12. **Surprises / operator notes** — anything unexpected; gotcha #17 cycle risks; layer-client interface friction; reconciler edge cases; backfill counts if any
13. **Git status** — confirm no `git add` / commit / push / amend was attempted (Rule 2 + 12)
14. **Next** — Phase 4.2 dispatchable if 4.1 shipped; Phase 4.3 dispatchable if 4.2 shipped; Phase 4.4 dispatchable if 4.3 shipped; Phase 5 dispatchable if 4.4 closes out Phase 4.

The §13 report is what the operator pastes back to the Cowork primary chat for review against the §4.5 / §5.6 / §6.5 / §7.8 acceptance gates.

---

*Authored by Cowork primary at session-23, 2026-05-13, after the Phase 3 production deploy (Railway 6-migration walk clean at `e1f2a3b4c5d6`) + Phase 1D circular-import bug fix (`5faa37c`). Phase 4 closes out when 4.4 ships; Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI) becomes the next dispatchable lane. The Outbox decision-lock at §2 row must close before Phase 4.1 dispatches; the operator decides "ship Outbox now" (recommended — magic-link is must-not-lose) vs "defer to V1.5" at paste-time. The dispatch prompt at `outputs/cursor_dispatch_prompt_phase_4_1.md` SHA-patches the chosen answer.*
