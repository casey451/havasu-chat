# Cursor Dispatch Prompt — Phase 1C

> Short paste-into-Cursor prompt for Phase 1C dispatch. The heavy-prescriptive operating doc remains `outputs/cursor_brief_phase_1_entity_schema.md`.

---

```
Read outputs/cursor_brief_phase_1_entity_schema.md end-to-end again.

Phase 1A (ff9832d) and Phase 1B (d475b06) are both SHIPPED per master plan
§4 Phase 1 "Shipped (incremental)" list — start your §0 baseline against
current main HEAD (run git log --oneline -5; should top at recent session-15
commits including 24fa935).

Ship Phase 1C ONLY per §3 + §7 of the brief — the application read pivot.
Touch list:
- app/providers/queries.py
- app/providers/view_models.py
- app/chat/tier2_db_query.py
- app/contrib/places_client.py
- app/contrib/enrichment.py
- scripts/places_load.py

Per-file pattern choice per §7.1:
- Pattern A (ENTITY-first) for app/chat/tier2_db_query.py
- Pattern B (Legacy + alias via Provider.entity relationship) for
  app/providers/queries.py and app/providers/view_models.py
- Light touches on app/contrib/* and scripts/places_load.py (read paths
  only; writes stay legacy-only — dual-write lands in Phase 1D)

THIS IS THE HIGHEST-RISK SUB-PHASE. Chat-route response shape must not
change. Provider profile page must render identical HTML. Tier 2 catalog
lookup must return identical rows in identical order. §7.3 regression
coverage is REQUIRED, not optional:
- Extend tests/test_chat_route_integration.py with at least 3 new methods
  pinning pre-vs-post output for representative queries
- Extend or create tests/test_provider_profile_page.py to assert identical
  rendering for a representative Provider with hours, contact info, category
- New tests/test_tier2_db_query_entity_pivot.py with at least 5 query-shape
  regressions (entity-named, category-named, time-windowed, location-filtered,
  open-now)

HALT at the §3 Phase 1C boundary. Do not start Phase 1D.

Same constraints as 1A/1B:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per §13

Operator note: if you haven't already, drop+recreate the local SQLite dev
DB before §0 — Phase 1A's Path A self-check surfaced pre-1A drift at
"1a2b3c4d5e6f → 2a3b4c5d6e7f duplicate column name: slot"; recreating
clears it so §0 baseline runs clean against a fresh DB walking the full
chain through b2c3d4e5f6a7.
```

---

## After Cursor returns with the §13 report

Same rhythm as 1A + 1B: paste back here, primary reviews against §7 acceptance gates (§7.4), recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 6 modified application/script files
- 3 new or extended test files (regression coverage)
- Possibly 1-2 light helper modules if Cursor factors shared logic (e.g., `Provider.entity.*` join helpers)

Expected pytest delta: +15-25 new regression tests (the brief specifies ≥5 in `test_tier2_db_query_entity_pivot.py` plus extensions to existing test files).

Expected effort: 7-10 day brief estimate; one or two Cursor sessions realistically.

Expected pragmatic deviations: file-path-overlap with Phase 1B's `app/db/models.py` (Provider.entity / Event.entity / Program.entity relationships added in 1B will be read in 1C — no conflict, just a dependency). Possibly more if Cursor finds that some query shapes don't pivot cleanly through ENTITY without additional join helpers — flag and accept if reasonable per brief §11.
