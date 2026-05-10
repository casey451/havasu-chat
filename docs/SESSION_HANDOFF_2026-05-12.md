# Session Handoff — 2026-05-12 (fresh-session entry point)

> **⚠️ STRATEGIC PIVOT LANDED THIS SESSION.** Before reading further, read **`docs/STRATEGY_PIVOT_2026-05-12.md`** end-to-end (~5 min). The product is pivoting from chat-first concierge to structured local directory + chat as one of three front doors. That pivot doc is the authoritative strategic-priority signal — when this handoff or `docs/BACKLOG.md` disagrees with it, the pivot doc wins.

**Audience:** the agent picking up where the 2026-05-12 session left off. Today's session shipped one substantive ticket — #64 (confabulation harness v2: emit `category` / `activity_category` in `per_row.csv` + config-driven anchor allowlist) — closing the spec-vs-toolchain gap surfaced by yesterday's HALT 3 close-out template ambiguity-resolution lane. Plus the lockstep alignment of `halt3_closeout.md` to the v2 harness shape. **Then** the session reviewed an external strategic deep-research report (`uploads/deep-research-report.md`) and locked a directory-first pivot — see `STRATEGY_PIVOT_2026-05-12.md`. Three commits, one substantive (`aa3abd4`), one close-out (`426f992`), one handoff (`eb6f2e1`); plus a fourth pending (pivot doc + this handoff update).

**Read time:** ~3 minutes for this doc.

**Companion docs:**

