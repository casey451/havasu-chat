# Cursor Dispatch Prompt — Phase 2B.1 (photos schema + R2 client + Pillow pipeline + upload route)

> Short paste-into-Cursor prompt for Phase 2B.1 dispatch — the first sub-phase of Lane 2B (image storage + search) of Phase 2 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_2b_image_storage_search.md` (read it again, especially §3 + §5 + §9 + §10 + §11 + §12). Phase 2B.1 is the **2A.3-gated** sub-phase of Lane 2B — the upload route imports `app/auth/dependencies.py::require_user` (Phase 2A.2-shipped) and `app/auth/claims.py::find_existing_claim` (Phase 2A.3-shipped). Do NOT dispatch 2B.1 until 2A.3 has shipped on origin.
>
> **Operator gate:** Phase 2B.1 requires the Cloudflare R2 prereq to be locked per `outputs/operator_prereqs_phase_2.md` §2 — bucket created, API token generated, the five canonical env vars (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL_BASE`) dropped into Railway, Path A (default `pub-<hash>.r2.dev`) or Path B (custom domain `cdn.havasuchat.com`) decision made. The brief §0 step 8 baseline check halts gracefully if any of the five env vars is missing, so dispatch-with-unset-vars surfaces a clean halt rather than a half-broken state — but the operator should lock R2 before dispatching to avoid the round-trip.
>
> **Author note:** this prompt was pre-positioned during Phase 2A.3 + Phase 2B.2 in-flight authoring, before either had shipped. The §0 baseline values (top SHAs, pytest count, alembic head) reference the 2A.3 ship + the 2B.2 ship — fill in after both §13 reports land. If 2B.2 shipped before 2A.3, the alembic head will already have advanced past `92ce4899dc08`; chain the 2B.1 photos migration off whichever head `python -m alembic heads` reports at dispatch time.

---

