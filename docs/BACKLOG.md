# Backlog

Open and recently-closed work items with attribution to commits. Updated at the end of each session that opens, closes, or ships against a backlog item.

Status conventions:

- **OPEN** — identified, not yet addressed
- **RESOLVED** / **CLOSED** — shipped; commit referenced
- **DEFERRED** — explicitly out of scope until a precondition is met
- Numbered backlog items predate the canonical-docs introduction; new items can use the same format or whatever shape suits

Ship log entries at the bottom record what shipped per session. New ones are appended; old ones are not edited.

---

# Multi-day events - Tier 2 backlog

**Context:** Multi-day schema/retrieval work and parser prompt updates are now shipped together and verified in production.

---

## Backlog 1 - `tier2_parser` date extraction gap (**RESOLVED**)

**Original issue:** Tier 2 parser often emitted `time_window` and left `date_exact` null for natural-language calendar queries, so date-specific retrieval could not reliably execute.

**Resolution shipped:**
- **`63a4535`** - parser prompt contract update in `prompts/tier2_parser.txt`:
  - documents `date_exact`, `date_start`/`date_end`, `month_name`, `season`
  - enforces one temporal-group rule with priority
  - adds few-shots for explicit date, range, month, season, and precedence cases
- **`d763775`** - multi-day schema/retrieval plus backfill support needed for end-to-end correctness once `date_exact`/range fields are extracted.

**Verification:** Local and production chat checks confirmed date-specific queries now route through correct temporal fields and return expected events for middle-day overlap cases.

---

## Backlog 2 - `_time_bucket_first_hits` and broad `span` (**OPEN**)

**Issue:** For broad windows (`span > 30`) with many matches, `_time_bucket_first_hits` can sample across the window and omit chronologically clustered events.

**Effect:** Returned top-eight list can hide relevant early-window events even when SQL overlap is correct.

**Scope:** Product/UX decision (sampling vs strict chronological priority) and potential query/selection adjustment.

**Reference:** `app/chat/tier2_db_query.py` (`_is_still_clustered_early`, `_time_bucket_first_hits`).

---

## Backlog 3 - year inference for undated calendar queries (**OPEN**)

**Issue:** `tier2_parser` does not pass current local date context into the model prompt. Queries like "events on May 8" (no year) rely on model guesswork.

**Desired fix:** Code change in `app/chat/tier2_parser.py` prompt assembly to inject current local date context (user/system note) so undated calendar phrases resolve deterministically to the intended year.

**Out of scope of shipped fix:** Prompt docs/few-shots alone; this needs parser code-path context injection.

---

## Backlog 4 - day relevance ranking for overlapping multi-day events (**RESOLVED**)

**Original issue:** For a queried day, events that *start on that day* should rank above events that merely overlap the day from earlier start dates.

**Resolution shipped:** **`1c262ad`** — SQL `ORDER BY` for `date_exact` queries in `app/chat/tier2_db_query.py` prioritizes `Event.date == date_exact` (starts-on-day) before overlap-only rows, then `Event.date`, then `start_time`. Verified in production (e.g. May 9, Session 2).

**Documentation closure:** Backlog 4 remained marked OPEN in this file until Session 2 follow-up (**`d279165`**), which records the close explicitly. No further code change required for this backlog item.

---

## Backlog 5 - clickable source URLs in chat output (**OPEN**)

**Issue:** Chat output does not consistently surface `event_url` links for events across sources and Tier 2 paths (deterministic all-event renderer vs LLM path, mixed rows, etc.).

**Effect:** Users may lack clickable links where catalog data has a URL but the active Tier 2 formatting path omits or mishandles link emission.

**River Scene scope (RESOLVED):** Wrong link targets, operator scaffolding in descriptions, and dedupe tied to the article URL without a separate stable identity were addressed by the **`source_url`** migration, ingestion/dedupe/render/backfill stack — see **`docs/maintainability/river_scene_event_output_decision.md`** (shipped **2026-04-30**, commits **`83e4995`..`6bec1ec`**).

