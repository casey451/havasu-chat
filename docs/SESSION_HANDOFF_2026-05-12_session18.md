# Session-18 Handoff — 2026-05-12

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_19_boot_prompt.md`. Most state is durable on origin; this doc captures the deltas since the session-17 close (`0d73b0f`) + what's queued.

---

## §1 — What session-18 accomplished

Seven commits on origin, all pushed. Origin/main HEAD = `<TBD-this-close-out-commit-SHA>`. **Phase 2 Lane 2A is COMPLETE on origin (all 3 sub-phases shipped); Phase 2 Lane 2B is 1 of 3 sub-phases shipped (2B.2 FTS infra); 2B.1 + 2B.3 dispatch prompts pre-positioned and ready to paste.**

| Commit | Summary |
|---|---|
| `5fea2ce` | **Phase 2A.3 — claim flow + favorites + admin role parallel-path + viewer_is_owner + Lane 2A close-out.** 20 files (+1725/-17). Cursor session, single dispatch. Closes out Lane 2A — magic-link login + signed-in user sessions + claim-and-verify flow with admin review queue + favorites + admin role parallel-path on `_guard` + viewer_is_owner plumbing. Pytest **1563 → 1586** (+23 net-new). Alembic head unchanged at `92ce4899dc08` (no migration in 2A.3). Six pragmatic deviations flagged + accepted (admin claim routes location, `_guard` 403-for-non-admin, `render_tier2_provider_cards_html` helper not wired into chat formatter, claim notes UI-only, flat template path, test_auth_flow import-order fix). |
| `6f7f1e9` | Docs: Phase 2A.3 shipped line on master plan + Lane 2A SHIPPED header + dispatch prompt SHA patch. Replaced 2 duplicate "Phase 2A.3 — pending" stubs (session-17 docs hygiene) with the 2A.3 narrative + Lane 2A SHIPPED footer (lane-wide pytest delta 1518 → 1586 +68; final lane alembic head 92ce4899dc08). |
| `d631c77` | **Phase 2B.2 — Postgres FTS + pg_trgm + tier 2 LIKE→FTS dispatch.** 10 files (+761/-99). Cursor session, single dispatch. New alembic migration `c8d9e0f1a2b3_entities_fts_pgtrgm` chains off `92ce4899dc08`; dialect-gated Postgres-only DDL with SQLite no-op early return. New `app/search/` package (fts.py 140 / sqlite_fallback.py 52 / ranking.py 95). New `app/chat/tier2_synonyms.py` 95 (synonym extraction for circular-import dodge; tier2_db_query.py re-exports for back-compat). Tier 2 chat query LIKE→FTS dispatch via `_is_postgres(session)` runtime check; legacy ILIKE predicates RETAINED for SQLite parity. Pytest **1586 → 1607** (+21 net-new, 1 skipped under skip-unless-postgres). Alembic head `92ce4899dc08 → c8d9e0f1a2b3`. Six pragmatic deviations including a **scope expansion**: two partial JSON indexes on `providers.attributes` (`ix_providers_emergency_service` + `ix_providers_dog_friendly` filtered to `'true'`) beyond brief §6.2 — additive Postgres-only via dialect gate. |
| `bc9cebc` | Docs: Phase 2B.2 shipped line on master plan + STATE.md session-18 refresh (Production block 5-field update + Recent commits prepend with 5fea2ce + 6f7f1e9 + d631c77 + new Recently shipped §1 session-18 entry above session-17 entry). 2B.1 + 2B.3 pending stubs added. |
| `740223a` | Chore: Phase 2B.1 + 2B.3 dispatch prompt artifacts (pre-positioned by parallel general-purpose sub-agents during Cursor in-flight time per session-17's pre-author-while-Cursor-works pattern). 2B.1 prompt is 302 lines covering brief §5.1-§5.10 with `<TBD-FILL-AFTER-2A.3-LANDS>` placeholders + R2 operator-prereq gate; 2B.3 prompt is 281 lines covering brief §7.1-§7.4 with placeholders for 2A.3 / 2B.2 / FTS migration rev / pytest count. |
| `4cb329d` | **`dispatch_channels.md` gotcha #15** — bash mount `git` operations leave a `.git/index.lock` that Linux can't unlink, Windows `git` then refuses to commit. Surfaced mid-session when primary ran `git status -s` from bash during spot-check and Casey then hit `fatal: Unable to create .git/index.lock: File exists` on the subsequent Windows commit. Cure: `Remove-Item .git\index.lock` from PowerShell. Scope extends gotcha #4 (bash mount staleness) — bash-side git is unsafe even for read-only operations in mixed-OS sessions because of the index-lock seam. From session-19 forward, use Read + Grep + Glob tools for all working-tree inspection; bash-side git-adjacent operations are limited to `python3 + zlib.decompress` on `.git/objects/...` per gotcha #14 parent-walk pattern (those bypass the index lock). |
| `<TBD>` | This close-out commit — session-18 handoff doc + session-19 boot prompt + STATE.md Recent commits final prepend. Mirrors session-17 `0d73b0f` precedent. |

**Phase 2 scorecard:** Lane 2A COMPLETE on origin (3 of 3 sub-phases shipped — `6000138 → 714ca52 → 5fea2ce`); Lane 2B 1 of 3 shipped (`d631c77` = 2B.2). Cumulative pytest delta this session: 1563 → 1607 (+44 net-new). Final alembic head: `c8d9e0f1a2b3`. 2B.1 + 2B.3 are the only Lane 2B sub-phases remaining; both dispatch prompts pre-positioned.

---

## §2 — What's in flight or queued

- **Phase 2B.1 — ready to dispatch.** Dispatch prompt at `outputs/cursor_dispatch_prompt_phase_2b_1.md`. Brief §5 specifies the deliverables: Photo schema (FK to `entities.id` with `ondelete CASCADE`) + alembic migration chaining off `c8d9e0f1a2b3` (current head) + new `app/photos/` package (r2_client + processor + schemas + limits + routes + sweep) + main.py wiring + provider queries derive_hero_photo / derive_gallery + 6 new test files. **Operator gate:** Cloudflare R2 setup per `outputs/operator_prereqs_phase_2.md` §2 (~30-45 min) — Cloudflare bucket + API token + Railway env vars. 2A.3's claim flow + viewer_is_owner now shipped so 2B.1's upload-auth dependency is unblocked the moment R2 is locked. ~3-4 day Cursor estimate.
- **Phase 2B.3 — ready to dispatch in parallel (file-disjoint with 2B.1 per Rule 3).** Dispatch prompt at `outputs/cursor_dispatch_prompt_phase_2b_3.md`. Brief §7 specifies: new `GET /api/search` endpoint dispatching to 2B.2's FTS / SQLite-fallback infrastructure + search bar UI on home.html + provider_profile.html + new `app/static/search.js` + test suite. **No operator prereq beyond 2B.2 ship** (which is done). Independent of 2B.1 (search bar doesn't need photos; photos don't need search bar UI). ~1-2 day Cursor estimate.
- **Production deploy of `bc9cebc`-or-later** — Phase 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 are NOT yet deployed. Operator-cadence call. Chat-route response shape + anonymous-viewer experience pinned unchanged across the entire stack; safe whenever. When deploy ships, alembic advances production through `b2c3d4e5f6a7 → f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3` (three migrations). The 2B.2 migration's Postgres-only DDL (`CREATE EXTENSION pg_trgm`, `ADD COLUMN search_vector tsvector GENERATED ALWAYS AS ... STORED`, 4 CREATE INDEX statements) is the new behavior to watch on first deploy — Railway's Postgres has `pg_trgm` available; the migration is gated on `bind.dialect.name == "postgresql"` so it short-circuits on the SQLite test path. Operator should also smoke the FTS path on Railway/staging Postgres with a Tier 2 query + confirm `EXPLAIN` uses GIN where expected + run the `downgrade -1` / `upgrade head` cycle there before counting it as proven.
- **Phase 3 district paragraphs polish** — 5 `[CASEY: ...]` placeholders + 5 "Casey to verify" items in `outputs/chatgpt_response_district_paragraphs_v1.md`. ~15-20 min operator polish; no rush (Phase 3 isn't dispatching until Phase 2 closes out).

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Deploy `bc9cebc`-or-later to production | Anytime | Carries Phase 1C + 1D code + Phase 2A.1/.2/.3 + Phase 2B.2. Three alembic migrations apply on first deploy. Watch Railway logs for any FTS-DDL surprise (extension permission, generated-column constraint, partial-index syntax — all standard Postgres but first deploy is the truth-teller). |
| Cloudflare R2 setup | Pre-Phase-2B.1 dispatch | ~30-45 min per `outputs/operator_prereqs_phase_2.md` §2. Path A (default `r2.dev`) is the fastest unblock; custom domain `cdn.askhava.com` can land any time before public launch. |
| Dispatch Phase 2B.1 (after R2) + Phase 2B.3 in parallel | Anytime post-R2 | File-disjoint per Rule 3. Two Cursor chats. ~3-4 day + ~1-2 day estimates. 2B.3 can also dispatch independently of 2B.1 if R2 is still pending. |
| Polish district paragraphs `[CASEY: ...]` placeholders + verify items | Pre-Phase-3 dispatch | ~15-20 min. `outputs/chatgpt_response_district_paragraphs_v1.md`. Same item as session-17 §3. |
| 3 trivial category audit lock-now items + 4 Phase-3 review questions | At Phase 3 start | Carry-over from session-15 §3; not relevant before Phase 2 ships. |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember

Phase 2A.3 (commit `5fea2ce`):
- **Admin claim routes live in `app/admin/router.py`** (not `app/auth/routes.py`) — reuses `_guard`, stays next to existing admin HTML.
- **`_guard` parallel-path returns 403 for authenticated non-admin** instead of redirecting to `/admin/login` (clearer; anonymous redirect behavior unchanged).
- **`render_tier2_provider_cards_html` is a helper NOT wired into the chat Tier-2 formatter** — preserves anonymous chat response shape; ready for future catalog surfaces per brief §11 deferring merchant-edit-form UI to a follow-up lane.
- **Claim "notes" field is UI-only** (accepted on form, not persisted to DB). V1 simplicity; revisit if claim-submission needs richer data.
- **Flat `account_favorites.html` template** (matches existing template tree shape).
- **`tests/test_auth_flow.py` import-order fix** — `app.main` imported FIRST to avoid models ↔ database listener circular-import edge at pytest collection.
- **`create_pending_claim` uses `db.get(Entity, id)` + explicit `entity_is_claimable()` check** instead of brief §7.1's recommended JOIN-at-insert shape. Simpler, atomic enough.

Phase 2B.2 (commit `d631c77`):
- **Synonym helpers extracted to `app/chat/tier2_synonyms.py`** (circular-import dodge: `sqlite_fallback.py` would otherwise pull `tier2_db_query` → `models` → cycle); `tier2_db_query.py` re-exports `_category_needle_set` / `_category_synonyms` / `_singularize_category` so existing `tests/test_tier2_db_query.py` callers stay unchanged.
- **`sqlite_fallback.py` lazy-imports `Entity`** inside `build_ilike_entity_select` for the same cycle reason (mirrors Phase 1A dialect-branch discipline).
- **FTS tests Postgres-only execution path is `skip-unless-postgres`** (no TestContainers in this pass; the 1 skipped test in pytest count is this).
- **Postgres WHERE clause keeps legacy ILIKE predicates AND adds `entities.search_vector @@ to_tsquery`** as an extra OR branch (recall is a strict superset of ILIKE-only on Postgres; SQLite path uses ILIKE exclusively).
- **`to_tsquery` safety:** tokens must match `[a-z0-9]+` and `or` / `and` / `not` are dropped from input so injection-like phrases never become tsquery operators; `bindparams` used for the query string itself.
- **Scope expansion (worth grepping for later):** two partial JSON indexes on `providers.attributes` (`ix_providers_emergency_service`, `ix_providers_dog_friendly` filtered to `'true'`) were added alongside the brief §6.2-scoped FTS DDL. Additive Postgres-only performance indexes for Tier 2 attribute filters, gated to Postgres via the same dialect check so SQLite path is unaffected. Defensible but not in Cursor's flagged-deviations list — flagged here.

---

## §5 — New lessons absorbed in session-18

1. **Gotcha #15: bash mount `git` index.lock corruption in mixed-OS sessions** (commit `4cb329d`). Bash-side `git status -s` / `git diff --stat HEAD` against the working tree acquires `.git/index.lock`, can't unlink it on close (`Operation not permitted` from sandbox permission model), and the stale lock then blocks all subsequent Windows `git commit` operations. Cure: `Remove-Item .git\index.lock` from PowerShell. Scope: **bash mount git is unsafe even for read-only operations in mixed-OS sessions**; use Read + Grep + Glob tools (Windows-authoritative) for all working-tree inspection. Pure object reads via `python3 + zlib.decompress` on `.git/objects/...` per gotcha #14 are the only safe bash-side git-adjacent operation.

2. **Parallel-dispatch validation at production scale.** First time the Rule 3 parallel-dispatch posture (set up across sessions 15 + 17) actually ran with two Cursor lanes simultaneously. Both lanes worked independently on file-disjoint domains (Lane 2A: `app/auth/*` + admin/router + providers/router + claim/favorites templates + tier2_catalog_render; Lane 2B: `app/search/*` + FTS migration + tier2_db_query + new tier2_synonyms). Both returned coordinated §13 reports showing pytest 1607 — that number = 1563 baseline + 23 (2A.3) + 21 (2B.2) confirms both test suites pass together in the combined working tree. Commits stayed file-disjoint per Rule 8 (one substantive lane per commit), so the lanes split cleanly into separate substantive feat commits with their own docs commits. Pattern validates — parallel dispatch is production-ready.

3. **Sub-agents are great for docs-only dispatch-prompt authoring during Cursor in-flight time.** Two general-purpose sub-agents in parallel pre-positioned 2B.1 (302 lines) + 2B.3 (281 lines) dispatch prompts to disjoint `outputs/` paths while the Cursor 2A.3 + 2B.2 lanes were still running. Each sub-agent read the brief + the closest template prompt + wrote one new file. Worth the parent-context burn (~10 + ~17 tool calls per sub-agent reports) because next-dispatch latency drops from ~30 min brief-authoring to ~0 min paste.

4. **Working tree with both parallel lanes' code present at commit time is fine.** When two Cursor lanes operated on the same on-disk repo, both saw each other's uncommitted changes during their own work + final pytest run. The 1607 figure converged in both reports. The risk vector (one lane breaks the other's tests) didn't materialize because the lanes ARE actually file-disjoint per Rule 3 + brief §0 baseline checks halt gracefully on broken state. Rule 8 (one substantive lane per commit) preserved through `git add` per-file-list — staging only one lane's files at a time per commit kept the commit narratives clean.

5. **Pre-author-while-Cursor-works pattern continued.** Session-17 pre-positioned 2A.2 / 2A.3 / Lane 2B brief + 2B.2 prompt during Cursor in-flight time; session-18 continued with 2B.1 + 2B.3 prompts via parallel sub-agents. Pattern is now durable enough to bake into the primary's working rhythm: whenever scope for the next-after-current sub-phase is locked, author the prompt during Cursor work rather than at the next dispatch.

---

## §6 — Pointers for the next agent

Boot order:
1. `outputs/session_19_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-12 at session-18 close — start with the Production block)
3. `docs/maintainability/master_build_plan.md` §4 Phase 2 ("Shipped (incremental)" list now has full Lane 2A SHIPPED + 2B.2 ship-line + 2B.1/2B.3 pending stubs) and §4 Phase 3 (next major phase after Phase 2 closes)
4. `outputs/cursor_dispatch_prompt_phase_2b_1.md` (if dispatching 2B.1 — check R2 operator prereq first) AND/OR `outputs/cursor_dispatch_prompt_phase_2b_3.md` (if dispatching 2B.3, optionally in parallel; no operator prereq)
5. `outputs/cursor_brief_phase_2b_image_storage_search.md` §5 (for 2B.1 reference) + §7 (for 2B.3 reference) — the heavy-prescriptive operating doc
6. `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules) + `docs/maintainability/dispatch_channels.md` (15 gotchas as of session-18 close — gotcha #15 bash mount index.lock corruption is new this session)
7. `outputs/chatgpt_response_district_paragraphs_v1.md` (if spare cycles for the placeholder polish; not blocking)

Session-18 absorbed five new lessons (above) worth carrying into future dispatches. The narrative in `docs/STATE.md` "Recently shipped" §1 captures every commit + decision + deviation with enough detail that the next agent shouldn't need to re-read this handoff except for §3 + §4 above.

---

*Authored at session-18 close, 2026-05-12. Next agent picks up at Phase 2B.1 + 2B.3 parallel-dispatch posture — operator prereqs (Resend ✅; R2 ❌ until needed for 2B.1) usefully scope what can dispatch when. Once 2B.1 + 2B.3 ship, Phase 2 of the master build plan is COMPLETE and Phase 3 (v1.1 schema pass + districts + categories + alerts) becomes the next dispatchable major phase.*