```
Read outputs/cursor_brief_phase_2b_image_storage_search.md end-to-end,
especially §3 (sub-phase boundaries, halt etiquette), §5 (Phase 2B.1
deliverable list -- the photos schema + R2 + Pillow + upload route
sub-phase of Lane 2B), §9 (what NOT to do -- Postgres portability +
EXIF strip mandatory + no PhotoVariant table + no entity_type column
on photos), §10 (acceptable deviations), §11 (risk register), §12
(final report format).

Phase 2A.1 SHIPPED on origin (commit 6000138 + 5bf4c14 dispatch
artifacts + 9150be5 docs ship-line + 2423d4f Phase 2A.2 dispatch
artifact). Phase 2A.2 SHIPPED at commit 714ca52. Phase 2A.3 SHIPPED
at commit 5fea2ce (Lane 2A close-out — claim
flow + favorites + admin role + viewer_is_owner). Phase 2B.2 may
also be shipped by the time you read this — if so, it shipped at
commit d631c77 (FTS migration + app/search/
package + chat tier 2 LIKE->FTS swap). Run `git log --oneline -10`
and report the top SHAs. Pytest collect baseline going in is
**1607** tests (1 skipped under skip-unless-postgres for the 2B.2
Postgres-only FTS execution path; baseline after both 2A.3 and 2B.2
shipped). Alembic head is **c8d9e0f1a2b3** (Phase 2B.2 FTS + pg_trgm,
chained off 92ce4899dc08 from Phase 2A.1 account-lite v0.1). Chain
the 2B.1 photos migration off c8d9e0f1a2b3 — verify with
`python -m alembic heads`.

Ship Phase 2B.1 ONLY per §3 + §5 of the brief -- photos schema +
new app/photos/ package (r2_client + processor + routes + sweep +
schemas + limits) + Alembic migration + three-tier hero/gallery
extension on app/providers/queries.py + _hourly_cleanup_loop fold.
**No Postgres FTS, no search bar UI, no app/search/ package** --
all of that is 2B.2 (FTS + chat tier 2 swap) and 2B.3 (search bar
UI + /api/search endpoint).

ORDER MATTERS WITHIN PHASE 2B.1:
1. First: read the docs + source files in brief §0. Note that the
   brief was authored mid-2A.2 + before 2B.2, so line offsets in
   app/db/models.py, app/main.py, app/providers/queries.py,
   app/chat/tier2_db_query.py may have moved since authoring (2A.3
   shipped no migration but did extend several modules; 2B.2 if
   shipped first added the entities.search_vector column via
   migration + new app/search/ package). Re-grep before anchoring
   edits.
2. Then: append Photo model to app/db/models.py per brief §4.1
   verbatim. Tail-append alongside Phase 2A.1 User /
   MagicLinkToken / AuthSession / UserFavorite / Claim. FK
   entity_id -> entities.id + FK uploaded_by_user_id ->
   users.id both ON DELETE CASCADE. CHECK constraints on status
   + mime_type. Five indexes (entity_id, uploaded_by_user_id,
   status, image_hash + composite entity_hash_status). sa.true()
   / sa.false() / sa.func.now() defaults per Postgres
   portability rule.
3. Then: anchored Edit on Entity class in app/db/models.py per
   brief §4.1 tail block -- add the photos viewonly relationship
   (primaryjoin filters status='live'; viewonly=True so write
   cascades don't route through; order_by Photo.display_order)
   after sponsorship_slots (~:685 pre-2A.3; re-grep to verify).
4. Then: new alembic migration <rev>_photos_table.py per brief §4.3
   first bullet + §5. Chains off whichever alembic head is current
   at dispatch time (92ce4899dc08 at minimum; later if 2B.2 added
   a migration -- verify with `python -m alembic heads` and chain
   off the current single head). Single op.create_table('photos',
   ...) + indexes + CHECK constraints + FKs. Reversible:
   downgrade() is op.drop_table('photos'). No data backfill.
   Mirror the 92ce4899dc08_account_lite_v01.py shape -- sa.true()
   / sa.false() server defaults, no raw SQL.
5. Then: factor app/photos/__init__.py + app/photos/r2_client.py
   per brief §5.2. Lazy-singleton get_r2_client() (raises
   RuntimeError on missing env vars, NOT at import time;
   region_name='auto', signature_version='s3v4'). upload_bytes(
   key, content, content_type) sets Cache-Control: public,
   max-age=31536000, immutable + returns public URL via
   R2_PUBLIC_URL_BASE. delete_object(key) best-effort (V1 photo-
   delete is soft via status='deleted'). build_public_url(key)
   joins prefix + key cleanly.
6. Then: factor app/photos/processor.py per brief §5.3 -- six-
   stage pure-function pipeline (decode_and_validate ->
   strip_exif -> compute_hash -> generate_variants ->
   upload_all_variants -> finalize_photo_row) plus the
   process_uploaded_photo(photo_id, content, declared_mime)
   BackgroundTask orchestrator. Variants 256x256 / 512x512 /
   1280x720 x WebP-q82 + JPEG-q85 via ImageOps.fit center-crop.
   EXIF strip MANDATORY (failure -> flag row exif_strip_failed,
   never upload-with-EXIF). MIME-sniff: declared mime must match
   Pillow's decoded format. SHA-256 dedup on post-strip pixel
   bytes. Orchestrator idempotent (re-run against status='live'
   row is no-op + WARNING).
7. Then: factor app/photos/schemas.py + app/photos/limits.py per
   brief §5.8. schemas.py exposes PhotoUploadResponse +
   PhotoListItem Pydantic models. limits.py exposes
   check_uploader_daily_cap (20/day) + check_entity_photo_cap
   (50 for place, 100 for commercial; counts live + uploading).
   Mirror app/auth/email_helpers rate-limit shape.
8. Then: factor app/photos/sweep.py per brief §5.5 --
   run_stuck_photo_sweep() flips status='uploading' rows older
   than 24h to status='flagged' with processing_error=
   'decode_failed'. Returns count for logging/tests.
9. Then: factor app/photos/routes.py per brief §5.4. Four
   endpoints: POST /api/entities/{entity_id}/photos (multipart
   upload, auth=require_user, authz=admin OR verified Claim via
   find_existing_claim, entity_type must be commercial|place,
   MIME whitelist + 10 MB cap + rate-limit checks, creates Photo
   row in status='uploading' + schedules BackgroundTask, returns
   201 with {photo_id, status}); DELETE /api/photos/{id} (soft-
   delete, admin OR uploader OR verified claimant); POST
   /api/photos/{id}/set-hero (atomic clear-siblings + flip);
   POST /api/photos/{id}/reorder (display_order update). Error
   envelopes mirror Phase 2A.2 routes shape.
10. Then: anchored Edit on app/main.py per brief §5.6 -- (a) add
    photos router include after existing include_router block;
    (b) extend _hourly_cleanup_loop at ~:246 (re-grep; 2A.3 may
    have shifted) to also call asyncio.to_thread(
    run_stuck_photo_sweep) alongside run_expired_review_cleanup.
11. Then: anchored Edit on app/providers/queries.py per brief
    §5.7 -- extend derive_hero_photo + derive_gallery to three-
    tier: Tier 1 (NEW) owner Photo row (is_hero=True,
    status='live') -> hero_url; Tier 2 (EXISTING) attributes.
    hero_pin_photo_url; Tier 3 (EXISTING) google_photo_refs[0].
    Gallery extends similarly with hero excluded. Re-grep
    derive_hero_photo to find current offsets (brief cites
    :80-91; 2A.3 / 2B.2 may have shifted).
12. Then: new tests per brief §5.9 -- six test files totaling
    ~41 tests:
      tests/test_photos_schema.py (~8): table existence, columns,
        CHECK constraints, FK cascade, indexes, Entity.photos
        relationship live-only filter.
      tests/test_photos_processor.py (~10): each stage
        independently + orchestrator end-to-end with R2 mocked
        + dedup + R2 failure recovery.
      tests/test_photos_r2_client.py (~4): missing env vars,
        boto3 mock, put_object headers, build_public_url.
      tests/test_photos_routes.py (~13): anon 401, no-claim
        403, verified 201, admin bypass, MIME 400, size 413,
        non-photo-eligible entity_type 400, missing entity 404,
        per-entity cap 429, daily cap 429, DELETE flows,
        set-hero atomic.
      tests/test_photos_sweep.py (~2): stuck >24h flagged;
        <24h untouched.
      tests/test_provider_queries_hero_photo.py (~4, new OR
        extend): three-tier fallback chain coverage.
13. After all of the above: confirm full pytest stays green, ruff
    clean, that `python -m alembic upgrade head` against a fresh
    dev DB reaches the new photos migration revision cleanly +
    alembic head advances by one. Then ALSO confirm
    `python -m alembic downgrade -1 && python -m alembic upgrade
    head` cycles cleanly (verify reversibility). Manual smoke
    (operator runs against staging with real R2 env vars set):
    curl POST a real JPEG to /api/entities/<id>/photos with a
    cookie from a verified claimant -- verify R2 bucket has the
    six variant objects (thumbnail/medium/hero x WebP/JPEG) +
    Photo row transitions to status='live' + cdn_url / hero_url
    / thumbnail_url / medium_url populated. Cursor can't fully
    smoke this without R2 access; document in §12 if Cursor
    ran only the unit + integration tests with R2 mocked.

POSTGRES COMPATIBILITY (carried forward from brief §9):
- The bash sandbox + tests run SQLite; production runs Postgres.
- The Phase 2A.1 92ce4899dc08_account_lite_v01.py migration is the
  most recent precedent for portable indexes + CHECK constraints +
  FK ondelete=CASCADE. Mirror that shape for the 2B.1 photos
  table migration.
- Use sa.true() / sa.false() (NOT sa.text("1") / sa.text("0")) for
  Boolean server_default values (is_hero defaults to False; cite
  Phase 1 Entity at app/db/models.py:648 + 92ce4899dc08 as
  precedents).
- Use sa.func.now() (NOT sa.text("CURRENT_TIMESTAMP")) for default
  timestamps where the migration needs a server-side default.
- No raw SQL inside op.execute() unless verified portable. SQLite
  is loose about quoting + keyword strictness + NULL handling in
  unique constraints + JSON syntax; Postgres is strict.

DEVIATION INVITATIONS (per brief §10):
- R2 env-var stubs in tests/conftest.py via os.environ.setdefault
  (RECOMMENDED). Set the five canonical R2 vars to harmless stub
  values so unit tests don't hit real R2 + don't require operator
  setup for `pytest`. Cite Phase 2A.2's AUTH_DEV_MODE=1
  setdefault pattern as precedent. Flag in §13 if you go a
  different route (e.g., monkeypatch get_r2_client per-test).
- run_stuck_photo_sweep fold into _hourly_cleanup_loop
  (RECOMMENDED). Mirrors Phase 2A.1 deviation #5 (expired-token
  cleanup fold) + 2A.2/2A.3 follow-on folds. Same hourly tick,
  same asyncio.to_thread wrapper. Document in §12.
- before_flush Session listener safety net for Photo row creation
  if test fixtures create rows directly bypassing the upload
  route. Same precedent as Phase 1D + Phase 2A.1. Optional;
  flag if you do.
- Orchestrator exception envelope -- process_uploaded_photo
  wrapped in try/except that flips row to flagged on any uncaught
  exception is a reasonable defensive shape (sync vs deferred
  processing itself is LOCKED at BackgroundTasks per brief §9).
- Photo size + count caps + boto3 region_name are LOCKED ('auto'
  per R2 convention; 10 MB / 20 daily / 50 place / 100 provider
  / 50 daily-per-IP per brief §2). Deviate only if implementation
  surfaces a hard need; flag in §13.

WHAT NOT TO DO (per brief §9):
- Don't dispatch 2B.1 before Phase 2A.3 has shipped. Upload route
  imports require_user (2A.2) + find_existing_claim (2A.3); if
  2A.3 hasn't shipped, halt at §0 step 8. 2B.2 + 2B.3 have no
  such dependency.
- Don't touch app/search/* -- 2B.2 domain (FTS + tier 2 swap +
  fts.py / ranking.py / sqlite_fallback.py). Even if 2B.2 hasn't
  shipped yet, the package is reserved.
- Don't touch app/auth/* beyond importing dependencies/helpers.
  require_user / get_current_user / find_existing_claim are
  consumed via import; modifying or adding to app/auth/ is OUT
  of scope (that was Lane 2A).
- Don't add the search bar UI / /api/search route -- 2B.3 scope.
- Don't introduce a custom-CDN-domain dependency in V1. Path A
  (default pub-<hash>.r2.dev URL) is fully acceptable; Path B
  (custom cdn.havasuchat.com) is a config-only env-var swap.
  Code reads R2_PUBLIC_URL_BASE; never hard-codes the host.
- Don't drop app/photos/sweep.py "for cleanliness." Stuck-upload
  sweep is the R2-transient-failure safety net (risk #7); without
  it, status='uploading' rows accumulate indefinitely.
- Don't touch chat-route response shape. 2B.1 ships zero new chat
  surfaces; Photo data flows to chat ONLY via the existing
  derive_hero_photo chain (extended to three-tier per step 11).
  Existing chat integration tests are the regression bar.
- Don't add a polymorphic entity_type column on photos. FK to
  entities.id + Entity's discriminator is the LOCKED shape per
  master plan §4 Phase 2 amendment + Phase 1 ENTITY pivot.
- Don't add a separate PhotoVariant child table. Three String URL
  columns + storage_key prefix is the LOCKED shape per design
  memo §5.1.
- Don't store EXIF metadata; strip is mandatory (design memo §6
  stage 2 + §7). On strip failure flag exif_strip_failed.
- Don't trust the original filename for the storage key. UUIDs
  only per design memo §7.
- Don't add Cloudinary / Cloudflare Images / AWS Rekognition /
  automated moderation / video / GIF / HEIC / signed URLs /
  cropping UI / on-the-fly transforms. Design memo §13 lists
  every V1 exclusion.
- Don't add Photo entity_types beyond commercial + place. Events
  + programs are NOT photo-uploadable in V1 (route returns 400).
- Don't pre-process photos synchronously in the upload route.
  FastAPI BackgroundTasks per design memo §4 step 7.

HALT at the §3 Phase 2B.1 boundary. After 2B.1 ships + commits,
halt for operator re-dispatch in a fresh session for 2B.3 (search
bar UI + endpoint + close-out) if 2B.3 hasn't already shipped via
parallel dispatch. Do NOT start 2B.2 or 2B.3 in the same session.

Same constraints as the Phase 2A lanes:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 2B.1 only

Operator note: the five R2 env vars (R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_ENDPOINT_URL, R2_BUCKET_NAME,
R2_PUBLIC_URL_BASE) must be set in tests/conftest.py via
os.environ.setdefault to stub values (e.g.,
"test-access-key-id" / "test-secret" / "https://test.r2.cloudflarestorage.com"
/ "test-bucket" / "https://pub-test.r2.dev") so the unit tests
DON'T hit real R2 and DON'T require operator R2 setup for test
runs. The R2 client is constructed lazily, so test fixtures can
either let the stub-env-var client build (and mock boto3 calls
on it) or monkeypatch get_r2_client to return a Mock. Cite Phase
2A.2's AUTH_DEV_MODE=1 setdefault pattern in tests/conftest.py as
the precedent for this kind of test-only env-var stubbing.
```

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phases: paste back to the Cowork primary chat, primary reviews against §5.10 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 7 new files in `app/photos/` (`__init__.py`, `r2_client.py`, `processor.py`, `routes.py`, `schemas.py`, `limits.py`, `sweep.py`)
- 1 new alembic migration (`alembic/versions/<rev>_photos_table.py`)
- 6 new test files (`tests/test_photos_schema.py`, `tests/test_photos_processor.py`, `tests/test_photos_r2_client.py`, `tests/test_photos_routes.py`, `tests/test_photos_sweep.py`, `tests/test_provider_queries_hero_photo.py` — last one may extend existing rather than new-file, Cursor's call)
- 1 modified `app/db/models.py` (Photo class appended; Entity.photos relationship anchored Edit)
- 1 modified `app/main.py` (photos router include + `_hourly_cleanup_loop` fold of `run_stuck_photo_sweep`)
- 1 modified `app/providers/queries.py` (`derive_hero_photo` + `derive_gallery` three-tier extension)
- 1 modified `tests/conftest.py` (five R2 env-var setdefault stubs)
- 1 modified `requirements.txt` (Pillow + boto3 + `python-multipart` if not already pulled in by FastAPI)

Expected pytest delta: +40-50 net-new tests (the brief specifies ~41 across the six test files: 8 schema + 10 processor + 4 r2_client + 13 routes + 2 sweep + 4 hero_photo). Pre-existing chat-route + Provider-profile anonymous-viewer tests must all stay green; the three-tier hero/gallery extension is additive and should not regress entities without owner Photos.

Expected effort: 3-4 day brief estimate; one Cursor session realistically (possibly two if test scaffolding + R2 mocking takes longer than expected).

Expected pragmatic deviations: (a) R2 env-var stub mechanism in `tests/conftest.py` — `os.environ.setdefault` is the recommended shape, cite 2A.2 `AUTH_DEV_MODE=1` precedent; (b) `run_stuck_photo_sweep` fold into `_hourly_cleanup_loop` — recommended deviation, follow 2A.1 fold pattern; (c) `before_flush` Session listener safety net for Photo row creation if test fixtures benefit — optional; (d) MIME-sniff implementation detail (Pillow `.format.lower()` vs alternate shape); (e) boto3 `region_name='auto'` vs `'wnam'` if operator's R2 bucket is region-pinned; (f) `derive_hero_photo` line offsets — brief cites `:80-91` but 2A.3 / 2B.2 may have shifted; re-grep to find current.

## After Phase 2B.1 ships

Lane 2B is closer to close-out (combined with 2B.2 + 2B.3 ship lines). Update master plan §4 Phase 2 "Shipped (incremental)" list with the 2B.1 ship-line (same pattern as 2A.1 entry). If 2B.2 + 2B.3 have already shipped via parallel dispatch, the Lane 2B SHIPPED header lands now; otherwise it lands after the remaining sub-phases. Update STATE.md Production block + "Recently shipped" §1 with the 2B.1 close-out narrative — photos schema live, R2 + Pillow pipeline functional, upload route gated on verified claim, three-tier hero/gallery extension active for entities with owner Photos.

## After full Lane 2B ships (2B.1 + 2B.2 + 2B.3, in any order)

Phase 2 Lane 2B is COMPLETE. Update master plan §4 Phase 2 header to mark Lane 2B as SHIPPED. Combined with Lane 2A (shipped at 2A.3 close-out), **Phase 2 of the master build plan is COMPLETE**, and Phase 3 (v1.1 schema pass + operator-curated fields + category taxonomy rewrite + district paragraphs + alerts schema) becomes the next dispatchable lane.
