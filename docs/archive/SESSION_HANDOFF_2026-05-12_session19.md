# Session-19 Handoff — 2026-05-12

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_20_boot_prompt.md`. Most state is durable on origin; this doc captures the deltas since the session-18 close (`aed79ac`) + what's queued.

---

## §1 — What session-19 accomplished

**Phase 2 of the master build plan SHIPPED to COMPLETION on origin.** Seven commits this session (including this close-out). Origin/main HEAD = `<TBD-this-close-out-commit-SHA>`. Lane 2A was closed out in session-18 (`5fea2ce`); session-19 closed out Lane 2B (final chain `d631c77 → 8338505 → 1c57c73`), which closed out Phase 2 overall.

| Commit | Summary |
|---|---|
| `8338505` | **Phase 2B.3 — public `GET /api/search` + home + provider profile search bar + Lane 2B consumer wiring.** 7 files (+769/-1). Cursor session, single dispatch. New `app/search/routes.py` (~320 lines): no-auth `GET /api/search` (q required → 400 if missing; category/district/entity_type filters; limit default 20 max 50; cursor pagination via opaque base64 `{"o":<offset>}`); response shape `{results: [...], next_cursor: str | None}` per row `{entity_id, entity_type, slug, name, description, district, hero_url, profile_url}`. Postgres dispatch via 2B.2's `search_fts.build_tsquery_string(filters)` + `search_fts.entities_search_vector_match(tsq)`; SQLite test path via in-route `_sqlite_entity_text_and` mirroring `sqlite_fallback` shape. Additive OR-branch `_provider_synonym_exists_predicate` for commercial recall using 2B.2's `_category_needle_set`. Search bar in `home.html` as `<section class="directory-search-wrap">` placed BEFORE existing hero chat composer; compact variant in `provider_profile.html` topbar. Vanilla JS at `app/static/js/search.js`. 9 net-new tests. Pytest **1607 → 1616**. Alembic head unchanged at `c8d9e0f1a2b3`. Seven pragmatic deviations flagged + accepted (most notable: brief symbol-name adaptation `build_fts_query` → actual 2B.2 names; `profile_url` additive row field; provider-synonym EXISTS scope expansion). |
| `c464007` | Docs: Phase 2B.3 shipped line on master plan §4 Phase 2 + STATE.md session-19 refresh (mid-session) + R2 prereq locked annotation on 2B.1 pending stub. |
| `1c57c73` | **Phase 2B.1 — photos schema + R2 client + Pillow pipeline + upload routes + sweep + three-tier hero/gallery + Lane 2B close-out + Phase 2 COMPLETE.** 19 files (+2296/-16). Cursor session, single dispatch; ran in parallel with 2B.3 lane. New alembic migration `f9e8d7c6b5a4_photos_table` chains off `c8d9e0f1a2b3`. New `app/photos/` package (`__init__.py`, `r2_client.py` lazy-singleton + boto3, `processor.py` 6-stage pipeline + BackgroundTask orchestrator, `routes.py` 4 endpoints, `schemas.py`, `limits.py` 20/day + 50 place / 100 commercial caps, `sweep.py` stuck-uploading row sweep). Photo model on `models.py` tail-append. `Entity.photos` viewonly relationship with string primaryjoin (circular-import dodge — no `foreign()` at class body time). `app/main.py`: `photos_router` include + `run_stuck_photo_sweep` folded into `_hourly_cleanup_loop`. `app/providers/queries.py`: `derive_hero_photo` + `derive_gallery` extended to three-tier (owner Photo → legacy pinned → Google); `selectinload(Entity.photos)` on profile load. `/api/search`'s `hero_url` consumer flows through automatically. `requirements.txt`: `Pillow==12.0.0` + `boto3==1.42.17`. `tests/conftest.py`: 5 R2_* env-var setdefault stubs. 47 net-new tests across 6 files. Pytest **1616 → 1663**. Alembic head `c8d9e0f1a2b3 → f9e8d7c6b5a4`. Migration upgrade + downgrade-1 + upgrade cycle green on SQLite (Postgres cycle pending operator smoke on Railway). Five pragmatic deviations flagged + accepted. |
| `3d89e58` | **Chore: bundled commit — Phase 3 brief + 3.1 dispatch prompt artifacts + master plan §4 Phase 2 ship-line updates + STATE.md session-19 refresh.** Originally planned as two separate commits (docs + chore) per Rule 8, but the docs commit's `-m '...'` body contained embedded `"SHIPPED 2026-05-12"` double-quotes — PowerShell's native-command argument re-tokenizer broke on the quote pair even inside the single-quoted body, causing the commit to fail with a pathspec error. The docs files stayed in the git staging index from the prior `git add`; next `git add` for outputs added to the staged set; chore commit bundled all 4 files. Subject mislabels as `chore(outputs):` but the body covers brief + dispatch prompt only; future archeologists need to look at the file list to know master plan + STATE.md are also in here. Rule 12 (don't amend pushed commits) means we live with the mislabel. **Captured as gotcha #16 candidate for `dispatch_channels.md`** (next session): even inside `-m '...'` single-quoted bodies on PowerShell, avoid embedded `"..."` double-quotes. |
| `c9ab794` | Chore: patch Phase 3.1 dispatch prompt TBD placeholders to session-19 ship SHAs (`<TBD-FILL-AFTER-2B.1-LANDS>` → `1c57c73`; `<TBD-PHOTOS-MIGRATION-REV>` → `f9e8d7c6b5a4`; `<TBD-pytest-count>` → `1663`). Mirrors session-18 patched-2A.3-prompt pattern in `6f7f1e9`. |
| `<TBD>` | This close-out commit — session-19 handoff doc + session-20 boot prompt + STATE.md Recent commits final prepend. Mirrors session-17 `0d73b0f` + session-18 `aed79ac` precedent. |

**Phase 2 scorecard:** **COMPLETE on origin.** Lane 2A chain `6000138 → 714ca52 → 5fea2ce` + Lane 2B chain `d631c77 → 8338505 → 1c57c73`. Total Phase 2 pytest delta: **1518 → 1663** (+145 net-new). Final Phase 2 alembic head: `f9e8d7c6b5a4`. Production Postgres still at `b2c3d4e5f6a7` — `f8e9d0c1b2a3 + 92ce4899dc08 + c8d9e0f1a2b3 + f9e8d7c6b5a4` all ship on the next deploy (four migrations to walk).

---

## §2 — What's in flight or queued

- **Phase 3.1 — ready to dispatch.** Dispatch prompt at `outputs/cursor_dispatch_prompt_phase_3_1.md` (patched in `c9ab794` with `1c57c73` + `f9e8d7c6b5a4` + `1663` baseline values). Brief at `outputs/cursor_brief_phase_3_v11_schema_pass.md` (~580 lines). 3.1 scope: 7 new entity columns (heat_exposure, crowd_notes, is_mobile_service, boat_access, seasonal_hours, district_id, featured) + 5 new tables (districts, alert_subscriptions, alerts_dispatched, external_conditions_cache, peer_recommendations) + users.preferred_mode column + ORM models + ~15-20 new tests. **Additive-only.** No data backfill, no category seed rewrite, no district seed — all 3.2. **No operator prereq for 3.1.** ~3-4 day Cursor estimate.
- **Phase 3.2 — pending; dispatch prompt to be authored after 3.1 ships** (chains off whatever 3.1's alembic revision is). 3.2 scope: category taxonomy rewrite (rename 7 surviving slugs + delete `family`/`community` + insert `classes-sports-recreation`/`public-civic-resources` per `docs/maintainability/category_backfill_mapping_audit_2026-05-14.md`) + audited Provider/Program category backfill (Buckets A/B/C/E per audit memo §2) + district paragraphs seed from `outputs/chatgpt_response_district_paragraphs_v1.md` (10 districts) + `entities.district_id` backfill from String + `entities.featured` backfill from Provider + `users.preferred_mode` NOT NULL flip + CATEGORY_LABELS update at `app/home/queries.py:27-55` + validator vocab update at `scripts/ingest/validate_enrichment_csv.py` + Phase 3 close-out (Phase 3 SHIPPED header). **Phase 3.2 dispatch gated on:**
  1. **Operator lock of 5 Bucket C decisions** per brief §7: `beauty_personal_care` final disposition (recommendation: NULL queue / V1.5 deferral), `tourism` final disposition (recommendation: NULL queue), `barbershop` test fixture disposition (recommendation: NULL), K-12 / charter / public schools disposition (recommendation: `classes-sports-recreation`), bowling / arcades / mini golf disposition (recommendation: `classes-sports-recreation`). Each lock takes ~1-2 min.
  2. **Operator polish of the district paragraphs draft** — 5 `[CASEY: ...]` placeholders (Mesquite Bay, Pittsburgh Point ×2, Castle Rock area, South side) + 5 "Casey to verify" items at the bottom of `outputs/chatgpt_response_district_paragraphs_v1.md`. ~15-20 min.
- **Production deploy of `c9ab794`-or-later** — Phase 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 + 2B.3 + 2B.1 are NOT yet deployed. Operator-cadence call. Phase 2 is feature-complete on origin and the chat-route response shape + anonymous-viewer experience is pinned unchanged across the entire stack; safe whenever. When deploy ships, alembic advances production through `b2c3d4e5f6a7 → f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3 → f9e8d7c6b5a4` (four migrations). The 2B.2 Postgres-only FTS DDL + the 2B.1 photos migration cycle both await first-deploy smoke on Railway Postgres — operator should run `EXPLAIN` on a Tier 2 query to confirm GIN index usage + run `downgrade -1` / `upgrade head` cycle on staging Postgres before counting the deploy as proven.
- **Phase 3 district paragraphs polish** — same as last session-18's mention: 5 `[CASEY: ...]` placeholders + 5 verify items at `outputs/chatgpt_response_district_paragraphs_v1.md`. ~15-20 min operator polish. **Now blocking Phase 3.2 dispatch** (not "no rush" any more).

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Deploy `c9ab794`-or-later to production | Anytime | Carries Phase 1C + 1D + 2A.1/.2/.3 + 2B.2 + 2B.3 + 2B.1 + the chore/docs commits. Four alembic migrations apply on first deploy. Watch Railway logs for: (a) 2B.2 FTS DDL (`CREATE EXTENSION pg_trgm`, `ADD COLUMN search_vector tsvector GENERATED ALWAYS AS ... STORED`, four CREATE INDEX statements) — first deploy is the truth-teller; (b) 2B.1 photos table create + 5 indexes + 2 CHECK constraints + 2 FK ondelete cascades — should be portable but smoke on staging Postgres first. R2 env vars are live in Railway since session-19 R2 lockdown; no env-var changes needed for the deploy. |
| Dispatch Phase 3.1 | Anytime | Patched dispatch prompt at `outputs/cursor_dispatch_prompt_phase_3_1.md` ready to paste. No operator prereq. ~3-4 day Cursor estimate. |
| Lock 5 Bucket C category-backfill decisions | Pre-Phase-3.2 dispatch | Per brief §7. ~5-10 min total (each is 1-2 min). Recommended dispositions provided in brief; operator confirms or overrides. |
| Polish district paragraphs draft | Pre-Phase-3.2 dispatch | `outputs/chatgpt_response_district_paragraphs_v1.md` — 5 `[CASEY: ...]` placeholders + 5 verify items. ~15-20 min. Same item as session-17 §3 + session-18 §3 + session-19 §3; bumped from "no rush" to "blocking Phase 3.2 dispatch" this session. |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember (session-19 ships)

Phase 2B.3 (commit `8338505`):
- **Brief symbol-name adaptation** — brief assumed `build_fts_query` symbol on `app/search/fts.py` but 2B.2 actually shipped `build_tsquery_string` / `entities_search_vector_match` / `build_entity_select_for_filters`. Cursor's §0 re-grep caught + adapted. (Exactly the brief-staleness recognition the §0 read protocol exists for.)
- **UI placement** — search section between topbar and hero on home.html (above the chat-style composer in the hero — brief §10 explicit menu option).
- **JS path `/static/js/search.js`** matches existing `js/chat-new.js` convention, not the brief's `app/static/search.js` at repo root.
- **Pagination cursor shape** — opaque base64 JSON `{"o":<offset>}` offset (brief §10 explicitly allows).
- **Additive `profile_url` row field** beyond brief §7.1's row spec so events route to `/events/{id}` and programs to `/programs/{id}` (events/programs not slug-routable; places fall back to `/home` placeholder).
- **Scope expansion** — additive OR-branch `_provider_synonym_exists_predicate` reuses 2B.2's `_category_needle_set` for commercial recall on `q=barbershop` → `barber_shop`-tagged providers. **NOT a raw-LIKE FTS bypass** — parallel taxonomy matching via 2B.2 helpers, additive OR with the FTS branch.
- **Template smoke** = string containment on rendered HTML, not BS4 parse (brief §10 explicit).

Phase 2B.1 (commit `1c57c73`):
- **`Entity.photos` primaryjoin string + no `foreign()`** — circular-import dodge for class-body-time evaluation. Same pattern as Phase 2B.2's `sqlite_fallback.py` lazy-import discipline.
- **Upload rate-limit order: `entity_cap` BEFORE `daily_cap`** — better UX (full-entity returns clearer error than masked-by-daily-cap).
- **`set_hero` response typing `dict[str, Any]`** — pragmatic FastAPI shape for `is_hero: bool` return field flexibility.
- **Orchestrator broad try/except → `flagged/decode_failed`** — brief §10 explicitly invited the defensive shape.
- **R2 failure path** — row stays `uploading` on exception; sweep handles long stalls (risk #7 mitigation).

Session-19 process deviations:
- **Bundled chore+docs commit at `3d89e58`** — PowerShell double-quote-in-`-m`-body parsing failure caused the docs commit attempt to fail, staged docs files got picked up by the next chore commit. Subject mislabel; Rule 12 says don't amend. Captured as candidate gotcha #16 for `dispatch_channels.md`.

---

## §5 — New lessons absorbed in session-19

1. **Gotcha #15 (bash mount `git` index.lock) discipline scales.** Zero working-tree bash git operations across the entire session; HEAD verification via Read on `.git/refs/heads/main`, recent commits via STATE.md cross-reference, alembic head via Glob on `alembic/versions/`, file-presence via Glob/Grep. One slip (`git ls-tree` for commit-content verification) left a `.git/index.lock` on the Linux mount but didn't propagate to Casey's Windows-side filesystem (`Remove-Item .git\index.lock` returned `path not found`); harm was theoretical only. Future agents: even read-only `git ls-tree` should be replaced with `python3 + zlib.decompress` tree-walk if you need commit-content verification from the sandbox.

2. **Gotcha #16 candidate — embedded `"..."` inside `-m '...'` PowerShell.** Even inside `-m 'plain single-quoted body'`, PowerShell's native-command argument re-tokenizer treats embedded `"..."` as token boundaries and breaks the argument. Symptom: `error: pathspec '<rest-of-body>' did not match any file(s) known to git`. Fix: avoid embedded double-quotes entirely in `-m '...'` bodies; use plain text (no quotes needed for emphasis) or Unicode curly quotes (`"..."`). Session-19 first surfaced this at the docs commit attempt; the bundled-commit-as-consequence was the impact. **Should land in `dispatch_channels.md` next session as gotcha #16.**

3. **Per-step operator walkthrough scales for one-shot consequences.** Bulk-mode dump of all 6 R2 setup steps was acceptable as a first pass, but Casey opted into per-step mode for actual execution. Step 4 (Cloudflare API token creation) in particular benefits from step-by-step warning ("the secret is shown ONCE; have a temp note ready") since irrecoverable. The Cloudflare onboarding-funnel UX detour (first attempt landed on account-level API token UI with 200+ permissions instead of the streamlined R2-specific token UI; cure: direct URL `<account-id>/r2/api-tokens`) is worth a one-liner in `outputs/operator_prereqs_phase_2.md` §2 step 4 if that doc ever gets a refresh.

4. **Three-track parallelism validated.** Session-18 first validated Rule 3 file-disjoint parallel dispatch at production scale (2A.3 + 2B.2 Cursor lanes). Session-19 confirmed the pattern works for THREE-track scenarios: 2B.3 lane in Cursor + R2 walkthrough operator-side + 2B.1 lane in Cursor (started while 2B.3 was still running but after R2 lockdown produced the env-var setdefault values). Both Cursor lanes saw each other's commits land on disk during their work (2B.3 committed mid-2B.1; 2B.1 saw the search_router include + `/api/search` route during its `app/main.py` anchored Edit + correctly slotted `photos_router` next to it). Working tree converges; commits stay file-disjoint per Rule 8 via per-file `git add` staging.

5. **Primary-side brief authoring during Cursor in-flight time scales for strategic docs.** Session-18 sub-agented dispatch-prompt authoring (docs-only, structured), but the Phase 3 brief is heavy strategic synthesis work (~580 lines + locked decisions + risk register + scope discipline + operator-decision-locks) — primary-side authoring is more efficient when the primary already has fresh context from reading the audit memo + master plan §4 Phase 3 + district draft moments earlier. Sub-agent pattern still right for narrow tightly-scoped prompts; primary-side right for synthesis-heavy work. **Bake into rhythm: primary-author when you have context cached + parallel Cursor lane is active; sub-agent when scope is small + structured.**

6. **Dispatch prompt SHA-patch pattern continues durable.** Patched 2B.3 prompt in-place via Edit before paste (file's durable, future reads see real SHAs not `<TBD-...>`); same for 2B.1 prompt at R2-lock time; same for Phase 3.1 prompt at 2B.1 ship in this session's `c9ab794`. Patched copy presented inline in chat for paste so Casey doesn't have to navigate to the file in his editor. Pattern is now standard primary-side rhythm for any pre-positioned dispatch prompt with TBD placeholders.

---

## §6 — Pointers for the next agent

Boot order:
1. `outputs/session_20_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-12 at session-19 close — start with the Production block + `c9ab794` HEAD + Phase 2 COMPLETE annotation)
3. `docs/maintainability/master_build_plan.md` §4 Phase 2 ("Shipped (incremental)" list has full Lane 2A + 2B SHIPPED + Phase 2 SHIPPED header) and §4 Phase 3 (the next dispatchable major phase — scope outline at line ~158-188 plus audit-memo + synthesis cross-references)
4. `outputs/cursor_dispatch_prompt_phase_3_1.md` (Phase 3.1 dispatch prompt — patched + ready to paste; chains off `f9e8d7c6b5a4` photos head; baseline `1663` pytest)
5. `outputs/cursor_brief_phase_3_v11_schema_pass.md` §4 + §6 + §7 + §10 + §11 — the heavy-prescriptive operating doc (Phase 3.1 deliverables in §4, locked decisions in §6, the 5 Bucket C operator-decision-locks for Phase 3.2 in §7, risk register in §10, don't-do in §11)
6. `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules) + `docs/maintainability/dispatch_channels.md` (15 gotchas as of session-18; gotcha #16 candidate from session-19 — embedded `"..."` in `-m '...'` PowerShell — should land next session)
7. `outputs/chatgpt_response_district_paragraphs_v1.md` (10 district paragraphs draft; 5 `[CASEY: ...]` placeholders + 5 verify items — **operator polish blocking Phase 3.2 dispatch**)

Session-19 absorbed six new lessons (above) worth carrying into future dispatches. The narrative in `docs/STATE.md` "Recently shipped" §1 captures every session-19 commit + decision + deviation with enough detail that the next agent shouldn't need to re-read this handoff except for §3 + §4 above.

---

*Authored at session-19 close, 2026-05-12. Next agent picks up at Phase 3.1 dispatch posture — operator prereqs (Resend ✅; R2 ✅) usefully scope what can dispatch when. Once Phase 3.1 ships, Phase 3.2 dispatches after operator locks the 5 Bucket C decisions + polishes the district paragraphs draft; once 3.2 ships, Phase 3 of the master build plan is COMPLETE and Phase 4 (background-jobs + layered scrape infrastructure) becomes the next dispatchable major phase.*
