# Cursor Dispatch Prompt — Phase 4.2 (layered-scrape client interface + Google Places refactor: app/contrib/ingest_base.py + app/contrib/google_places_scraper.py + app/contrib/google_types_mapping.py + anchored edits on scripts/places_discovery.py + scripts/places_enrichment.py)

> Short paste-into-Cursor prompt for Phase 4.2 dispatch — the layered-scrape framework + Google Places refactor sub-phase of Phase 4 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_4_background_jobs_scrape.md` (read end-to-end, especially §0 + §3 + §5 + §8 + §9 + §10 + §11 + §12). Phase 4.2 is the framework + refactor sub-phase: new abstract `BaseIngestClient` interface in `app/contrib/ingest_base.py` + new `app/contrib/google_places_scraper.py` library module extracted from the existing `scripts/places_discovery.py` + `scripts/places_enrichment.py` + new `app/contrib/google_types_mapping.py` operator-maintainable types-mapping table + anchored edits on the two existing scripts to call the library + (recommended) `--category` flag on `scripts/places_discovery.py` per design memo §6.1 step 1 + ~10-15 new tests. **No new layer-2/3/4 clients, no reconciler, no chat-surface changes, no migrations, no new Python deps** — all of that is 4.3 / 4.4.
>
> **Gating dependency:** Phase 4.1 of the master build plan COMPLETE on origin (`91cd37b` feat substantive + `f5b3953` ruff autofix + `a75cfe8` docs ship-line) — `app/core/background.py` retry-wrapper + Outbox table + magic-link wrap + `tests/test_phase4_background.py` (+28) all on origin. Phase 4.2 does NOT depend on Phase 4.1 import-wise (the layered-scrape clients write to ENTITY via Phase 1D dual-write helpers — `app/db/__init__.py:36-38` centralized seam — NOT via `app/core/background.py`'s `BackgroundTasks` retry helpers), but the brief authored both sub-phases as Phase 4 internals so 4.2 inherits 4.1's import-discipline lessons (gotcha #17 cure — package `__init__.py` for cross-module hook registration; lazy-import in leaf modules; carry forward from session-22 `5faa37c` + session-23 `91cd37b`).
>
> **No operator prereq for Phase 4.2.** Phase 4.2 is pure application code — refactor + new abstract interface + new mapping table + thin script wrappers. No new Railway services, no new env vars, no Resend changes, no Cloudflare changes, no R2 changes. The two existing scrape scripts (`scripts/places_discovery.py` + `scripts/places_enrichment.py`) already work end-to-end against Google Places API; Phase 4.2 is a behavior-preserving refactor — same DB rows out, same rate-limit semantics, same idempotency posture (resume-safe `load_processed_ids` pattern preserved verbatim).
>
> **Operator decision-lock BEFORE paste:** none. The brief §9 deviation invitations for 4.2 (BaseIngestClient method count 4 vs 5, run_discovery/run_enrichment method names, EntityPayload shape, google_types_mapping initial coverage, --category flag invitation, places_client.py refactor scope) are all "flag in §13 if you deviate" style — no hard pre-dispatch locks. Recommendation baked into the body below: ship the `--category` flag on `scripts/places_discovery.py` per brief §5.4 + design memo §6.1 step 1 (Phase 4.4 close-out wires per-category cron services that depend on this flag; deferring would block 4.4).
>
> **Author note:** this prompt was authored at session-23 close after Phase 4.1 shipped on origin. The §0 baseline values reference the post-Phase-4.1 state — `git log --oneline -10` top SHA is `a75cfe8` (session-23 docs close-out); alembic head is `0a1b2c3d4e5f` (Phase 4.1 outbox table); pytest baseline is **1733** (1732 passed + 1 skipped + 30 subtests).

---

```
Read outputs/cursor_brief_phase_4_background_jobs_scrape.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3 (sub-phase
boundaries), §5 (Phase 4.2 deliverable list -- the layered-scrape
client interface + Google Places refactor sub-phase), §8 (locked vs
open), §9 (acceptable deviations), §10 (risk register), §11 (what
NOT to do), §12 (final report format).

