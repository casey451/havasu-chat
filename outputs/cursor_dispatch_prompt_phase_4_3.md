# Cursor Dispatch Prompt — Phase 4.3 (minimal OSM Overpass client + cross-layer reconciler: app/contrib/osm_overpass_client.py + scripts/osm_overpass_pull.py + app/contrib/ingest_reconciler.py)

> Short paste-into-Cursor prompt for Phase 4.3 dispatch — the second-client + cross-layer reconciler sub-phase of Phase 4 of the master build plan. **This is the parallel-eligibility proof** per master plan §4 Phase 4 effort estimate: shipping a second `BaseIngestClient` subclass + the reconciler that lets two scrape layers coexist proves the framework holds without rework. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_4_background_jobs_scrape.md` (read end-to-end, especially §0 + §3 + §6 + §8 + §9 + §10 + §11 + §12). Phase 4.3 ships a minimal OSM Overpass-QL client (single-category proof: `leisure=dog_park`) conforming to the `BaseIngestClient` abstract interface from Phase 4.2 + a cross-layer `ingest_reconciler.reconcile_hit()` with three match strategies (google_place_id exact / geo proximity 50m / normalized name) + ~25-32 new tests. **No layer-3/4 clients, no Railway-cron service stand-up, no chat-surface changes, no new Python deps, no entities.sources JSON-array migration** (deferred per brief §6.5 recommendation — comma-separated string in `entity.source` suffices for V1) — all of that is Phase 4.4 / Phase 5 / V1.5.
>
> **Gating dependency:** Phase 4.2 of the master build plan COMPLETE on origin (commit `86eeaf8` substantive — fill at paste time from `git log --oneline -10`; the ruff-autofix + docs commits if any). Phase 4.2 ships the abstract `BaseIngestClient` interface in `app/contrib/ingest_base.py` (4 methods: `discover` / `enrich` / `dedupe_key` / `to_entity_payload`) + the `GooglePlacesClient` Layer-1 subclass in `app/contrib/google_places_scraper.py` + the `google_types_mapping.py` table + ~10-15 new tests in `tests/test_phase4_ingest_client_interface.py`. **Phase 4.3 cannot dispatch until 4.2 closes out** — the OSM client subclasses `BaseIngestClient` and the reconciler uses `EntityPayload` from `ingest_base.py`. Verify 4.2 close-out on origin before pasting this prompt (operator commits Cursor's 4.2 work, push to origin, then dispatch 4.3 in a fresh session).
>
> **No operator prereq for Phase 4.3.** Phase 4.3 is pure application code — new OSM client + new reconciler + tests. No new Railway services, no new env vars (OSM Overpass-QL is a public no-auth API), no Cloudflare changes, no Resend changes, no R2 changes. OSM Overpass is rate-limited generously (0.5 QPS comfortable per strategy memo §3.2); the new `OSM_OVERPASS_LIMITER: Final = SourceLimiter("osm_overpass", qps=0.5)` in `app/contrib/osm_overpass_client.py` reuses the existing `app/contrib/rate_limiter.py::SourceLimiter` interface verbatim (no rewrites of rate_limiter; consistent with Phase 4.2 reusing GOOGLE_PLACES_LIMITER).
>
> **Operator decision-lock BEFORE paste:** **DEFER `entities.sources` JSON-array migration** per brief §6.5 recommendation. The reconciler computes `merge_fields` for "update" actions including a `source` field; Phase 4.3 writes it back to the existing `entity.source` singular string column as a comma-separated multi-source string OR overwrites with the higher-priority single source (operator-typed > Google > OSM > city > specialized). Migrating to a JSON-array column adds a migration + alembic head advance for no V1 user-visible benefit; Phase 5 / V1.5 can revisit when query patterns force it. If Cursor finds the comma-separated approach genuinely doesn't work (e.g., reconciler logic gets tangled), it MAY flag in §13 and propose the migration — but recommendation is DEFER + ship the reconciler with comma-separated `source` semantics.
>
> **Author note:** this prompt was authored at session-23 close alongside the Phase 4.2 dispatch prompt artifact. The §0 baseline values reference the post-Phase-4.1 state — `git log --oneline -10` top SHA after 4.2 ships will be Cursor's 4.2 substantive ship + any chore/docs follow-ups (SHA-patch the `86eeaf8` slot at paste time per the session-19 + 20 + 21 + 22 + 23 SHA-patch-at-paste rhythm); alembic head stays at `0a1b2c3d4e5f` (Phase 4.1 outbox table — Phase 4.2 has no migration); pytest baseline after 4.2 will be **1733 + 10-15 net-new = ~1743-1748** (SHA-patch the actual count from Cursor's 4.2 §13 report into the `1749` slot at paste time).

---

```
Read outputs/cursor_brief_phase_4_background_jobs_scrape.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3 (sub-phase
boundaries), §6 (Phase 4.3 deliverable list -- minimal OSM Overpass
client + cross-layer reconciler), §8 (locked vs open), §9
(acceptable deviations), §10 (risk register), §11 (what NOT to do),
§12 (final report format).