- `docs/SESSION_HANDOFF_2026-05-11.md` — yesterday's entry point (HALT 3 hardening + #64 filing + #65 design narrative)
- `docs/SESSION_HANDOFF_2026-05-10.md` — Phase 2 follow-up cluster + sponsor outreach surface narrative
- `docs/STATE.md` — canonical "where is the project right now"
- `docs/BACKLOG.md` — ship logs + open tickets (entries up through #65)
- `docs/maintainability/dispatch_protocol.md` — 12-rule reference card
- `docs/maintainability/dispatch_channels.md` — channel-pick playbook + 7 common gotchas
- `docs/maintainability/halt3_closeout.md` — close-out template, now aligned to harness v2 shape

---

## §0 — Boot sequence

1. **Read `docs/STRATEGY_PIVOT_2026-05-12.md` end-to-end first (~5 min).** The product strategy changed materially this session. This handoff and BACKLOG priorities are stale relative to the pivot doc.
2. Read this doc end-to-end (~3 min) for ship details + state confirmation.
3. Skim `docs/SESSION_HANDOFF_2026-05-11.md` if you want the prior-day narrative (pre-pivot).
4. Confirm repo state: `git log --oneline -6` should start with the pivot-doc commit (pending at session close) sitting on **`eb6f2e1`** (handoff doc) on **`426f992`** (#64 close-out) on **`aa3abd4`** (#64 ship) on **`4f9a322`** (yesterday's STATE close-out).
5. Pytest verification (operator-side per Rule 7): `python -m pytest -q` should hit **1422 passed** (no test changes from the pivot doc).
6. Check Railway: production deployed revision should still be at or behind `54a56b1` — runtime behavior unchanged since then. All 10+ commits since `54a56b1` are doc-only, test-only, or eval-tooling-only.
7. Ask Casey which thread he wants to start with — §7 below has been rewritten around the pivot.

## §1 — One-paragraph project summary

havasu-chat is a local concierge chat product for Lake Havasu City, AZ. Hava (the chat persona) answers questions about local businesses, events, and activities in 1–3 sentences. Production is at https://havasu-chat-production.up.railway.app, deployed via Railway from `main`. Phase 1 (trust pipeline) shipped 2026-05-09 morning. Phase 2 first-week (Lanes 1–4 + sponsor outreach surface) shipped 2026-05-09 evening through 2026-05-11. The project is currently in a forward-looking / hardening posture: no production runtime changes for several days as the team works on (a) operator enrichment sprint readiness, (b) HALT 3 close-out tooling and pre-investigation, and (c) Phase 2.5 third-party-source rate-limiter design. The flag-flip cascade (`FEATURE_FLAG_DISCLOSURE_RENDERER=false → true`) is gated on enrichment populating ≥1 Sponsor + matching Provider rows.

## §2 — Final state at session close (2026-05-12)

- **Repo `main` HEAD:** **`426f992`** — `docs(BACKLOG+STATE+halt3): close out #64 + halt3 v2 alignment`. Sits on `aa3abd4` (#64 harness v2 ship). Local main is **2 commits ahead of origin/main** at session close — push when convenient.
- **Pytest:** **1422 passed** (1417 → 1422; +5 net-new test methods + 1 in-place 7→9 column header pin extension in `tests/test_confabulation_report.py`).
- **Alembic head:** `d6e7f8a9b0c1` (Lane 4 disclosure-render telemetry columns); unchanged.
- **Feature flags:** `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (HOLD), `FEATURE_FLAG_CONFIDENCE_TIER=true`. Audience-signal persistence: AUTOMATIC.
- **Production runtime:** unchanged since `54a56b1`. The eval surface at `app/eval/confabulation_report.py` and `scripts/confabulation_eval.py` is harness/reporter code, not on the chat-route runtime path — #64's changes do not deploy to production behavior.
- **Working tree:** clean at session close. No parallel lanes in flight.

## §3 — What shipped on 2026-05-12

1. **`aa3abd4`** — `feat(eval): #64 emit category + activity_category in per_row.csv + config-driven anchor allowlist`. Confabulation harness v2 for HALT 3 close-out tooling. `app/eval/confabulation_report.py::write_per_row_csv` now emits 9 columns with `category` (Provider) and `activity_category` (Program) inserted after `row_name`. The 2-name regression-anchor allowlist moved from inline at the previous `:167-173` to a module-top constant `_DEFAULT_REGRESSION_ANCHORS = ("Aqua Beginnings", "Grace Arts Live")` with governance comments referencing `halt3_definition.md` §6; `write_summary_md(..., *, anchors=...)` accepts an optional tuple override. `scripts/confabulation_eval.py::_probe_name_map()` now returns `dict[str, dict[str, str | None]]`; `_enrich_for_reports` fills `category` / `activity_category` by row type; new `--anchor-set-file PATH` CLI arg reads newline-delimited names with `#`/blank skipping. Ship channel: Cursor (after a v1 brief to CC halted at step-0; see §5 lesson). +5 net-new tests in `tests/test_confabulation_report.py` + minimal fixture updates in `tests/test_confabulation_eval_script.py`.
2. **`426f992`** — `docs(BACKLOG+STATE+halt3): close out #64 + halt3 v2 alignment`. BACKLOG #64 status flip + ship-log paragraph. STATE.md HEAD/pytest/commits-chain update + new "Recently shipped" entry. `halt3_closeout.md` aligned to v2 harness shape — §2 per_row.csv schema (9 cols), §3.2 anchor-set composition + governance + per-category methodology (read columns directly, no DB join needed), §3.3 per-row offender ranking source (9-col header pin).
3. **`eb6f2e1`** — `docs(handoff): add 2026-05-12 session handoff entry point`. This doc, in its initial pre-pivot form.
4. **Pending commit (pivot)** — `docs(strategy): pivot to directory-first + chat-as-one-of-three-doors`. New `docs/STRATEGY_PIVOT_2026-05-12.md` (~210 lines) authored after Casey reviewed an external strategic deep-research report (`uploads/deep-research-report.md`) and locked four strategic answers: directory-first vision is the real target, bootstrapped/revenue-funded, Casey-as-primary-salesperson, pivot-now (pause enrichment as-scoped, redirect operator effort, build category pages). V1 directory category locked: Home Services. This handoff doc updated in lockstep with §0/§3/§7 reflecting the pivot. **Read the pivot doc first** when booting — its §6 backlog re-prioritization supersedes BACKLOG.md priority signals until further notice.

**Deferred / not shipped:**

- Per-category breakdown section in `summary.md` (optional in #64 ticket — close-out actor can derive from `per_row.csv`).
- `relay/halt3-anchor-set.txt` (operator-authored at HALT 3 close-out time if using `--anchor-set-file`).

## §4 — Dispatch channels

Five channels in active rotation; see `docs/maintainability/dispatch_channels.md` for the canonical playbook + 7 common gotchas.

- **Cursor** — focused-file edits, schema migrations. Today's #64 implementation lane after CC halted on the column-name issue. Took the multi-file lane cleanly with a heavily prescriptive brief.
- **Claude Code** — multi-file refactors, audits. Today: dispatched the v1 #64 brief; CC halted appropriately at step-0 catching the `track_kind` column-name error (this is exactly the right behavior).
- **ChatGPT** — non-file work; not used today.
- **General-purpose sub-agent** — direct dispatch via the Task tool; not used today.
- **Yourself** — direct file tools for BACKLOG/STATE/halt3_closeout updates after the Cursor ship landed.

**Channel-pick wrinkle today:** the v2 brief was authored for CC (multi-file lane fits CC's strengths per the rubric) but Casey routed to Cursor instead. Worked fine — Cursor handled the multi-file scope cleanly with a heavily prescriptive brief (line numbers, suggested signatures, exact column ordering, enumerated test cases). Worth absorbing: a sufficiently prescriptive brief flattens the channel-fit difference for bounded multi-file scope.

## §5 — Working agreements + lessons absorbed

Canonical reference: `docs/maintainability/dispatch_protocol.md` (12 rules). All rules in force; no additions today.

**Two forensic notes worth elevating from today's #64 lane:**

1. **Schema-adjacent sub-agent investigations should ground column names against `app/db/models.py` directly, not just consuming code paths.** Yesterday's halt3 ambiguity-resolution sub-agent surface-read `track_kind` from doc/code text and propagated it into BACKLOG #64's description. The column doesn't exist on `Program` — actual column is `activity_category`. CC caught it at step-0 of the v1 implementation lane via the brief's "trust the source" clause; v2 brief shipped under the corrected name. The cure is a process discipline: when authoring a forensics report that names DB columns, the report should cite the model file at line offset, not just the consuming function. (See BACKLOG #64 ship-log, STATE.md "Recently shipped" §1, for the full forensic.)

2. **Don't trust a single Glob for "does this file exist."** Pre-dispatch source-surface check on #64 used `**/test_confabulation*.py` to look for an existing test file; Glob returned "No files found" and the v2 brief said "no test file exists, author one." The file did exist with 6 pre-existing tests. Cursor caught the false negative by reading the actual tests directory and extending in place rather than authoring fresh. The cure: pair Glob with a `Read` of a likely path (e.g. `tests/test_confabulation_report.py` directly) or a `Grep` for distinctive content from the suspected file (e.g. `Grep "write_per_row_csv" --type py`). The Glob result alone is unreliable for non-existence claims.

These two lessons are also captured in the BACKLOG #64 ship-log and STATE.md "Recently shipped" entry, but elevating them here makes them visible at session boot for the next agent.

## §6 — Open backlog at session close

### Truly open (could ship anytime)

- **#39** — thread audience signal into placement-regime selection (DEFERRED to Phase 2; precondition: 4–6 weeks of `chat_logs.audience_signal` data).
- **#62** — trade-superlative scoring: alias-resolution vs disambiguation behavior (P3; forward-looking, gated on catalog density from enrichment sprint).
- **#65** — Phase 2.5 third-party-source rate-limiter implementation (DESIGN SHIPPED 2026-05-11; implementation OPEN, MEDIUM, gated on the 7 §8 open questions in `docs/maintainability/phase2_5_rate_limiter_design.md` + Casey's decision on Phase 2.5 launch concurrency).
- Backlog #2 — `_time_bucket_first_hits` and broad `span` (Phase 2 candidate, pre-Phase-1).
- Backlog #18 — Repo hygiene & documentation hierarchy (PM phases A–D, pre-Phase-1).

### Spec-resolution work (no ticket; sub-agent forensics + apply edits pattern)

- **Smoke catalog ambiguity resolution** — 6 open spec questions in `docs/maintainability/post_enrichment_smoke_catalog.md`: regime-naming spec mismatch, category alignment of candidate sponsors, regime B suppression on zero-organic, cache key composition, multi-sponsor rotation determinism, CT2.B ship status. Same shape as yesterday's halt3 ambiguity-resolution lane. Sub-agent dispatchable; no operator round-trip.

### Strategic — gates Phase 2.5

- **#53** — HALT 3 multi-week work-to-close. Definition recovered (`docs/maintainability/halt3_definition.md`); close-out template (`docs/maintainability/halt3_closeout.md`) now aligned to harness v2 shape (per #64 ship today). The three numeric bands (gating-rate, anchor-regression, catalog-flagging) are still placeholders awaiting the baseline confabulation harness run. Sequencing unchanged: enrichment sprint → flag flip → ≥1 week production traffic dwell → harness baseline run → set bands → run negative-set extension → close-out → unblock P2.PREM.1.

### Operator-driven (not agent dispatchable)

- **50-business enrichment sprint** for top-queried categories (restaurants, plumbers, HVAC, pool service, boat repair, urgent care, auto repair). Toolchain shipped 2026-05-08 + 2026-05-09; operator-facing playbook at `docs/sponsor_outreach/enrichment_sprint_runbook.md`. Casey fills CSVs → validates → dry-runs ingest → applies.
- **HALT 3 close-out multi-week sequence** — see #53 above.

## §7 — What to do first (post-pivot)

Read `docs/STRATEGY_PIVOT_2026-05-12.md` first. Its §8 lists 7 open Casey-owned decisions that block the next 2–3 days of work:

1. Lock the canonical category taxonomy (12 categories or refined cut)
2. `Place` model scope for V1 (full or defer to Phase 2)
3. Account-lite auth provider choice (SendGrid / Resend / Postmark)
4. Map provider choice (Mapbox / Leaflet+OSM / Google)
5. Pricing finalization (cold-pitch ground-truth before locking)
6. Sponsor package SKU naming
7. `PROJECT.md` and `HAVA_CONCIERGE_HANDOFF.md` rewrites (defer full rewrite; add pivot notices for now)

**Recommended first session post-pivot:** work through decisions 1–4 with Casey via `AskUserQuestion`. Once locked, the next two weeks of work are:

- Schema additions (`Category` model, `category_id` FK on Provider/Program, `Place` model if scoped in, `attributes` JSON on Provider) — Cursor lane, anchored Edits to `app/db/models.py` + Alembic migration
- Add pivot notices to `PROJECT.md` and `HAVA_CONCIERGE_HANDOFF.md` (small Edits)
- Re-scope enrichment sprint operator workflow to feed the new structured fields

**Alternative starting threads** (for sessions where Casey isn't available for the open decisions):

- **#65 rate-limiter implementation prep.** Now more urgent under the pivot — directory hits Places API more than chat ever did. Casey-owned §8 questions still gate full ship, but P1 design is clear enough to start the implementation lane in parallel.
- **#18 repo hygiene continuation.** Ongoing; relevant under either vision.

**Threads to NOT start without Casey explicit go-ahead** (these were promoted in the pre-pivot handoff but are now deprioritized — see pivot doc §6):

- ~~Smoke catalog ambiguity resolution~~ — chat-only concern, deprioritized
- ~~Enrichment sprint kickoff as originally scoped~~ — needs re-scoping for new directory shape first
- ~~HALT 3 close-out pre-investigation~~ — chat-surface gating, deprioritized

## §8 — Reference docs and operational knowledge

- **Project state:** `docs/STATE.md`
- **Backlog:** `docs/BACKLOG.md`
- **Dispatch protocol (12 rules):** `docs/maintainability/dispatch_protocol.md`
- **Dispatch channel playbook + 7 gotchas:** `docs/maintainability/dispatch_channels.md`
- **Phase 2 strategic plan:** `docs/maintainability/phase2_lane_decomposition.md`
- **HALT 3 definition + close-criteria:** `docs/maintainability/halt3_definition.md`
- **HALT 3 close-out template (v2-aligned 2026-05-12):** `docs/maintainability/halt3_closeout.md`
- **Post-enrichment smoke catalog (6 open spec Qs):** `docs/maintainability/post_enrichment_smoke_catalog.md`
- **Phase 2.5 rate-limiter design (7 open §8 Qs):** `docs/maintainability/phase2_5_rate_limiter_design.md`
- **LLM-mock pattern (project standard):** `docs/maintainability/llm_mock_pattern.md`
- **Confabulation eval runbook:** `docs/confabulation-eval-runbook.md`
- **Phase 1 deploy runbook:** `docs/maintainability/phase1_deploy_runbook.md`
- **Smoke catalog (39 queries, UTF-8 patched):** `docs/maintainability/backlog_46_smoke_check_queries.md`
- **Sponsor outreach surface:** `docs/sponsor_outreach/cold_email_templates.md`, `cold_email_variants_2026-05-09.md`, `reply_handlers.md`, `post_launch_comms.md`, `enrichment_sprint_runbook.md`, `sponsor_quick_reference.md`
- **End-user FAQ:** `docs/user_facing/hava_user_faq.md`

---

*This handoff supersedes `SESSION_HANDOFF_2026-05-11.md` for purposes of "where is the project right now" — the body of the older doc remains valid for prior-session narrative context. Next agent: read THIS doc, skim 2026-05-11 if you want yesterday's narrative, then dispatch.*