**Desired fix:** Ensure formatter/renderer includes clickable event links wherever `event_url` is available in Tier 2 responses, including mixed and LLM-formatter paths beyond the deterministic all-event catalog renderer.

---

## Backlog 6 - formatter count/prose drift (**CLOSED**)

**Original issue:** Response prose could claim a different event count than the rendered list; Tier 2 formatter LLM omitted rows despite prompt guardrails (Session 2 verification failures on May 2 and May 8; flaky on May 9).

**Resolution shipped:** **`d279165`** — For Tier 2 rows that are **all** `type: event`, catalog text is rendered deterministically in Python via **`render_tier2_events`** in **`app/chat/tier2_catalog_render.py`**. Row count, order (matching SQL), verbatim titles, and optional `{n} events:` header are structurally guaranteed. `event_url` is emitted as markdown `[title](url)` when non-empty. Mixed or non-event rows continue to use the existing LLM formatter path and `prompts/tier2_formatter.txt`.

**Supersedes:** Session 2 prompt-only completeness/count/order rules at **`1c262ad`** are **architecturally insufficient** for the observed failure mode (LLM ignored mid-prompt rules); deterministic rendering replaces that approach for event listings.

**Historical notes:** Past-date retrieval context in `6934d1d`; Session 2 SQL ordering partial ship at `1c262ad`; Session 3 Layer 2 UI markdown link rendering at `cdc4ac7`. Session 3 **Layer 3** (formatter prompt to emit markdown links) is **closed without ship** — the renderer emits links for events; no separate Layer 3 prompt session is required for that intent.

---

## Backlog 7 - `event_quality.py` orphan symbols after legacy `/chat` removal (**OPEN**)

**Context:** After **H1** (`61387e4`..`23a39a5`), `app/core/event_quality.py` is imported from `app/main.py` (`friendly_errors` on `RequestValidationError`) and indirectly via the unified router stack. Many symbols existed primarily for the deleted legacy router path.

**Symbols to verify and likely trim (per-symbol usage audit):** `apply_user_reply_to_field`, `build_pending_review_create`, `first_invalid_field`, `has_any_contact`, `normalize_partial_event`, `try_build_event_create`, `CONTACT_OPTIONAL_PROMPT`, `REVIEW_OFFER_MESSAGE`, `SUBMITTED_REVIEW_MESSAGE`.

**Scope:** Small follow-up ship — delete dead exports / consolidate after grep confirms no references.

---

## Backlog 8 - `unified_router.py` `tier_used` comment (**RESOLVED**)

**Issue:** Near line ~96, the `tier_used` enumeration includes `'track_a'` (documented as DB-only; unified path never emits `track_a`). After H1, **no code path emits `track_a`** anywhere — it exists only on historical `chat_logs` rows.

**Desired fix:** Update the comment to state that `track_a` appears only in historical DB rows, not in current emitters.

Cross-reference: matches `docs/maintainability/findings_app_chat.md` finding L7 (same comment, same module, same fix).

**Resolution shipped:** Updated comment at `app/chat/unified_router.py:96` to: `'track_a' (historical chat_logs rows only; no current emitter)`, replacing the ambiguous "DB only" wording. Component doc `docs/components/unified_router.md` line 52 already captures precise track_a semantics (historical sentinel in `chat_logs.tier_used` only, no Python emitter remains, appears only as legacy analytics data); no component doc update required per WORKING_AGREEMENT §54-58. The L7 cross-reference (`findings_app_chat.md`) is about the broader Literal-vs-comment design question (disposition: "accept and document"); unaffected by this wording fix.

---

## Backlog 9 - Tier 1 hit rate (**OPEN**)

**Observation:** ~33/486 ≈ **7%** Tier 1 hits pre-H1 — lower than expected for templated provider lookups.

**Next step:** After the live catalog stabilizes (River Scene + contributions), re-measure; if it stays low, investigate (signal worth pulling on).

---

## Backlog 10 - `HAVASU_CHAT_MASTER.md` test fixture (**CLOSED**)

**Was:** Eight seed/backfill tests failed without **`HAVASU_CHAT_MASTER.md`** at repo root.

