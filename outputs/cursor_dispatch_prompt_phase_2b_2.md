# Cursor Dispatch Prompt — Phase 2B.2 (Postgres FTS + pg_trgm + chat tier 2 LIKE→FTS swap)

> Short paste-into-Cursor prompt for Phase 2B.2 dispatch — the middle sub-phase of Lane 2B (image storage + search) of Phase 2 of the master build plan. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_2b_image_storage_search.md` (read it again, especially §3 + §6 + §9 + §10 + §11 + §12). Phase 2B.2 is the **dependency-free** sub-phase of Lane 2B — it can dispatch independently of Phase 2A.3 (which 2B.1 depends on). Per dispatch_protocol Rule 3, 2B.2 is file-disjoint from any in-flight 2A lane, so it can run as a parallel second-Cursor lane.
>
> **Operator gate:** Phase 2B.2 has **NO operator prereq** (R2 setup is only needed for 2B.1 photos, not for FTS). The brief's §0 step 8 may surface a check for R2 env vars; ignore that for 2B.2 dispatch since the brief is scoped across all three Lane 2B sub-phases — the §0 baseline check Cursor will run is fine as-is.

---

```
Read outputs/cursor_brief_phase_2b_image_storage_search.md end-to-end,
especially §3 (sub-phase boundaries, halt etiquette), §6 (Phase 2B.2
deliverable list — the most complex sub-phase of Lane 2B), §9 (what
NOT to do — Postgres portability + FTS-on-SQLite handling), §10
(acceptable deviations), §11 (risk register), §12 (final report format).

Phase 2A.1 SHIPPED on origin (commit 6000138 + 5bf4c14 dispatch
artifacts + 9150be5 docs ship-line + 2423d4f Phase 2A.2 dispatch
artifact). Phase 2A.2 may also be shipped by the time you read this
(in flight as of 2B.2 prompt authoring); run git log --oneline -10
and report the top SHAs. Lane 2B brief artifact landed at
outputs/cursor_brief_phase_2b_image_storage_search.md (uncommitted as
of authoring; will be committed alongside subsequent ship commits).
Pytest collect baseline going in is **1543** at minimum (Phase 2A.1
floor); higher if Phase 2A.2 shipped its ~20 net-new tests by
dispatch time. Alembic head is **92ce4899dc08** (Phase 2A.1 account-
lite v0.1 schema).

Ship Phase 2B.2 ONLY per §3 + §6 of the brief — Postgres FTS +
pg_trgm + chat tier 2 LIKE→FTS swap + ranking heuristic + new
app/search/ package. **No photo upload, no R2, no search bar UI** —
all of that is 2B.1 (photos, gated on 2A.3) and 2B.3 (search bar UI).

ORDER MATTERS WITHIN PHASE 2B.2:
1. First: read the docs + source files in brief §0. Note that the
   brief was authored before 2A.2 shipped, so line offsets in
   app/chat/tier2_db_query.py + app/main.py may have moved
   slightly. Verify before anchoring edits.
2. Then: factor app/search/__init__.py + app/search/fts.py per brief
   §6.1 + §6.3. The fts module provides the FTS query builder
   (websearch_to_tsquery wrappers, rank-weighted SELECT against
   entities.search_vector). Pure functions over a SQLAlchemy session;
   no side effects.
3. Then: factor app/search/sqlite_fallback.py per brief §6.4. SQLite
   doesn't support tsvector; tests + dev environment use this
   fallback path (LIKE chains on entity.name + extension columns,
   preserving the existing _category_needle_set synonym semantics).
   The dispatch decision between fts.py and sqlite_fallback.py is
   `op.get_bind().dialect.name == "postgresql"` at migration time +
   a runtime `_is_postgres()` helper for query-time dispatch. Cite
   Phase 1A's passive_deletes precedent as the SQLite-vs-Postgres
   divergence pattern.
4. Then: factor app/search/ranking.py per brief §6.5. The ranking
   heuristic per design memo: verification +30, recency +15,
   featured +25, FTS rank score (ts_rank_cd) as the base. Pure
   function: takes a (entity, fts_score) tuple, returns a final
   composite float. Easy to unit test.
