# Session-21 Handoff — 2026-05-12

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_22_boot_prompt.md`. Most state is durable on origin; this doc captures the deltas since the session-20 close (`c4fdc69`) + what's queued.

---

## §1 — What session-21 accomplished

**Phase 3.2 of the master build plan SHIPPED on origin — Phase 3 of the master build plan is COMPLETE on origin (3.1 + 3.2).** Five-plus commits this session (including this close-out). Origin/main HEAD = `43b5f8f`. Session-21 substantive chain: `5dbde39 → bd9b00f → 294567b → 43b5f8f → 59521dd → <SHA-patch chore>`.

| Commit | Summary |
|---|---|
| `5dbde39` | **Phase 3.2 — category taxonomy rewrite + audited Provider/Program backfill + district seed as backend tag + entity backfills (11 files, +1237/-67).** Single Cursor dispatch on the pre-positioned + locked prompt at `outputs/cursor_dispatch_prompt_phase_3_2.md`. New alembic migration `e1f2a3b4c5d6_phase3_data_pass` chains off `d0e1f2a3b4c5`. Renames 7 surviving slugs (eat-and-drink → eat-drink etc.); backs up family + community UUIDs to ad-hoc `_phase32_category_bak` table for downgrade-restoration; NULLs providers/programs FK references + DELETEs `entity_categories` junction rows (junction `category_id` is NOT NULL — brief §9 either-or collapsed to DELETE-only); deletes family + community; inserts classes-sports-recreation + public-civic-resources; resets sort_order 1-12 per synthesis §1. Four-pass Provider/Program backfill per audit memo §2 (Pass 1 Bucket A + Bucket E renames; Pass 2 Bucket B improved homes + entertainment_attractions NULL queue per Phase 5 defer; Pass 3 Bucket B professional-services NULL queue; Pass 4 Bucket C three explicit NULL UPDATEs only — beauty_personal_care, tourism, barbershop). Deterministic 10-district `op.bulk_insert` with `paragraph=NULL` per **path (b) operator lock**. `entities.district_id` backfill from `locations.district` name match (the `entities.district` String column never existed — Phase 1A semantics caught at dispatch time; brief §5.4's drop-column instruction was moot). `entities.featured` backfill from `Provider.featured`. `users.preferred_mode` SQL no-op (3.1 direct-NOT-NULL). Anchored Edits on `app/home/queries.py` (CATEGORY_LABELS replaced; NEW `LEGACY_PROVIDER_CATEGORY_LABELS` preserves free-text Provider.category display until Phase 13), `app/providers/queries.py`, `app/db/models.py` (District.paragraph nullable), `scripts/ingest/validate_enrichment_csv.py`. 5 test files updated for slug ripples + new `tests/test_phase3_data_pass.py` with 22 tests. Pytest **1681 → 1702** (+21). Alembic head **`d0e1f2a3b4c5 → e1f2a3b4c5d6`**. Ruff clean. **Five accepted deviations per brief §9:** (1) entities.district nonexistent → locations.district source; (2) entity_categories junction DELETE not NULL; (3) Bucket C A.4 + A.5 documented-only locks per session-21 mid-session clarification (A.4 subsumed by Bucket B Pass 2 education mapping; A.5 subsumed by entertainment_attractions NULL deferral with Phase 5 google_primary_category triage rule); (4) NEW LEGACY_PROVIDER_CATEGORY_LABELS constant (interim plumbing); (5) test helpers mirror migration ORM semantics. |
| `bd9b00f` | **chore: Phase 3.2 dispatch prompt artifact (post-ship).** Lands `outputs/cursor_dispatch_prompt_phase_3_2.md` (~500 lines) as historical artifact. On-disk prompt preserves pre-clarification framing for items A.4 + A.5; post-clarification reframe lives in `5dbde39` migration + tests + commit body. Mirrors session-19 `3d89e58` + session-20 `38abbcb` dispatch-prompt-as-chore precedent. |
| `294567b` | **Phase 3.2 docs close-out + Phase 3 SHIPPED master plan header.** master plan §4 Phase 3 gets SHIPPED 2026-05-12 annotation + Status line + Phase 3.2 ship-line appended below the 3.1 ship-line under Shipped (incremental). STATE.md Production block refreshed across 5 paragraphs (HEAD `5dbde39`, alembic `e1f2a3b4c5d6`, pytest 1702, build phase notes Phase 3 COMPLETE, 6-migration deploy chain, Phase 4 next dispatchable). STATE.md Recent commits prepended with this commit (TBD) + bd9b00f + 5dbde39 + c4fdc69 (session-20 SHA-patch chore brought into the block since `37c1bd9` close-out's Recent-commits update predated it). STATE.md Recently shipped §1 prepended with comprehensive session-21 entry covering the 3.2 ship + mid-session Bucket C clarification + 6 session-21 lessons. District paragraphs draft top-matter status flipped from "illustrative not canonical pending UX direction" to "V1 deferred to V1.5; preserved for V1.5 re-engagement". |
| `43b5f8f` | Session-21 close-out commit — session-21 handoff doc + session-22 boot prompt + STATE.md Recent commits final prepend with `294567b` (patching the docs close-out TBD placeholder) + a new TBD placeholder for this close-out (resolved post-cron-pause via the follow-up SHA-patch chore — see row below). Mirrors session-19 `26e6eb4` + session-20 `37c1bd9` close-out precedent. |
| `59521dd` | **chore(ci): pause parks-rec-scrapes cron until production deploy lands.** Comments out the `schedule:` block in `.github/workflows/parks-rec-scrapes.yml` with PAUSED commentary citing the re-enable trigger (6-migration production deploy) + diagnosis pointer (sec 2 of this handoff). Keeps `workflow_dispatch` so operator can run the workflow manually post-deploy. Stops the 6h scraper failures until deploy. |
| `<SHA-patch chore>` | **chore: SHA-patch follow-up — patch `43b5f8f` + `59521dd` into the session-22 boot prompt + this handoff doc + STATE.md Recent commits.** Mirrors session-20 `c4fdc69` SHA-patch precedent but landed at session-21 close (NOT session-22 boot) — explicit choice to close out session-21 with zero pending placeholders. Both close-out SHA + cron-pause SHA known at patch time (cron-pause landed first, then this chore). |

**Phase 3.2 scorecard:** **SHIPPED on origin** at `5dbde39`. Phase 3 of the master build plan COMPLETE on origin. Single alembic migration `e1f2a3b4c5d6` chained off `d0e1f2a3b4c5`. Pytest delta: 1681 → 1702 (+21 net-new). Production Postgres still at `b2c3d4e5f6a7` — next deploy walks **6 migrations** (`f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3 → f9e8d7c6b5a4 → d0e1f2a3b4c5 → e1f2a3b4c5d6`).

---

## §2 — What's in flight or queued

- **Phase 4 — pending brief authoring + dispatch.** Phase 4 brief does NOT exist yet; that's the gating artifact for Phase 4 dispatch. Per master plan §4 Phase 4: background-jobs + layered scrape infrastructure (Option A from `docs/maintainability/background_job_infrastructure_decision.md` — Railway scheduled jobs + FastAPI BackgroundTasks + optional Outbox + layered scrape strategy from `docs/maintainability/layered_scrape_strategy.md`). Estimated L (10-15 days dispatch); parallel-eligible sub-lanes (OSM client + LHC open data clients separable). Next session pick lane: (a) author Phase 4 brief, (b) production deploy of Phase 1C/1D + 2A/2B + 3, (c) hold.

- **Production deploy of `294567b`-or-later** — Phase 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 + 2B.3 + 2B.1 + 3.1 + 3.2 are NOT yet deployed. Operator-cadence call. Six alembic migrations apply on first deploy (`f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3 → f9e8d7c6b5a4 → d0e1f2a3b4c5 → e1f2a3b4c5d6`). Chat-route response shape + anonymous-viewer experience pinned unchanged across the entire stack; safe whenever. Operator should run `EXPLAIN` on a Tier 2 query (GIN usage on entities.search_vector) + `downgrade -1` / `upgrade head` cycle on staging Postgres for the 2B.2 FTS + 2B.1 photos + 3.1 schema + 3.2 data pass migrations before counting the deploy as proven. R2 env vars are live in Railway since session-19; Resend env vars since session-17.

- **parks-rec-scrapes workflow failing every 6h since Phase 3.1 ship (session-20 2026-05-12).** Surfaced at run #24 via screenshot Casey shared in session-21. **Root cause (high-confidence diagnosis, no log inspection yet):** the scheduled scraper runs against production Postgres but uses ORM code from origin/main. Production is at alembic head `b2c3d4e5f6a7` (Phase 1B); origin is at `e1f2a3b4c5d6` (Phase 3.2). ORM `Entity` class on origin references 7 columns added in Phase 3.1 (`heat_exposure`, `crowd_notes`, `is_mobile_service`, `boat_access`, `seasonal_hours`, `district_id`, `featured`) + 5 new tables + `users.preferred_mode`. Any INSERT/SELECT against entities that touches those columns crashes against production Postgres with "column does not exist". Symptom: every cron run (every 6h, 15 minutes past the hour) returns exit code 1. **Cron-pause chore commit follows this close-out** (one-line patch to `.github/workflows/parks-rec-scrapes.yml` commenting out the cron trigger, keeping `workflow_dispatch` so operator can run manually post-deploy). Re-enable cron after production deploy lands.

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Deploy `294567b`-or-later to production | Anytime (recommended SOON — unblocks parks-rec-scrapes) | Carries Phase 1C/1D + Phase 2A/B + Phase 3.1 + 3.2 + session-21 docs commits. **Six alembic migrations** apply on first deploy. R2 + Resend env vars live since session-17/19; no env-var changes needed. Watch Railway logs for: (a) 2B.2 FTS DDL (CREATE EXTENSION pg_trgm; verify pg_trgm available pre-push); (b) 2B.1 photos table + 5 indexes + 2 CHECK constraints + 2 FK ondelete cascades; (c) 3.1 schema additions cycle (5 new tables + 7 entity columns + users.preferred_mode); (d) 3.2 data pass (4-pass backfill against any existing Provider/Program rows in prod). Post-deploy: re-enable parks-rec-scrapes cron + manually run workflow once to confirm scraper recovers. |
| Author Phase 4 brief | Session-22 or later | Phase 4 brief authoring is the gating artifact for Phase 4 dispatch. Read `docs/maintainability/background_job_infrastructure_decision.md` + `docs/maintainability/layered_scrape_strategy.md` end-to-end first. |
| Resolve `docs/BACKLOG.md` unstaged modification | Session-22 or later | Stray modification in working tree from before session-21; left uncommitted to keep close-out scope clean. Either commit as its own lane or revert if stray. |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember (session-21 ships)

Phase 3.2 (commit `5dbde39`):
- **`entities.district` String column never existed.** Cursor caught at dispatch time. Phase 1A unified district into `locations` extension table; brief §5.4's drop-column instruction assumed entities.district existed. Source for `district_id` backfill is `locations.district` (same string Phase 1B's entity backfill copies from Provider.district into locations). ORM relationship stays `district → District` (no rename, no drop_column). Future Cursor inheritance: when a brief instruction touches a column, always verify the column exists in models.py before authoring SQL. Same lesson scope as Phase 3.1's seasonal_hours JSON column vs extension table coexistence (session-20 brief §4.1 narration).
- **`entity_categories` junction DELETE not NULL.** Junction's `category_id` is NOT NULL, so the brief §9 NULL-or-DELETE either-or collapsed to DELETE-only. Schema-forced choice; documented in `5dbde39` commit body.
- **Bucket C items A.4 + A.5 documented-only locks per session-21 mid-session clarification.** A.4 (K-12/charter/public schools) doesn't have standalone legacy `Provider.category` strings in audit memo §2 — it's a sub-question of `education` (already locked in Bucket B Pass 2 → `classes-sports-recreation`). A.5 (bowling/arcades/mini golf) is a SUBSET of `entertainment_attractions` (NULL queue per Phase 5 defer). Sub-agent caught the gap pre-flight during Cursor in-flight time; mid-session clarification message reframed both items as documented-only locks; Cursor absorbed cleanly. Pass 4 final shape is three explicit NULL UPDATEs only (A.1 beauty_personal_care, A.2 tourism, A.3 barbershop).
- **NEW `LEGACY_PROVIDER_CATEGORY_LABELS` constant** in `app/home/queries.py` (+ used in `app/providers/queries.py`). Preserves free-text `Provider.category` display until Phase 13 — prevents blank labels for operator-queue rows (Bucket C NULLs + Bucket B prof-services NULLs) on profile/admin views. Arguably "beyond what audit memo + synthesis specify" per brief §11 but rationale sound: interim plumbing for the operator-queue period.
- **Test helpers mirror migration UPDATE/ORM semantics.** Standard testing pragmatism since the migration doesn't re-run per test.

Session-21 process deviations:
- **Cursor mid-session clarification absorbed cleanly.** Pattern works when (a) the clarification is small + targeted (one section of the prompt), (b) Cursor hasn't already locked the decision into code. Session-21 used it for items A.4 + A.5 reframe; Cursor reframed Pass 4 + Test #23/#24 in the same dispatch without HALT. Future sessions: if Cursor is mid-flight + a gap surfaces (especially from pre-flight sub-agent verification), send a focused clarification message; don't always wait for §13 HALT and re-dispatch.

---

## §5 — New lessons absorbed in session-21

1. **Sub-agent pre-flight verification catches dispatch-prompt gaps before Cursor halts.** The audit memo §2 cross-check sub-agent ran during Cursor in-flight time surfaced that A.4 + A.5 didn't have standalone legacy strings; the mid-session clarification message landed in <1 min of Cursor time and Cursor absorbed cleanly. **Pattern: use Explore sub-agent for pre-flight dispatch-prompt verification during long Cursor sessions when there's audit/memo cross-referencing to do.** The cost is one sub-agent context burn (~350 words report); the savings is one or more Cursor round-trips.

2. **Mid-session clarification messages work — but the message has to be small + targeted.** Paste-into-Cursor reframe of items A.4 + A.5 was absorbed in the same session without HALT. The clarification was ~25 lines, anchored on specific dispatch-prompt sections (LOCKED OPERATOR DECISIONS items A.4 + A.5; Test #23 + #24). Future sessions: if Cursor is mid-flight + a gap surfaces, send a focused clarification message; don't always wait for §13 HALT and re-dispatch.

3. **Dispatch prompt as-shipped historical artifact is the right framing.** Preserves pre-clarification context as a record; post-clarification reframe lives in commit message + STATE.md narrative + tests. Mirrors session-20 brief §4.1 narration precedent (didn't patch the brief; narrated in commit). Decision-rule for future agents: brief / dispatch-prompt content stays as-authored-pre-Cursor; mid-flight deviations get narrated in the post-ship commit + STATE.md.

4. **Phase 1A semantics still surfacing in Phase 3.** Cursor caught that `entities.district` String column never existed (Phase 1A unified district into `locations` extension); brief §5.4's drop-column instruction was authored assuming entities.district existed. Future Cursor inheritance: when a brief instruction touches a column, always verify the column exists in models.py before authoring SQL. Same lesson scope as Phase 3.1's seasonal_hours JSON column vs extension table coexistence (session-20 brief §4.1 narration).

5. **Gotcha #15 discipline held throughout** (continuation; three-session streak now session-19 + session-20 + session-21) — zero bash `git` operations against working tree all session; HEAD verification via Read on `.git/refs/heads/main` + parent-walk decompression via `python3 + zlib.decompress` on `.git/objects/` per gotcha #14 cure pattern; alembic head via Glob on `alembic/versions/`; file-presence via Glob/Grep.

6. **Gotcha #16 discipline held throughout** (continuation; two-session streak now session-20 + session-21) — all session-21 commit recipes used PowerShell-safe single-quoted `-m` bodies with em-dashes / `->` / plain text for emphasis; no embedded double-quote pairs; all commits landed clean. Hyphens (`-`) work fine as emphasis brackets when used in pairs as a quote-like-affordance.

---

## §6 — Pointers for the next agent

Boot order:
1. `outputs/session_22_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-12 at session-21 close — start with the Production block + `5dbde39` HEAD reference + Phase 3 COMPLETE annotation)
3. `docs/maintainability/master_build_plan.md` §4 Phase 3 (SHIPPED 2026-05-12 — Status line at top + "Shipped (incremental)" sub-section now has both 3.1 + 3.2 ship-lines) + §4 Phase 4 (next dispatchable; brief not yet authored)
4. `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules) + `docs/maintainability/dispatch_channels.md` (16 gotchas as of session-20)
5. `docs/maintainability/background_job_infrastructure_decision.md` + `docs/maintainability/layered_scrape_strategy.md` (Phase 4 design context for the brief authoring task)

Session-21 absorbed six new lessons (above) worth carrying into future dispatches. The narrative in `docs/STATE.md` "Recently shipped" §1 captures every session-21 commit + decision + deviation with enough detail that the next agent shouldn't need to re-read this handoff except for §3 above.

**Carry-over urgency for session-22:** the parks-rec-scrapes failure is cron-paused but production deploy is the durable fix. If Casey wants to deploy in session-22, that becomes lane (b); otherwise lane (a) is Phase 4 brief authoring. Both are reasonable; Casey decides.

---

*Authored at session-21 close, 2026-05-12. Next agent picks up at Phase 4 brief-authoring posture OR production deploy posture (operator-cadence call). Once Phase 4 ships, the next major phase becomes Phase 5 (Tier 1 data gathering).*
