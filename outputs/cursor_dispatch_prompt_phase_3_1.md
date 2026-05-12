# Cursor Dispatch Prompt — Phase 3.1 (v1.1 schema additions: 7 new entity columns + 5 new tables + users.preferred_mode)

> Short paste-into-Cursor prompt for Phase 3.1 dispatch — the schema-additions sub-phase of Phase 3 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_3_v11_schema_pass.md` (read end-to-end, especially §0 + §3 + §4 + §6 + §9 + §10 + §11 + §12). Phase 3.1 is the additive-schema sub-phase: 7 new entity columns + 5 new tables + 1 new users column + ORM model classes + ~15-20 new tests. **No data backfill, no category seed rewrite, no district paragraphs population, no CATEGORY_LABELS update, no validator vocab update** — all of that is 3.2.
>
> **Gating dependency:** Phase 2B.1 (photos schema + R2 + Pillow + upload route) MUST have shipped on origin before Phase 3.1 dispatches. The 3.1 alembic migration chains off whatever single head `python -m alembic heads` reports at dispatch time — at minimum `c8d9e0f1a2b3` (2B.2 FTS), one higher if 2B.1 has shipped its photos migration.
>
> **No operator prereq beyond Phase 2 close-out.** Phase 3.1 has no Cloudflare / Resend / external-service prereq. Operator decisions for Bucket C strings + district paragraph polish are needed for Phase 3.2 dispatch, NOT 3.1.
>
> **Author note:** this prompt was pre-positioned during Phase 2B.1 in-flight authoring. The §0 baseline values (top SHAs, pytest count, alembic head) reference the Phase 2B.1 ship — fill in after 2B.1 §13 report lands. The 2B.1 ship SHA goes in the `1c57c73` slot; the 2B.1 alembic head (chain-off target for Phase 3.1) goes in the `f9e8d7c6b5a4` slot; the pytest baseline goes in `1663`.

---

```
Read outputs/cursor_brief_phase_3_v11_schema_pass.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3 (sub-phase
boundaries), §4 (Phase 3.1 deliverable list -- the schema-additions
sub-phase), §6 (locked decisions), §9 (acceptable deviations), §10
(risk register), §11 (what NOT to do), §12 (final report format).

Phase 2 of the master build plan is COMPLETE on origin (Lane 2A at
5fea2ce + 6f7f1e9 + 5132162 + Lane 2B at d631c77 + 8338505 +
1c57c73). Phase 2B.1 SHIPPED at commit
1c57c73 (photos schema + R2 client + Pillow
pipeline + upload route + sweep + three-tier hero/gallery on
app/providers/queries.py). Run `git log --oneline -10` and report
the top SHAs. Pytest collect baseline going in is **1663**
tests (~1657+ expected after 2B.1 lands; 1616 was the post-2B.3
baseline, 2B.1 adds ~40-50 net-new tests per brief §5.9). Alembic
head is **f9e8d7c6b5a4** (the Phase 2B.1 photos-
table revision, chained off c8d9e0f1a2b3 from 2B.2). Chain the
Phase 3.1 schema-additions migration off
f9e8d7c6b5a4 -- verify with `python -m alembic heads`.

Ship Phase 3.1 ONLY per §3 + §4 of the brief -- 7 new entity
columns + 5 new tables + 1 new users column + ORM model classes
+ tests. **No data backfill, no category seed rewrite, no district
paragraphs population, no CATEGORY_LABELS update, no validator
vocab update** -- all of that is 3.2 (data pass + Phase 3 close-
out). Single alembic migration. Additive-only.

ORDER MATTERS WITHIN PHASE 3.1:
1. First: read the docs + source files in brief §0 step 6 + step 7.
   Note that the brief was authored at session-19 mid-flight while
   Phase 2B.1 was running in parallel; line offsets in app/db/models.py,
   app/main.py, app/providers/queries.py may have moved since
   authoring (2B.1 appended Photo model + extended Entity with
   photos viewonly relationship + extended derive_hero_photo to
   three-tier). Re-grep before anchoring edits.