Phase 4.2 of the master build plan COMPLETE on origin at
`86eeaf8` (the layered-scrape framework + Google
Places refactor sub-phase; ships app/contrib/ingest_base.py
BaseIngestClient + app/contrib/google_places_scraper.py
GooglePlacesClient + app/contrib/google_types_mapping.py +
anchored edits on scripts/places_discovery.py +
scripts/places_enrichment.py + tests/test_phase4_ingest_client_
interface.py). Run `git log --oneline -10` and report the top
SHAs. Pytest collect baseline going in is **1749**
tests (1733 from session-23 + 4.2's net-new). Alembic head is
**0a1b2c3d4e5f** (Phase 4.1 outbox table; Phase 4.2 had no
migration; the post-4.2 origin tip).

Ship Phase 4.3 ONLY per §3 + §6 of the brief -- new
app/contrib/osm_overpass_client.py minimal OSM Overpass-QL Layer-2
client conforming to BaseIngestClient (single-category proof:
leisure=dog_park) + new scripts/osm_overpass_pull.py thin wrapper
+ new app/contrib/ingest_reconciler.py cross-layer dedupe module
(google_place_id / geo proximity / normalized name; SOURCE_PRIORITY
field-merge) + ~25-32 new tests across tests/test_phase4_osm_client.py
+ tests/test_phase4_ingest_reconciler.py + anchored edit on
app/contrib/google_places_scraper.py to call reconcile_hit() before
each session.add(Provider(...)). **No layer-3/4 clients, no
Railway-cron service stand-up, no chat-surface changes, no new
Python deps, no entities.sources JSON-array migration** -- 4.4 +
Phase 5 + V1.5 close out the rest.

OPERATOR DECISION-LOCK (per brief §6.5 + §2 row "Source provenance"):
DEFER entities.sources JSON-array migration. Phase 4.3 writes
multi-source provenance to the existing entity.source singular
string column -- comma-separated multi-source string OR overwrite
with the higher-priority single source per SOURCE_PRIORITY table
(operator-typed > google_places > osm > lhc_open_data / az_roc >
npi_registry / usapickleball / pdga). No new migration; alembic
head stays at 0a1b2c3d4e5f. If during 4.3 work this proves
genuinely untenable (e.g., comma-parsing in reconciler logic gets
tangled), flag in §13 -- otherwise ship the comma-separated
approach.

ORDER MATTERS WITHIN PHASE 4.3:
1. First: read the docs + source files in brief §0 step 6 + step 7
   PLUS the Phase 4.2 ship surface. Critical reads: brief §6 end-to-
   end (the four sub-deliverable blocks); app/contrib/ingest_base.py
   (the BaseIngestClient + RawHit/EnrichedHit/EntityPayload dataclasses
   from 4.2 -- this is the seam 4.3's OsmOverpassClient subclasses);
   app/contrib/google_places_scraper.py (4.2's GooglePlacesClient --
   anchored Edit target in step 5 to call reconcile_hit()); 
   app/contrib/rate_limiter.py end-to-end (SourceLimiter shape that
   OSM_OVERPASS_LIMITER reuses; DO NOT modify); app/db/__init__.py
   (Phase 1D dual-write hook seam -- reconciler returns metadata, 
   caller writes via session.add()); app/db/models.py (Entity + 
   Location columns the reconciler queries for matches); 
   docs/maintainability/layered_scrape_strategy.md §4 (reconciliation
   logic spec; 3 match strategies in priority order) + §3.2 (OSM
   Overpass Lake Havasu bounding box: south=34.43, west=-114.41,
   north=34.59, east=-114.30; per-category coverage estimates);
   tests/test_phase1d_dual_write.py (subprocess import-chain test
   shape -- mirror for the OSM client + reconciler import-chain
   regressions).
2. Then: new app/contrib/osm_overpass_client.py per brief §6.1.
   OSM Overpass-QL client conforming to BaseIngestClient (from 4.2).
   OSM_OVERPASS_LIMITER = SourceLimiter("osm_overpass", qps=0.5)
   at module top (reuses the SourceLimiter interface; 0.5 QPS is
   comfortable for the public Overpass endpoint per strategy memo
   §3.2). OSM_OVERPASS_ENDPOINT = "https://overpass-api.de/api/
   interpreter". LHC_BOUNDING_BOX = (34.43, -114.41, 34.59, -114.30).
   `build_query(tag, value) -> str` returns Overpass-QL syntax:
   `[out:json][timeout:60];(node["{tag}"="{value}"]({s},{w},{n},
   {e});way["{tag}"="{value}"]({s},{w},{n},{e}););out body geom;`
   OsmOverpassClient(BaseIngestClient) subclass; source_name = "osm";
   methods: discover(query) -- POST to OSM_OVERPASS_ENDPOINT via
   httpx.Client + OSM_OVERPASS_LIMITER.request(), parse elements,
   return list[RawHit] (only elements with tags.name set);
   _element_to_raw_hit(el) -- internal helper computing 
   source_stable_id = f"osm_{type}_{id}" + lat/lng from el or
   el.center; enrich(hit) -- no-op (Overpass discovery returns full
   detail), returns EnrichedHit(raw_hit=hit); dedupe_key(hit) -- 
   returns hit.source_stable_id; to_entity_payload(hit) -- maps
   OSM tags -> EntityPayload with entity_type="place" + category_
   slug="outdoors-parks-trails" (default for the single-category
   proof) + Feature extension payloads derived from wheelchair=yes/
   limited -> ada_accessible=True / wheelchair=no -> False / fee=no
   -> free=True / fee=yes -> False. **CRITICAL: do NOT import from
   app/db/models at module top.** Reuse Phase 4.1 + 4.2's lazy-
   import discipline (gotcha #17 cure carried from session-22 + 23).
3. Then: new scripts/osm_overpass_pull.py per brief §6.2.
   Thin wrapper that instantiates OsmOverpassClient + runs discovery
   for a configurable category list. argparse with --tag (default
   "leisure"), --value (default "dog_park"), --dry-run (action
   store_true). Mirrors the Phase 4.1 scripts/outbox_redrive.py thin-
   script shape -- function-scope imports keep the script lightweight;
   if __name__ == "__main__": sys.exit(main()).
4. Then: new app/contrib/ingest_reconciler.py per brief §6.3.
   Cross-layer dedupe module. `@dataclass ReconcileResult(action:
   str, existing_id: str | None = None, merge_fields: dict | None
   = None, reason: str | None = None)` where action in {"insert",
   "update", "ambiguous"}. Module-level constants: 
   `GEO_PROXIMITY_THRESHOLD_M = 50.0` (operator-tunable per strategy
   memo §8 Q3 + brief §10 risk row 8); `SOURCE_PRIORITY = {"operator":
   0, "google_places": 1, "osm": 2, "lhc_open_data": 3, "az_roc": 3,
   "npi_registry": 4, "usapickleball": 4, "pdga": 4}`. Pure helpers:
   `haversine_m(lat1, lng1, lat2, lng2) -> float` (Earth radius
   6371000m, ~10 lines of inline math; NO new geopy dep); 
   `slugify(name: str) -> str` (lowercase + alnum-or-space + collapse
   whitespace + hyphen-join; ~3 lines of inline string ops; NO new
   slugify dep). `reconcile_hit(db: Session, payload: EntityPayload)
   -> ReconcileResult` with 3 match strategies in priority order:
   (1) google_place_id exact match (definitive when both source +
   existing have it) -> action="update"; (2) geo proximity (within
   GEO_PROXIMITY_THRESHOLD_M default 50m) AND normalized name match
   -> action="update"; geo proximity AND name mismatch ->
   action="ambiguous"; (3) normalized name only (no geo) -> 
   action="ambiguous" (last-resort surface for operator review);
   no match anywhere -> action="insert". `_compute_merge_fields(db,
   existing_id, payload) -> dict` returns field-merge dict per
   SOURCE_PRIORITY: operator-typed wins (empty merge = no overwrite);
   higher-priority new source overwrites name + description + source;
   lower-priority new source fills missing fields only. **CRITICAL:
   reconciler returns metadata; caller does session.add(Provider(...))
   for "insert" actions + session.merge()/update pattern for "update"
   actions. Reconciler does NOT bypass Phase 1D dual-write helpers
   -- every write still goes through the centralized before_flush
   hook at app/db/__init__.py.**
5. Then: anchored Edit on app/contrib/google_places_scraper.py
   (from 4.2) to call ingest_reconciler.reconcile_hit() before each
   ORM session.add(Provider(...)) in the run_discovery() and
   run_enrichment() write paths. **Texture rule from brief §1:**
   same DB rows out for the "insert" action (matches 4.2 behavior);
   "update" action does session.merge() with the merge_fields dict;
   "ambiguous" action logs a warning + skips the write (operator-
   review queue surface; admin form is Phase 5 / V1.5 territory).
6. Then: new tests per brief §6.4.
   tests/test_phase4_osm_client.py (~8-12 tests):
     - build_query produces valid Overpass-QL for leisure=dog_park
     - OsmOverpassClient is a BaseIngestClient subclass
     - OsmOverpassClient.source_name == "osm"
     - Mocked Overpass response -> 3 RawHit objects with names + 
       lat/lng
     - dedupe_key returns "osm_node_12345" shape
     - wheelchair=yes -> extension_payloads["ada_accessible"]=True
     - wheelchair=no -> False
     - fee=no -> extension_payloads["free"]=True
     - fee=yes -> False
     - Empty Overpass response (no elements) -> empty RawHit list
     - Overpass 5xx -> empty RawHit list (no raise; per with_retry
       pattern from 4.1)
     - OSM rate-limiter integration: OSM_OVERPASS_LIMITER is a
       SourceLimiter
   tests/test_phase4_ingest_reconciler.py (~15-20 tests):
     - haversine_m returns ~0 for identical points
     - haversine_m returns ~111000 for 1-degree-latitude separation
     - slugify("English Village") == "english-village"
     - slugify("Lake Havasu Aquatic Park!") == "lake-havasu-aquatic-
       park"
     - reconcile_hit empty DB -> "insert"
     - reconcile_hit existing entity with same google_place_id -> 
       "update"
     - reconcile_hit existing entity within 50m + matching name -> 
       "update"
     - reconcile_hit existing entity within 50m + mismatched name -> 
       "ambiguous"
     - reconcile_hit existing entity > 50m + matching name -> 
       "ambiguous" (name only; no geo)
     - reconcile_hit no match anywhere -> "insert"
     - _compute_merge_fields operator-typed entity -> no overwrites
       (empty merge)
     - _compute_merge_fields Google source over existing OSM source
       -> name + description + source updated
     - _compute_merge_fields OSM source over existing Google source
       (lower priority) -> only fill missing description
     - Idempotency: same hit twice -> first inserts, second updates
       with empty merge (no field changes)
     - GEO_PROXIMITY_THRESHOLD_M == 50.0 is the documented constant
     - SOURCE_PRIORITY priority order: operator < google_places <
       osm < lhc_open_data / az_roc < npi_registry / usapickleball /
       pdga
     - Edge case: payload missing lat/lng skips strategy 2
     - Edge case: payload missing google_place_id skips strategy 1
     - Slugify handles unicode + punctuation cleanly
     - Reconciler does not bypass Phase 1D -- it returns metadata;
       caller writes via session.add(...) (verify the test does NOT
       mock session.add and the reconcile call does NOT touch
       entities table directly)
     - Import-chain regression: subprocess import test that 
       `from app.contrib.osm_overpass_client import OsmOverpassClient`
       + `from app.contrib.ingest_reconciler import reconcile_hit`
       both succeed without gotcha #17 cycle (mirror
       tests/test_phase4_background.py::test_background_module_does
       _not_import_models_at_module_top shape)
7. After all of the above: confirm full pytest stays green
   (1749 floor + 25-32 net-new), ruff clean.
   Manual smoke deferred-to-operator (`python -m scripts.osm_
   overpass_pull --tag leisure --value dog_park --dry-run` returns
   parseable Overpass response + maps to expected entity payloads)
   -- flag in §13.

POSTGRES COMPATIBILITY (carried forward from brief §11):
- The bash sandbox + tests run SQLite; production runs Postgres.
- NO migration in Phase 4.3 (per operator decision-lock above).
- If entities.sources migration is unavoidable (it shouldn't be),
  use Phase 4.1 outbox migration as recent-precedent shape: sa.JSON
  for the array column, sa.func.now() defaults, no Postgres-only
  types, no raw op.execute().

DEVIATION INVITATIONS (per brief §9 Phase 4.3):
- OSM single-category default -- brief recommends leisure=dog_park
  (small + well-mapped + low risk). If you want a different proof
  category (e.g., leisure=park or amenity=marina), flag in §13.
  Recommendation: dog_park.
- Lake Havasu bounding box -- brief uses (34.43, -114.41, 34.59,
  -114.30). If a tighter or different box reads more accurate
  (e.g., excludes Topock + Havasu Landing), flag in §13.
  Recommendation: strategy memo box; tuning is V1.5+ operator
  concern.
- ingest_reconciler.py strategy order -- brief specifies 
  google_place_id -> geo -> name. If you want a different order or
  different criteria (e.g., OSM stable ID also serves as definitive
  match), flag in §13. Recommendation: stay with brief order; OSM
  stable ID is layer-2-only and doesn't generalize.
- SOURCE_PRIORITY table -- brief specifies 8 entries (operator /
  google_places / osm / lhc_open_data / az_roc / npi_registry /
  usapickleball / pdga). If you want explicit "unknown" or "manual"
  entries, flag in §13.
- entities.sources JSON-array migration -- DEFERRED per operator
  decision-lock at top of this prompt. If during work you find
  comma-separated approach untenable, flag + propose migration in
  §13.
- Reconciler "ambiguous" action -- brief specifies it logs +
  skips the write (operator-review queue surface, admin form is
  Phase 5/V1.5). If you want a different default behavior (e.g.,
  insert anyway with a flag), flag in §13. Recommendation: skip
  + log; conservative default avoids false merges.
- Phase 4.2 reconciler hook-site -- brief invites anchored Edit
  on app/contrib/google_places_scraper.py to call reconcile_hit()
  before each session.add(Provider(...)). If 4.2 shipped a
  different write surface (e.g., a run_discovery_with_writes()
  method that does its own ORM writes), the anchored Edit lands
  there instead. Confirm 4.2 surface via Read before anchoring.

WHAT NOT TO DO (per brief §10 + §11):
- Don't add Layer 3 or Layer 4 clients. Phase 5.
- Don't add new Python dependencies (no overpy / geopy /
  python-slugify). httpx (existing) handles Overpass HTTP;
  haversine is ~10 lines of inline math; slugify is ~3 lines of
  inline string ops.
- Don't modify app/contrib/rate_limiter.py. The SourceLimiter
  interface is stable.
- Don't modify app/contrib/places_client.py. It's the Phase 5.2
  provider-enrichment client.
- Don't modify app/contrib/ingest_base.py. The BaseIngestClient
  abstract interface from Phase 4.2 is the contract; 4.3 subclasses
  it.
- Don't bypass Phase 1D dual-write. Reconciler returns metadata;
  caller writes via session.add(...) for "insert" / session.merge()
  for "update" / log+skip for "ambiguous".
- Don't import from app/db/models at module top in
  app/contrib/osm_overpass_client.py or 
  app/contrib/ingest_reconciler.py. Lazy-import inside methods
  for ORM access. Prevents gotcha #17 cycle.
- Don't add module-import-time hooks anywhere except 
  app/db/__init__.py. Gotcha #17 cure carries forward.
- Don't change GEO_PROXIMITY_THRESHOLD_M based on speculation.
  50m is the strategy memo §8 Q3 recommendation; operator tunes
  after real data lands.
- Don't auto-merge across all three strategies. Strategy 2 +
  strategy 3 (name-only without geo) return "ambiguous" -- only
  google_place_id exact match OR geo+name match auto-update.
  Conservative default.
- Don't ship OSM Railway-cron service in 4.3. Phase 4.4 close-
  out has the runbook; actual Railway service stand-up is
  operator action.
- Don't change the DB rows produced by Phase 4.2's GooglePlacesClient
  pre-Edit. The anchored Edit adds the reconcile_hit() pre-write
  call; behavior on the "insert" action is unchanged (matches 4.2
  pre-Edit row shape).
- Don't modify chat-route response shape, provider profile render,
  /api/search response, home page, photos surface, or any other
  user-visible surface. Phase 4 ships zero user-visible surface
  changes.
- Don't add admin-form surfaces for the operator-review queue
  ("ambiguous" reconciler outputs). V1.5+.
- Don't dispatch Phase 4.4 in the same Cursor session. HALT at
  the §3 Phase 4.3 boundary.

HALT at the §3 Phase 4.3 boundary. After 4.3 ships + commits,
halt for operator re-dispatch in a fresh session for Phase 4.4
(close-out: operator runbook + Railway-cron-service template +
master plan SHIPPED header + STATE.md refresh). Phase 4.4
dispatches only after Phase 4.3 ships + commits + pushes to
origin.

Same constraints as Phase 4.1 + Phase 4.2 + Phase 2 + Phase 3
sub-phases:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 4.3 only

Pre-dispatch checklist (verify before paste):
- Phase 4.2 SHIPPED on origin (`86eeaf8`)
- 0a1b2c3d4e5f is the current single alembic head on origin
  (Phase 4.2 had no migration; 4.3 also no migration per operator
  decision-lock)
- Pytest baseline going in matches Phase 4.2 §13 report's final
  count (SHA-patch the 1749 slot)
- DEFER entities.sources migration is the operator decision-lock
- OSM single-category default = leisure=dog_park (brief
  recommendation)
- session-23 close-out chain + Phase 4.2 close-out chain verified
  on origin per `git log --oneline -10` step at top of this prompt
```

---

## After Cursor returns with the §12 report

Same rhythm as Phase 4.1 + Phase 4.2 + every prior sub-phase: paste back to the Cowork primary chat, primary reviews against §6.5 acceptance gates + brief §11 scope discipline, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new `app/contrib/osm_overpass_client.py` (`OsmOverpassClient` subclass of `BaseIngestClient`)
- 1 new `scripts/osm_overpass_pull.py` (thin script wrapper)
- 1 new `app/contrib/ingest_reconciler.py` (`reconcile_hit` + `_compute_merge_fields` + `haversine_m` + `slugify` + `ReconcileResult` dataclass + module constants)
- 1 modified `app/contrib/google_places_scraper.py` (anchored Edit: call `reconcile_hit()` before each `session.add(Provider(...))` in `run_discovery` + `run_enrichment` write paths)
- 1 new test file `tests/test_phase4_osm_client.py` (~8-12 tests)
- 1 new test file `tests/test_phase4_ingest_reconciler.py` (~15-20 tests)

Expected pytest delta: +25-32 net-new tests. Pre-existing Phase 4.2 tests must remain green (the GooglePlacesClient anchored Edit changes the write path but not the row shape on the "insert" action). Pre-existing Phase 4.1 + Phase 3 + Phase 2 + Phase 1 tests must remain green.

Expected effort: 2-3 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations:
1. OSM single-category default — flag if not `leisure=dog_park`
2. LHC bounding box — flag if tightened or shifted from `(34.43, -114.41, 34.59, -114.30)`
3. Reconciler strategy order — flag if not `google_place_id → geo → name`
4. SOURCE_PRIORITY table — flag if not the 8 entries spec
5. `entities.sources` JSON-array migration — should be DEFERRED per operator decision-lock; flag if you ship it with rationale
6. Reconciler "ambiguous" action default behavior — flag if not log+skip
7. Phase 4.2 reconciler hook-site — flag if 4.2 surfaced a different write seam than `session.add(Provider(...))`
8. Refactor-regression smoke (deferred-to-operator: `python -m scripts.osm_overpass_pull --tag leisure --value dog_park --dry-run` returns parseable Overpass response) — flag in §13

## After Phase 4.3 ships

Update master plan §4 Phase 4 — append the Phase 4.3 ship-line under the existing "Shipped (incremental)" subsection (added in session-23's `a75cfe8` docs commit; extended with Phase 4.2's ship-line whenever 4.2 closes out). Pattern matches Phase 3.1 → 3.2 incremental shipping. Update STATE.md Production block (HEAD SHA, pytest count) + "Recently shipped" §1 prepend with the 4.3 close-out narrative.

Phase 4.4 dispatch prompt to be authored after 4.3 ships — chains off whatever 4.3's HEAD SHA is; alembic head stays at `0a1b2c3d4e5f` (4.3 deferred the entities.sources migration). 4.4 dispatch is gated on 4.3 close-out.

## After Phase 4.4 ships (Phase 4 close-out)

Phase 4 is COMPLETE. Master plan §4 Phase 4 gets the SHIPPED header (replaces the 🟡 IN FLIGHT status added in session-23's `a75cfe8` docs commit). STATE.md Production block + "Recently shipped" §1 capture the close-out narrative. Phase 5 (Tier 1 data gathering, parallel with Phase 6 UI build) becomes the next dispatchable lane — see the pre-positioned prereq checklist at `outputs/phase5_prereq_checklist.md` (authored at session-23 alongside this 4.3 dispatch prompt) for the operator decisions to lock + external data-source verifications to complete before Phase 5 paste.
