# Phase 2 First-Week Dispatch Playbook

**Audience:** A fresh Cowork primary picking up the project after the 2026-05-09 Phase 1 close.
**Purpose:** Get to dispatch within ~10 minutes of opening this doc. Ready-to-paste prompts for the first 5 lanes; tool-use guidance for routing work to the available agents; risks/gotchas anchored to today's discoveries.
**Companion docs:** `docs/SESSION_HANDOFF_2026-05-09.md` (what landed yesterday), `docs/STATE.md` (canonical project state), `docs/BACKLOG.md` (every ship-log + open item with attribution), `docs/maintainability/phase2_lane_decomposition.md` (the 17-lane / 5-phase strategic plan this playbook executes).

---

## §1 — Boot sequence

Before dispatching anything:

1. Read `docs/SESSION_HANDOFF_2026-05-09.md` §0–§4 (~5 min). Critical: §3.1 explains the §6.2 CT flag verification chain that surfaced #47/#48/#49 — without that context, lane 1 below won't make sense.
2. Verify the local pytest baseline:
   ```powershell
   cd C:\Users\casey\projects\havasu-chat
   .\.venv\Scripts\python.exe -m pytest -q
   ```
   Expect: **1327 passed**. If different, `git log --oneline -10` to see what changed.
3. Verify production hasn't drifted (Railway dashboard for deploy SHA + a quick smoke):
   ```powershell
   Invoke-RestMethod -Method Post -Uri "https://havasu-chat-production.up.railway.app/api/chat" -ContentType "application/json; charset=utf-8" -Body '{"query":"find a plumber","session_id":"boot-1"}'
   ```
   Expect: HTTP 200, response with `tier_used: 2`, NO `Sponsored` text, NO `recommend calling to confirm`. If either flag-on artifact appears, check Railway env vars before doing anything else.
4. Ask the operator (Casey) which lane to start with. The order in §3 below is opinionated but he overrides.

---

## §2 — Tool-use playbook

You have **four channels** for delegating work. Pick the right one for the task; mismatched dispatches waste a round-trip.

### Cursor — focused-file edits, anchored work

**Best for:** single-file-or-few-files surgical edits, schema migrations, ops scripts, CSS/template work, anything where the spec is precise and the diff is bounded.

**Strengths:** Precise. Respects anchored Edits cleanly. Good at "do exactly this and report back." Has full repo file access.

