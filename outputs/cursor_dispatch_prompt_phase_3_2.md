# Cursor Dispatch Prompt — Phase 3.2 (category taxonomy rewrite + audited Provider/Program backfill + district seed as backend tag + entity backfills + Phase 3 close-out)

> Short paste-into-Cursor prompt for Phase 3.2 dispatch — the data-pass sub-phase of Phase 3 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_3_v11_schema_pass.md` (read end-to-end, especially §0 + §3 + §5 + §6 + §7 + §8 + §9 + §10 + §11 + §12). Phase 3.2 is the data-pass sub-phase: category seed rewrite + Provider/Program backfill (4 passes including Bucket C locks) + district seed (10 districts as backend tag, paragraphs NULL per path (b) operator lock) + `entities.district_id` backfill from String column + `entities.featured` backfill from Provider + `users.preferred_mode` backfill + NOT NULL flip (no-op since 3.1 shipped direct-NOT-NULL) + `CATEGORY_LABELS` update at `app/home/queries.py` + validator vocab update at `scripts/ingest/validate_enrichment_csv.py` + Phase 3 close-out. **Single alembic migration** `<rev>_phase3_data_pass.py` chaining off `d0e1f2a3b4c5` (Phase 3.1 schema additions).
>
> **Gating dependency:** Phase 3.1 (additive v1.1 schema additions) MUST have shipped on origin before Phase 3.2 dispatches. The 3.2 alembic migration chains off `d0e1f2a3b4c5` per `python -m alembic heads` at dispatch time.
>
> **Operator decision-locks captured at session-21 authoring time (all LOCKED — do not relitigate inside the dispatch):**
> 1. **5 Bucket C category-backfill decisions** (brief §7) — locked at recommendation: `beauty_personal_care` → NULL queue (V1.5 defer); `tourism` → NULL queue for operator triage; `barbershop` test fixture → NULL; K-12 / charter / public schools → `classes-sports-recreation`; bowling / arcades / mini golf → `classes-sports-recreation`.
> 2. **District UX direction** (brief §7 operator reality check) — locked as path (b): seed 10 districts as backend tag with `slug + name + display_order` from the draft naming order, `paragraph` column NULL. NO paragraph landing pages in Phase 6 — that work defers cleanly to V1.5 where the UX primitive can be re-thought. Do NOT polish or insert the draft paragraphs; do NOT read them as canonical content.
>
> **No additional operator prereq for 3.2.** R2 / Resend env vars are live in Railway since session-17/19. Phase 3.2 is a portable additive data migration — no external-service prereq.

---

```
Read outputs/cursor_brief_phase_3_v11_schema_pass.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3 (sub-phase
boundaries -- 3.2 IS the Phase 3 close-out), §5 (Phase 3.2
deliverable list), §6 (locked decisions), §7 (operator decision-
locks -- all 5 Bucket C items + district UX direction are LOCKED
per dispatch-prompt header above), §8 (Postgres portability), §9
(acceptable deviations -- Phase 3.2 subsection), §10 (risk
register), §11 (what NOT to do), §12 (final report format).

ALSO read docs/maintainability/category_backfill_mapping_audit_2026-
05-14.md §2 end-to-end. That memo is the authoritative source for
the Bucket A + Bucket B + Bucket C category backfill mapping; the
brief §5.2 cites it. Do NOT re-derive the mapping; do NOT improvise
new mappings; do NOT extend the mapping to strings not present in
the audit.

Phase 3.1 of the master build plan SHIPPED on origin at commit
7925a14 (v1.1 schema additions: 5 new tables -- districts,
alert_subscriptions, alerts_dispatched, external_conditions_cache,
peer_recommendations -- plus 7 new entity columns plus
users.preferred_mode NOT NULL with server_default='default' plus
ORM model classes plus 17 new tests). Run `git log --oneline -10`
and report the top SHAs. Pytest collect baseline going in is
**1681** tests collected (1680 passed + 1 skipped + 30 subtests).
Alembic head is **d0e1f2a3b4c5** (the Phase 3.1 schema-pass
revision, chained off f9e8d7c6b5a4 from Phase 2B.1 photos). Chain
the Phase 3.2 data-pass migration off d0e1f2a3b4c5 -- verify with
`python -m alembic heads`.