Phase 4.1 of the master build plan COMPLETE on origin at `a75cfe8`
(session-23 docs close-out; substantive feat at `91cd37b`, ruff
autofix at `f5b3953`). Run `git log --oneline -10` and report the
top SHAs. Pytest collect baseline going in is **1733** tests (1732
passed + 1 skipped + 30 subtests). Alembic head is **0a1b2c3d4e5f**
(Phase 4.1 outbox table; the post-4.1 origin tip, NOT yet deployed
to production -- production prod alembic head is still
`e1f2a3b4c5d6` per the session-22 deploy).

Ship Phase 4.2 ONLY per §3 + §5 of the brief -- new
app/contrib/ingest_base.py abstract BaseIngestClient interface +
new app/contrib/google_places_scraper.py library module extracted
from the existing scripts/places_discovery.py +
scripts/places_enrichment.py + new app/contrib/google_types_mapping.py
operator-maintainable types-mapping table + anchored edits on the
two existing scripts to call the library + `--category` flag on
scripts/places_discovery.py + ~10-15 new tests in
tests/test_phase4_ingest_client_interface.py. **No layer-2/3/4
clients, no reconciler, no chat-surface changes, no migrations,
no new Python deps** -- 4.3 + 4.4 close out the rest.

NO OPERATOR DECISION-LOCK (per brief §9 -- all Phase 4.2 deviation
invitations are "flag in §13 if you deviate" style). One
recommendation baked in:
- Ship the `--category` flag on scripts/places_discovery.py per
  brief §5.4 + design memo §6.1 step 1 (Phase 4.4 close-out wires
  per-category Railway-cron services that depend on this flag;
  deferring blocks 4.4).

ORDER MATTERS WITHIN PHASE 4.2:
1. First: read the docs + source files in brief §0 step 6 + step 7.
   Critical reads: brief §5 end-to-end (the four sub-deliverable
   blocks); existing `scripts/places_discovery.py` end-to-end
   (~264 lines; httpx + GOOGLE_PLACES_LIMITER usage, paginated
   discovery loop, JSONL output writers); existing
   `scripts/places_enrichment.py` end-to-end (~349 lines; resume-
   safe load_processed_ids pattern at lines 80-100, Place Details
   field mask, flattened-row writers); `app/contrib/rate_limiter.py`
   end-to-end (the SourceLimiter + GOOGLE_PLACES_LIMITER that
   Phase 4.2 reuses verbatim -- DO NOT modify); `app/contrib/
   places_client.py` (existing Phase 5.2 provider-enrichment client
   -- the refactored library may borrow shape from it but the
   existing scripts use httpx + GOOGLE_PLACES_LIMITER directly,
   NOT places_client.py); `app/db/__init__.py` (the Phase 1D
   hook-registration seam; gotcha #17 cure carried from
   session-22); `app/db/entity_dual_write.py`
   (`create_provider_and_entity` helper that the refactored library
   either calls directly OR feeds via session.add(Provider(...))
   to let the centralized before_flush hook auto-promote);
   `app/core/background.py` (the Phase 4.1 module -- read its
   gotcha-#17 cure docstring; Phase 4.2 leaf modules follow the
   same lazy-import discipline if they need any ORM class at
   module scope).
2. Then: new `app/contrib/ingest_base.py` per brief §5.1.
   Abstract BaseIngestClient class with 4 abstract methods:
   discover(query) -> list[RawHit], enrich(hit) -> EnrichedHit,
   dedupe_key(hit) -> str, to_entity_payload(hit) -> EntityPayload.
   Type aliases for RawHit / EnrichedHit / EntityPayload (use
   @dataclass for clarity; same shapes as brief §5.1 spec).
   Docstring documents the layered-scrape pattern + the Phase 1D
   dual-write seam (clients write via session.add(Provider/Event
   /Program) which the centralized before_flush hook auto-
   promotes; clients do NOT bypass into entities/extensions
   tables directly). **CRITICAL: do NOT import from
   app/db/models at module top.** ingest_base is pure-Python
   dataclasses + ABC; no ORM dependency at module top. If a
   subclass needs ORM access for write semantics, it lazy-imports
   inside its own methods (mirror Phase 4.1's app/core/background.py
   discipline).