5. Then: new alembic migration <rev>_entities_fts_pgtrgm.py per
   brief §6.2 + §4.2. Chains off whichever alembic head is current
   at dispatch time (92ce4899dc08 at minimum; later if 2A.2 added
   a migration — verify with `python -m alembic heads` and chain
   off the current single head). The migration:
   - adds entities.search_vector tsvector generated column
     (weighted: name A, description B, extension columns C+)
   - creates GIN index on entities.search_vector
   - creates CREATE EXTENSION pg_trgm (gated on
     dialect.name == "postgresql" via op.get_bind() check; SQLite
     path skips silently with a comment)
   - creates trigram GIN index on entities.name for typo-tolerant
     LIKE queries
   - Postgres-only DDL is gated via dialect check (NOT raised as
     errors on SQLite — silent skip with comment, so fresh-DB
     upgrade still passes on test SQLite)
6. Then: anchored Edit on app/chat/tier2_db_query.py per brief §6.6.
   Three query functions migrate from LIKE chains to FTS dispatch.
   PRESERVE THE _category_needle_set SYNONYM EXPANSION at ~:469 —
   FTS query construction MUST receive the expanded synonym set so
   Tier 2 results don't regress. Dispatch via _is_postgres() runtime
   check: postgres path uses fts.py; SQLite path uses
   sqlite_fallback.py LIKE chains. The two paths MUST return
   identical row ordering for the existing pytest baseline to stay
   green (or at worst, the FTS path needs new test fixtures and
   the SQLite path keeps the legacy fixtures — flag in §13).
7. Then: new tests per brief §6.7. Two test files:
   - tests/test_search_fts.py — Postgres path coverage (skip on
     SQLite or use a conftest fixture that boots a Postgres TestContainer
     if available; OR mark these tests as @pytest.mark.postgres-only
     and skip via conftest if dialect != postgres). ~10 tests.
   - tests/test_search_parity.py — same query input through both
     postgres and SQLite paths returns equivalent result-sets (modulo
     ordering for low-rank ties). ~6 tests. Ensures the SQLite
     fallback doesn't silently regress chat tier 2 behavior on the
     test environment.
8. After all of the above: confirm full pytest stays green, ruff clean,
   that `python -m alembic upgrade head` against a fresh dev DB
   reaches the new FTS revision cleanly (SQLite path silently skips
   FTS DDL; alembic head advances). Then ALSO confirm
   `python -m alembic downgrade -1 && python -m alembic upgrade head`
   cycles cleanly. If you have access to a Postgres test environment
   (TestContainer, local docker postgres, etc.), also smoke-test
   the FTS path with a sample query against seeded entities.

POSTGRES COMPATIBILITY (carried forward from brief §9 — extra-critical
for 2B.2 since FTS is Postgres-specific):
- The bash sandbox + tests run SQLite; production runs Postgres.
- ALL FTS DDL (CREATE INDEX ... USING GIN, CREATE EXTENSION pg_trgm,
  ALTER TABLE ... ADD COLUMN ... GENERATED ALWAYS AS) is Postgres-only.
  Gate every Postgres-only construct via dialect check inside the
  migration. SQLite path: skip silently with a one-line comment in
  the migration body explaining the dialect gate.
- Use sa.true() / sa.false() for any Boolean defaults; sa.func.now()
  for timestamps. (Unlikely 2B.2 adds new such columns, but the rule
  carries.)
- The Phase 1D migration f8e9d0c1b2a3_legacy_entity_id_not_null.py
  is the most recent precedent for a clean Postgres-portable
  additive migration; the Phase 2A.1 92ce4899dc08_account_lite_v01.py
  is the most recent precedent for indexes + CHECK constraints
  + FK ondelete = CASCADE. Mirror those shapes.

DEVIATION INVITATIONS (per brief §10):
- before_flush listener safety net for any new ORM state — likely
  not needed for 2B.2 since no new ORM model classes ship in this
  sub-phase (Photo lands in 2B.1; search_vector is a generated
  column on entities not a new class). Flag in §13 if you reach
  for it for something else.
- _hourly_cleanup_loop fold — also unlikely for 2B.2 since no new
  short-lived rows ship. Flag if applicable.
- Test-skip-on-SQLite vs Postgres-TestContainer — both are
  acceptable for the FTS-specific tests; pick whichever fits the
  existing tests/conftest.py setup cleanly and document choice in
  §13. The SQLite-LIKE-parity tests run on the existing SQLite
  test path unconditionally.
- _category_needle_set integration into fts.py vs sqlite_fallback.py
  separately — pick the shape that minimizes duplication; flag.

WHAT NOT TO DO (per brief §9):
- Don't drop or alter the existing LIKE codepath until the FTS path
  is proven equivalent in tests. The runtime dispatch via
  _is_postgres() means BOTH paths must coexist permanently for the
  SQLite test environment to keep passing. Production runs Postgres
  so the LIKE path is unreachable in prod — but it MUST stay alive
  for test parity.
