# Session Handoff — 2026-05-10 (fresh-session entry point)

**Audience:** A fresh Cowork primary picking up the havasu-chat project after the 2026-05-09 marathon session that shipped the entire Phase 2 first-week dispatch playbook.

**Read time:** 3 minutes for this doc; ~5 minutes for full bootstrap (boot sequence in §0).

**Companion docs:**

- `docs/SESSION_HANDOFF_2026-05-09.md` — Phase 1 close + Phase 2 kickoff (yesterday morning)
- `docs/SESSION_HANDOFF_2026-05-09_evening.md` — Lane 1 / Lane 2 / HALT 3 audit + the Phase-2-first-week-shipped addendum at the top
- `docs/STATE.md` — canonical "where is the project right now"
- `docs/maintainability/phase2_first_week_dispatch.md` — playbook for Lanes 1–5 (1–4 done, 5 operator-driven)
- `docs/maintainability/phase2_lane_decomposition.md` — broader 17-lane / 5-phase strategic plan
- `docs/maintainability/halt3_definition.md` — recovered HALT 3 spec; gates Phase 2.5
- `docs/sponsor_outreach/cold_email_variants_2026-05-09.md` — drafted cold-email variants for enrichment sprint

---

## §0 — Boot sequence

1. Read this doc end-to-end (~3 min).
2. Skim `docs/SESSION_HANDOFF_2026-05-09_evening.md` top addendum for the lessons-learned narrative (~2 min).
3. Verify production hasn't drifted: `python -m pytest -q` should hit **1348 passed**.
4. Confirm repo state: `git log --oneline -15` should start with `24abe82` (Lane 4 P2.OBS.1) — or whatever the latest is if the session has started shipping already.
5. Check Railway: production should be on `24abe82` or later. Dashboard → app service → Variables — confirm `FEATURE_FLAG_DISCLOSURE_RENDERER=false`, `FEATURE_FLAG_CONFIDENCE_TIER=true`.
6. Ask the operator (Casey) which thread he wants to start with. §6 below names three viable starting points.

## §1 — One-paragraph project summary

havasu-chat is a local concierge chat product for Lake Havasu City, AZ. Hava (the chat persona) answers questions about local businesses, events, and activities in 1–3 sentences. Production is at https://havasu-chat-production.up.railway.app, deployed via Railway from main branch. Phase 1 (trust pipeline — confidence tiers, disclosure renderer, audience signal logging, half-sprint UI data correctness) shipped 2026-05-09 morning. Phase 2 first-week (Lanes 1–4 — entity matcher cross-category guard, /home DISCLOSURE_WORD consistency, verification_method CHECK expansion, disclosure-renderer observability instrumentation) shipped 2026-05-09 late evening. Phase 2 mid-week and Phase 2.5 (Premier inventory open) are next, gated on operator enrichment sprint and HALT 3 close-out.

## §2 — Final state at last session close (2026-05-09 ~21:00 PT)

