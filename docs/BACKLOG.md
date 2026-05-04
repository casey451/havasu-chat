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

## Backlog 9 - Tier 1 hit rate (**DEFERRED**)

**Observation:** ~33/486 ≈ **7%** Tier 1 hits pre-H1 — lower than expected for templated provider lookups.

**Next step:** After the live catalog stabilizes (River Scene + contributions), re-measure; if it stays low, investigate (signal worth pulling on).

**Status changed:** OPEN → DEFERRED (Slice 20). The original "Next step" said "After the live catalog stabilizes (River Scene + contributions), re-measure." Per current STATE.md catalog posture, **the precondition isn't time-based — it's data-based**: `providers` table is empty after the 2026 RS-only cleanup; Tier 1 templated provider lookups have nothing to hit, so hit rate would currently measure near 0% regardless of query mix. Re-measurement is meaningless until providers actually populate.

**Precondition for re-opening:** Provider rows exist in production catalog. Routes to provider population include (a) approved contributions with `entity_type='provider'`, (b) future provider ingestion lane (filed as Phase C §5 sub-bullet under Backlog #18; forward-looking spec not yet shipped), (c) Tier 3 mention promotions creating Provider rows (operational since Slice 8's `end_to_end_creation.md` Path 3). Once providers are populated and a representative query mix has run for a measurement window (e.g., a week of chat traffic), re-measure Tier 1 hit rate against `chat_logs` and re-evaluate.

No code change required. Tracking until precondition is met.

---

## Backlog 10 - `HAVASU_CHAT_MASTER.md` test fixture (**CLOSED**)

**Was:** Eight seed/backfill tests failed without **`HAVASU_CHAT_MASTER.md`** at repo root.

**Resolution:** Non-River-Scene seed/import lanes (master-backed provider seed, REAL_SEED, instructions import, Google bulk ingest, etc.) were removed in the **2026 cleanup stream**; those tests and fixtures are gone. Full `pytest` no longer depends on the master file.

---

## Backlog 11 - slowapi deprecation warnings on Python 3.14 (**DEFERRED**)

**Issue:** Six identical **`DeprecationWarning`** lines from `slowapi/extension.py:717` (`asyncio.iscoroutinefunction` vs `inspect.iscoroutinefunction`).

**Scope:** Library-side / upstream. Track until **`slowapi`** releases a fix or a version pin is warranted.

**Status changed:** OPEN → DEFERRED (Slice 19). The original Scope line already said "Track until slowapi releases a fix or a version pin is warranted." Formalizing as DEFERRED matches the canonical convention: explicitly out of scope until a precondition is met.

**Precondition for re-opening:** Either (a) slowapi releases a version that uses `inspect.iscoroutinefunction()` instead of `asyncio.iscoroutinefunction()` (eliminating the warning at upstream level), or (b) a version pin to a future Python release that drops `asyncio.iscoroutinefunction()` becomes warranted (forcing us to either update or pin slowapi). Until then, the 5 warnings per pytest run are benign — they don't fail tests, don't affect production behavior, and don't surface to users.

No code change required.

---

## Backlog 12 - `scripts/run_query_battery.py` retarget to `/api/chat` (**RESOLVED**)

**Issue:** **`scripts/run_query_battery.py`** still POSTs to **`/chat`** with **`{session_id, message}`** payload. After the H1 deletion ship (**2026-04-29**, **`61387e4..23a39a5`**), **`POST /chat`** returns **404** — the script is broken until retargeted.

**Desired fix:** Update the script to POST to **`/api/chat`** with the concierge payload shape (`{query, session_id}`). Verify against the current concierge response shape (`response`, `mode`, `sub_intent`, `entity`, `tier_used`, `latency_ms`, `llm_tokens_used`, `chat_log_id`). Update the battery's expected-response parsing accordingly.

**Adjacent:** **`docs/runbook.md`** §3.5 and **`scripts/README.md`** currently document the script as broken; once retargeted, both should be updated to describe the script as functional against **`/api/chat`**.

**Discovered during:** Phase 2 of the documentation reconciliation pass (commit **`26590b3`**).

**Resolution shipped:** **`fd313bb`** — Retargeted via raw-passthrough scope (Slice 16). Endpoint and payload updated to `/api/chat` with `{query, session_id}` shape; response classifier rewritten to capture new ConciergeChatResponse fields (`mode`, `sub_intent`, `entity`, `tier_used`, `latency_ms`, `llm_tokens_used`, `chat_log_id`) verbatim. Old intent-based expected/actual matching dropped — the new tier-based router output doesn't 1:1 map to pre-H1 intent labels, so the 115 SINGLE_SHOT tuples retain their `expected` field but it's unused. Single-query production smoke test confirmed runtime behavior (1 chat_log row created). Pytest count unchanged at 949 (script not in test coverage).

Restoring expected-label categorization for the new tier-based shape — so the battery can detect regressions automatically — is queued as **Backlog #25**.

Adjacent doc updates from the OLD entry are still valid: `docs/runbook.md` §3.5 and `scripts/README.md` reference this script. The README's "BROKEN" note becomes stale; updating it is a nice follow-up but not strictly required for the script to work. Phase C `CI query-battery story` sub-bullet under #18 was BLOCKED on this; now unblocked (still requires #25 + actual CI infra to fully address).

---

## Backlog 13 - `STATE.md` "Working tree" wording is H1-anchored (**RESOLVED**)

**Original issue:** **`docs/STATE.md`** **Working tree** section referenced H1-era close-out language and drifted.

**Resolution:** **`docs/STATE.md`** rewritten **2026-05-03** with ship-agnostic working-tree guidance and broader STATE refresh.

---

## Backlog 14 - `pytest --collect-only` discipline not canonicalized (**RESOLVED**)

**Issue:** During the H1 deletion ship, **`python -m pytest --collect-only -q`** was used as a pre-push runtime backstop to catch references to deleted symbols that static grep can miss (parametrize args, `skipif` conditions, decorator-time evaluation). Neither **`docs/POST_SHIP_CHECKLIST.md`** nor **`docs/WORKING_AGREEMENT.md`** documents this practice.

**Decision needed:** Should **`--collect-only`** be canonical pre-push discipline for all ships, or only for deletion ships, or only when triggered case-by-case? The H1 ship's value-add was clear (deletion ship with cross-cutting references). Less clear for additive ships.

**Desired fix:** Either add a one-line bullet to **`POST_SHIP_CHECKLIST`** under verification steps, with a clause defining when it applies, or close this item with a deliberate "not canonicalized — judgment per ship" decision.

**Resolution shipped:** Decision: **judgment per ship; not canonical pre-push discipline.**

Grounded in 17 slices of post-H1 ship experience (today's session, 2026-05-04). Every slice used `python -m pytest -q` alone for pre/post verification; all 17 verified cleanly. This includes 4 deletion-flavored ships:

- Slice 5 — removed 2 misfiled transcript .txt files
- Slice 11 — removed 5 tracked output JSONs (~410KB) + README paragraph
- Slice 14 — removed `/admin/debug-pw` endpoint + helper + test + 2 doc references (5-file removal)
- Slice 17 — removed inline Anthropic boilerplate (helper migration)

None had hidden import-time or collection-time issues that `--collect-only` would have caught earlier than `pytest -q`. The H1 ship that originally motivated this concern had cross-cutting parametrize-arg + skipif-decorator references to legacy modules — that complexity was itself removed in H1, and post-H1 code doesn't have similar pattern.

**Heuristic for future use:** reach for `python -m pytest --collect-only -q` ONLY when removing or renaming symbols that are referenced by `@pytest.mark.parametrize` argument values, `@pytest.mark.skipif` condition expressions, decorator-time eval'd attributes, or other test-collection-time string references. For ordinary code change / removal / addition ships, `pytest -q` exercises every test path that `--collect-only` would have flagged anyway — collection happens as part of execution.

No `POST_SHIP_CHECKLIST.md` or `WORKING_AGREEMENT.md` update required; the canonical workflow stays as-is.

---

## Backlog 15 - Stale wording in `docs/query-test-battery.md` ~286 (**RESOLVED**)

**Original issue:** **`docs/query-test-battery.md`** near line ~286 referenced **`app/core/venues.py`** as a hypothetical "problem area." After H1, **`venues.py`** no longer existed — the wording could be misread as a current module.

**Resolution:** Wording updated **2026-05-03** to mark `venues.py` as historical / removed in H1.

---

## Backlog 16 - migrate `scripts/run_voice_audit.py` to consolidated LLM helpers (**RESOLVED**)

**Issue:** `scripts/run_voice_audit.py` still reproduces Anthropic-call boilerplate (`anthropic.Anthropic(...)` + `client.messages.create(...)` + token-usage extraction) instead of the shared helpers. H2 shipped **`app/core/llm_messages.py`** (`docs/maintainability/h2_consolidation_decision.md` § Status — completed); this item is now a straightforward follow-on.

**Desired fix:** Migrate the script's Anthropic call sites to use `call_anthropic_messages` and the `Usage` dataclass. Out of `app/chat/` scope and not on the production request path; low-risk one-commit change (line numbers drift — locate call sites by search).

**Severity:** LOW.

**Resolution shipped:** `ab8df88` — Migrated both `messages.create()` call sites in `_run_voice_audits()` to use `call_anthropic_messages()` from `app/core/llm_messages.py` (the H2 consolidation point). Removed inline `import anthropic` + client construction from `main()`. Updated `_run_voice_audits` signature to drop the `client` parameter (helper constructs its own client internally). Kept the `api_key = os.getenv()` pre-flight check for early-error UX before cost estimation. Pytest count unchanged at 949 (script not in test coverage); `py_compile` confirmed syntactic correctness.

**Production runtime verification deferred** — the voice audit script makes 100+ Anthropic calls per run (~$2-5 in API costs), so smoke testing isn't cost-effective. The next legitimate audit run will exercise the migrated path; runtime regressions would surface as `ERROR` verdicts in the output JSON.

This makes scripts/run_voice_audit.py the second Anthropic caller fully on the H2 helper (after the in-app callers migrated in the original H2 ship). Backlog #17 (OpenAI helper extraction) remains DEFERRED — `app/chat/hint_extractor.py` is still the sole OpenAI caller; pattern only pays off with a second drifting caller.

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
- [ ] **C — Documentation depth where code is complex.**
  - [ ] **Component docs growth** (ongoing). Tier2 stack, contrib/River Scene, admin.
  - [x] **§5 gap: Railway service/env matrix** (Slice 7, `765ee61`): `docs/maintainability/railway_layout.md` consolidates process types, env var matrix, DB URL resolution, health checks, deploy flow.
  - [x] **§5 gap: HTTP API sketch** (Slice 8, `5f14f36`): `docs/maintainability/http_api.md` consolidates all 58 routes — mount layout, public routes by group, admin HTML routes (cookie-gated `verify_admin`), admin JSON API routes (`Depends(require_admin)`), auth posture summary, rate limits (slowapi + custom contribute limiter), schema pointers.
  - [ ] **§5 gap: CI query-battery story** (how-to-run-in-CI doc; depends on Backlog #12 retarget first).
  - [ ] **§5 gap: Provider ingestion lane (forward-looking spec).**
  - [x] **§5 gap: End-to-end provider/program creation** (Slice 9, `c1cd8b0`): `docs/maintainability/end_to_end_creation.md` documents the four paths producing catalog rows (public submission, River Scene auto-import, Tier 3 mention scan promotion, admin direct create), Contribution status state machine, and per-entity-type fields touched at creation.
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

## Backlog 19 - Migrate tool default output paths to `scripts/output/` (**RESOLVED**)

**Issue:** Several CLI tools write outputs directly to `scripts/` rather than the `scripts/output/` convention established in `scripts/README.md` (Slice 4):

- `scripts/run_voice_audit.py` line 1097: `out_path = _ROOT / "scripts" / f"voice_audit_results_{_today()}.json"`
- `scripts/diagnose_search.py`: writes `diagnose_output.txt` to `scripts/` per README
- Possibly others (audit at fix time via `grep -rn "scripts/" scripts/*.py` and similar).

**Effect:** Newly-generated outputs land in tracked-by-default territory; easy to accidentally commit. The `scripts/output/` directory and its `.gitignore` entry exist but no tool uses them.

**Desired fix:** Update each tool's default `out_path` to `scripts/output/`. Keep `--output-dir` overrides where they exist. Add a small follow-up confirming gitignore catches new outputs.

**Severity:** LOW. No functional impact; purely organizational hygiene.

**Cross-reference:** Backlog #18 Phase B `scripts/` sub-ship (Slice 4 — `28cd5c6`).

**Resolution shipped:** `d429fe7` — `scripts/run_voice_audit.py:1097` and `scripts/diagnose_search.py:19` migrated to write under `scripts/output/`; `parent.mkdir(parents=True, exist_ok=True)` added before each `write_text` call to handle fresh-clone directory absence (matches the pattern already used by `extract_tier3_queries.py:60` and `run_voice_spotcheck.py:206`). The other tools surveyed (`extract_tier3_queries.py`, `run_voice_spotcheck.py`, `confabulation_eval.py`) already used a correct convention. Pytest count unchanged pre/post (behavior-neutral; no script is in test coverage). **Bonus findings noted but not addressed:**

- `diagnose_search.py:18` has `BASE_URL = "https://web-production-bbe17.up.railway.app"`, which does NOT match production (`havasu-chat-production.up.railway.app` per `docs/STATE.md`). The script would fail if run as-is.
- `diagnose_search.py:4` docstring still references the old output path (`scripts/diagnose_output.txt`); the functional definition at line 19 was migrated to `scripts/output/`. One-line docstring fix possible in a future small commit if anyone wants doc-vs-code consistency.

---

## Backlog 20 - Disposition for tracked dated `voice_audit_results_*.json` files (**RESOLVED**)

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

**Resolution shipped:** `15f7248` — All 5 legacy tracked outputs removed via `git rm`:

- `scripts/battery_results.json` (~68KB) — documented as "canonical baseline" but `run_query_battery.py` is broken (Backlog #12), so the baseline is stale. When #12 ships, it'll produce a fresh baseline; until then, recoverable via `git log -- scripts/battery_results.json`.
- `scripts/voice_audit_results_2026-04-21.json`, `scripts/voice_audit_results_2026-04-21-phase614-verify.json`, `scripts/voice_audit_results_2026-04-22-phase86.json`, `scripts/voice_audit_results_2026-04-23.json` (~340KB total) — dated snapshots, not active reference data per the README's own definition. Future runs of `run_voice_audit.py` write under `scripts/output/` per Slice 10 (#19 closure).

`scripts/README.md` legacy paragraph (the one that explicitly said "queued in Backlog #20") removed in the same commit.

**Three other doc references to these files were deliberately LEFT in place** as historical context per the project_index convention (`docs/maintainability/project_index.md` post-doc-list paragraph from Slice 5: removed-from-tree files recoverable via `git log --all -- <path>`):

- `docs/havasu-development-plan.md:78` — narrative reference to the historical 96.67% pass rate.
- `docs/runbook.md:291` — operational note giving `battery_results.json` as an example of "baselines in scripts/ are not auto-applied."
- `docs/known-issues.md:129` — references a specific sample (`t3-01`) in one of the dated voice_audit JSONs.

All three are narrative/historical, not operational. Pytest count unchanged pre/post (no code touched).

This closes the Phase B follow-up family entirely (#19 closed in Slice 10; #20 closed here).

---

---

## Backlog 21 - `POST /events` posture review (**RESOLVED**)

**Issue:** `POST /events` is a public-facing rate-limited (5/min) endpoint at the top level (`app/main.py:create_event`). Surfaced as an observation in `docs/maintainability/http_api.md` (Slice 8) with note "verify intent." It's unclear whether this is intentional (public event creation accepted with rate limiting) or a Phase 1 leftover before the contribution-flow path was designed.

**Effect:** Public clients can POST events directly without going through the Contribution → admin review approval flow that all other catalog row creation goes through (per `docs/maintainability/end_to_end_creation.md`).

**Desired action:** Casey-level decision on whether the endpoint should:
- (a) Stay public (intentional bypass for some use case)
- (b) Move behind admin auth (`Depends(require_admin)`)
- (c) Be removed entirely (Phase 1 leftover)

If (b) or (c), small follow-up slice to implement.

**Severity:** LOW. The rate limit (5/min) plus catalog `status='live'` default means abuse risk is bounded but real.

**Cross-reference:** Surfaced in `docs/maintainability/http_api.md` (Slice 8, `5f14f36`).

**Resolution shipped:** `b1a0add` — Disposition (d) chosen: cookie-gate now, queue full removal as Backlog #24. Files touched (6):

- `app/main.py`: import + local `require_admin` + `Depends(require_admin)` on `create_event`.
- `tests/test_phase1.py`, `tests/test_permalinks.py`: local `_login_admin` helper + login call before POST /events.
- `tests/test_phase6.py`: login call (helper already exists).
- `docs/maintainability/http_api.md`: row updated with Admin-gated note; auth posture summary drops +1 public write (17 → 16).
- `docs/maintainability/end_to_end_creation.md`: Path 4 events note reflects cookie-gating.

Rationale: investigation found `POST /events` allowed any unauthenticated client to create immediately-live, "verified", admin-attributed catalog rows (the Pydantic schema lets the caller set `status` / `source` / `verified` directly). Rate limit (5/min) provided only DOS protection, not abuse protection. Disposition (d) addresses the abuse vector immediately while deferring the bigger refactor (test fixtures using HTTP endpoint instead of SQLAlchemy direct) to **Backlog #24**.

DRY tradeoffs accepted in this slice: `require_admin` now exists in 3 modules; `_login_admin` now exists in 3 test files. Consolidation is separate work.

Pytest count unchanged pre/post (949).

---

## Backlog 22 - `/admin/debug-pw` posture review (**RESOLVED**)

**Issue:** `GET /admin/debug-pw` is an admin-routed endpoint (`app/admin/router.py:admin_debug_pw`) that is NOT cookie-gated by `verify_admin`. Surfaced as an observation in `docs/maintainability/http_api.md` (Slice 8) with note "verify production posture."

**Effect:** Anyone who can reach the production URL can hit `/admin/debug-pw` without authentication. The endpoint's purpose is unclear from the name alone — possibly a debug helper that shouldn't be exposed in production.

**Desired action:** Casey-level review:
- Read what the handler actually does (`app/admin/router.py:admin_debug_pw`).
- Decide whether the endpoint should:
  - (a) Stay accessible (intentional sandbox / known-safe)
  - (b) Be cookie-gated like the rest of `/admin/*`
  - (c) Be removed entirely from production
  - (d) Stay in dev but be guarded against production via env-var check

If (b), (c), or (d), small follow-up slice to implement.

**Severity:** LOW-MEDIUM. Severity depends on what the handler exposes.

**Cross-reference:** Surfaced in `docs/maintainability/http_api.md` (Slice 8, `5f14f36`).

**Resolution shipped:** `72728e2` — Disposition (c) chosen: endpoint removed entirely. Files touched (5):

- `app/admin/router.py`: import + handler removed (the `@router.get("/debug-pw")` block).
- `app/admin/auth.py`: `admin_password_debug_info` helper removed (was only used by this one endpoint).
- `tests/test_phase6.py`: `test_admin_debug_pw_reports_stripped_length` test removed (no longer applicable).
- `docs/maintainability/http_api.md`: `/admin/debug-pw` row removed from admin auth+dashboard table.
- `docs/runbook.md`: "Debug (non-secret)" subsection removed (single-bullet section that became empty).

Rationale: the endpoint's docstring marked it "Temporary"; it lived past its purpose. The info it leaked (boolean `pw_set` + integer `pw_length`) is minor but unnecessary. Option (b) cookie-gate would defeat the endpoint's own purpose (an authenticated admin already knows the password is set). Option (d) env-var-guard adds maintenance for an endpoint nobody uses. Removing eliminates the leak with zero functional cost; if Railway env-var visibility ever needs debugging again, Railway logs/shell are the right tools.

Pytest dropped from 950 to 949 (the one removed test).

---

## Backlog 23 - `scripts/diagnose_search.py` cleanup: stale BASE_URL + stale docstring (**RESOLVED**)

**Issue:** Two stale references in `scripts/diagnose_search.py` surfaced during Slice 10's tool default-path migration but deferred:

- **Line 18 BASE_URL drift:** `BASE_URL = "https://web-production-bbe17.up.railway.app"` does NOT match production (`havasu-chat-production.up.railway.app` per `docs/STATE.md`). The script targets a stale Railway URL and would fail with connection errors if run as-is.
- **Line 4 docstring drift:** Docstring still references the old output path (`scripts/diagnose_output.txt`); the functional path was migrated to `scripts/output/diagnose_output.txt` in Slice 10 (`d429fe7`).

**Effect:** Anyone trying to use `diagnose_search.py` would hit either a connection failure (BASE_URL) or be confused by the docstring's mismatch with the actual output path.

**Desired fix:** One small commit:
- Update line 18 `BASE_URL` to the current production URL.
- Update line 4 docstring to reference `scripts/output/diagnose_output.txt`.

Could be expanded to also wire the BASE_URL through an env var (`HAVASU_DIAGNOSE_BASE` or similar) so it doesn't drift again, but the minimum viable fix is just the two-line update.

**Severity:** LOW. Diagnostic tool, not production code path.

**Cross-reference:** Surfaced in Backlog #19 closure (Slice 10, `d429fe7`) bonus findings.

**Resolution shipped:** `c94afb6` — Both edits applied:

- Line 4 docstring updated to reference `scripts/output/diagnose_output.txt`.
- Line 18 `BASE_URL` updated to `https://havasu-chat-production.up.railway.app` (matches `docs/STATE.md` production URL).

Minimum-viable fix; did not wire `BASE_URL` through an env var (e.g., `HAVASU_DIAGNOSE_BASE`) to prevent future drift. If drift recurs, that's a separate small follow-up. Pytest count unchanged pre/post (behavior-neutral; no test loads these constants).

---

## Backlog 24 - Remove `POST /events` entirely + refactor tests to SQLAlchemy fixtures (**OPEN**)

**Issue:** Slice 15 (Backlog #21 close via option (d)) cookie-gated `POST /events` to address the abuse vector but did not remove the endpoint. The endpoint now requires admin auth, making it functionally a redundant admin direct-create path. It is preserved primarily because three test files use it for fixture creation:

- `tests/test_phase1.py:test_create_event` (the actual test of the endpoint)
- `tests/test_permalinks.py:_create_event` helper (used by 2+ test methods to seed events)
- `tests/test_phase6.py:test_post_events_returns_friendly_message_for_invalid_title` (tests 422 validation behavior)

After Slice 15 these all login first, but the underlying pattern (tests POSTing through HTTP for fixture creation) is fragile and shouldn't depend on a production endpoint that may be removed.

**Desired fix:**

- Refactor the 3 test sites to create Event rows via SQLAlchemy directly (`db.add(Event.from_create(payload)); db.commit()`) instead of going through the HTTP endpoint. Test-fixture creation should not depend on production endpoints.
- Remove `POST /events` handler from `app/main.py` (and the `require_admin` local copy if no other endpoint in main.py uses it).
- Remove `EventRead` import from `app/main.py` (verify no other caller).
- Update `docs/maintainability/http_api.md` to remove `POST /events` entirely from the events section.
- Update `docs/maintainability/end_to_end_creation.md` Path 4 to note `POST /events` is gone (admin event creation has no direct-create UI; events come via Path 1, Path 2, or Path 3).

**Severity:** LOW. The cookie-gate from Slice 15 closes the abuse vector; this follow-up is hygiene cleanup.

**Cross-reference:** Surfaced in Backlog #21 closure (Slice 15).

---

## Backlog 25 - Rebuild `SINGLE_SHOT` expected labels for new ConciergeChatResponse shape (**OPEN**)

**Issue:** Slice 16 (Backlog #12 close) retargeted `scripts/run_query_battery.py` to `/api/chat` via raw-passthrough scope: endpoint, payload, response parsing, and record fields all updated. But the 115 hardcoded `SINGLE_SHOT` tuples retain their pre-H1 `expected` labels (e.g., `{"EVENTS"}`, `{"OUT_OF_SCOPE"}`) which assume the OLD intent-based categorization. The current `classify()` function ignores those labels and just produces tier-based passthrough strings (`TIER1`, `TIER2`, `TIER3`, `CHAT`, etc.) — no expected/actual matching, no regression-detection.

**Effect:** The battery now runs and produces useful diagnostic output, but it can't automatically flag regressions. Anyone reviewing the battery JSON has to eyeball each query's tier+mode+sub_intent+response and decide whether it looks right.

**Desired fix:** Audit the 115 SINGLE_SHOT tuples (and the SEQUENCES tuples) and assign new expected labels using the ConciergeChatResponse fields. Possibilities:

- Express expectations as expected `tier_used` (e.g., "boat race" → expect TIER2; "thanks" → expect CHAT/GREETING).
- Express expectations as expected `mode` + `sub_intent` (e.g., "boat race" → mode=ask, sub_intent=EVENT_LOOKUP or similar).
- Combine: tier as primary expectation, mode/sub_intent as secondary.
- Or: expected `response_snippet` substring matches for queries with deterministic answers.

Once expected labels exist, restore `match` field in record output and write a summary block (e.g., "115/120 matched, 5 mismatched: query #N expected TIER2 got TIER3 ...").

**Severity:** LOW. The retarget already addresses the abuse-vector-shaped problem (script was 404'ing); regression-detection is hygiene improvement.

**Cross-reference:** Surfaced in Backlog #12 closure (Slice 16). Adjacent: Phase C CI query-battery sub-bullet under #18 (now unblocked but still requires this work + actual CI infra).

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