**Watch for:** Sometimes ships pragmatic deviations from the dispatch and reports them at the end (e.g. yesterday's #41a "shipped naive-on-read instead of always-aware-on-read because pure always-aware would force out-of-scope context_builder edits"). Re-read Cursor's reports for "deviation" callouts before integrating.

**How you dispatch:** Operator pastes your prompt into Cursor. Cursor returns a text report. Operator pastes that report back to you for integration.

### Claude Code (CC) — heavy lanes, multi-file refactors, comprehensive coverage

**Best for:** test-suite triage, multi-file refactors, audit lanes (deploy runbook audit, code review of large changes), comprehensive test suite generation, architectural investigation.

**Strengths:** Handles multi-file scope without losing the thread. Strong at producing comprehensive test coverage. Good at "investigate this and propose a fix" lanes.

**Watch for:** May report back with assumptions ("Class A tests landed GREEN-on-arrival because Cursor's fix was already in working tree" — yesterday's adversarial test coverage lane). Verify the assumption matches reality.

**How you dispatch:** Same pattern as Cursor — operator pastes your prompt; CC returns a text report.

### ChatGPT — non-file research, drafting, brainstorming

**Best for:** anything that doesn't need codebase access. Sponsor outreach drafts, adversarial input brainstorms, market research, copy editing, research questions.

**Strengths:** Fast, no file access overhead. Good at structured creative work (cold email templates, adversarial query patterns, comparative analysis).

**Cannot:** Read the codebase, execute code, or modify files. Anything you give it must be self-contained in the prompt.

**How you dispatch:** Same pattern — operator pastes prompt to ChatGPT; pastes output back to you. You save to file if useful (yesterday's `cold_email_templates.md` and `backlog_46_smoke_check_queries.md` patterns).

### General-purpose agent (via your `Agent` tool)

**Best for:** parallel verification lanes that can run while other agents work, code reviews, voice-battery-style adversarial testing, research questions that require file access, anything you want to keep out of the operator's hand-off cycle.

**Strengths:** Direct dispatch from you (no operator round-trip). Has file tools + bash. Good at "go investigate X and report back."

**Cost:** Burns context. Use for genuinely useful parallel work, not for things you could do in one Edit yourself.

**How you dispatch:** Use the `Agent` tool with a tight self-contained prompt. The agent runs, reports back, and the result is in your context.

### Decision matrix — quick reference

| Task | First choice | Why |
|---|---|---|
| Multi-file production code refactor | Claude Code | Multi-file scope handled cleanly |
| Single-file surgical edit | Cursor | Anchored Edits, precise |
| New test suite for a fix | Claude Code | Generates comprehensive coverage |
| Audit existing docs / runbook | Claude Code | Punch-list output is clean |
| Schema migration | Cursor | One file + one model edit + one test |
| Operator-facing copy / outreach | ChatGPT | No file access needed |
| Brainstorm adversarial inputs | ChatGPT | Fast, no codebase context required |
| Code review of a recent ship | General-purpose agent (review focus) | Independent second opinion |
| Voice-battery-style live verification | General-purpose agent (with bash) | Can run pytest + ad-hoc Python against `data/events.db` |
| Read a long doc end-to-end + summarize | General-purpose agent | Cheap, returns the salient points |
| Quick file edit you have full context on | Just do it yourself with Edit tool | No round-trip overhead |

---

## §3 — Lane sequence (recommended; operator overrides)

The Phase 2 lane decomposition spec at `docs/maintainability/phase2_lane_decomposition.md` originally had **P2.OBS.1 (observability instrumentation) as the highest-leverage first-week lane.** Yesterday's §6.2 CT flag verification surfaced #47/#48/#49 — production behavior bugs that mean observability data collected NOW would be polluted by known-buggy responses. So the lane order is reshuffled:

1. **Lane 1: #47/#48/#49 fix bundle** — restores `FEATURE_FLAG_CONFIDENCE_TIER` to a re-flippable state. Without this, no point flipping CT for observability.
2. **Lane 2: P2.HOME.1** — `DISCLOSURE_WORD` consistency on `/home`.
3. **Lane 3: P2.BL.45** — verification_method CHECK constraint expansion.
4. **Lane 4: P2.OBS.1** — disclosure-renderer observability instrumentation. Now safe to ship after Lane 1.
5. **Lane 5: Operator enrichment sprint** — operator-driven, parallel to all engineering lanes. Tooling is shipped.

The dispatch prompts for each lane are below in §4–§8. Each is self-contained — paste into the named agent and the agent has full context.

---

## §4 — Lane 1: #47/#48/#49 fix bundle (Cursor — heavy lane, may need to split)

**Why this lane is first:** All three bugs surfaced from the same §6.2 verification chain and share fix infrastructure. Shipping them as a bundle minimizes regression risk vs landing them piecemeal. The bundle is bounded (3 files at most: `app/chat/entity_matcher.py`, `app/chat/tier3_handler.py` or its post-processor home, `app/chat/llm_cache.py`) but each fix has its own design call. **Read each backlog entry in `docs/BACKLOG.md` (#47, #48, #49) before dispatching** — the recommended fix sketches are detailed and the verification harnesses are spec'd.

**Decision before dispatch:** ship as a single Cursor lane, or split into 3 lanes?

- **Single lane** — faster to land, single git commit, easier rollback. Cursor handles 3 files.
- **Split** — each lane gets independent verification, easier to spot which fix broke something. More overhead.

Recommend single lane unless the operator wants extra caution. The dispatch prompt below assumes single-lane.

### Dispatch prompt — paste into Cursor

```
**Lane:** Backlog #47 + #48 + #49 fix bundle — entity matcher cross-category false positive + post-processor blind insertion + LlmResponseCache pollution. All three surfaced from the §6.2 CT flag verification chain on 2026-05-09 and must ship before `FEATURE_FLAG_CONFIDENCE_TIER` can safely re-enable in production.

**Estimate:** 60–90 min. Three coordinated fixes; each has a recommended approach in `docs/BACKLOG.md`. Read those entries first — they have full reproduction recipes and verification harnesses.

**Files in scope:**
1. `app/chat/entity_matcher.py` — fix #47 (category-aware reranking or row-pruning at retrieval).
2. `app/chat/tier3_handler.py` and/or `app/chat/tier2_formatter.py::_enforce_low_tier_phone` — fix #48 (negation-aware skip in post-processor).
3. `app/chat/llm_cache.py` — fix #49 (cache raw LLM output, re-run post-processors on cache hit).

**Out of scope (do NOT touch):** any test file outside the new ones you add for these fixes. `app/db/types.py`, `app/chat/context_builder.py`, `app/chat/confidence_tier.py`, `app/chat/disclosure_render.py` (unless one of the three fixes genuinely needs to touch them — flag in your report if so).

**Recommended approach per fix:**

1. **#47:** see backlog #47 §"Recommended fix" — Option 2 (Tier 3 row-pruning at retrieval, filter by category match against query intent) is most consistent with existing architecture. Reuse the intent classifier's category extraction.
2. **#48:** see backlog #48 §"Recommended fix" — Option 1 (negation-aware skip in `_enforce_low_tier_phone` before appending) is minimal and operationally cheap. Pattern list: "no result", "not in catalog", "I don't have", "I don't see", "no [category]".
3. **#49:** see backlog #49 §"Recommended fix" — Option 1 (cache raw LLM output, re-run post-processors on cache hit) is most principled. Trade-off: cache hits become deterministic-on-current-code, which is the right contract.

**New tests required (add as you ship each fix):**

- `tests/test_entity_matcher_category_guard.py` — adversarial cases for #47 (the exact `"what is the best plumber in lake havasu"` query and 3-5 sibling cases). Must pin the category-guard behavior so this can't regress.
- `tests/test_tier3_postprocess_negation_skip.py` — adversarial cases for #48 (LLM voice contains negation pattern; row has phone; verify post-processor skips).
- `tests/test_llm_cache_raw_storage.py` — verify cache stores raw text and post-processor runs on hit (#49).

**Verification harness — must all pass before reporting ship:**

```
python -m pytest tests/test_entity_matcher.py tests/test_entity_matcher_adversarial.py tests/test_entity_matcher_category_guard.py tests/test_phase38_gap_and_hours.py -q
python -m pytest tests/test_tier3_handler.py tests/test_tier3_phone_enforcement.py tests/test_tier3_postprocess_negation_skip.py -q
python -m pytest tests/test_llm_cache.py tests/test_llm_cache_raw_storage.py -q
python -m pytest -q
```

The full suite must hit ≥ 1327 passed (baseline). Adversarial check (run inline Python or add a smoke script):

```
phone for addrss              → None / None
sloane number                 → None / None
what is the best plumber...   → entity is a real plumber OR None (NOT Lake Havasu City BMX)
hours for All Seasons Plumbing → entity = All Seasons Plumbing (preserves Tier 1 path)
```

**Report:**
1. Summary of what changed in each of the three files (function-level diff).
2. New test counts (per new test file).
3. Final pytest line for the full suite.
4. The four adversarial check results.
5. Confirmation no out-of-scope files were touched.
6. Ship-log entry as raw markdown — three sections (one per backlog item) marked **SHIPPED**.

**Protocol:** anchored Edit only on existing files. New test files are fine to Write. If the Linux mount shows mid-write garbage, report it but don't fix unless it blocks tests. After ship: `FEATURE_FLAG_CONFIDENCE_TIER` is safe to re-enable in production via Railway env var.
```

### After Cursor reports done

1. Re-read Cursor's report for any deviations from the dispatch.
2. Integrate the three ship-log entries into `docs/BACKLOG.md` (anchored Edit appending after the last entry).
3. Flip the OPEN status headers on #47/#48/#49 to RESOLVED.
4. Update `docs/STATE.md` with a new top entry capturing the close.
5. Operator runs `git status` + commit + push. Railway redeploys.
6. Operator (with you) re-verifies via `Invoke-RestMethod` smoke + the four adversarial checks against production. If clean, CT flag can re-enable.
7. Once CT flag is re-enabled and verified, Lane 4 (P2.OBS.1) becomes safe to dispatch.

---

## §5 — Lane 2: P2.HOME.1 — `DISCLOSURE_WORD` consistency on `/home` (Cursor — small, bounded)

**Why this lane:** Spotlight cards on `/home` still use the literal `Spotlight` badge in the Jinja template. The renderer module constant `DISCLOSURE_WORD = "Sponsored"` in `app/chat/disclosure_render.py` is the canonical source of truth for the chat path; aligning the homepage badges to the same constant prevents drift between channels. Filed in the Lane S2 ship-log; tracked as P2.HOME.1 in the Phase 2 spec.

### Dispatch prompt — paste into Cursor

```
**Lane:** P2.HOME.1 — `DISCLOSURE_WORD` consistency on `/home`.

**Estimate:** 15–25 min.

**Files in scope:**
1. `app/templates/home.html` (Jinja template — find the Spotlight badge markup).
2. `app/home/queries.py` or wherever the Spotlight card data is assembled (verify the badge text isn't hardcoded there).
3. Maybe `app/static/styles/home.css` if the badge has Spotlight-specific styling that should generalize to "Sponsored".

**Recommended approach:** Import `DISCLOSURE_WORD` from `app.chat.disclosure_render` and use it as the badge text. Don't hardcode `"Sponsored"` — reference the constant.

**Out of scope:** the chat-path disclosure renderer (already correct). Anything outside `/home` template + queries.

**Tests:**
- Add a test in `tests/test_home_queries.py` (or new file `tests/test_home_disclosure_word.py`) that asserts the rendered Spotlight card markup contains `DISCLOSURE_WORD` and not the literal `"Spotlight"`.
- Run `python -m pytest tests/test_home_queries.py tests/test_home_queries_lane_a.py -q` to verify no regression.

**Report:** anchored diff summary, new test added, pytest line, ship-log markdown entry.
```

---

## §6 — Lane 3: P2.BL.45 — `verification_method` CHECK constraint expansion (Cursor — small, schema-touching)

**Why this lane:** The enrichment ingest script (`scripts/ingest/ingest_enrichment_csv.py`, shipped 2026-05-08) compresses operator vocab (`phone_call`, `in_person`, `web_form_submission`, `email_confirmation`) into the existing 5-value DB enum (`manual`, `scraper`, `owner_confirmed`, `npi_registry`, `none`) via a lossy mapper. Phone vs in-person verification becomes indistinguishable in the DB. This lane drops the mapper by expanding the CHECK constraint to allow the operator vocab natively.

### Dispatch prompt — paste into Cursor

```
**Lane:** Backlog #45 — Expand `verification_method` CHECK constraint to preserve operator audit fidelity.

**Estimate:** 30–45 min.

**Files in scope:**
1. New `alembic/versions/<sha>_expand_verification_method_constraint.py` — drops the existing CHECK and adds the new one.
2. `app/db/models.py` — update the `Provider.verification_method` mapped column comment / docstring (the column itself is `String(32)`; no type change needed).
3. `scripts/ingest/ingest_enrichment_csv.py` — drop the `_VERIFICATION_METHOD_DB_MAP` dictionary; write operator vocab values directly to `Provider.verification_method`.
4. `templates/enrichment/README.md` — update if any column documentation references the old mapping.
5. `tests/test_enrichment_ingestion.py` — update the fixture/assertion to expect operator vocab values in the DB after ingest.

**Migration shape (read `alembic/versions/f7e8d9c0b1a2_add_verification_and_audience_columns.py` for the existing pattern):**

```python
def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_providers_verification_method", type_="check")
        batch_op.create_check_constraint(
            "ck_providers_verification_method",
            sa.text(
                "verification_method IS NULL OR verification_method IN ("
                "'manual', 'scraper', 'owner_confirmed', 'npi_registry', 'none', "
                "'phone_call', 'in_person', 'web_form_submission', 'email_confirmation'"
                ")"
            ),
        )

def downgrade() -> None:
    # Reverse — but note: any rows with the new vocab values must be remapped before
    # the downgrade can succeed, or the constraint creation will fail.
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_providers_verification_method", type_="check")
        batch_op.create_check_constraint(
            "ck_providers_verification_method",
            sa.text(
                "verification_method IS NULL OR verification_method IN ("
                "'manual', 'scraper', 'owner_confirmed', 'npi_registry', 'none'"
                ")"
            ),
        )
```

**Out of scope:** any other migration. Don't touch the audience_signal CHECK or any unrelated column.

**Verification:**
- `python -m alembic upgrade head` (clean upgrade against fresh SQLite)
- `python -m alembic downgrade -1` (clean downgrade — note the downgrade caveat above; if any test rows have new vocab values, the test should clean them first)
- `python -m alembic upgrade head` (re-upgrade clean)
- `python -m pytest tests/test_enrichment_ingestion.py -q` — must still hit 16 passed (or higher if you added tests for the new vocab).
- Full suite: `python -m pytest -q` must still hit ≥ 1327 passed.

**Report:** migration file path, downgrade caveat note, new alembic head SHA, pytest line, ship-log markdown entry.
```

---

## §7 — Lane 4: P2.OBS.1 — disclosure-renderer observability instrumentation (Claude Code — multi-file)

**Why this lane (now safe after Lane 1 ships):** Per the Phase 2 spec §3, this is the highest-leverage instrumentation lane. Every downstream Phase 2 decision (HALT 3 close, X3 Tier 2 extension green-light, #39 audience A/B, Premier inventory open) depends on having structured per-render telemetry to read.

**Spec note from CC's audit yesterday:** `disclosure_renderer_spec.md` §7.2 currently suggests logging telemetry to `chat_logs.llm_tokens_used` as JSON. **Reject that suggestion** — it's a misuse of a typed numeric column and would pollute existing token-spend dashboards. The lane should add typed columns or a JSON column via a new migration instead.

### Dispatch prompt — paste into Claude Code

```
**Lane:** P2.OBS.1 — Disclosure-renderer observability instrumentation.

**Estimate:** 45–75 min. Multi-file: schema migration + renderer instrumentation + handler wiring + tests.

**Background:** When `FEATURE_FLAG_DISCLOSURE_RENDERER=true` runs in production, every render decision (regime selected, sponsor picked, tone allowlist pass/fail, eligibility gate result) needs to be logged to `chat_logs` so Phase 2 can audit hedge-leakage on HIGH rows, measure regime-selection accuracy against Backlog #39 audience-signal data, and gate Premier inventory open on real telemetry.

**The spec at `docs/maintainability/disclosure_renderer_spec.md` §7.2 currently suggests logging to `chat_logs.llm_tokens_used` as JSON — REJECT that approach.** It's a misuse of a typed numeric column. Instead, add a dedicated structured column.

**Files in scope:**
1. New `alembic/versions/<sha>_add_disclosure_render_telemetry_column.py` — adds `chat_logs.disclosure_render_decision` as a JSON column (or split into typed columns: `disclosure_regime VARCHAR(32)`, `disclosure_sponsor_id VARCHAR(64)`, `disclosure_tone_allowlist_passed BOOLEAN`, `disclosure_eligible BOOLEAN`). Operator's call — pick one approach and document why.
2. `app/db/models.py` — add the matching column(s) to `ChatLog`.
3. `app/chat/disclosure_render.py` — return a structured `RenderDecision` dataclass alongside the existing `SponsoredBlock` so the handler can log it.
4. `app/chat/tier3_handler.py` — capture the `RenderDecision` from `_maybe_render_sponsored_block` and pass it through to the chat_logs write.
5. `app/db/chat_logging.py` — extend the write to persist the new column(s).
6. `tests/test_disclosure_render.py` — add tests for the `RenderDecision` shape.
7. `tests/test_disclosure_render_integration.py` — add tests verifying the decision is persisted to `chat_logs` correctly.
8. `docs/maintainability/disclosure_renderer_spec.md` — update §7.2 to document the chosen approach (and explicitly note that logging to `llm_tokens_used` was rejected as a misuse).

**Out of scope:** the audience-signal column / Lane S3 work (already in production). The CT flag observability path (separate lane — file as P2.OBS.2 follow-up if it surfaces during this work).

**Verification:**
- `python -m alembic upgrade head` then `downgrade -1` then `upgrade head` (clean round-trip).
- `python -m pytest tests/test_disclosure_render.py tests/test_disclosure_render_integration.py -q` — must pass.
- Full suite ≥ 1327.
- Live smoke after deploy with `FEATURE_FLAG_DISCLOSURE_RENDERER=true`: query the chat, then verify the new column populates correctly via psql.

**Report:** migration file path, schema design choice (JSON column vs typed columns) with rationale, new test counts, pytest line, ship-log markdown entry, spec update summary.
```

---

## §8 — Lane 5: Operator enrichment sprint (operator-driven, parallel to engineering lanes)

**Why this lane runs in parallel:** Without enrichment data (`Provider.last_verified_at` populated for the top-queried businesses), every chat response that names a Provider currently has `confidence_hint = LOW` (because NULL last_verified_at = stale by definition). When CT flag re-flips after Lane 1, every Tier 2 LLM / Tier 3 response surfaces the `recommend calling to confirm` hedge for every Provider — that's UX-noisy. Enrichment populates `last_verified_at` for the top 50 businesses, moving them to HIGH or MEDIUM tier and reducing hedge spam.

**Tooling shipped 2026-05-08 (ready to use):**

- `templates/enrichment/business_enrichment_template.csv` — fill this out
- `templates/enrichment/README.md` — column-by-column documentation
- `scripts/ingest/validate_enrichment_csv.py --dry-run` — validates CSV before any DB writes
- `scripts/ingest/ingest_enrichment_csv.py --dry-run` and `--apply` — idempotent upsert

**Parallel ChatGPT lane — sponsor outreach** (already drafted at `docs/sponsor_outreach/cold_email_templates.md`). Operator can paste-and-send these to the priority categories during the enrichment sprint to start filling sponsor inventory.

### Operator workflow

1. Open `templates/enrichment/business_enrichment_template.csv` in Excel or a CSV editor.
2. Fill out 5–10 rows for the top-queried categories (start with restaurants, plumbers, HVAC).
3. Save as e.g. `enrichment_2026-05-10.csv` (don't overwrite the template).
4. Validate (no DB writes):
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.ingest.validate_enrichment_csv .\enrichment_2026-05-10.csv
   ```
5. Dry-run ingest (no DB writes):
   ```powershell
   $env:DATABASE_URL = "<Railway Postgres URL>"
   .\.venv\Scripts\python.exe -m scripts.ingest.ingest_enrichment_csv .\enrichment_2026-05-10.csv --dry-run
   Remove-Item env:DATABASE_URL
   ```
6. Review the dry-run log; if clean, apply:
   ```powershell
   $env:DATABASE_URL = "<Railway Postgres URL>"
   .\.venv\Scripts\python.exe -m scripts.ingest.ingest_enrichment_csv .\enrichment_2026-05-10.csv --apply
   Remove-Item env:DATABASE_URL
   ```
7. Verify in production via a chat smoke that hits an enriched Provider — confidence should now be HIGH/MEDIUM and (with CT flag on) the hedge should NOT appear.

### Sponsor outreach in parallel

Open `docs/sponsor_outreach/cold_email_templates.md`, pick a category, copy the cold email, replace `[Business Name]` and add 1–2 personalizations, send from a personal email address. Track responses in a spreadsheet.

---

## §9 — Risks and gotchas

**Anchored to today's discoveries — all verified in production:**

1. **Linux mount staleness.** The Cowork bind sometimes serves stale or truncated views of files mid-write. Windows-side files (Read tool via Windows path) are authoritative. If `git status` shows "No commits yet" or files appear truncated mid-line, re-verify via Windows path before assuming corruption.
2. **PowerShell + `curl.exe --data-binary $body` mangles JSON.** Use `Invoke-RestMethod -Body '{"query":"..."}'` for any chat-API smoke. The runbook is corrected; if you copy from any older doc that uses curl, swap it.
3. **Cache pollution survives flag flips for up to 7 days.** `LlmResponseCache` TTL is `DEFAULT_TTL_DAYS = 7`. After any flag flip or prompt change, run `scripts/cleanup/purge_llm_cache.py --apply` (with `DATABASE_URL` set) to flush.
4. **Bare-form severe typos return None in entity matcher.** That's the existing `_best_score_padded` F6 early-return path. Use the realistic chat shape `phone for X` for severe-typo verification — bare typos alone don't fire the WRatio scorer.
5. **HALT 3 status is unverified.** Strategy doc treats HALT 3 close as a Phase 1 deliverable + a precondition for Premier inventory open. The 2026-05-09 STATE entry does NOT name HALT 3 as completed. If a Phase 2.5 lane ships before HALT 3 is closed, you may have a hidden gate. Recommend auditing HALT 3 status before locking the Phase 2.5 calendar.
6. **CT flag is OFF — keep it off until Lane 1 ships.** Flipping it now reproduces #47/#48/#49 in production immediately. The smoke-check doc at `docs/maintainability/backlog_46_smoke_check_queries.md` has 30 queries to run after Lane 1 lands and CT flag re-enables — comprehensive verification surface.

---

## §10 — When to wrap or hand off

**Sign you can wrap this session cleanly:**

- Lane 1 (#47/#48/#49) shipped, verified in production, CT flag re-enabled with no hedge regressions on the smoke catalog.
- Lane 2 (P2.HOME.1) shipped or explicitly deferred.
- Lane 3 (P2.BL.45) shipped or explicitly deferred.
- BACKLOG.md and STATE.md integrated for all shipped lanes.
- Operator has explicit guidance for Lane 4 (P2.OBS.1) and Lane 5 (enrichment) for the next session.

**Sign you should hand off to a fresh agent:**

- Three or more substantive exchanges into the session and you've crossed ~70% context (rough rule of thumb).
- About to start a major new strategic direction (e.g. distribution channel kickoff, visitor-mode UI design, Phase 3 planning).
- The current conversation has accumulated more than ~10 agent reports and you're starting to lose track of which lanes shipped which fixes.

**How to hand off:** write a fresh `docs/SESSION_HANDOFF_2026-05-<NN>.md` following the same structure as `docs/SESSION_HANDOFF_2026-05-09.md` — §0 boot sequence, §1 one-paragraph summary, §3 production state with the verification-chain narrative if anything went sideways, §4 priority-ordered backlog, §5 next steps with pointers to whatever doc anchors the new dispatch playbook (could be this one, or a fresh one if the lane sequence has changed materially).

---

*This playbook is meant to evolve. After each Phase 2 lane lands, update §3 with the new sequence and add the next lane's dispatch prompt. The pattern is: handoff doc captures "what happened"; this playbook captures "what to do." Keep them in lockstep.*
