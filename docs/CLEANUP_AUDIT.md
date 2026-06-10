# Repo Cleanup & Efficiency Audit — Phase 0

**Date:** 2026-06-10 · **Mode:** read-only audit, no code changed · **Method:** delta-verification against the two prior audits (`docs/RUST_MIGRATION_AUDIT_2026-06-04.md`, `docs/TECH_DIRECTION_DECISION_2026-06-04.md`) + fresh sweeps (ruff F401/F811, vulture 2.16 @90% confidence, template/CSS reference tracing, `git ls-files` tracked-status checks, pip dependency-graph verification). All claims below were verified directly; subagent findings that contradicted ground truth were discarded (noted where relevant).

**Headline:** this repo was audited for exactly these questions six days ago, and most of the prescribed fixes have **already shipped**. The remaining work is: (1) a large but low-risk stale-file cleanup (~1.5 GB reclaimable, almost all untracked), (2) a small confirmed-dead set of templates/CSS orphaned by the Desert re-skin, (3) one dependency removal (`anthropic`), (4) four surviving efficiency items (one O(N) algorithmic, three small), and (5) **no justified language change** — re-confirmed, with the prior decision doc's reasoning still holding.

---

## 0. What already shipped since the 2026-06-04 audits (verified in current code)

| Prior finding | Status today | Evidence |
|---|---|---|
| Dead modules `app/core/program_search.py`, `app/core/dedupe.py`, `app/events/view_model.py`, `app/home/browse_tiles.py` | **Already deleted** | Files gone from disk; `tests/test_wp12_count_reconciliation.py:150` comment confirms the T3.4 dead-code purge |
| P3: N+1 on category landing pages | **Fixed** | Batched `build_card_view_models()` at `app/providers/queries.py:1056` (3 bulk queries); bulk provider maps used at `app/api/routes/category_pages.py:574,769` |
| P4: composite indexes | **Fixed** | `alembic/versions/e5f6a7b8c9d0_t33_composite_indexes.py` creates `ix_providers_entity_active_draft` + `ix_events_date_entity` (merged) |
| P5a: disclosure regexes compiled at call time | **Fixed** | Module-level `_DISALLOWED_REGEX` tuple, `app/chat/disclosure_render.py:153-155` |
| Leak: `_LAST_SEEN_MONO` unbounded | **Fixed** | Cap + prune at `app/auth/session.py:34,87-101` |
| Leak/perf: per-call `OpenAI()` clients | **Fixed** | Singleton cache `app/core/openai_client.py:39-46`, used by `hint_extractor.py:200` |
| mypy in CI, xdist, branch protection | **Done** | CI runs ruff + pytest + mypy; `main` protection on since 2026-06-05 |

Lint/dead-import state: `ruff check . --select F401,F811` → clean except one unused import in an **untracked** scratch file (`docs/proposals/A2-migration-classifier.py`). Vulture @90% on `app/` → only SQLAlchemy event-callback params (false positives) and the `tzid` param of `ical_parse.py:32` — which is the known tz **bug**, not dead code (see §4).

---

## 1. Dead code (confirmed, with how dynamic use was ruled out)

**Method:** built the *live* template set = all python render sites (`name="*.html"` / `TemplateResponse` greps — no dynamic/f-string template names exist, verified) ∪ all `{% extends %}` / `{% include %}` / `{% import %}` targets, then diffed against the template inventory. CSS traced via `<link>` hrefs in templates **plus** `@import` chains inside CSS (the `@import` chain is what keeps `components/hava_card.css` etc. alive — naive filename grep gives false positives here).

### 1a. Dead templates (4 files)

| File | Why dead | Dynamic-use check |
|---|---|---|
| `app/templates/sandstone_base.html` | All 44 page templates extend `desert_base.html` (its drop-in replacement); nothing renders or extends it | Only textual mentions are comments (`desert_base.html:3`, `app/api/routes/gas.py:88`) |
| `app/templates/lake_light_base.html` | Same — superseded two re-skins ago | Its lake_light partials are NOT dead (still included by live `desert_base.html`) — only the base itself |
| `app/templates/category_landing.html` | Route `category_landing` (`category_pages.py:1043`) now returns a `RedirectResponse`; nothing renders the template | Not in render set, not included/extended anywhere |
| `app/templates/components/themed_tile.html` | `themed_group_landing.html` includes `components/hava_card.html` instead (line 114) | Not in include set |

### 1b. Dead CSS (~36 KB, 15 files)

Linked-by-live-templates set is: `desert*.css`, `sandstone.css`*, `lake_light.css`*, `chat_cards.css`, `components/hava_card.css`, `components/map_view.css` (*only from the dead base templates above — so they die with them*).