- **Repo `main` HEAD:** `24abe82` (Lane 4 P2.OBS.1) on top of `3c40ff4` (BACKLOG #55) on top of `1749675` (Lane 3) on top of `130f8ad` (Phase A docs) on top of `913e790` (revert) on top of the keystone chain `dd484a0`/`db718ac`/`8c5d008`/`489915f`/`d6cd782`. **Run `git log --oneline -15` to verify the chain.**
- **Pytest:** 1348 passed, 6 subtests passed.
- **Alembic head:** `d6e7f8a9b0c1` (Lane 4 disclosure-render telemetry columns); clean linear history.
- **Feature flags:** `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (HOLD until enrichment lands ≥1 Sponsor + matching Provider rows); `FEATURE_FLAG_CONFIDENCE_TIER=true` (verified mid-session). Audience-signal persistence: AUTOMATIC.
- **LlmResponseCache:** flushed twice during 2026-05-09; current entries are in #49 raw-text format (post-`strip_soft_suggest`, no phone+hedge baked in).
- **chat_logs telemetry columns:** four new nullable columns (`disclosure_regime`, `disclosure_sponsor_id`, `disclosure_tone_allowlist_passed`, `disclosure_eligible`) live in production but dormant (renderer flag is OFF; columns will populate when flag flips post-enrichment).

## §3 — Dispatch channels available

You have **four channels** for delegating work. The operator (Casey) is at the keyboard for paste-based channels.

### Cursor — focused-file edits

Best for: single-file or few-files surgical edits, schema migrations, ops scripts, anything bounded with precise scope.
Pattern: write a self-contained dispatch prompt → operator pastes into a fresh Cursor chat → Cursor returns text report → operator pastes report back to you for review/integration.
Strengths: precise, anchored Edit-friendly, good at "do exactly this and report back."
Watch for: occasionally ships pragmatic deviations from the dispatch and reports them at the end. Re-read for "deviation" callouts before integrating. Sometimes adds ship-log entries to BACKLOG.md directly — fine, just verify the format.

### Claude Code — heavy multi-file lanes

Best for: multi-file refactors, audit lanes, comprehensive test suite generation, architectural investigations.
Pattern: same as Cursor — operator pastes prompt; CC returns text report.
Strengths: handles multi-file scope without losing the thread. Good at "investigate this and propose a fix" lanes. Strong at producing comprehensive test coverage.
Watch for: may report assumptions in the text. Verify against reality.

### ChatGPT — non-file research, drafting, brainstorming

Best for: anything that doesn't need codebase access — sponsor outreach drafts, adversarial input brainstorms, market research, copy editing, comparative analysis.
Pattern: same paste-based; ChatGPT returns text; you save useful artifacts to file via the Write tool.
Cannot: read codebase, modify files, run tests.
Strengths: fast, no file access overhead. Good at structured creative work.

### General-purpose agent — direct dispatch via your `Agent` tool

Best for: parallel verification lanes, code reviews, voice-battery-style adversarial testing, doc audits, recovery investigations.
Pattern: dispatch directly via your `Agent` tool with a self-contained prompt; agent runs in its own context window and returns text. **No operator round-trip needed.**
Strengths: parallel work that doesn't block the main conversation. Has file tools + bash. Good at "go investigate X and report back."
Cost: burns context (the agent's report comes into your context). Use for genuinely useful parallel work.

## §4 — Working agreements (lessons learned, hard-won)

These are the protocol rules from the 2026-05-09 marathon. **Read before dispatching anything.**

1. **Anchored Edit over full-file Write on shared files.** Truncation incidents established this; held throughout 2026-05-09 with no collisions.
2. **Wait for the agent's text report before any `git add`.** The text report is the explicit "I'm done writing files" signal. Working-tree state alone is unreliable when an agent is mid-flight. **A parallel Cursor + Claude Code dispatch caused a `git add -A` to capture partial Lane 4 work in a Lane 3 commit, which broke Railway with multi-head alembic state. Recovery took 75 minutes.**
3. **Sequential dispatch when lanes touch overlapping files** (especially `app/db/models.py` and `alembic/versions/`). Parallel is fine for non-overlapping scopes (e.g., a chat-code lane in parallel with a docs/recovery agent investigation).
4. **PowerShell single-quoted bodies for `Invoke-RestMethod`.** Double-quoted strings interpolate `$variables` — Railway URLs with `$` in passwords get mangled. Use single quotes.
5. **`curl.exe --data-binary $body` mangles JSON.** Use `Invoke-RestMethod -Body '{"query":"..."}'` for any chat-API smoke. Same family as #4.
6. **Anchored Edit only on existing files.** Use Write tool for new files only.
7. **Linux-mount-staleness vs Windows-side authoritative.** The Cowork Linux bind sometimes serves stale or truncated views of files. Windows-side files (Read tool via `C:\Users\casey\projects\havasu-chat\...`) are authoritative; bash `cat`/`grep`/`wc` on `/sessions/.../mnt/havasu-chat/...` may show transient truncation.
8. **Sequential commits per lane.** Don't bundle Lane N's substantive code with Lane N+1's substantive code in one commit. Mix code + docs is fine; mixing two lanes' substantive code is the failure mode.
9. **Production cache purge via Railway web SQL.** Railway dashboard → Postgres tile → Data tab → Query → `DELETE FROM llm_response_cache;`. No `DATABASE_URL` env-var fiddling required (which has its own family of bugs — see runbook).
10. **Voice-battery / smoke catalog as the protocol-rule-5 verification step.** For any matcher / scorer / classifier change, dispatch an adversarial verification. The 39-query smoke catalog at `docs/maintainability/backlog_46_smoke_check_queries.md` is the proven instrument.
11. **Force-stop CC / Cursor before any cleanup.** If you need to reset the working tree mid-flight (`git checkout -- .` / `git clean -fd`), make sure no agent is still running — otherwise it'll re-clobber files behind you.

## §5 — Open backlog

### Truly open (could ship anytime)

- **#39** — thread audience signal into placement-regime selection (DEFERRED to Phase 2; precondition: 4–6 weeks of `chat_logs.audience_signal` data).
- **#50** — single-char queries match short entity prefix (LOW; pre-existing matcher behavior).
- **#51** — accent-bearing queries return HTTP 400 (LOW; pre-existing preprocessing).
- **#52** — trade-superlative queries return null where real entities exist (LOW; #47 over-conservatism).
- **#54** — dangling `relay/halt1-closure-final-lexicons.md` doc references (LOW; cosmetic doc-hygiene).
- **#55** — extend `confidence_tier._KNOWN_METHODS` for Lane 3's new operator vocab (LOW but **should ship before enrichment sprint completes** so the confidence-tier classifier doesn't under-rank operator-vocab rows).
- Backlog #2 — `_time_bucket_first_hits` and broad `span` (Phase 2 candidate, pre-Phase-1).
- Backlog #18 — Repo hygiene & documentation hierarchy (PM phases A–D, pre-Phase-1).

### Strategic — gates Phase 2.5

- **#53** — HALT 3 undefined on-tree → recovered into `docs/maintainability/halt3_definition.md` 2026-05-09 evening. **Multi-week work-to-close** (enrichment sprint completion → `FEATURE_FLAG_DISCLOSURE_RENDERER=true` flip → ≥1 week production traffic → confabulation harness baseline run → set the three bands → close-out doc → unblock P2.PREM.1).

### Operator-driven (not agent dispatchable)

- **50-business enrichment sprint** for top-queried categories (restaurants, plumbers, HVAC, pool service, boat repair, urgent care, auto repair). Toolchain shipped 2026-05-08:
  - `templates/enrichment/business_enrichment_template.csv`
  - `templates/enrichment/README.md`
  - `scripts/ingest/validate_enrichment_csv.py`
  - `scripts/ingest/ingest_enrichment_csv.py` (`--dry-run` and `--apply`)
  - Cold-email variants drafted at `docs/sponsor_outreach/cold_email_variants_2026-05-09.md`
  Casey fills CSVs, validates, dry-runs ingest, applies.

## §6 — What to do first (recommended starting points)

Pick whichever matches Casey's energy when he comes back. Three viable starts:

1. **Phase 2 mid-week lanes** per `docs/maintainability/phase2_lane_decomposition.md`. Dispatch the next lane in the 17-lane plan. Bounded engineering work; you have all four dispatch channels at your disposal. Ask Casey which lane to prioritize.

2. **Operator enrichment sprint kickoff.** Casey-driven; you're a thinking partner / structuring helper. Help Casey prioritize the first 5–10 businesses, draft validation runs, debug any toolchain issues. Unblocks Phase 2.5 / HALT 3 close eventually.

3. **#55 small fix** — extend `confidence_tier._KNOWN_METHODS`. Small Cursor lane (15–30 min). Hygiene before enrichment lands operator-vocab rows. Confidence-building ship if Casey wants a small win first.

If asked to recommend, my default ordering: option 3 first (small confidence-building ship + hygiene win) → option 1 next (substantive lane progress) → option 2 in parallel as Casey has bandwidth.

## §7 — Reference docs and operational knowledge

- **Project state:** `docs/STATE.md`
- **Backlog:** `docs/BACKLOG.md`
- **Phase 2 strategic plan:** `docs/maintainability/phase2_lane_decomposition.md`
- **Phase 2 first-week dispatch playbook:** `docs/maintainability/phase2_first_week_dispatch.md`
- **HALT 3 definition + close-criteria:** `docs/maintainability/halt3_definition.md`
- **Phase 8.8.6 spec (recovered):** `docs/phase-8-8-6-step-0-eval-harness-spec.md`
- **Confabulation eval runbook:** `docs/confabulation-eval-runbook.md`
- **Disclosure renderer spec (with §7.2 observability update):** `docs/maintainability/disclosure_renderer_spec.md`
- **Phase 1 deploy runbook:** `docs/maintainability/phase1_deploy_runbook.md` (corrected for `Invoke-RestMethod` and field-name bugs)
- **Smoke catalog (39 queries):** `docs/maintainability/backlog_46_smoke_check_queries.md`
- **Cold email templates + 2026-05-09 variants:** `docs/sponsor_outreach/cold_email_templates.md`, `docs/sponsor_outreach/cold_email_variants_2026-05-09.md`

---

*This handoff supersedes the "remaining work" section of `SESSION_HANDOFF_2026-05-09_evening.md` (which itself supersedes the same section of `SESSION_HANDOFF_2026-05-09.md`). The body of those older docs remains valid for historical context. The next agent reads this doc, skims the previous evening's addendum for lessons-learned narrative, then dispatches.*