3. Then: new `app/contrib/google_types_mapping.py` per brief §5.3.
   Module-level dict `_PRIMARY_TYPE_MAP: dict[str, tuple[str,
   str | None]]` mapping Google Places `types[]` primary value ->
   (category_slug, place_type) where place_type in {"commercial",
   "place", None}. Initial coverage ~28 entries per brief §5.3
   table (restaurant, cafe, bar, plumber, doctor, dentist,
   lodging, store, gas_station, park, dog_park, marina, beach,
   veterinary_care, school, gym, library, city_hall, etc.).
   Pure function `map_google_types_to_slug_and_place_type(types:
   list[str]) -> tuple[str | None, str | None]` -- tries primary
   type first, fallbacks through the rest, returns (None, None)
   if no match (operator-queue surface for review per Phase 5).
4. Then: new `app/contrib/google_places_scraper.py` per brief §5.2.
   Library module extracting the shared logic from
   scripts/places_discovery.py + scripts/places_enrichment.py.
   GooglePlacesClient class subclasses BaseIngestClient; source_name
   = "google_places"; reuses GOOGLE_PLACES_LIMITER for QPS pacing
   + retry on 429/5xx (DO NOT rewrite rate_limiter.py); preserves
   the resume-safe load_processed_ids pattern verbatim. Methods:
   discover(query) -- paginated Text Search; enrich(hit) -- Place
   Details fetch via place_id; dedupe_key(hit) -- returns
   google_place_id; to_entity_payload(hit) -- maps Google response
   to source-agnostic EntityPayload using google_types_mapping
   for category_slug + place_type. Two thin orchestration methods:
   run_discovery(category, dry_run) and run_enrichment(dry_run) --
   match the existing script entry-point shapes so the script
   wrappers in step 5 are 5-10 lines each.
5. Then: anchored Edits on scripts/places_discovery.py +
   scripts/places_enrichment.py per brief §5.4. Replace inline
   discovery/enrichment orchestration with thin wrappers that
   instantiate GooglePlacesClient + call its run_discovery() /
   run_enrichment() methods. **Texture rule from brief §1:** same
   DB rows out (no schema change, no row-shape change), same log
   lines (preserve verbatim where possible), same rate-limit
   semantics. Add `--category` flag to places_discovery.py
   (recommendation baked in -- brief §5.4 + design memo §6.1
   step 1). Update the script docstrings to point at the new
   library module + note that the scripts are now thin entry
   points.
6. Then: new tests per brief §5.5 in
   tests/test_phase4_ingest_client_interface.py (~10-15 tests):
     - BaseIngestClient is abstract -- instantiating directly
       raises TypeError
     - Subclass with missing discover / enrich / dedupe_key /
       to_entity_payload raises TypeError (4 separate tests OR
       parametrized)
     - GooglePlacesClient is a BaseIngestClient subclass
     - GooglePlacesClient.source_name == "google_places"
     - GooglePlacesClient.dedupe_key() returns google_place_id
       exactly
     - map_google_types_to_slug_and_place_type for ["restaurant"]
       returns ("eat-drink", "commercial")
     - map_google_types_to_slug_and_place_type for ["dog_park",
       "park"] returns ("outdoors-parks-trails", "place")
       (primary type wins)
     - map_google_types_to_slug_and_place_type for unknown types
       returns (None, None)
     - GooglePlacesClient.to_entity_payload produces an
       EntityPayload with source="google_places" + correct
       category_slug + correct place_type
     - GooglePlacesClient uses GOOGLE_PLACES_LIMITER for rate-
       limiting (verify via attribute introspection OR via
       patching the limiter and asserting .acquire() was called)
     - **Import-chain regression:** `from
       app.contrib.google_places_scraper import GooglePlacesClient`
       does not trigger gotcha #17 cycle (subprocess import test
       mirroring tests/test_phase1d_dual_write.py::test_scraper_
       entry_point_import_chain_does_not_cycle shape OR
       tests/test_phase4_background.py::test_background_module_
       does_not_import_models_at_module_top shape)
     - Refactor regression: scripts/places_discovery.py --dry-run
       produces the same JSONL output as pre-refactor (use a
       fixture if available, or skip with deferred-to-operator
       note in §13)
7. After all of the above: confirm full pytest stays green (1733
   floor + 10-15 net-new), ruff clean. Manual smoke deferred-to-
   operator (`python -m scripts.places_discovery --category
   eat-drink --dry-run` produces same log output as pre-refactor;
   `python -m scripts.places_enrichment --limit 10 --dry-run`
   produces same log output as pre-refactor) -- flag in §13.