- **Dead with the dead bases:** `sandstone.css`, `lake_light.css`
- **Zero references anywhere:** `sandstone_category.css`, `sandstone_events.css`, `sandstone_gas.css`, `sandstone_modes.css`, `sandstone_portal.css`, `sandstone_profile.css`, `sandstone_search.css`, `category_landing.css`
- **Dead `@import` cluster:** `home.css` (nothing links it; only the dead `category_landing.css` imports it) plus the components only it imports: `components/map.css`, `components/search.css`, `components/themed_group.css`, `components/themed_tile.css`, `components/conditions_strip.css`

Note: `sandstone_*.js` files are **live** (`sandstone_category.js`, `sandstone_profile.js` linked from live templates) — only the CSS was superseded by the desert re-skin. No unreferenced JS found.

### 1c. Python dead code: clean negative result

No dead modules/functions found in `app/` beyond the items already purged. ruff F401/F811 clean; vulture @90% clean (above); prior audit's `lhcaz_aquatic.py` is **live** (imported by `scripts/run_scrapes.py:50`, source key for `data/scrapes/lhcaz_aquatic/`) — keep.

### 1d. Scripts triage: prior recommendation never executed

`scripts/` has grown to **110 scripts**; `scripts/archive/` was never created. The 2026-06-04 audit's triage (§3d there) still stands: ~30 completed one-off backfills/phase-verify harnesses are archive-or-delete candidates, and `scripts/run_query_battery.py` (306 LOC, documented broken since 2026-04-29, Backlog #12) still exists. Recommend executing that triage as written (archive re-runnable loaders/verifiers, delete completed one-offs) — per-script verification belongs in that PR, not re-derived here.

---

## 2. Stale files

Ground-truth note: tracked-status was verified per-file with `git ls-files --error-unmatch`. **`.env`, `.env.ghtoken`, `.env.ghtoken2`, `.env.produrl` are correctly gitignored and NOT tracked** (a subagent claimed otherwise — false). All root `*.log`, `*.bundle`, `*.patch`, report CSVs/JSONs, and `*.ps1` helpers are likewise untracked.

### 2a. Untracked, safe to delete (≈1.5 GB) — *no git history risk, but irreversible: delete only after Casey's nod*