2. Then: new alembic migration <rev>_phase3_schema_pass.py per
   brief §4.8. Chains off the current single head as reported by
   `python -m alembic heads` (f9e8d7c6b5a4 at
   dispatch time, possibly different by then -- always trust
   `alembic heads` over the brief). Single op.create_table() for
   each of: districts (§4.2), alert_subscriptions (§4.3),
   alerts_dispatched (§4.4), external_conditions_cache (§4.5),
   peer_recommendations (§4.6). Plus op.batch_alter_table('entities')
   for the 7 new entity columns (§4.1): heat_exposure VARCHAR
   nullable CHECK in ('indoor','shaded','outdoor','water_adjacent'),
   crowd_notes JSON nullable, is_mobile_service BOOLEAN NOT NULL
   default sa.false(), boat_access JSON nullable, seasonal_hours
   JSON nullable, district_id VARCHAR(36) nullable FK
   districts.id ON DELETE SET NULL INDEX, featured BOOLEAN NOT
   NULL default sa.false() INDEX. Plus op.batch_alter_table('users')
   for preferred_mode VARCHAR(16) NOT NULL default 'default' CHECK
   in ('default','boat'). All defaults use sa.true() / sa.false()
   / sa.func.now() per Postgres portability rule (NEVER sa.text("1")
   / sa.text("0")).

   WAIT: brief §4.1 flags a potential conflict on entities.seasonal_hours
   JSON column vs the seasonal_hours extension table from Phase 1A.
   Before authoring the column, verify whether the Phase 1A extension
   table exists (Glob alembic/versions/*seasonal_hours* or grep
   models.py for class SeasonalHours). If it exists, HALT and flag
   in §13 -- operator clarifies whether the new column is intentional
   or whether the extension table is the canonical seasonal-hours
   storage. Per brief §9, this is a known deviation invitation.
3. Then: downgrade() reverses by op.drop_table for the 5 new tables
   + op.batch_alter_table('entities') to drop the 7 columns +
   op.batch_alter_table('users') to drop preferred_mode. Reversibility
   test required.
4. Then: anchored Edit on app/db/models.py per brief §4.9. Append
   new model classes (District, AlertSubscription, AlertDispatched,
   ExternalConditionsCache, PeerRecommendation) at the file tail
   alongside Phase 2A.1 + 2B.1 classes. Extend Entity class with
   7 new Mapped properties + District relationship (
   relationship(District, foreign_keys=[district_id])). Extend User
   class with preferred_mode Mapped[str] property.
5. Then: new tests per brief §4.10 in tests/test_phase3_schema_additions.py
   (~15-20 tests):
     - Migration upgrade+downgrade+upgrade cycle on fresh SQLite
       (reversibility)
     - entities table has 7 new columns with expected types + defaults
     - Each CHECK constraint on enum-like columns rejects invalid
       values (3 tests: heat_exposure, alert_type, delivery_status)
     - districts table exists with expected columns
     - alert_subscriptions UNIQUE (user_id, alert_type, delivery_channel)
       rejects duplicates
     - alert_subscriptions FK CASCADE on user delete: dispatched
       audit rows also cascade-delete
     - external_conditions_cache upsert pattern (source PK) works
     - peer_recommendations UNIQUE (recommender_user_id, entity_id)
       rejects duplicates
     - peer_recommendations status CHECK rejects invalid statuses
     - users.preferred_mode defaults to 'default' on new user creation
     - entities.featured defaults to False on new entity creation
     - entities.is_mobile_service defaults to False on new entity
       creation
     - ORM relationship Entity.district returns District row when
       district_id set
     - ORM relationship Entity.district returns None when district_id
       NULL
     - Indexes exist (verify via inspect(engine).get_indexes('entities'))
6. After all of the above: confirm full pytest stays green, ruff
   clean, that `python -m alembic upgrade head` against a fresh
   dev DB reaches the new schema-additions revision cleanly +
   alembic head advances by one. Then ALSO confirm
   `python -m alembic downgrade -1 && python -m alembic upgrade
   head` cycles cleanly (verify reversibility). No manual smoke
   required for 3.1 (no user-visible surface; new columns/tables
   start empty + ORM is dormant until Phase 3.2 + Phase 5/6/8
   wire readers/writers).

POSTGRES COMPATIBILITY (carried forward from brief §8):
- The bash sandbox + tests run SQLite; production runs Postgres.
- The Phase 2A.1 92ce4899dc08_account_lite_v01.py migration + Phase
  2B.2 c8d9e0f1a2b3_entities_fts_pgtrgm.py + Phase 2B.1 photos
  migration are the recent precedents for portable migrations.
  Mirror their shape.
- Use sa.true() / sa.false() (NOT sa.text("1") / sa.text("0")) for
  Boolean server_default values (featured / is_mobile_service
  default to False).
- Use sa.func.now() (NOT sa.text("CURRENT_TIMESTAMP")) for default
  timestamps.
- For JSON columns: sa.JSON() is portable; both dialects support it
  (SQLite stores as TEXT, Postgres as JSONB if explicitly typed
  but sa.JSON() is fine for Phase 3 V1).
- For enum-like columns: VARCHAR + CHECK constraint is portable.
  Native ENUM type is NOT (Postgres-only). Mirror Phase 2A.1's
  users.role shape.
- For partial indexes (Postgres only): if you add any (e.g., on
  entities.featured = TRUE), gate via bind.dialect.name ==
  "postgresql" early return. Phase 2B.2 added two partial JSON
  indexes this way.
- No raw SQL inside op.execute() unless verified portable across
  both dialects.

DEVIATION INVITATIONS (per brief §9):
- entities.seasonal_hours JSON column vs Phase 1A seasonal_hours
  extension table -- HALT and flag if both exist; operator
  clarifies before authoring.
- entities.featured partial Postgres-only index (filter to
  featured=TRUE) -- nice-to-have performance optimization; mirror
  Phase 2B.2 two partial JSON indexes shape if you author. Flag
  if you skip; simple index acceptable for V1.
- alerts_dispatched.alert_type denormalization (also on
  alert_subscriptions) -- brief specifies denormalized for audit
  durability. If Cursor finds redundancy concern, flag in §13.
- users.preferred_mode NOT NULL with server_default='default' in
  3.1 vs nullable + backfill in 3.2 -- direct-NOT-NULL is cleaner
  if Postgres + SQLite both accept; brief allows either. Flag
  the choice in §13.
- ORM relationship loading strategies -- joinedload vs selectinload
  vs lazy default. District is bidirectional 1:N; AlertSubscription
  is 1:N from User. Pick reasonable defaults; flag any that diverge
  from existing model conventions.

WHAT NOT TO DO (per brief §10 + §11):
- Don't seed any data in 3.1 (categories, districts, anything).
  3.1 is additive-schema only. Data is 3.2's domain.
- Don't backfill entities.district_id from String district -- 3.2.
- Don't update CATEGORY_LABELS in app/home/queries.py -- 3.2.
- Don't update validator vocab in scripts/ingest/validate_enrichment_csv.py
  -- 3.2.
- Don't drop entities.district String column -- 3.2 after backfill.
- Don't add app-layer readers/writers for the new columns/tables
  beyond ORM Mapped properties -- those are Phase 5 (admin form)
  + Phase 6 (profile/card renderers) + Phase 8 (alerts dispatcher).
- Don't touch chat-route response shape. Phase 3 ships zero new
  chat surfaces.
- Don't touch the categories table -- 3.2.
- Don't propose a 13th category. 12-slug count is LOCKED per
  synthesis §1.
- Don't add ENUM types (Postgres-only). VARCHAR + CHECK constraint
  is portable.
- Don't skip CHECK constraints "for SQLite parity." Both dialects
  support CHECK on column definitions.
- Don't use sa.text("1") / sa.text("0") for Boolean defaults.
  Phase 1A's 5132162 hotfix is the canonical lesson.
- Don't modify existing tables beyond the explicit columns/
  changes in §4. Touching extensions tables (locations, hours,
  contact_points, features, offerings, service_areas, schedules,
  source_evidence, sponsorship_slots, photos) requires a separate
  brief.
- Don't add Phase 3 deliverables that aren't in master plan §4
  Phase 3 + brief §4. Scope discipline is critical.
- Don't dispatch Phase 3.2 in the same Cursor session. HALT at
  the §3 Phase 3.1 boundary.

HALT at the §3 Phase 3.1 boundary. After 3.1 ships + commits,
halt for operator re-dispatch in a fresh session for Phase 3.2
(category taxonomy rewrite + audited backfill + district seed +
Phase 3 close-out). Phase 3.2 dispatches only after the operator
has locked the 5 Bucket C decisions per brief §7 + polished the
district paragraphs draft (5 [CASEY: ...] placeholders + 5
verify items in outputs/chatgpt_response_district_paragraphs_v1.md).

Same constraints as Phase 2 sub-phases:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 3.1 only

Pre-dispatch checklist (verify before paste):
- Phase 2B.1 has shipped on origin at 1c57c73
- f9e8d7c6b5a4 is the current single alembic head
- Pytest baseline going in is 1663 (or matches the
  reality `python -m alembic heads` + `pytest --collect-only`
  return)
- No operator prereq for 3.1 (Bucket C decisions + district
  paragraph polish are for 3.2 only)
```

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phases: paste back to the Cowork primary chat, primary reviews against §4.10 acceptance gates + brief §11 scope discipline, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new alembic migration (`alembic/versions/<rev>_phase3_schema_pass.py`)
- 1 modified `app/db/models.py` (5 new model classes appended + Entity extended with 7 new Mapped properties + District relationship + User extended with preferred_mode)
- 1 new test file (`tests/test_phase3_schema_additions.py` ~15-20 tests)

Expected pytest delta: +15-20 net-new tests. Pre-existing chat-route + Provider-profile + search + photos tests must all stay green.

Expected effort: 3-4 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations:
1. `entities.seasonal_hours` JSON column vs Phase 1A extension table — HALT if both exist; operator clarifies
2. `entities.featured` partial Postgres-only index (mirror Phase 2B.2 pattern) — author or skip with rationale
3. `alerts_dispatched.alert_type` denormalization concern — flag if Cursor finds it redundant
4. `users.preferred_mode` NOT NULL with default vs nullable + backfill — Cursor picks; flag
5. ORM relationship loading strategies (joinedload / selectinload / lazy) — document if non-default choices

## After Phase 3.1 ships

Update master plan §4 Phase 3 — add a "Shipped (incremental)" subsection (same pattern as Phase 1 / Phase 2) with the 3.1 ship-line covering the schema-additions migration + new ORM classes + pytest delta + alembic head advancement. Update STATE.md Production block + "Recently shipped" §1 with the 3.1 close-out narrative.

Phase 3.2 dispatch prompt to be authored after 3.1 ships — chains off whatever 3.1's alembic revision is. 3.2 dispatch is gated on operator locking the 5 Bucket C decisions per brief §7 + polishing the district paragraphs draft.

## After Phase 3.2 ships (Phase 3 close-out)

Phase 3 is COMPLETE. Master plan §4 Phase 3 gets a SHIPPED header. STATE.md Production block + "Recently shipped" §1 capture the close-out narrative. Phase 4 (background-jobs + layered scrape infrastructure) becomes the next dispatchable lane.