**Resolution:** Non-River-Scene seed/import lanes (master-backed provider seed, REAL_SEED, instructions import, Google bulk ingest, etc.) were removed in the **2026 cleanup stream**; those tests and fixtures are gone. Full `pytest` no longer depends on the master file.

---

## Backlog 11 - slowapi deprecation warnings on Python 3.14 (**OPEN**)

**Issue:** Six identical **`DeprecationWarning`** lines from `slowapi/extension.py:717` (`asyncio.iscoroutinefunction` vs `inspect.iscoroutinefunction`).

**Scope:** Library-side / upstream. Track until **`slowapi`** releases a fix or a version pin is warranted.

---

## Backlog 12 - `scripts/run_query_battery.py` retarget to `/api/chat` (**OPEN**)

**Issue:** **`scripts/run_query_battery.py`** still POSTs to **`/chat`** with **`{session_id, message}`** payload. After the H1 deletion ship (**2026-04-29**, **`61387e4..23a39a5`**), **`POST /chat`** returns **404** — the script is broken until retargeted.

**Desired fix:** Update the script to POST to **`/api/chat`** with the concierge payload shape (`{query, session_id}`). Verify against the current concierge response shape (`response`, `mode`, `sub_intent`, `entity`, `tier_used`, `latency_ms`, `llm_tokens_used`, `chat_log_id`). Update the battery's expected-response parsing accordingly.

**Adjacent:** **`docs/runbook.md`** §3.5 and **`scripts/README.md`** currently document the script as broken; once retargeted, both should be updated to describe the script as functional against **`/api/chat`**.

**Discovered during:** Phase 2 of the documentation reconciliation pass (commit **`26590b3`**).

---

## Backlog 13 - `STATE.md` "Working tree" wording is H1-anchored (**RESOLVED**)

**Original issue:** **`docs/STATE.md`** **Working tree** section referenced H1-era close-out language and drifted.

**Resolution:** **`docs/STATE.md`** rewritten **2026-05-03** with ship-agnostic working-tree guidance and broader STATE refresh.

---

## Backlog 14 - `pytest --collect-only` discipline not canonicalized (**OPEN**)

**Issue:** During the H1 deletion ship, **`python -m pytest --collect-only -q`** was used as a pre-push runtime backstop to catch references to deleted symbols that static grep can miss (parametrize args, `skipif` conditions, decorator-time evaluation). Neither **`docs/POST_SHIP_CHECKLIST.md`** nor **`docs/WORKING_AGREEMENT.md`** documents this practice.

**Decision needed:** Should **`--collect-only`** be canonical pre-push discipline for all ships, or only for deletion ships, or only when triggered case-by-case? The H1 ship's value-add was clear (deletion ship with cross-cutting references). Less clear for additive ships.

**Desired fix:** Either add a one-line bullet to **`POST_SHIP_CHECKLIST`** under verification steps, with a clause defining when it applies, or close this item with a deliberate "not canonicalized — judgment per ship" decision.

---

## Backlog 15 - Stale wording in `docs/query-test-battery.md` ~286 (**RESOLVED**)

**Original issue:** **`docs/query-test-battery.md`** near line ~286 referenced **`app/core/venues.py`** as a hypothetical "problem area." After H1, **`venues.py`** no longer existed — the wording could be misread as a current module.

**Resolution:** Wording updated **2026-05-03** to mark `venues.py` as historical / removed in H1.

---

## Backlog 16 - migrate `scripts/run_voice_audit.py` to consolidated LLM helpers (**OPEN**)

**Issue:** `scripts/run_voice_audit.py` still reproduces Anthropic-call boilerplate (`anthropic.Anthropic(...)` + `client.messages.create(...)` + token-usage extraction) instead of the shared helpers. H2 shipped **`app/core/llm_messages.py`** (`docs/maintainability/h2_consolidation_decision.md` § Status — completed); this item is now a straightforward follow-on.

**Desired fix:** Migrate the script's Anthropic call sites to use `call_anthropic_messages` and the `Usage` dataclass. Out of `app/chat/` scope and not on the production request path; low-risk one-commit change (line numbers drift — locate call sites by search).

**Severity:** LOW.