Ship Phase 3.2 ONLY per §3 + §5 of the brief -- this is a data-
pass sub-phase. Single alembic migration <rev>_phase3_data_pass.py
chaining off d0e1f2a3b4c5. The migration is DATA-ONLY with two
small schema changes (drop entities.district String column AFTER
backfill per §5.4; users.preferred_mode NOT NULL flip is no-op
since 3.1 already direct-NOT-NULL per master plan §4 Phase 3
"Shipped (incremental)" deviation (b)). All other work is INSERT
INTO + UPDATE statements driven by the audit memo §2 mapping.

LOCKED OPERATOR DECISIONS (do NOT relitigate inside the migration;
encode them as explicit SQL):

A. The 5 Bucket C category-backfill decisions (brief §7):
   1. `beauty_personal_care` (Bucket C) -> NULL (V1.5 deferral)
      UPDATE providers SET category_id = NULL
      WHERE category = 'beauty_personal_care' AND category_id IS NULL
      (Same NULL-queue shape as Bucket B professional-services per
      brief §5.2 Pass 3.)
   2. `tourism` (Bucket C) -> NULL (operator triage queue)
      UPDATE providers SET category_id = NULL
      WHERE category = 'tourism' AND category_id IS NULL
   3. `barbershop` test fixture (Bucket C) -> NULL
      UPDATE providers SET category_id = NULL
      WHERE category = 'barbershop' AND category_id IS NULL
      (Note: this is a test-only fixture string. Operator confirmed
      NULL during session-20 decision lock. Doesn't matter for V1
      surface; documented for audit trail.)
   4. K-12 / charter / public schools (Bucket C) -> classes-sports-
      recreation. The audit memo §2 enumerates the exact strings
      that fall under this bucket; mirror that list verbatim. Cursor
      MUST re-read audit memo §2 before authoring this UPDATE to
      pin the exact source strings (e.g., 'k12_school', 'charter_school',
      'public_school' -- verify against audit memo not this prompt).
      UPDATE providers SET category_id = (SELECT id FROM categories
      WHERE slug='classes-sports-recreation')
      WHERE category IN (<exact strings per audit memo §2>)
      AND category_id IS NULL
   5. Bowling / arcades / mini golf (Bucket C) -> classes-sports-
      recreation. Same shape; pull the exact strings from audit memo
      §2 (likely 'bowling', 'arcades', 'mini_golf' or similar).
      UPDATE providers SET category_id = (SELECT id FROM categories
      WHERE slug='classes-sports-recreation')
      WHERE category IN (<exact strings per audit memo §2>)
      AND category_id IS NULL

B. District UX direction = path (b): seed 10 districts as backend
   tag with slug + name + display_order from the draft naming
   order; paragraph column = NULL on every row. Do NOT read or
   insert the paragraph bodies from
   outputs/chatgpt_response_district_paragraphs_v1.md -- that draft
   was flagged as illustrative not canonical at session-20. The
   draft survives as the SOURCE of the 10 district names + the
   display_order ordering; nothing else from the draft propagates
   into the seed.

   The 10 districts to seed (slug, name, display_order):
   ( english-village,         English Village,        1 )
   ( downtown-main-street,    Downtown / Main Street, 2 )
   ( north-end,               North End,              3 )
   ( lakefront,               Lakefront,              4 )
   ( mesquite-bay,            Mesquite Bay,           5 )
   ( highway-95-corridor,     Highway 95 Corridor,    6 )
   ( site-six,                Site Six,               7 )
   ( pittsburgh-point,        Pittsburgh Point,       8 )
   ( castle-rock-area,        Castle Rock area,       9 )
   ( south-side,              South side,            10 )

   Use op.bulk_insert against the districts Table object (NOT raw
   INSERT string concat) to bind id (uuid4 string), slug, name,
   paragraph=None, display_order, created_at=sa.func.now(),
   updated_at=sa.func.now(). Postgres-portable parameter binding;
   no SQL injection surface even with future paragraph content. The
   id column is VARCHAR(36) per Phase 3.1 migration -- use
   str(uuid.uuid4()) in Python at migration-author time, not at
   runtime, so the seed is deterministic across re-runs (idempotency
   matters; see Pass §5.4 backfill below).

   Idempotency: pre-flight check `SELECT COUNT(*) FROM districts`;
   if count > 0, skip the bulk_insert (migration already ran). This
   makes the seed safe under partial-failure replay scenarios.