| Group | Size | Notes |
|---|---|---|
| `.uv-cache/`, `.uv-tmp/` | ~595 MB | Package caches, regenerate on demand |
| Stale venvs: `.venv-linux` (381 MB), `.venv-p4` (183 MB), `.venv-test` (88 MB), `.venv-launch` (55 MB), `.venv-linux-new` (32 MB), `.venv-run` | ~740 MB | Active venv is `.venv` (CLAUDE.md). `.venv-linux*`: confirm no WSL/sandbox flow still uses one |
| `scripts/output/` | 54 MB | Gitignored script outputs (prior audit's caveat: confirm `places_pull/enrichment_raw.jsonl` not needed for liveness reruns) |
| Root logs: `backfill_photo_urls.log` (50 MB) + 11 smaller `*.log` | ~52 MB | Run logs of completed backfills |
| `data/` backups: `events.db.bak-*`, `_tmp_empty_upgrade.db`, `test_*.db` | ~18 MB | Local SQLite backups; `data/events.db` itself stays |
| Bundles: `p11-route-collapse.bundle` (10.6 MB) + 7 small `.bundle` | ~11 MB | Git bundles from past sessions; content already merged via PRs — spot-check `git bundle list-heads` before deleting |
| `tmp/`, `scratch/`, `sales/`, untracked `outputs/` files (~700), untracked `mockups/`, `docs/cowork/`, untracked `docs/proposals/` (20 files), root report CSVs/JSONs, `.sync_marker_delete_me`, `sentinel_ids.txt`, `_*.cmd`, `0001-fix-chat-*.patch` | ~15 MB | Session ephemera. **Exception — keep, Casey-only:** `check_prod_env.ps1` / `pull_prod_env.ps1` (prod-env helpers; memory says never commit; deleting is Casey's call), `.env*` files (secrets — out of scope for cleanup; note `.env.ghtoken*` hold the PAT Casey still needs to revoke) |
| Untracked docs at root & `docs/`: `SESSION_*`, `COWORK_*`, `PROMPT_*`, `CHAT_DIAGNOSTIC_*`, `ROLLOUT_LOG_*`, `docs/scraper/reports/*` | ~1 MB | Session handoffs already superseded by `docs/STATE.md`/memory; or move into a `docs/archive/` if Casey wants the paper trail |

### 2b. Tracked junk — untrack via small PR (`git rm`)

| File | Evidence it's dead weight |
|---|---|
| `h` (4 KB) | Captured pager output, accidentally committed; zero references |
| `cripts.voice_battery.grade --judge-model gpt-4.1-mini` (17 KB) | Mangled command line became a filename; zero references |
| `test_sync_check.tmp`, `test_write_check.tmp` | 18 bytes of sync-test sentinels; zero references |
| `.split_backup/` (9 files) | Frozen pre-refactor copies; history already has them; zero references |
| `palette-options.html`, `redesign-mockup.html` (95 KB) | Design explorations superseded by shipped templates; zero references |

### 2c. Tracked stale docs — Casey's judgment (propose `docs/archive/`, not deletion)

Tracked, referenced by nothing canonical (grep across README, CLAUDE.md, `docs/STATE.md`, `docs/START_HERE.md`, PROJECT/BACKLOG, code, CI): `BUILD.md` (27 KB), `CRITIQUE_AND_REDESIGN.md` (75 KB), `SITE_AUDIT_LIVE_2026-06-03.md` (61 KB), `DISPATCH_PLAN_2026-06-03.md`, `GAP_SWEEP_2026-06-03.md`, `SEO_ASSESSMENT_AND_RANKING_PLAN_2026-06-04.md`, `PRODUCTION_READY_PLAN_2026-06-03.md`, `MONETIZATION_UI_MASTER_PLAN_2026-06-07.md`, `ask-hava-detailed-plan.docx`, `AUDIT_TRIAGE_2026-06-03.md`, `ASK_HAVA_DIAGNOSIS_2026-06-04.md`, `CHAT_ROUTING_FIX_HANDOFF_2026-06-04.md`, `CROSS_SOURCE_DEDUP_SESSION.md`, `CURSOR_DEDUP_TASKS.md`, `DEPLOY_MIGRATION_GAP.md`, `EAT_CATEGORY_POLLUTION_AUDIT_2026-06-04.md`, `GOLAKEHAVASU_PROJECT_CLOSEOUT.md`, `LIVENESS_RANKING_HANDOFF_2026-06-03.md`, plus May-era `docs/SESSION_HANDOFF_*` (13 files). Suggest: `git mv` to `docs/archive/` so root/`docs/` stop being decoys for new agent sessions (this was Tier-3 item 9 in the tech-direction doc), keeping history intact.

**Do NOT touch (load-bearing, verified referenced):** `CLAUDE.md`, `.claude/`, `README.md`, `HAVA_CONCIERGE_HANDOFF.md` (referenced by README + ~40 files), `NEW_SCRAPER_CHECKLIST.md` (process doc), `docs/STATE.md`, `docs/START_HERE.md`, `docs/PROJECT.md`, `docs/BACKLOG.md`, `docs/WORKING_AGREEMENT.md`, `docs/STRATEGY_PIVOT_2026-05-12.md` (START_HERE directs sessions to it), `docs/persona-brief.md`, `docs/known-issues.md`, `docs/maintainability/*`, `docs/components/*`, `prompts/`, root `templates/` (email templates, code-referenced), tracked `mockups/` + `outputs/` tracked files (Casey's call; default keep), `graphify-out/`, all deploy/CI config, `data/events.db`.

---

## 3. Dependency hygiene

`requirements.txt` is a **fully-pinned freeze** (76 packages incl. transitive deps). That means "package not imported" ≠ removable — verified with `pip show Required-by`:

- **Remove: `anthropic==0.96.0`** — zero imports anywhere (`app/`, `scripts/`, `tests/`); LLM calls migrated to OpenAI 2026-05-07 (`app/core/llm_messages.py`). All its transitive deps (httpx, jiter, distro, …) are shared with `openai`/`sentry-sdk`, so nothing else needs to change. One-line PR.
- **Keep, despite "unused" appearance (transitive):** `Mako`←alembic, `limits`←slowapi, `click`←uvicorn+nltk, `colorama`←click/pytest/tqdm, `pyee`←playwright, `tqdm`←nltk+openai, `typing-inspection`+`annotated-doc`←fastapi/pydantic, `six`←dateutil, `Pygments`←pytest. (A subagent flagged all of these for removal — wrong; removing `Mako` breaks the prod deploy gate itself.)
- **Keep: `playwright`, `pytesseract`** — genuinely imported by `app/contrib/` AZ-regulatory clients (`az_roc_client.py`, `azmvd_client.py`, `azcc_towing_client.py`, `_azcc_captcha_solver.py`) and `scripts/az*_verify.py`. They do bloat the Railway image (~300 MB); if the AZ verifier flows are dormant, moving those clients + deps out of the web-app install is a *possible* follow-up — but it's a product/ops question for Casey, not a hygiene fix.
- **Optional micro-trim:** `websockets`, `watchfiles`, `httptools` have empty `Required-by` — they're `uvicorn[standard]` extras. `httptools` speeds prod HTTP parsing (keep); `watchfiles` is `--reload` dev-only and `websockets` is unused (no WS endpoints). Removing the two saves a few MB. Low value; bundle into the anthropic PR only if desired.
- No used-but-undeclared imports found. Pinning is uniformly `==` — good for Railway reproducibility.

---

## 4. Inefficiencies — what's still real (ranked)

1. **HIGH — O(N) brute-force fuzzy dedup, still present.** `app/events/dedup.py:233-247` (`resolve_venue_entity_id`: scans every active Entity with `token_sort_ratio`, then every active Provider for address match) and `app/contrib/ingest_reconciler.py:132` (all active Providers loaded per payload). Batch/ingest path only, not user-facing latency. Fix per prior audit: exact normalized-name dict first + load entities once per scrape batch (or `pg_trgm` SQL prefilter). ~1-2 days, biggest CPU win available.
2. **MEDIUM — entity-matcher first-request spike (partially fixed).** Rebuild is now batched to 4 queries with TTL (`app/chat/entity_matcher.py:344-463`), but the lifespan handler (`app/main.py:307-318`) still doesn't warm it — first request per process pays ~50-150 ms. 2-line fix.
3. **SMALL — `_trade_cluster_tags()` not memoized.** `app/chat/entity_matcher.py:170-196` re-runs ~6 regexes on the *same* normalized query once per candidate row (~2,200×/query) via the category guard at lines 262-266. `@lru_cache` = 1 line, single-digit ms/query on the chat hot path.
4. **CORRECTNESS (not perf) — iCal tz bug still present.** `app/events/scrapers/ical_parse.py:32-41`: `tzid` parsed but ignored; `Z`-suffixed UTC parsed to naive datetimes. ~5-line fix; this repo's recurring bug class (Backlog #27/#41 family). Vulture independently flagged the ignored param.

New-code sweep (taxonomy rewire #233/#234, leaf pages, search consolidation #222): **no new N+1s found** — the new paths reuse the bulk-load patterns (`entity_catalog_query.py` uses `selectinload`/bulk `in_` loads correctly, verified at lines 180-182, 262-289). Remaining repeated computation (`is_open_now` per entity in `category_pages.py:628-685,773-810`; `read_current_temperature_f` per sort at line 614) is cheap pure-Python/single-row work — not worth churn.

---

## 5. Optimization / language-change candidates

**No language change is justified. This is a re-confirmed negative result.**

The question was examined exhaustively on 2026-06-04 by two dedicated audits (`RUST_MIGRATION_AUDIT`, `TECH_DIRECTION_DECISION` — profiling-grade analysis of where request time goes, component-by-component Rust suitability, and a bug-class honesty check against the actual git log). Their conclusion — latency is dominated by LLM API calls (seconds) and Postgres; the one CPU hotspot (fuzzy matching) already runs on rapidfuzz's C++ core; a Rust matcher would shave ~10 ms on paths that include 1,000+ ms LLM calls — **still holds**, and has gotten *stronger* since: the prescribed cheap wins (composite indexes, N+1 elimination, client singleton, mypy-in-CI) have shipped, further shrinking the remaining CPU share. The only pre-approved ceiling remains the optional `havasu_match` PyO3 crate (plan in the prior audit §5, phases 1-4), gated on a *future* measured CPU bottleneck — e.g. if the 5k intent-phrase dataset or a much larger catalog makes dedup/matching the profiled pain point **after** the §4.1 algorithmic fix lands. Today, nothing clears the bar. The honest recommendation is the §4 Python wins, in order.

---

## 6. Proposed execution plan (each its own small PR, pytest + ruff + mypy green)

| # | PR | Risk | Contents |
|---|---|---|---|
| a | Stale-file cleanup | none (mostly untracked) | Delete §2a groups Casey approves; `git rm` §2b; optional `docs/archive/` move for §2c |
| b | Dead template/CSS removal | low | §1a 4 templates + §1b 15 CSS files; suite proves nothing referenced them |
| c | Scripts archive | low | Execute prior audit §3d triage; create `scripts/archive/`; decide `run_query_battery.py` (fix vs delete — Backlog #12) |
| d | Dependency trim | low | Remove `anthropic` (+ optionally `websockets`/`watchfiles`); fresh-install smoke via CI |
| e | Quick perf/correctness | low | Matcher warm-on-startup + `_trade_cluster_tags` lru_cache + iCal tz fix (with tests) |
| f | Dedup algorithmic fix | medium | §4.1 — exact-name dict + batch loading; characterization tests on current match outputs first |

Open questions for Casey before execution: ① delete vs archive for §2c tracked docs; ② confirm none of `.venv-linux*` is used by a WSL/sandbox flow; ③ are the AZ-regulatory verifier flows (playwright/pytesseract) still planned, or should that whole contrib cluster move out of the prod image eventually; ④ `check_prod_env.ps1`/`pull_prod_env.ps1` — keep locally (default) or delete; ⑤ bundles — OK to delete after `git bundle list-heads` spot-check?
