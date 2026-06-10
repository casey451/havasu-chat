# Session-20 Handoff — 2026-05-12

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_21_boot_prompt.md`. Most state is durable on origin; this doc captures the deltas since the session-19 close (`26e6eb4`) + what's queued.

---

## §1 — What session-20 accomplished

**Phase 3.1 of the master build plan SHIPPED on origin** — the first sub-phase of Phase 3 (additive v1.1 schema additions only; Phase 3.2 data backfill + close-out pending). Six commits this session (including this close-out). Origin/main HEAD = `37c1bd9`. Session-20 substantive chain: `3bf9f66 → 540efbd → 7925a14 → 38abbcb → 81a83a1 → <this close-out>`.

| Commit | Summary |
|---|---|
| `3bf9f66` | **dispatch_channels gotcha #16 — embedded `"..."` inside `-m '...'` bodies on PowerShell.** Session-19 surface: a docs commit failed when the `-m` body contained embedded double-quote pairs; PowerShell's native-command argument re-tokenizer split the argument at the embedded quote pair even inside an outer single-quoted body, and git read the rest as pathspecs. Cure: avoid embedded `"..."` entirely in `-m '...'` bodies on PowerShell; use plain text, Unicode curly quotes, backtick-escape, or `-F -` stdin-piped for long messages. Same lesson scope as gotchas #3 + #8 + #13 (PowerShell quoting surprises). Also extends gotcha #15: session-19 confirmed even read-only `git ls-tree` should be replaced with the parent-walk pattern; rule from session-20 forward is zero `git ...` from bash sandbox against the working tree. |
| `540efbd` | **Phase 3.2 district UX operator reality check.** `outputs/cursor_brief_phase_3_v11_schema_pass.md` §7 + `outputs/chatgpt_response_district_paragraphs_v1.md` top updated to capture: Lake Havasu (~57k pop, ~46 sq mi) is too small for a 10-district paragraph-landing-page UX. McCulloch is the main commercial strip (street-based search would match user mental models better than district filters); English Village is the only district with bounded character; the other 8 in the draft are directional, landmark-based, or geographic, not user-mental-model districts. Phase 3.1 schema (districts table + `entities.district_id` FK) is forward-compatible and ships unaffected. Phase 3.2 district UX direction OPEN with three candidate paths: (a) pare to 2-3 real districts + Greater Lake Havasu default, drop the 10-paragraph plan; (b) ship 3.2 with `district_id` backfill but defer paragraph landing pages to V1.5, use district as backend tag; (c) re-think the primitive entirely (districts demoted to backend tag, surface streets and landmarks). Decision deferred to Phase 3.2 dispatch authoring time. District paragraphs draft now flags itself as illustrative not canonical. |
| `7925a14` | **Phase 3.1 — v1.1 schema additions (5 new tables + 7 entity columns + `users.preferred_mode` + ORM + 17 tests).** 3 files (+1064/-2). Cursor session, single dispatch. New alembic migration `d0e1f2a3b4c5_phase3_schema_pass` chains off `f9e8d7c6b5a4` (Phase 2B.1 photos). Creates 5 new tables: `districts` (id, slug UNIQUE, name, paragraph, display_order, timestamps, index); `alert_subscriptions` (user_id FK, alert_type, delivery_channel, UNIQUE on triple, CHECK constraints); `alerts_dispatched` (audit log, denormalized alert_type per brief, delivery_status CHECK); `external_conditions_cache` (source string PK, upsert pattern, fetched_at index); `peer_recommendations` (recommender_user_id FK, entity_id FK UNIQUE per recommender, recommendation_text column-named `text`, status CHECK, entity_id_status composite index — ships disabled-by-flag for V1.5 pilot). Extends `entities` via `batch_alter_table` with 7 nullable-or-defaulted columns: `heat_exposure` VARCHAR(20) CHECK; `crowd_notes` JSON; `is_mobile_service` BOOL NOT NULL default false; `boat_access` JSON; `seasonal_hours` JSON (coexists with Phase 1A `seasonal_hours` extension table via brief §9 intentional-column path; ORM relationship renamed `seasonal_hours → seasonal_hour_rows`); `district_id` VARCHAR(36) FK `districts.id` ON DELETE SET NULL, indexed; `featured` BOOL NOT NULL default false, indexed (non-partial). Extends `users` with `preferred_mode` VARCHAR(16) NOT NULL default `'default'` CHECK. ORM: 5 new model classes + Entity/User extensions. 17 net-new tests covering migration upgrade-downgrade-upgrade cycle, table shapes, 5 CHECK constraint violations, UNIQUE duplicates, FK CASCADE via raw DELETE + PRAGMA foreign_keys=ON, defaults, ORM relationships, index presence. Pytest **1664 → 1681 collected** (+17; 1680 passed + 1 skipped + 30 subtests). Alembic head `f9e8d7c6b5a4 → d0e1f2a3b4c5`. Ruff clean. Five accepted deviations per brief §9 (most notable: seasonal_hours JSON column + extension table coexist — brief §4.1 explicit-HALT bypassed; operator-confirmed during commit as the right call since §4.1 listed the column as additive). |
| `38abbcb` | **chore: patch Phase 2B.1 + 2B.3 dispatch prompt TBD placeholders to session-19 ship SHAs.** 2 files (+15/-16). Session-19 SHA-patched these two prompts in-place at paste-time per the SHA-patch-and-inline-present rhythm (session-19 lesson #6), but the patched versions never got committed cleanly during session-19 close-out. They sat uncommitted in the working tree across all of session-20. Landed now as a small chore lane to preserve the historical state. Same shape as `c9ab794` (which patched the Phase 3.1 dispatch prompt). Diffs surgical: `<TBD-FILL-AFTER-2A.3-LANDS>` → `5fea2ce`, `<TBD-FILL-AFTER-2B.2-LANDS>` → `d631c77`, `<TBD-FTS-migration-rev>` → `c8d9e0f1a2b3`, `<TBD-pytest-count>` → `1607`. |
| `81a83a1` | **Phase 3.1 docs close-out.** master_build_plan.md §4 Phase 3 gets a "Shipped (incremental)" sub-section with the 3.1 ship line; STATE.md Production block refreshed (HEAD `7925a14`, alembic `d0e1f2a3b4c5`, pytest 1681, build phase + Phase 3.1 SHIPPED); STATE.md Recent commits prepended with 4 session-20 commits; STATE.md Recently shipped §1 prepended with the full session-20 entry. |
| `37c1bd9` | This close-out commit — session-20 handoff doc + session-21 boot prompt + STATE.md Recent commits final prepend with `81a83a1`. SHA-patched into the boot prompt + this handoff doc + STATE.md Recent commits via a follow-up chore commit (see below) mirroring the `c9ab794` + `38abbcb` SHA-patch pattern. Mirrors session-19 `26e6eb4` precedent. |

**Phase 3.1 scorecard:** **SHIPPED on origin** at `7925a14`. Schema additive only — new columns and tables start empty, ORM dormant until Phase 3.2 wires writers + Phase 5/6/8 wire readers. Single alembic migration `d0e1f2a3b4c5` chained off `f9e8d7c6b5a4`. Pytest delta: 1664 → 1681 (+17 net-new). Production Postgres still at `b2c3d4e5f6a7` — next deploy walks 5 migrations (`f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3 → f9e8d7c6b5a4 → d0e1f2a3b4c5`).

---

## §2 — What's in flight or queued

- **Phase 3.2 — pending dispatch.** Dispatch prompt to be authored in session-21 or later (chains off `d0e1f2a3b4c5`). 3.2 scope per brief §5: category taxonomy rewrite (rename 7 surviving slugs + delete `family`/`community` + insert `classes-sports-recreation`/`public-civic-resources`) + audited Provider/Program category backfill (Buckets A/B/C/E per audit memo §2) + `entities.district_id` backfill from String column + `entities.featured` backfill from Provider + `users.preferred_mode` NOT NULL flip (no-op since 3.1 already direct-NOT-NULL) + `CATEGORY_LABELS` update at `app/home/queries.py:27-55` + validator vocab update at `scripts/ingest/validate_enrichment_csv.py` + Phase 3 close-out (Phase 3 SHIPPED header). **Phase 3.2 dispatch is gated on:**
  1. **5 Bucket C category-backfill decisions LOCKED during session-20** (must be embedded into the 3.2 dispatch prompt at authoring time): `beauty_personal_care` → NULL queue / V1.5 defer; `tourism` → NULL queue for operator triage; `barbershop` test fixture → NULL; K-12 / charter / public schools → `classes-sports-recreation`; bowling / arcades / mini golf → `classes-sports-recreation`. All locked at recommendation. Captured in `outputs/cursor_brief_phase_3_v11_schema_pass.md` §7 (decisions inline) + STATE.md Recently shipped §1 session-20 entry.
  2. **District paragraph UX direction OPEN** per session-20 operator reality check. Three candidate paths in brief §7: (a) pare to 2-3 real districts + "Greater Lake Havasu" default, drop the 10-paragraph plan; (b) defer paragraph landing pages to V1.5, use `district_id` as backend tag; (c) re-think the primitive to streets/landmarks (highest cost; reopens 3.1 scope — not recommended). Decision deferred to Phase 3.2 dispatch authoring time. District paragraphs draft at `outputs/chatgpt_response_district_paragraphs_v1.md` now flags itself as illustrative not canonical and instructs operator/future Cursor not to polish until UX direction resolves. **NEW since session-19:** Casey raised this reality check during session-20 mid-flight on Cursor 3.1; same item that was bumped from "no rush" to "blocking Phase 3.2 dispatch" in session-18/19 handoffs is now flagged as a strategic-direction question rather than a polish-the-paragraphs question.
- **Production deploy of `81a83a1`-or-later** — Phase 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 + 2B.3 + 2B.1 + 3.1 are NOT yet deployed. Operator-cadence call. Phase 2 was feature-complete on origin since session-19; Phase 3.1 adds dormant schema only (no readers/writers wired). Chat-route response shape + anonymous-viewer experience pinned unchanged across the entire stack; safe whenever. When deploy ships, alembic advances production through `b2c3d4e5f6a7 → f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3 → f9e8d7c6b5a4 → d0e1f2a3b4c5` (five migrations). The 2B.2 Postgres-only FTS DDL + the 2B.1 photos migration cycle + 3.1 schema additions cycle all await first-deploy smoke on Railway Postgres — operator should run `EXPLAIN` on a Tier 2 query to confirm GIN index usage + run `downgrade -1` / `upgrade head` cycle on staging Postgres before counting the deploy as proven.

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Deploy `81a83a1`-or-later to production | Anytime | Carries Phase 1C/1D + Phase 2A/B + Phase 3.1 + 4 session-20 commits + this close-out. Five alembic migrations apply on first deploy. R2 env vars are live in Railway since session-19 R2 lockdown; no env-var changes needed. Watch Railway logs for: (a) 2B.2 FTS DDL — first deploy is the truth-teller; (b) 2B.1 photos table create + 5 indexes + 2 CHECK constraints + 2 FK ondelete cascades; (c) 3.1 schema additions cycle — should be portable but smoke on staging Postgres first. |
| Author Phase 3.2 dispatch prompt | Session-21 or later | Chains off `d0e1f2a3b4c5`. Embed the 5 Bucket C locks (this session) + resolve district paragraph UX direction before authoring. |
| Resolve district paragraph UX direction | Pre-Phase-3.2 dispatch | Three candidate paths in brief §7. Decision deferred to 3.2 dispatch authoring. Recommend (a) pare to 2-3 real districts OR (b) defer paragraphs to V1.5 — NOT (c) re-think primitive (reopens 3.1 scope). |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember (session-20 ships)

Phase 3.1 (commit `7925a14`):
- **seasonal_hours JSON column + Phase 1A extension table coexist** — brief §4.1 explicit-HALT bypassed by Cursor; operator confirmed during commit as the right call (§4.1 listed the column as additive which IS operator intent). ORM relationship renamed `seasonal_hours → seasonal_hour_rows` so the JSON column keeps the `seasonal_hours` name. Document for future Cursor inheritance.
- **`users.preferred_mode` direct NOT NULL with server_default** — brief §4.7 allowed either NOT NULL+default or nullable+backfill; Cursor picked direct, 3.2 backfill step is a no-op.
- **`PeerRecommendation.recommendation_text` Python attribute maps to DB column `text`** — minor naming choice; documented.
- **`alerts_dispatched.alert_type` left denormalized per brief** — durability for audit purposes.
- **`entities.featured` non-partial index on both dialects** — Postgres-only partial index skipped per brief §9 invitation; simple index acceptable for V1.

Session-20 process deviations:
- **Cursor §11 prose may be descriptive not change-revealing.** Cursor's §13 §11 mentioned `alembic/env.py` modification but the §4 file list only showed `app/db/models.py` modified. `git status` Windows-side confirmed env.py was NOT modified; §11 was descriptive of existing state (env.py already uses `get_database_url()` at runtime in 3 sites since some prior session). Rule from session-20 forward: always cross-check Cursor's claimed file list against actual `git status` Windows-side before staging; never trust §11 prose alone to determine commit scope.

---

## §5 — New lessons absorbed in session-20

1. **Gotcha #16 landed durably** — embedded `"..."` inside `-m '...'` bodies on PowerShell. Session-20 wrote its own gotcha #16 commit using gotcha #16's own medicine (`-m` body with em-dashes and plain text, no embedded double-quote pairs) and it parsed clean. All session-20 commit bodies used the same pattern; all landed clean. Future sessions inherit the rule.

2. **Operator reality-check feedback loop matters.** Casey pushed back on the 10-district paragraph plan with grounded local knowledge (Havasu too small, McCulloch is the strip, English Village is the only real district). Reality check captured durably in brief §7 + district draft top so Phase 3.2 dispatch authoring re-engages the question rather than executing the original plan. Strategic-direction updates from operator local knowledge always beat polished-from-research drafts; bake "ask the operator what's actually true about their geography/users" into early-phase brief authoring.

3. **Cursor §11 prose may be descriptive not change-revealing.** See §4 above. Always cross-check Cursor's claimed file list against actual `git status` Windows-side before staging.

4. **Dispatch prompt SHA-patch pattern continues durable.** Session-20's chore commit at `38abbcb` mirrored the `c9ab794` pattern, preserving session-19's in-place SHA fills as durable historical state. Future agents: when a dispatch prompt gets SHA-patched in-place pre-paste, land it as a chore commit at session close-out — don't let patched prompts sit in working tree across session boundaries.

5. **Primary-side parallel-work cadence during Cursor in-flight time scales.** Session-20 walked 5 Bucket C operator decisions + surfaced the Phase 3.2 district UX reality check + authored gotcha #16 docs + queued the session-19-dispatch-prompt chore all during Cursor 3.1's ~hour of in-flight time. The operator-decision walkthrough was efficient via structured AskUserQuestion calls with recommendations attached. Pattern is production-ready for any session where Cursor has substantial in-flight time.

6. **Gotcha #15 discipline held throughout (session-20 continuation).** Zero bash `git` operations against the working tree across the entire session; HEAD verification via Read on `.git/refs/heads/main`, recent commits via STATE.md cross-reference, alembic head via Glob on `alembic/versions/`, file-presence via Glob/Grep. Session-19's rule extension (no read-only `git ls-tree` either) held.

---

## §6 — Pointers for the next agent

Boot order:
1. `outputs/session_21_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-12 at session-20 close — start with the Production block + `7925a14` HEAD reference + Phase 3.1 SHIPPED annotation)
3. `docs/maintainability/master_build_plan.md` §4 Phase 3 ("Shipped (incremental)" list has the Phase 3.1 ship line; §3.2 description outlines the next dispatchable sub-phase)
4. `outputs/cursor_brief_phase_3_v11_schema_pass.md` §5 + §7 + §10 + §11 — the heavy-prescriptive operating doc (Phase 3.2 deliverables in §5, the 5 Bucket C operator decisions now locked + district UX reality check in §7, risk register in §10, don't-do in §11)
5. `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules) + `docs/maintainability/dispatch_channels.md` (16 gotchas as of session-20; gotcha #16 — embedded double-quotes inside `-m '...'` bodies on PowerShell — landed this session at `3bf9f66`)
6. `outputs/chatgpt_response_district_paragraphs_v1.md` (10 district paragraphs draft; **now flagged as illustrative not canonical** pending Phase 3.2 district UX direction resolution — do NOT polish the placeholders until UX direction resolves)

Session-20 absorbed six new lessons (above) worth carrying into future dispatches. The narrative in `docs/STATE.md` "Recently shipped" §1 captures every session-20 commit + decision + deviation with enough detail that the next agent shouldn't need to re-read this handoff except for §3 + §4 above.

---

*Authored at session-20 close, 2026-05-12. Next agent picks up at Phase 3.2 dispatch authoring posture — 5 Bucket C decisions are LOCKED (embed into 3.2 dispatch prompt), district paragraph UX direction is OPEN (resolve before authoring 3.2 prompt), Phase 3.1 schema is shipped and dormant. Once Phase 3.2 ships, Phase 3 of the master build plan is COMPLETE and Phase 4 (background-jobs + layered scrape infrastructure) becomes the next dispatchable major phase.*