POSTGRES COMPATIBILITY (carried forward from brief §11 + every
prior phase brief):
- The bash sandbox + tests run SQLite; production runs Postgres.
- NO migration in Phase 4.2 (pure application code).
- If for any reason a migration is unavoidable (it isn't), use the
  Phase 4.1 outbox migration as the recent-precedent shape:
  sa.JSON / sa.String + CHECK / sa.func.now() defaults / no
  Postgres-only types / no raw op.execute() / no sa.text("1") /
  sa.text("0") Boolean defaults.

DEVIATION INVITATIONS (per brief §9 Phase 4.2):
- BaseIngestClient abstract-method count -- brief specifies 4
  methods. If you find a fifth method (e.g., validate_payload for
  pre-write validation) is unavoidable, flag in §13. Recommendation:
  4 is sufficient; validation can live on the caller side.
- run_discovery + run_enrichment vs single run(query) method --
  brief specifies the split shape per the existing scripts. If
  a cleaner single run(query) on the base + per-subclass override
  reads better, flag in §13. (Recommendation: split is clearer
  for Google Places; OSM in 4.3 has no separate enrichment so
  its run() would be discovery-only.)
- EntityPayload.extension_payloads dict[str, Any] free-form vs
  typed -- brief uses free-form. If typed extension payloads
  (LocationExtension / ContactPointExtension dataclasses) read
  cleaner, flag in §13. Recommendation: free-form for V1; type
  aliases land naturally as Phase 5 fill-in adds new layer-
  specific shapes.
- google_types_mapping.py initial coverage (~28 types per brief
  §5.3). If you want to expand the table to match the full Google
  Places type list at dispatch time, flag in §13. Recommendation:
  ship the initial subset + grow incrementally as Phase 5 surfaces
  unmapped types in the operator queue (None, None) return.
- `--category` flag on scripts/places_discovery.py -- baked-in
  recommendation per design memo §6.1 step 1. If the existing
  script already has category-aware discovery via some other
  mechanism (e.g., a config file flag), flag in §13.
- Refactor scope of app/contrib/places_client.py -- brief §5.6
  says don't touch it. If the refactor naturally pulls a method
  from places_client.py into google_places_scraper.py (or vice
  versa), flag in §13. Recommendation: keep places_client.py as-
  is; it's the Phase 5.2 provider-enrichment client and stays
  separate from the Layer-1 scrape library.

WHAT NOT TO DO (per brief §10 + §11):
- Don't add new layer clients in 4.2 (OSM is 4.3; Layers 3/4 are
  Phase 5).
- Don't add a cross-layer reconciler in 4.2 (that's 4.3).
- Don't modify app/contrib/rate_limiter.py. The SourceLimiter
  interface is stable per its own docstring.
- Don't modify app/contrib/places_client.py. It's the Phase 5.2
  provider-enrichment client and stays parameterized for
  Provider scrapes.
- Don't change the DB rows produced by places_discovery +
  places_enrichment pre-refactor. Pure behavior-preserving
  refactor -- same Provider rows out, same Entity + Location +
  ContactPoint extension rows via the Phase 1D before_flush hook,
  same idempotency posture.
- Don't bypass the Phase 1D dual-write seam. Every new Provider/
  Event/Program row goes via session.add(Provider(...)) so the
  centralized before_flush hook in app/db/__init__.py auto-
  promotes to Entity + extensions. Direct entity-table inserts
  are forbidden -- they break the legacy-table + Entity-table
  consistency the entire Phase 1 lane was built to enforce.
- Don't add module-import-time hooks anywhere except
  app/db/__init__.py. Gotcha #17 is the canonical lesson;
  session-22 + session-23 carry forward.
- Don't import from app/db/models at module top in
  app/contrib/ingest_base.py or app/contrib/google_places_scraper.py.
  Lazy-import inside methods if needed. Prevents reintroducing
  the gotcha #17 cycle pattern.
- Don't add new Python dependencies. httpx is already present;
  reuse it for any HTTP needs.
- Don't modify chat-route response shape, provider profile
  render, /api/search response, home page, or any other user-
  visible surface. Phase 4 ships zero user-visible surface
  changes.
- Don't add admin-form surfaces for scrape-log inspection or
  operator review queues. V1.5+.
- Don't propose moving to a different rate-limiter implementation.
  The SourceLimiter is stable.
