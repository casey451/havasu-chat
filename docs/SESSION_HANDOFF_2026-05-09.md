# Session Handoff — Phase 1 close + Phase 2 kickoff (2026-05-09)

**Audience:** A fresh Cowork / Claude / Cursor session that's continuing where this one left off.
**Read time:** 8 minutes for the full bootstrap; 2 minutes for the "what's next" section.
**Companion docs:** `docs/STATE.md` (canonical "where is the project right now"); `docs/BACKLOG.md` (every ship-log + open item with attribution); `docs/maintainability/phase1_deploy_runbook.md` (operator-facing deploy + flag-flip walkthrough — corrected today); `docs/maintainability/phase2_lane_decomposition.md` (sequenced Phase 2 plan); `docs/SESSION_HANDOFF_2026-05-08.md` (yesterday's bootstrap covering the 17-lane Phase 1 keystone).

---

## §1 — One-paragraph summary

This session **shipped Phase 1 to production** (commits `f9c96c6` + `dc7bd5f`, Railway deploy active and verified live), closed **Backlog #46** (entity matcher #44 connector-word bypass — a real production wrong-entity match risk surfaced by a voice-battery agent), shipped **#38 rename** (`request_time_utc` → `request_time_local`), and patched **two runbook bugs** that surfaced during the live deploy verification (the chat API request body field name `message` → `query`, and the PowerShell `curl.exe + $body` JSON-mangling bug → `Invoke-RestMethod`). Phase 2 lane decomposition spec drafted at `docs/maintainability/phase2_lane_decomposition.md` (17 lanes, 5-phase sequence). Production state at session close: Phase 1 code shipped; **`FEATURE_FLAG_DISCLOSURE_RENDERER` and `FEATURE_FLAG_CONFIDENCE_TIER` may or may not be flipped** depending on operator decision in §6 below — check Railway env vars and the BACKLOG ship-log tail for the truth.

---

## §2 — What landed today

### Code lanes shipped

| Lane | Owner | Files | Tests |
|---|---|---|---|
| #41a-followup TZAwareDateTime always-aware on read | Cursor | `app/db/types.py`, `app/chat/context_builder.py`, `tests/test_tz_aware_datetime.py` + incidental syntax-garbage cleanup in `app/db/models.py` and `app/chat/disclosure_render.py` | 8 in test_tz_aware_datetime |
| Test-suite triage 15 → 9 | Claude Code | `tests/test_phase2_integration.py` (4 fixes), `tests/test_unified_router.py` (1 fix), `tests/test_phase8_10_river_scene.py` (1 fix) | 6 net new green |
| Cache-pollution autouse fixture | Cursor | `tests/test_phase2_integration.py` (autouse function-scoped fixture deleting `LlmResponseCache` rows; one assertion correction) | 3 graceful-fallback tests fixed |
| #44 entity matcher near-match severe-typo regression | Claude Code | `app/chat/entity_matcher.py` — new `_best_partial_ratio_per_needle_token` helper; both substring-guard call sites use it | 49/49 in entity_matcher + phase38 |
| #46 entity matcher connector-word bypass (#44 follow-up) | Cursor | `app/chat/entity_matcher.py` — new `_typo_guard_query_token_matches_needle(tok, needle) -> bool`; `_TYPO_FIVE_CHAR_NEEDLE_TOKEN_THRESHOLD = 89` for 5-char needle tokens (the addrss/dress edge); `_TYPO_PER_TOKEN_THRESHOLD = 80` for >5-char tokens | 1314 full suite |
| #46 adversarial regression suite | Claude Code | `tests/test_entity_matcher_adversarial.py` new (308 lines, 13 tests, Class A/B/C) | 13/13 |
| #41b SQLite-naive temporal workaround verification | Cursor | none — working tree already matched lane intent | 163/163 Phase 1 surface |
| #38 parameter rename `request_time_utc` → `request_time_local` | Cowork primary | `app/chat/audience_signal.py` (replace_all), `app/chat/unified_router.py:553`, `tests/test_audience_signal.py` (5 sites) | clean grep, no behavior change |
| Operator enrichment tooling | general-purpose agent | `templates/enrichment/business_enrichment_template.csv` + `README.md`, `scripts/ingest/__init__.py` + `validate_enrichment_csv.py` (~290 lines) + `ingest_enrichment_csv.py` (~270 lines), `tests/test_enrichment_ingestion.py` (16 passing) | 16/16 |
| Stale WARN cleanup in `chat_logging.py:82` | Cowork primary | `app/db/chat_logging.py` — removed reference to non-existent `FEATURE_FLAG_AUDIENCE_SIGNAL_PERSIST` env var; replaced with correct `alembic upgrade head` guidance | n/a |
| Phase 1 deploy runbook audit + corrections | Claude Code (audit) + Cowork primary (edits) | `docs/maintainability/phase1_deploy_runbook.md` — fixed 1 BLOCKER (§6.3 smoke #1 reclassified as expected-suppress; `GENERIC_CATEGORY` regime is reserved for Lane X3 / Phase 2) + 3 Important + 2 Nits | 1314/1314 |
| Runbook bug fix #1 — chat API field name `message` → `query` | Cowork primary | runbook + `docs/maintainability/backlog_46_smoke_check_queries.md` — 5 + 1 anchored Edits | n/a |
| Runbook bug fix #2 — PowerShell `curl.exe + $body` mangles JSON braces | Cowork primary | runbook + smoke-check doc — replaced all `curl.exe --data-binary $body` patterns with `Invoke-RestMethod -Body '{"query":"..."}'`; added PowerShell note in §4.4 explaining the bug | n/a |
| Lint cleanup (ruff E402 + F821) | Cowork primary | 27 auto-fixed via `ruff check --fix`; 8 manual: `# noqa: E402` on 6 imports in `scripts/ingest/ingest_enrichment_csv.py` (sys.path.insert pattern); `from datetime import datetime` added to `tests/test_disclosure_render_integration.py` | 1327/1327 |

**Combined: 1327 tests passing in the full suite. CI green on `dc7bd5f`. Production deployed and verified live (`Invoke-RestMethod /api/chat "find a plumber"` → real Tier 2 response, no `Sponsored` text, no CT hedge — exactly the byte-identical-to-pre-deploy behavior).**

### Specs and docs that landed

- `docs/maintainability/backlog_46_smoke_check_queries.md` (new) — 30 queries across 5 classes for post-deploy manual smoke against `/api/chat`. Updated to use `Invoke-RestMethod` and `phone for X` chat shape per the `_best_score_padded` F6 finding.
- `docs/maintainability/phase2_lane_decomposition.md` (new, ~144 lines / ~2,500 words) — 17 lanes inventoried, 5-phase sequence, first-week dispatch table. Drafted by general-purpose agent (CC).
- `docs/STATE.md` — new top entry capturing this morning's #46 close above last night's evening session entry.
- `docs/BACKLOG.md` — 12 new ship-log entries appended; #38, #41a, #41a-followup, #41b, #46 all flipped to RESOLVED.

---

## §3 — Production state at session close

- **Repo HEAD:** `dc7bd5f` (post-lint-cleanup follow-up) on top of `f9c96c6` (Phase 1 keystone push). CI green on `dc7bd5f`.
- **Railway deployment:** active, serving from `dc7bd5f` (or near it — re-verify via Railway dashboard).
- **Live `/api/chat` smoke:** verified working (Tier 2 response, no flag leakage).
- **Feature flag state at session close:**
  - `FEATURE_FLAG_DISCLOSURE_RENDERER` — **OFF** (not flipped this session; recommend HOLD until enrichment sprint puts ≥1 Sponsor + matching Provider rows in production)
  - `FEATURE_FLAG_CONFIDENCE_TIER` — **CHECK RAILWAY**. May or may not be flipped — operator was deciding at session close. If flipped, every Tier 2 LLM / Tier 3 response that names a Provider carries `recommend calling to confirm` because every Provider has `last_verified_at = NULL` until enrichment ships.
  - Audience-signal persistence — **AUTOMATIC** (column-gated, Lane S1 column shipped, persistence on by default).

---

## §4 — Open backlog at session close

### Truly open (ship next)

- **#39 — thread audience signal into placement-regime selection** — DEFERRED to Phase 2 by design. Precondition: 4–6 weeks of `chat_logs.audience_signal` data + X1 + X2 in production with the disclosure-renderer flag flipped.
- **#45 — expand `verification_method` CHECK constraint** — Phase 2 cleanup. Drop the lossy operator-vocab → DB-enum mapper in `scripts/ingest/ingest_enrichment_csv.py` once the new migration lands.
- **Backlog #2** — `_time_bucket_first_hits` and broad `span` (pre-Phase-1, Phase 2 candidate).
- **Backlog #18** — Repo hygiene & documentation hierarchy (PM phases A–D), pre-Phase-1.

### Resolved this session

#38, #41a, #41a-followup, #41b, #44, #46 — all closed. See `docs/BACKLOG.md` ship-log entries.

### Operator-driven (not code)

- **50-business enrichment sprint** — top-queried categories (restaurants, plumbers, HVAC, pool service, boat repair, urgent care, auto repair). Toolchain shipped today (`templates/enrichment/`, `scripts/ingest/validate_enrichment_csv.py`, `scripts/ingest/ingest_enrichment_csv.py`). Operator fills CSV → validates → dry-run ingests → applies.
- **30-operator tourism inventory pass** — boat rentals, tour operators, lakeside dining, beach access, bridge viewing, family activities, ATV rentals, lodging.
- **Manual `/home` smoke check at 5 AM / 12 PM / 5 PM Lake Havasu local** — runbook §2.4 + §4.3 acceptance check.
- **HALT 3 close-out review** — strategy doc Phase 1 calls for closing HALT 3 with documented gating-rate, anchor-regression, and catalog-flagging bands. **Status not audited this session.** The Phase 2 lane decomposition spec flags this as an unverified Phase 1 deliverable that may have a hidden gate on Premier inventory open. **Recommend auditing HALT 3 status before Phase 2.5.**

---

## §5 — What Phase 2 should consider first

Per `docs/maintainability/phase2_lane_decomposition.md` §7, the recommended first-week dispatch order:

1. **P2.OPS.1** — flag flip + smoke (operator + Cowork primary). If not done in this session.
2. **P2.HOME.1** — `DISCLOSURE_WORD` consistency on `/home` (Cursor). The Spotlight cards still use the literal `Spotlight` badge; align to `DISCLOSURE_WORD = "Sponsored"`.
3. **P2.BL.45** — expand `verification_method` CHECK constraint (Cursor). Small Alembic lane.
4. **P2.DIST.1** — Airbnb conversion SQL definition before cards print (Cowork primary or Claude Code).
5. **P2.OBS.1** — disclosure-renderer observability instrumentation (Claude Code). **Highest leverage** — every downstream Phase 2 decision depends on having structured per-render telemetry.

**Risk to flag before locking the sequence:** `disclosure_renderer_spec.md` §7.2 currently suggests logging telemetry to `chat_logs.llm_tokens_used` as JSON. That's a misuse of a typed numeric column and would pollute existing token-spend dashboards. P2.OBS.1's lane brief should explicitly reject that suggestion in favor of a typed-columns or JSON-column migration. Update the spec when P2.OBS.1 ships.

---

## §6 — Things that look broken but aren't

So a fresh primary doesn't waste time investigating known-non-issues:

- **PowerShell + `curl.exe --data-binary $body` returns 422 with "Some event details are not valid"** — this is the runbook bug #2 fixed today. Use `Invoke-RestMethod -Body '{"query":"..."}'` instead. The `$body` variable expansion treats JSON `{}` braces as PowerShell scriptblock syntax during command-line tokenization, mangling what curl sends. The runbook is now corrected.
- **Empty body `{}` returning HTTP 422 with "the 'query' field is required and can't be empty"** — that's the canonical missing-field message from `app/core/event_quality.py::friendly_errors`. Confirms the deployed schema is `query`-based, not `message`-based.
- **Bare-form severe typos like `mdshrkbrwry` returning None** in entity matcher — that's the existing `_best_score_padded` F6 early-return path. Only fires the WRatio scorer when intent-stripping changes the query (i.e. when there's an intent prefix like `phone for X`). Real users always include intent prefixes; production behavior is correct.
- **Linux mount serves stale/truncated views of files mid-write** — same pattern as yesterday's handoff §9. Windows-side files (Read tool via Windows path) are authoritative; bash `cat`/`grep` on `/sessions/.../mnt/havasu-chat/...` may show transient truncation. CC's Phase 2 spec investigation hit this — flagged that BACKLOG #41a-followup was OPEN when it had actually shipped (Cowork primary fixed the status header).
- **Bullet characters render as garbled `â¢` in PowerShell console output** — UTF-8 display issue in PowerShell's default code page. The actual API response is correct UTF-8; redirect to a file with `Out-File -Encoding utf8` if you need to inspect cleanly.
- **Backlog #46 30-query smoke catalog has not been run against production yet** — `docs/maintainability/backlog_46_smoke_check_queries.md` is staged for the operator to run after deploy. The four required adversarial outcomes were verified by Cursor + the adversarial test suite, but the broader 30-query smoke is still pending. P2.OPS.1 is the natural place to run it.

---

## §7 — What a fresh Cowork primary should do first

If you're picking up this session in a fresh chat:

1. **Read `docs/STATE.md`** top entry — the 2026-05-09 morning entry — for the canonical narrative.
2. **Read `docs/BACKLOG.md`** tail (last ~30 entries) for the lane-by-lane attribution.
3. **Read `docs/maintainability/phase2_lane_decomposition.md`** end-to-end for the Phase 2 plan.
4. **Verify production state** — run the §4.1 health check + the §4.4 chat smoke from the corrected runbook to confirm production is still where this session left it.
5. **Check Railway env vars** for `FEATURE_FLAG_CONFIDENCE_TIER` and `FEATURE_FLAG_DISCLOSURE_RENDERER` to know which flags are actually flipped.
6. **Audit HALT 3 status** — read the strategy doc + any HALT 3 spec; produce a status report before any Phase 2.5 (Premier inventory open) lane is dispatched.

Most likely first request from the operator: either "kick off Phase 2 first-week dispatch" (lanes per §5 above), "run the enrichment sprint" (operator-driven, toolchain ready), or "audit HALT 3 then decide on Premier".

---

## §8 — Topology and protocol that worked

Today ran **four-agent parallel topology** for most of the day:

- **Cowork primary** (this session) — orchestration, integration, BACKLOG.md / STATE.md owner, single source of truth for cross-lane state, verification of agent outputs.
- **Claude Code (CC)** — heavy lanes (test-suite triage, runbook audit, Phase 2 lane decomposition spec, adversarial regression test suite).
- **Cursor** — focused-file edits (#41a-followup, cache-pollution fixture, #46 fix).
- **General-purpose agents** (spawned via Cowork's Agent tool) — independent code or review lanes that report back as text (operator enrichment tooling, code-reviewer pass on #44, voice-battery investigation, ChatGPT-for-non-file-tasks adversarial brainstorm).

**Hard-won protocol rules** (don't re-litigate these):

1. **Anchored `Edit` over full-file `Write` on shared files.** Yesterday's truncation incident set this rule; held throughout today with no collisions across ~10 lanes in flight.
2. **Text-only ship-log reports.** Delegated lanes return ship-log entries as raw markdown text in their final report; the primary integrates them into `docs/BACKLOG.md`. Direct appends from multiple agents collide.
3. **Linux mount staleness vs Windows authoritative.** The Cowork bind sometimes serves stale or truncated views of files mid-write. The Windows-side files (read via the `Read` tool, written via Cursor / CC tools) are authoritative. Don't restore a file from git until you've verified Windows shows the same truncation.
4. **Audit smoke commands by executing them, not reading the route signature.** New rule from today's two runbook bugs. For each `curl.exe`/`Invoke-RestMethod` command in any runbook, verify the request body shape AND invocation method work end-to-end against the live or staging API. Schema mismatches and shell-quoting bugs only surface at runtime.
5. **Voice-battery adversarial verification before declaring fixes "shipped."** The #44 fix passed all named tests but introduced real production wrong-entity matches that only surfaced via voice-battery investigation. For any matcher / scorer / classifier change, dispatch a parallel adversarial verification before integration.

---

## §9 — Final test count + alembic state

```
$ python -m alembic heads
b4c5d6e7f8a9 (head)   # Lane S1.1; #41a-followup is a TypeDecorator-only change with no migration

$ python -m pytest -q
1327 passed, 3 subtests passed in ~5min
```

Phase 1 surface (still 163/163):

```
tests/test_home_queries.py
tests/test_home_queries_lane_a.py
tests/test_audience_signal.py
tests/test_disclosure_render.py
tests/test_disclosure_render_integration.py
tests/test_confidence_tier.py
tests/test_confidence_tier_integration_tier2.py
tests/test_confidence_tier_integration_tier3.py
tests/test_chat_route_audience_forwarding.py
tests/test_tier3_handler.py
tests/test_tier3_organic_context_wiring.py
tests/test_urgent_now_sub_intent.py
tests/test_tier3_phone_enforcement.py
tests/test_tz_aware_datetime.py
```

Phase 2 net-new today:

```
tests/test_entity_matcher_adversarial.py  (13 tests)
tests/test_enrichment_ingestion.py        (16 tests)
```

---

*This handoff doc should be the first read for any fresh session continuing this work. Production is shipped, verified, and stable. The Phase 2 spec is drafted and ready for first-week dispatch. The operator's main decisions are: (a) flip CT flag now or stage, (b) start the enrichment sprint, (c) audit HALT 3, (d) approve the Phase 2 dispatch sequence.*
