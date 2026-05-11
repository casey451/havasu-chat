# Cursor Dispatch Prompt — Phase 1D

> Short paste-into-Cursor prompt for Phase 1D dispatch — the close-out sub-phase of the Phase 1 ENTITY schema lane. The heavy-prescriptive operating doc remains `outputs/cursor_brief_phase_1_entity_schema.md` (read it again, especially §3 + §8 + §10 + §11 + §12). After Phase 1D ships, Phase 1 of the master build plan is complete and Phase 2 (account-lite + image storage + search index) becomes the next dispatchable lane.

---

```
Read outputs/cursor_brief_phase_1_entity_schema.md end-to-end again.

Phase 1A (ff9832d), Phase 1B (d475b06), and Phase 1C (e0417c8) are all
SHIPPED per master plan §4 Phase 1 "Shipped (incremental)" list. Origin/main
HEAD should top at e2e66ad (the 1C ship-line on the master plan) — run
git log --oneline -5 and confirm. Pytest collect baseline going in is
**1512** tests (1503 entering 1C + 9 net-new from the 1C regression suite).
Alembic head is b2c3d4e5f6a7 (Phase 1B backfill — unchanged through 1C
since 1C was application-layer only).

Ship Phase 1D ONLY per §3 + §8 of the brief — write dual-target +
close-out + entity_id NOT NULL flip. This is the smallest sub-phase
(3-5 day brief estimate) but it's the lane that completes Phase 1 of
the master build plan.

ORDER MATTERS WITHIN PHASE 1D (per §8.0):
1. First: factor app/db/entity_dual_write.py with create_provider_and_entity,
   create_event_and_entity, create_program_and_entity helpers. Each helper
   constructs the legacy row + Entity row + extension records in the same
   SQLAlchemy session, wires legacy.entity_id = entity.id, returns both for
   caller convenience. Idempotent — calling twice for the same input
   doesn't double-write.
2. Then: route every ingest path through the appropriate helper:
   - app/admin/router.py (admin form Provider create)
   - app/contrib/approval_service.py (contribution-approval Provider/Event/Program create)
   - scripts/places_load.py (Places loader Provider create)
   - scripts/ingest/ingest_enrichment_csv.py (CSV upsert)
   - app/contrib/parks_rec_loader.py (Parks & Rec Program create)
   - app/contrib/river_scene_pull.py / app/contrib/river_scene.py (River Scene Event create)
   - app/api/routes/events.py (or wherever Event POST lands — grep first)
3. Then: sponsor query routing per §8.2. RECOMMEND the discriminator-branching
   approach (NOT the unified Entity join) — Sponsor.business_id is currently
   Integer not String UUID, and Phase 11 monetization will unify cleanly.
   Grep for `Sponsor.business_id` to find call sites.
4. Then AND ONLY THEN: new alembic migration that flips
   providers.entity_id, events.entity_id, programs.entity_id to NOT NULL.
   Single op.alter_column × 3 with nullable=False. Migration chains off
   b2c3d4e5f6a7. Generate a fresh revision ID; do NOT reuse a placeholder.
5. After migration: run full pytest. If ANY test fails because a fixture
   path constructs a Provider/Event/Program row directly without going
   through the dual-write helper, that fixture is the bug — update the
   fixture to use the helper. The Phase 1B test
   `test_entity_id_fk_columns_remain_nullable_for_dual_write_gap` should
   now FAIL — invert it (or delete it + replace with a NOT NULL pin) since
   the gap it documented is closed.

POSTGRES COMPATIBILITY (per brief §10, session-15 lesson):
- The bash sandbox runs SQLite; production runs Postgres. The NOT NULL
  flip migration is portable (op.alter_column with nullable=False works on
  both), but if you write any other migration constructs, use Alembic
  portable helpers — sa.true()/sa.false() not sa.text("1")/sa.text("0")
  for boolean defaults; sa.func.now() not sa.text("CURRENT_TIMESTAMP")
  for timestamp defaults.

DECISION POINT FOR PHASE 1D (flag in your §13 report whichever path
you take): Phase 1C used a hybrid read pattern (legacy-driver outerjoin
Entity + entity_id IS NULL orphan fallback) instead of the brief's strict
Pattern A (ENTITY-first select(Entity)). The orphan-fallback branches
were necessary in 1C because test fixtures created legacy rows without
entity_id. After Phase 1D's dual-write helpers + NOT NULL flip land,
those orphan branches become dead code paths in production. Two options:
  Option X: leave the hybrid pattern as-is — defensive, no churn,
    re-tightening can land in Phase 13 cleanup if ever needed.
  Option Y: simplify the orphan-fallback branches in app/chat/tier2_db_query.py
    + app/providers/queries.py + scripts/places_load.py, since the
    NOT NULL constraint now guarantees every legacy row has an Entity.
RECOMMEND Option X for 1D — keep scope tight, the dead branches do no
harm, and Phase 13 has a natural cleanup pass anyway. If you want to do
Option Y as part of 1D, halt and ask before doing it (it expands scope
beyond brief §8).

Tests required per §8.3:
- Extend each ingest-path test with assertions that BOTH the legacy row
  AND the corresponding entities row + extensions are created in the same
  transaction. ~6-10 new tests across the ingest paths.
- New Sponsor-resolution test: insert a Sponsor with entity_type="commercial"
  + business_id pointing to a Provider; assert resolution returns the right
  Provider. Add at least one per entity_type the discriminator handles in
  the post-1D code (commercial today; place stays as a no-row code path).

HALT at the §3 Phase 1D boundary. After Phase 1D ships + commits, Phase 1
of the master build plan is COMPLETE — Phase 2 (account-lite + image
storage + search index) becomes the next dispatchable lane.

Same constraints as 1A/1B/1C:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits — Rule 2+12)
- Pytest must stay green throughout
- Report per §13

Operator note: the local SQLite dev DB should already be clean from
the Phase 1C dispatch prep. If not, drop+recreate it before §0 — the
NOT NULL flip migration in step 4 above won't apply cleanly to a stale
DB that has rows with NULL entity_id values.
```