ORDER MATTERS WITHIN PHASE 3.2:
1. First: read brief §0 step 6 + step 7 docs + source files. Re-
   read audit memo §2 end-to-end to pin the exact Bucket A + B + C
   source strings (the brief was authored at session-19; audit memo
   is the immutable source). Note that line offsets in
   app/home/queries.py:27-55 may have moved since session-19
   authoring (no recent commits to that file but verify before
   anchoring edits). Same for scripts/ingest/validate_enrichment_csv.py.
2. Then: new alembic migration <rev>_phase3_data_pass.py per brief
   §5. Chains off d0e1f2a3b4c5 -- always trust `alembic heads` over
   the brief.
3. Then: §5.1 category seed update. Five steps:
   3a. Rename 7 surviving slugs via op.execute() with portable SQL
       per brief §5.1 step 1. The 7 UPDATEs each set slug + name to
       the new values; legacy slugs at old shape.
   3b. Pre-flight FK guard per brief §5.1 step 2 + §5.11 + risk
       register row #1: COUNT(*) on entity_categories rows that
       FK into categories.id where slug IN ('family', 'community').
       If count > 0: NULL the entity_categories.category_id for
       those rows (preserves the entity-row pair record) OR DELETE
       the entity_categories rows entirely (removes the pair).
       Cursor's call per data semantics; flag in §13. ALSO check
       other FK referencers if any (e.g., if entities or providers
       FK directly into categories — verify via models.py).
   3c. DELETE FROM categories WHERE slug IN ('family', 'community')
   3d. INSERT 2 new categories: classes-sports-recreation +
       public-civic-resources. Use op.bulk_insert with proper
       parameter binding (mirror the district seed pattern); UUIDs
       generated at migration-author time for determinism.
   3e. Reset sort_order per Tier 1/2/3 ordering per brief §5.1 step
       5. The brief suggests Tier 1: eat-drink (1), home-property-
       services (2), health-wellness-care (3), shopping-essentials
       (4), auto-rv-fuel (5); Tier 2: outdoors-parks-trails (6),
       on-the-water (7), classes-sports-recreation (8), events (9),
       lodging-vacation-rentals (10); Tier 3: pets (11), public-
       civic-resources (12). Verify against synthesis §1 (cited in
       brief §5.1); synthesis wins if it differs. Cite synthesis
       in the migration docstring per brief §5.1 step 5.
4. Then: §5.2 Provider/Program category backfill. FOUR passes per
   brief §5.2:
   4a. Pass 1 (Bucket A, ~24 strings): slug-rename-only mapping.
       For each (legacy_string, new_slug) pair in audit memo §2
       Bucket A list, run:
       UPDATE providers SET category_id = (SELECT id FROM categories
       WHERE slug='<new_slug>')
       WHERE category = '<legacy_string>' AND category_id IS NULL
       Same pattern for programs.activity_category if present (Phase
       1A may have unified the column shape on programs; verify via
       app/db/models.py before authoring).
   4b. Pass 2 (Bucket B improved homes, 5 strings per brief §5.2):
       childcare_education / education / edu -> classes-sports-rec;
       religion_community -> public-civic-resources; fitness_sports
       -> health-wellness-care (partial backfill; recreational
       subset re-triages in Phase 5 per audit memo §4 item 12);
       entertainment_attractions DEFER to Phase 5 (leave NULL, will
       surface in operator queue).
   4c. Pass 3 (Bucket B professional-services V1.5 deferral, 5
       strings):
       UPDATE providers SET category_id = NULL
       WHERE category IN ('insurance', 'financial', 'legal',
       'real_estate', 'professional_services')
       AND category_id IS NULL
       Surface count in §13 report.
   4d. Pass 4 (Bucket C operator-locked, 5 strings per the LOCKED
       OPERATOR DECISIONS block above). Encode each Bucket C
       decision as explicit SQL per the locks; do NOT improvise;
       do NOT halt for re-decision (already locked at session-21).
   4e. After all 4 passes: surface counts in §13 report per pass +
       overall (rows updated, rows NULL, rows unmapped if any).
       Idempotency guard `AND category_id IS NULL` on each UPDATE
       makes re-run safe.
5. Then: §5.3 district seed per LOCKED OPERATOR DECISIONS block B
   above. 10 op.bulk_insert rows with slug + name + display_order +
   paragraph=None + timestamps. Pre-flight idempotency check.