- Don't dispatch Phase 4.3 / 4.4 in the same Cursor session.
  HALT at the §3 Phase 4.2 boundary.

HALT at the §3 Phase 4.2 boundary. After 4.2 ships + commits,
halt for operator re-dispatch in a fresh session for Phase 4.3
(OSM Overpass client + cross-layer reconciler). Phase 4.3
dispatches only after Phase 4.2 ships + commits + pushes to
origin.

Same constraints as Phase 4.1 + Phase 2 + Phase 3 sub-phases:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 4.2 only

Pre-dispatch checklist (verify before paste):
- Phase 4.1 SHIPPED on origin -- `91cd37b` feat + `f5b3953` autofix
  + `a75cfe8` docs close-out
- 0a1b2c3d4e5f is the current single alembic head on origin
  (production deploy still at e1f2a3b4c5d6 -- Phase 4.1 not yet
  deployed; 4.2's no-migration scope doesn't depend on prod walking
  the 4.1 migration first)
- Pytest baseline going in is 1733 (or matches reality per
  `python -m pytest --collect-only -q | tail -3`)
- No operator decision-lock required for 4.2
- `--category` flag inclusion baked in as recommendation
- session-23 close-out chain verified on origin per `git log
  --oneline -10` step at top of this prompt
```

---

## After Cursor returns with the §12 report

Same rhythm as Phase 4.1 + every prior sub-phase: paste back to the Cowork primary chat, primary reviews against §5.5 acceptance gates + brief §11 scope discipline, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new `app/contrib/ingest_base.py` (abstract `BaseIngestClient` + `RawHit` / `EnrichedHit` / `EntityPayload` dataclasses)
- 1 new `app/contrib/google_types_mapping.py` (Google `types[]` → `(slug, place_type)` table)
- 1 new `app/contrib/google_places_scraper.py` (library module extracted from the two existing scripts; `GooglePlacesClient` subclass)
- 1 modified `scripts/places_discovery.py` (thin wrapper + `--category` flag)
- 1 modified `scripts/places_enrichment.py` (thin wrapper)
- 1 new test file `tests/test_phase4_ingest_client_interface.py` (~10-15 tests)

Expected pytest delta: +10-15 net-new tests. Pre-existing places-scraper tests (if any) must remain green. Pre-existing magic-link / Phase 3 / Phase 2 / Phase 1 tests must remain green.

Expected effort: 2-3 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations:
1. BaseIngestClient method count — flag if you ship a 5th method
2. `run_discovery` + `run_enrichment` vs single `run(query)` — flag if you collapse
3. `EntityPayload.extension_payloads` typed vs free-form — flag if typed
4. `google_types_mapping.py` coverage — flag if you ship more or fewer than ~28 entries
5. `--category` flag inclusion — should be IN per recommendation; flag if you skip with rationale
6. `places_client.py` refactor scope — flag if you touch it
7. Refactor-regression smoke (deferred-to-operator: `python -m scripts.places_discovery --category eat-drink --dry-run` produces same log output as pre-refactor) — flag in §13

## After Phase 4.2 ships

Update master plan §4 Phase 4 — append the Phase 4.2 ship-line under the existing "Shipped (incremental)" subsection (added in session-23's `a75cfe8` docs commit alongside the Phase 4.1 ship-line). Pattern matches Phase 3.1 → Phase 3.2 incremental shipping. Update STATE.md Production block (HEAD SHA, pytest count, alembic head unchanged at `0a1b2c3d4e5f` since 4.2 has no migration) + "Recently shipped" §1 prepend with the 4.2 close-out narrative.

Phase 4.3 dispatch prompt to be authored after 4.2 ships — chains off whatever 4.2's HEAD SHA is; alembic head stays at `0a1b2c3d4e5f` unless 4.3 ships the `entities.sources` JSON-array migration per brief §6.5 (recommendation: defer; comma-separated string in `entity.source` sufficient for V1). 4.3 dispatch is gated on 4.2 close-out.

## After Phase 4.4 ships (Phase 4 close-out)

Phase 4 is COMPLETE. Master plan §4 Phase 4 gets the SHIPPED header (replaces the 🟡 IN FLIGHT status added in session-23's `a75cfe8` docs commit). STATE.md Production block + "Recently shipped" §1 capture the close-out narrative. Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI build) becomes the next dispatchable lane.