---

## Backlog 17 - extract OpenAI client into `app/core/llm_chat.py` (**DEFERRED**)

**Issue:** `app/chat/hint_extractor.py` is the only OpenAI caller in the repo today. The H2 maintainability finding flagged it as a partial duplication candidate; the H2 Session 1 design (`docs/maintainability/h2_consolidation_decision.md` §3) deferred consolidation because the helper-extraction pattern only pays off when there are multiple drifting callers. One caller is just abstraction debt.

**Precondition:** A second OpenAI caller appears in the codebase.

**Desired fix:** Mirror the `app/core/llm_messages.py` pattern from H2 with a parallel `app/core/llm_chat.py` (OpenAI's API noun) covering API-key check, client construction, response/usage extraction. Migrate both callers in the same ship.

**Severity:** LOW. No drift problem until a second caller exists.

---

## Backlog 18 - Repo hygiene & documentation hierarchy (PM phases A–D) (**OPEN**)

**Context:** PM brief at `docs/maintainability/project_manager_organization_brief.md` defines a phased program to keep the repo organized as features accumulate. This epic tracks execution as small, separately approved ships — not a stealth mega-refactor.

**Phases (each ships independently, gated):**

- [ ] **A — Single source of truth.** STATE/BACKLOG stay aligned with git and production after every ship. Resolve any doc-vs-code drift discovered in a session as its own small commit.
- [ ] **B — Filesystem contract.**
  - [x] **EOL normalization** (Slice 2, `23b2054`): `.gitattributes` policy (`text=auto eol=lf` default; explicit binary markers for `.png`, `.gz`, plus future-proof set). HEAD was already LF; primary effect is fixing Windows-side CRLF drift on checkout. Verified pre/post pytest baseline matched exactly.
  - [x] **Repo root convention** (Slice 6, `ea4fcfb`): root reserved for project spine (top-level packages, build/deploy config, tooling config, architecture spine doc); operational clutter (local DBs, script logs, env overrides, bytecode) gitignored; live-session captures go to `relay/`. Convention documented in `README.md` along with a current-Hava rewrite (replacing the stale Phase 1 16-line stub) and a "Where to look" navigation table. Misfiled `admin-dashboard-pending.png` (~30KB, no references) `git rm`'d; recoverable via git log.
  - [x] **`scripts/` convention** (Slice 4, `28cd5c6`): `scripts/README.md` rewritten with directory convention table (`scripts/*.py` tools, `fixtures/` test fixtures, `confabulation_eval_results/baselines/` tracked baselines, `output/` ephemeral outputs) and alphabetical inventory of all 16 tracked CLI tools. Tool default-path migration queued under Backlog #19; legacy tracked-output disposition queued under Backlog #20.
  - [x] **`docs/` archive convention** (Slice 5, `f8da738`): session transcripts and slice-complete writeups removed from working tree once value is captured in canonical docs or git history; live-session captures go to `relay/` (gitignored). Documented in `docs/CURSOR_ORIENTATION.md` (Process conventions bullet) and `docs/maintainability/project_index.md` (post-doc-list paragraph). Two misfiled `phase-6-1-*` transcripts removed; recoverable via git log.
- [ ] **C — Documentation depth where code is complex.** Grow `docs/components/` for the tier2 stack, contrib/River Scene, and admin. Fill `project_index.md` §5 gaps (Railway service/env matrix, HTTP API sketch, CI query-battery story) one small ship at a time.
- [ ] **D — Engineering gates.** CI lint + tests on PR. Single formatting tool, scoped to avoid whole-repo cosmetic churn in feature PRs.

**Anti-patterns (per brief §6):** mega-refactors that mix tree reorg with behavior change; parallel specs (one topic, one canonical doc); silent commits that change contracts without component-doc / BACKLOG / STATE updates; assuming pytest ran in every environment.

**Success (per brief §8):** new features land with a clear subsystem home, updated/new component docs when contracts change, and BACKLOG/STATE reflecting reality. Onboarding follows one reading path, not chat-log archaeology.

**Pre-Slice 2 finding (2026-05-03) — working-tree truncation:** During Slice 2's survey, `docs/BACKLOG.md` and `docs/STATE.md` were found truncated mid-content in the working tree (BACKLOG ended at "Layer 3 ", missing 28 lines including 3 ship log entries; STATE ended at "under `relay/` ", missing 13 lines including the "How to update this document" section). Both files terminated without trailing newline. HEAD versions were intact — corruption was unstaged-only. Restored via `git checkout HEAD -- docs/BACKLOG.md docs/STATE.md` as Slice 2 pre-step. Cause unknown; possible candidates: aftermath of stale `.git/index.lock` from 2026-05-02 22:11, an editor crash, or a sync/backup tool writing partial. Forensic file-stat snapshot pre-restore: `BACKLOG.md` Length 17862, LastWriteTime 5/3/2026 3:20:20 PM; `STATE.md` Length 6461, LastWriteTime 5/3/2026 3:21:46 PM (PowerShell `Get-Item`, Cursor agent host). **No tripwire in place beyond awareness — if this pattern recurs, escalate to investigation.**

**Follow-up (2026-05-03 evening, Slice 3):** Subsequent investigation found the bash sandbox view of Casey's filesystem produces spurious artifacts in at least two modes — appending NUL bytes to file ends (flagged on `app/main.py` and ~80 other files during Slice 2 setup) and truncating files mid-content (flagged on `docs/STATE.md` during Phase A survey). All such artifacts have been verified clean on Casey's actual filesystem via PowerShell, both via `git status` and direct byte inspection (`[IO.File]::ReadAllBytes`). The original truncation incident logged above was diagnosed only from the bash sandbox view and was never independently verified via PowerShell at the time; it may have been a sandbox artifact rather than real corruption. **Treat this entry as historical context, not as evidence of recurring filesystem corruption.** Future PM surveys must cross-verify any bash-side anomaly via PowerShell before logging it as an incident.

**First-week actions (per brief §7):**
1. Read STATE / WORKING_AGREEMENT / BACKLOG / project_index. (Done by PM 2026-05-03.)
2. Open this epic. (This entry.)
3. Land Phase A drift fixes first, then Phase B in separate approved commits.
4. Stand up a lightweight recurring review (monthly or per milestone): root listing, `scripts/` tracked files, STATE vs Railway, OPEN backlog count vs narrative.

---

## Backlog 19 - Migrate tool default output paths to `scripts/output/` (**OPEN**)

**Issue:** Several CLI tools write outputs directly to `scripts/` rather than the `scripts/output/` convention established in `scripts/README.md` (Slice 4):

- `scripts/run_voice_audit.py` line 1097: `out_path = _ROOT / "scripts" / f"voice_audit_results_{_today()}.json"`
- `scripts/diagnose_search.py`: writes `diagnose_output.txt` to `scripts/` per README
- Possibly others (audit at fix time via `grep -rn "scripts/" scripts/*.py` and similar).

**Effect:** Newly-generated outputs land in tracked-by-default territory; easy to accidentally commit. The `scripts/output/` directory and its `.gitignore` entry exist but no tool uses them.

**Desired fix:** Update each tool's default `out_path` to `scripts/output/`. Keep `--output-dir` overrides where they exist. Add a small follow-up confirming gitignore catches new outputs.

**Severity:** LOW. No functional impact; purely organizational hygiene.

**Cross-reference:** Backlog #18 Phase B `scripts/` sub-ship (Slice 4 — `28cd5c6`).

---

## Backlog 20 - Disposition for tracked dated `voice_audit_results_*.json` files (**OPEN**)

**Issue:** Five legacy tracked outputs in `scripts/` were written directly there before the `scripts/output/` convention existed (~410KB total):

- `scripts/voice_audit_results_2026-04-21.json` (~85KB)
- `scripts/voice_audit_results_2026-04-21-phase614-verify.json` (~82KB)
- `scripts/voice_audit_results_2026-04-22-phase86.json` (~84KB)
- `scripts/voice_audit_results_2026-04-23.json` (~83KB)
- `scripts/battery_results.json` (~68KB; documented in legacy README as "canonical baseline" but `run_query_battery.py` itself is broken per Backlog #12, so the baseline is stale anyway)

**Decision needed:** For each file (or group), pick one:

- **(a) Move to `scripts/baselines/<tool>/`** — if it's a canonical regression-compare reference. Requires creating `scripts/baselines/` subtree (first time).
- **(b) Move to `scripts/output/` + `git rm` from index** — if it's an ephemeral snapshot we want on disk locally but not in git.
- **(c) `git rm`** — if it's no longer current and recoverable from git history if needed.

**Severity:** LOW. ~410KB of tracked data not actively referenced. Mostly housekeeping.

**Cross-reference:** Backlog #18 Phase B `scripts/` sub-ship (Slice 4 — `28cd5c6`); Backlog #19 (tool migration); Backlog #12 (`run_query_battery.py` broken; resolves whether `battery_results.json` matters).

---

## Ship log - Session 2 follow-up, Tier 2 deterministic event rendering (**`d279165`**)

**What shipped:** Deterministic Python rendering for all-event Tier 2 catalog responses; `tier2_formatter.format()` dispatches empty rows → fixed empty message, all-event rows → renderer `(text, 0, 0)`, mixed/non-event rows → unchanged Anthropic path. Programs and providers remain LLM-formatted (scope-limited to events where dropping/count bugs were observed).

**Why:** Formatter LLM dropped rows and fabricated counts on event-date queries; prompt additions in **`1c262ad`** had **zero observable effect** on that behavior.

**Links / backlog:** Event markdown links from catalog data; Backlog **6** closed; Backlog **4** documentation closed as above. Layer 3 formatter-link prompt obviated for events.

**Tests / verification:** +22 tests, suite total 997; pre-commit pytest and post-deploy May 2/8/9 sampling with catalog fingerprint and `tier_used` response checks per session runbook.

---

## Ship log - H1 deletion ship — legacy `/chat` router (**`61387e4`..`23a39a5`**)

**What shipped:** Deleted legacy **`POST /chat`** router and dependents; **`POST /api/chat`** (unified concierge) unchanged. Removed **`app/chat/router.py`**, **`app/core/venues.py`**, **`tests/test_phase4.py`**, **`tests/test_search_relevance.py`**; trimmed **`app/main.py`**, **`app/db/chat_logging.py`**, **`app/schemas/chat.py`**, and mixed tests per plan. **Production:** `/health` 200 (`db_connected`, `event_count` 114); `/chat` → 404; `/api/chat` → 200 concierge shape. **Deploy** `6c416456-d1aa-4945-922a-cd6d7466c133`.

**Tests / verification:** 942 passing post-ship vs 987 pre-ship (**45** legacy `/chat` tests removed); **8** seed/backfill failures unchanged (baseline).

**Follow-ups:** Backlog **7**–**15** (through slowapi warnings; later items include **`run_query_battery`** retarget, STATE wording, **`--collect-only`** discipline, **`query-test-battery`** wording — see current **`BACKLOG.md`**).

---

## Ship log - RS-only catalog cleanup + retrospective (**`5e75bf5`..`7cba51e`**)

**What shipped:** Removed non–River-Scene ingestion and seed lanes from code; `scripts/cleanup_non_river_scene.py` and production DB apply removed non-RS catalog rows. Retrospective: `docs/maintainability/non_river_scene_cleanup.md`.

**Follow-ups:** Provider ingestion and chat eval deferred per `docs/maintainability/chat_behavior_followup_plan.md`.

---

## Ship log - Documentation refresh (**`e83ccf0`..`905ce17`**)

**What shipped:** Chat followup plan, `docs/maintainability/project_index.md`, repo-root `HAVA_CONCIERGE_HANDOFF.md` (architecture spine), pruned historical tier/Railway/handoff markdown (recoverable from git). **`docs/STATE.md`**, **`docs/PROJECT.md`**, **`docs/persona-brief.md`**, **`docs/BACKLOG.md`** (Backlog **16** → OPEN; **13**, **15** → RESOLVED), `docs/query-test-battery.md`, `docs/known-issues.md`, and cross-references updated for consistency.