6. Then: §5.4 entities.district_id backfill from existing String
   `district` column per brief §5.4:
   UPDATE entities SET district_id = (
     SELECT districts.id FROM districts
     WHERE LOWER(TRIM(districts.name)) = LOWER(TRIM(entities.district))
   )
   WHERE district IS NOT NULL AND district_id IS NULL
   Unmatched String values (no matching row) leave district_id
   NULL. Surface unmatched count in §13 report.
   After backfill: op.batch_alter_table('entities') as batch_op:
       batch_op.drop_column('district')
   ORDER: backfill BEFORE drop_column. Per brief §5.11.
7. Then: §5.5 entities.featured backfill from Provider.featured for
   commercial entities per brief §5.5:
   UPDATE entities SET featured = (
     SELECT providers.featured FROM providers
     WHERE providers.entity_id = entities.id
   )
   WHERE entity_type = 'commercial'
   AND id IN (SELECT entity_id FROM providers WHERE featured = TRUE)
   Non-commercial entities keep featured=false (default from 3.1).
8. Then: §5.6 users.preferred_mode backfill + NOT NULL flip is a
   NO-OP since Phase 3.1 shipped direct-NOT-NULL with
   server_default='default' per master plan §4 Phase 3 Shipped
   (incremental) deviation (b). The 3.2 migration documents this in
   a comment block but does no SQL for this step.
9. Then: anchored Edit on app/home/queries.py per brief §5.7. The
   CATEGORY_LABELS constant is at approximately lines 27-55 (re-
   grep to anchor). Replace the ~28-line dict with the new-taxonomy
   12 slug -> display name mapping, ordered per Tier 1/2/3 sort:
       'eat-drink':                'Eat & Drink',
       'home-property-services':   'Home & Property Services',
       'health-wellness-care':     'Health, Wellness & Care',
       'shopping-essentials':      'Shopping & Essentials',
       'auto-rv-fuel':             'Auto, RV & Fuel',
       'outdoors-parks-trails':    'Outdoors, Parks & Trails',
       'on-the-water':             'On the Water',
       'classes-sports-recreation':'Classes, Sports & Recreation',
       'events':                   'Events',
       'lodging-vacation-rentals': 'Lodging & Vacation Rentals',
       'pets':                     'Pets',
       'public-civic-resources':   'Public & Civic Resources',
   Verify the exact dict shape (OrderedDict vs dict vs list of
   tuples) by reading the source first; preserve the shape.
10. Then: anchored Edit on scripts/ingest/validate_enrichment_csv.py
    per brief §5.8. Find the category allowlist constant (list /
    set / dict — read the file to determine shape). Update to
    contain the new 12 slugs. Add the 7 renamed legacy slugs (`eat-
    and-drink`, `home-services`, `health`, `outdoors-and-parks`,
    `shopping`, `auto-and-gas`, `lodging`) plus deleted slugs
    (`family`, `community`) to a "rejected" list so legacy CSVs
    fail validation with a clear error.