- Don't add R2 / photo upload / Photo ORM class — that's 2B.1 scope.
- Don't add the search bar UI / /api/search route — that's 2B.3 scope.
- Don't touch app/auth/* (any of the Phase 2A code) — that's a
  separate file domain.
- Don't touch chat-route response shape for Tier 2 queries. The
  ranking heuristic may reorder results within the existing response
  envelope; the envelope itself stays unchanged. The pre-2B.2
  baseline pytest fixtures may need updates if the FTS-side rank
  ordering differs from the LIKE-side ordering — that's expected
  and flagged in brief §11 risk #X. Update fixtures to be order-
  insensitive where reasonable; otherwise flag in §13.
- Don't drop sqlite_fallback.py "for cleanliness" once FTS works
  in prod. SQLite tests need it indefinitely. Phase 13 cleanup may
  revisit if the test infrastructure migrates to Postgres-only;
  not before.

HALT at the §3 Phase 2B.2 boundary. After 2B.2 ships + commits, halt
for operator re-dispatch in a fresh session for 2B.3 (search bar UI +
endpoint + close-out). Do NOT start 2B.3 in the same session.

Same constraints as the Phase 2A lane:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits — Rule 2+12)
- Pytest must stay green throughout (both SQLite path AND, if you
  can boot one, the Postgres path)
- Report per brief §12 (final report format) for sub-phase 2B.2 only

Operator note: this sub-phase can dispatch in parallel with Phase
2A.2 / 2A.3 — Lane 2A's file domain (app/auth/*, app/templates/login*,
app/admin/router.py role hook) is disjoint from Lane 2B.2's
(alembic migration, app/search/* package, app/chat/tier2_db_query.py
LIKE→FTS swap). Per dispatch_protocol Rule 3, this is the kind of
parallel-eligible work the operator might run as a second Cursor
chat once the first Cursor lane is mid-flight.
```

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phases: paste back to the Cowork primary chat, primary reviews against §6.8 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 4 new files in `app/search/` (`__init__.py`, `fts.py`, `sqlite_fallback.py`, `ranking.py`)
- 1 new alembic migration (`alembic/versions/<rev>_entities_fts_pgtrgm.py`)
- 2 new test files (`tests/test_search_fts.py`, `tests/test_search_parity.py`)
- 1 modified `app/chat/tier2_db_query.py` (3 query functions migrate to dialect-dispatching FTS)
- Possibly 1 modified `tests/conftest.py` if Postgres-specific test fixtures or markers need wiring

Expected pytest delta: +14-18 net-new tests (the brief specifies ~10 FTS-path tests + ~6 parity tests). The pre-existing chat tier 2 tests should stay green after FTS dispatch — confirm via full pytest.

Expected effort: 3-4 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations: (a) FTS-test-skip mechanism (mark-and-skip vs TestContainer) — pick what fits conftest.py cleanly; (b) handling of `_category_needle_set` synonym expansion across both dispatch paths — pick the shape that minimizes duplication; (c) chat tier 2 fixture updates if FTS rank ordering differs from LIKE ordering for ambiguous queries — order-insensitive assertions are usually the cleanest fix; (d) pg_trgm `CREATE EXTENSION` may fail on some Postgres deployments that don't pre-install pg_trgm — flag if the migration needs operator-side `CREATE EXTENSION` setup OR if Railway's Postgres has pg_trgm pre-enabled (almost certainly yes; verify).

## After Phase 2B.2 ships

Update master plan §4 Phase 2 "Shipped (incremental)" list with the 2B.2 ship-line (same pattern as 2A.1 entry). Then re-dispatch for 2B.3 (search bar UI + endpoint + close-out) with a fresh dispatch prompt — author after 2B.2 lands so the prompt can cite the actual SHA + pytest delta. **Note:** if 2B.1 hasn't shipped yet (still gated on 2A.3), that's fine — 2B.3 can ship before 2B.1 since the search bar UI doesn't need photos. The full Lane 2B isn't closed-out until all three ship; the order is flexible.

## After full Lane 2B ships (2B.1 + 2B.2 + 2B.3, in any order)

Phase 2 Lane 2B is COMPLETE. Update master plan §4 Phase 2 header to mark Lane 2B as SHIPPED. Combined with Lane 2A (if shipped), Phase 2 of the master build plan is COMPLETE; Phase 3 (v1.1 schema pass + operator-curated fields + category taxonomy rewrite + district paragraphs) becomes the next dispatchable lane.