---

## After Cursor returns with the §13 report

Same rhythm as 1A + 1B + 1C: paste back here, primary reviews against §8.4 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new shared helper module (`app/db/entity_dual_write.py`)
- 1 new alembic migration (the NOT NULL flip; chains off `b2c3d4e5f6a7`)
- ~7 modified ingest-path files (admin router, approval_service, places_load, ingest_enrichment_csv, parks_rec_loader, river_scene*, events route)
- 1-2 modified sponsor-query files (depending on where `Sponsor.business_id` is resolved)
- ~8-12 modified or new test files (per-ingest-path dual-write assertions + sponsor-resolution test + Phase 1B's `test_entity_id_fk_columns_remain_nullable_for_dual_write_gap` inverted/deleted)

Expected pytest delta: +10-18 net-new tests (the brief specifies ~6-10 ingest-path tests + sponsor-resolution test; reality usually trends to the upper end given the order-matters rhythm of step 5 in the prompt).

Expected effort: 3-5 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations: (a) Sponsor.business_id type mismatch may surface real complexity if there's any production sponsor data — investigate before assuming it's empty; (b) some ingest paths may have edge cases (e.g., Provider rows created via `before_insert` listeners; cross-loader idempotency) that the helper signature needs to accommodate; (c) the Phase 1B nullable-pin test will need to flip — Cursor should flag this explicitly rather than silently delete.

## After Phase 1D ships

Phase 1 of the master build plan is COMPLETE. Update master plan §4 Phase 1 "Shipped (incremental)" list with the 1D ship-line (same pattern as 1A/1B/1C entries). Then update master plan §4 Phase 1 header to mark Phase 1 as SHIPPED with overall pytest delta + total commit chain. Then standby for Phase 2 dispatch — Phase 2 is two parallel lanes (2A account-lite + 2B image storage + search index) per master plan §4 Phase 2; the lanes are file-disjoint so they can dispatch concurrently if desired (per dispatch_protocol Rule 3 — sequential when files overlap, parallel when they don't).