11. Then: downgrade() reverses ALL of the above by:
    - Re-creating the entities.district String column via
      op.batch_alter_table
    - Reverse-backfilling district_id -> district String (SELECT
      name from districts where id = entities.district_id)
    - Setting category_id = NULL on rows the migration backfilled
      (per brief §5.2 reverse semantics; restores pre-3.2 state)
    - Setting featured = false on entities (reversed from Provider
      backfill)
    - DELETE FROM districts (all 10 rows) -- gated on
      idempotency seed pattern
    - DELETE FROM categories WHERE slug IN ('classes-sports-
      recreation', 'public-civic-resources')
    - INSERT INTO categories family + community (restoring deleted
      rows with original UUIDs IF retrievable; otherwise new UUIDs
      and document the slug-only-restoration semantics in §13)
    - Reverse-rename the 7 surviving slugs back to legacy names
    - Reset sort_order to pre-3.2 state (capture in migration
      docstring as a reference for future Cursor inheritance)
    Reversibility test required per brief §5.9 test 2 + §5.10.
12. Then: new tests per brief §5.9 in tests/test_phase3_data_pass.py
    (~15-20 tests). MODIFIED test #13: "Slug english-village exists
    in districts; paragraph column IS NULL" (path b lock — was "non-
    empty"). All other tests per brief §5.9 unchanged. Specifically:
      1.  Migration upgrade reaches new revision cleanly
      2.  Migration downgrade restores pre-3.2 state (per brief §5.9
          test 2)
      3.  After upgrade: categories table has exactly 12 rows
      4.  After upgrade: slugs match new-taxonomy 12 list (set ==)
      5.  After upgrade: `family` + `community` slugs absent
      6.  After upgrade: `classes-sports-recreation` + `public-
          civic-resources` slugs present
      7.  After upgrade: sort_order reflects Tier 1/2/3 ordering
      8.  Bucket A: fixture provider category='food_drink' ->
          category_id points to eat-drink row
      9.  Bucket B: fixture provider category='childcare_education'
          -> category_id points to classes-sports-recreation
      10. Bucket B: fixture provider category='religion_community'
          -> category_id points to public-civic-resources
      11. Bucket B V1.5 defer: fixture provider category='insurance'
          -> category_id IS NULL
      12. Districts table has exactly 10 rows after seed
      13. (MODIFIED per path b lock): slug 'english-village' exists
          in districts; paragraph column IS NULL (NOT non-empty);
          name = 'English Village'; display_order = 1
      14. entities.district_id backfill: fixture entity with
          district='English Village' -> district_id points to
          english-village row
      15. entities.district String column has been dropped (verify
          via inspect(engine).get_columns('entities'))
      16. entities.featured backfill: fixture provider featured=TRUE
          -> resulting Entity featured=TRUE
      17. CATEGORY_LABELS now contains new-taxonomy slugs (assert
          dict subset / key set match in app/home/queries.py)
      18. Validator vocab now rejects deleted slugs (`family`,
          `community`, renamed-legacy 7) + accepts new slugs
      19. Backfill is idempotent (re-running migration's data-pass
          logic produces identical state)
      20. Pre-flight FK guard: fixture with entity_categories row
          pointing at `family` produces defensive resolution before
          the DELETE per brief §5.1 step 2 (Cursor's choice between
          NULL or DELETE; pin behavior in test)
      21. (NEW) Bucket C lock: fixture provider category=
          'beauty_personal_care' -> category_id IS NULL
      22. (NEW) Bucket C lock: fixture provider category='tourism'
          -> category_id IS NULL
      23. (NEW) Bucket C lock: fixture provider category='k12_school'
          (or whichever audit-memo string for schools) ->
          category_id points to classes-sports-recreation
      24. (NEW) Bucket C lock: fixture provider category='bowling'
          (or audit-memo string) -> category_id points to classes-
          sports-recreation

13. After all of the above: confirm full pytest stays green, ruff
    clean, that `python -m alembic upgrade head` against a fresh
    dev DB reaches the new data-pass revision cleanly + alembic
    head advances by one. Then ALSO confirm `python -m alembic
    downgrade -1 && python -m alembic upgrade head` cycles cleanly
    (verify reversibility per §5.10). No manual smoke required
    for 3.2 (no user-visible surface; CATEGORY_LABELS change is
    backend-only until Phase 5/6 wires category landing pages).

POSTGRES COMPATIBILITY (carried forward from brief §8):
- The bash sandbox + tests run SQLite; production runs Postgres.
- Phase 2A.1 92ce4899dc08, Phase 2B.2 c8d9e0f1a2b3, Phase 2B.1
  f9e8d7c6b5a4, and Phase 3.1 d0e1f2a3b4c5 migrations are the
  recent precedents for portable migrations. Mirror their shape.
- Use sa.true() / sa.false() (NOT sa.text("1") / sa.text("0")) for
  Boolean server_default values.
- Use sa.func.now() (NOT sa.text("CURRENT_TIMESTAMP")) for default
  timestamps.
- For raw SQL inside op.execute(): the subquery UPDATE shape
  (UPDATE providers SET category_id = (SELECT id FROM categories
  WHERE slug='...') WHERE category = '...' AND category_id IS NULL)
  is portable across both dialects per brief §9 Phase 3.2 paragraph
  2. Do NOT use Postgres-only JOIN-style UPDATE (UPDATE providers
  SET category_id = c.id FROM categories c WHERE ...) — that breaks
  SQLite.
- For LOWER(TRIM(...)) string-comparison in the district_id backfill
  (brief §5.4): both dialects support both functions. Portable.
- For op.bulk_insert with Table objects: portable parameter binding;
  no SQL-injection surface. Use this for category seed inserts +
  district seed inserts. Do NOT use raw INSERT string concat per
  risk register row #3.
- For batch_alter_table on entities (drop_column): SQLite requires
  batch_alter_table for column drops; Postgres prefers it for
  consistency. Mirror Phase 1D + 2A.1 pattern.
- Idempotency: AND category_id IS NULL guard on each UPDATE makes
  re-run safe (risk register row #9).

DEVIATION INVITATIONS (per brief §9 Phase 3.2 subsection):
- entity_categories orphan handling on family/community delete --
  NULL vs DELETE -- Cursor's call per data semantics; flag in §13.
- Bucket A SQL pattern -- subquery vs JOIN-style UPDATE -- subquery
  is portable; flag any deviation.
- District seed paragraph rendering -- IRRELEVANT under path (b)
  since all paragraphs are NULL.
- Bucket B partial backfill for fitness_sports -- brief says force
  to health-wellness-care; Cursor may prefer NULL queue for the
  recreational subset. Flag if deviating.
- CATEGORY_LABELS Tier ordering -- synthesis §1 wins if it differs
  from brief §5.1. Cite synthesis source in migration docstring.
- validate_enrichment_csv.py allowlist shape -- read existing shape
  before anchoring edits; flag any deviation from brief's "set
  literal" assumption.

WHAT NOT TO DO (per brief §5.11 + §11 + LOCKED OPERATOR DECISIONS
block):
- Don't relitigate the 5 Bucket C decisions. They are LOCKED per
  the dispatch-prompt header. Encode the locks as explicit SQL.
- Don't relitigate the district UX direction. Path (b) is LOCKED
  per the dispatch-prompt header. 10 districts seeded with
  paragraph=NULL. Don't read or insert the draft paragraphs.
- Don't propose a 13th category. 12-slug count is LOCKED per
  synthesis §1.
- Don't force any of the 5 professional-services strings into an
  imperfect home. NULL queue is LOCKED (Bucket B Pass 3).
- Don't skip the pre-flight FK guard on entity_categories ->
  categories before deleting family + community rows. Risk register
  row #1.
- Don't drop entities.district String column BEFORE backfilling
  district_id -- order matters; drop column AFTER backfill per
  step 6.
- Don't drop Provider.featured column -- Phase 13+ only.
- Don't drop legacy Provider.category text column -- V1.5 / Phase
  13 only after the operator queue surfaces are reviewed.
- Don't process Bucket C decisions inline without using the LOCKED
  values above. If a string surfaces during dispatch that isn't in
  audit memo §2 + isn't covered by the LOCKED OPERATOR DECISIONS
  block, HALT and flag in §13 -- do NOT improvise a mapping.
- Don't modify the audit memo or synthesis docs.
- Don't change the order of the new-taxonomy 12 sort_order without
  re-verifying against synthesis §1.
- Don't change CATEGORY_LABELS or validator vocab beyond what the
  audit memo + synthesis specify.
- Don't touch admin form free-text category field at
  app/admin/router.py:1439 -- Phase 5 owns admin form extensions.
- Don't touch chat-route response shape. Phase 3 ships zero new
  chat surfaces.
- Don't seed paragraph content into the districts table. Paragraph
  column is NULL on every seed row per path (b) lock.
- Don't read outputs/chatgpt_response_district_paragraphs_v1.md
  for content -- the draft is illustrative not canonical. The
  district NAMES + display_order come from the dispatch-prompt
  header LOCKED OPERATOR DECISIONS block B, not the draft.
- Don't run any external HTTP calls during the migration. Pure
  SQL + Python data-binding only.
- Don't push without operator approval. Rules 2 + 12.
- Don't dispatch Phase 4 or any other lane in the same Cursor
  session. HALT at the Phase 3 close-out boundary -- this dispatch
  IS the Phase 3 close-out; Phase 4 dispatches in a fresh session.

HALT at the Phase 3 close-out boundary. Phase 3.2 IS the Phase 3
close-out -- once 3.2 ships + commits, Phase 3 of the master build
plan is COMPLETE. Operator dispatches Phase 4 (background-jobs +
layered scrape infrastructure) in a fresh session after the Phase
3 close-out docs land (master plan §4 Phase 3 SHIPPED header +
STATE.md Production block refresh).

Same constraints as Phase 3.1 + prior sub-phases:
- Anchored Edit on existing files (app/home/queries.py +
  scripts/ingest/validate_enrichment_csv.py); Write only for new
  files (the new migration + new test file) (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 3.2 only

Pre-dispatch checklist (verify before paste):
- Phase 3.1 has shipped on origin at 7925a14
- d0e1f2a3b4c5 is the current single alembic head
- Pytest baseline going in is 1681 (or matches reality `python -m
  alembic heads` + `pytest --collect-only` return)
- 5 Bucket C decisions are LOCKED per dispatch-prompt header
- District UX direction is LOCKED as path (b) per dispatch-prompt
  header
- Audit memo (docs/maintainability/category_backfill_mapping_audit_
  2026-05-14.md §2) is the authoritative source for Bucket A + B
  + C source strings; re-read before authoring backfill SQL
```

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phases: paste back to the Cowork primary chat, primary reviews against §5.10 acceptance gates + brief §11 scope discipline + LOCKED OPERATOR DECISIONS adherence, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

**Cross-check Cursor's claimed file list against actual `git status` Windows-side before staging** per session-20 lesson 3 (Cursor §11 prose may be descriptive not change-revealing).

Expected files touched:
- 1 new alembic migration (`alembic/versions/<rev>_phase3_data_pass.py`)
- 1 modified `app/home/queries.py` (CATEGORY_LABELS dict replaced)
- 1 modified `scripts/ingest/validate_enrichment_csv.py` (allowlist + rejected list updated)
- 1 new test file (`tests/test_phase3_data_pass.py` ~20-24 tests)

Expected pytest delta: +20-24 net-new tests. Pre-existing chat-route + Provider-profile + search + photos + Phase 3.1 schema tests must all stay green.

Expected effort: 5-8 day brief estimate; one Cursor session realistically (may run longer than 3.1 due to 4-pass backfill complexity + downgrade reversibility).

Expected pragmatic deviations:
1. `entity_categories` orphan handling on family/community delete — NULL vs DELETE — Cursor picks; flag in §13.
2. Bucket A SQL pattern — subquery vs JOIN-style UPDATE — subquery is portable; flag any deviation.
3. Bucket B `fitness_sports` partial backfill — brief says force to health-wellness-care; Cursor may prefer NULL queue. Flag if deviating.
4. CATEGORY_LABELS dict shape (OrderedDict vs dict vs list of tuples) — Cursor reads existing shape, preserves.
5. validate_enrichment_csv.py allowlist shape (list / set / dict) — Cursor reads existing shape, preserves.
6. Downgrade reversal of category UUID values — re-INSERTing deleted family + community with new UUIDs vs preserving original UUIDs (likely not retrievable post-DELETE). Document the slug-only-restoration semantics in §13 if applicable.
7. Sort_order pre-3.2 reference for downgrade — capture in migration docstring as a snapshot.

## Commit recipe (after Cursor §13 lands and Casey approves)

PowerShell-safe single-quoted `-m '...'` body. No embedded double-quotes per gotcha #16. Suggested subject:

```
feat(db+app): Phase 3.2 -- category taxonomy rewrite + audited backfill + district seed as backend tag + entity backfills + Phase 3 close-out
```

(Single subject line; body uses plain text or em-dashes for emphasis; cite the audit memo + brief §5 + the LOCKED OPERATOR DECISIONS values in the body.)

## After Phase 3.2 ships

Phase 3 is COMPLETE on origin. Update master plan §4 Phase 3 — add a Phase 3.2 ship-line under the "Shipped (incremental)" subsection AND add a Phase 3 SHIPPED header at the top of §4 Phase 3 (same pattern as Phase 1 / Phase 2 close-outs). Update STATE.md Production block + "Recently shipped" §1 with the 3.2 close-out narrative + Phase 3 SHIPPED annotation. Update the district paragraphs draft (`outputs/chatgpt_response_district_paragraphs_v1.md`) top-matter to note that path (b) shipped — paragraphs deferred to V1.5; draft preserved for V1.5 re-engagement.

Phase 4 (background-jobs + layered scrape infrastructure) becomes the next dispatchable major phase per master plan §4 Phase 4. The Phase 4 brief authoring is a separate dispatch-prep task; not gated by Phase 3 close-out.
