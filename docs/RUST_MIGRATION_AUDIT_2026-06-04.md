# Rust Migration, Optimization & Dead-Code Audit — havasu-chat

**Date:** 2026-06-04 · **Mode:** read-only audit (no changes made) · **Method:** 4 parallel audit agents (architecture, dead code, performance, Rust feasibility) + manual spot-verification of key claims against the code.

---

## Executive summary

The honest answer to "convert as much as possible to Rust" is: **convert very little, deliberately.** This codebase's latency and bug history are dominated by things Rust cannot fix — LLM API calls (seconds), Postgres round-trips, scraper breakage from upstream HTML drift, and fuzzy-match *threshold tuning*. The CPU-heavy hot spots that do exist (fuzzy entity matching and dedup) already run on rapidfuzz's C++ core; Python is only the loop driver.

The maximum defensible Rust footprint is **one PyO3 extension crate** (`havasu_match`) covering entity-matcher scoring + dedup scoring, shadow-tested behind a flag, with the Python implementation kept forever as fallback. Everything else — and there is a lot of "everything else" — gets more speed and more bug-prevention from Python-level fixes (algorithmic dedup fix, N+1 elimination, indexes, `mypy --strict`) at a fraction of the risk. A full rewrite would be 6–12 months for a solo operator against 2,827 byte-stability tests and a `main`-auto-deploys-to-prod pipeline; it fails the "without causing problems" requirement outright.

Separately, the audit found **~430–530 LOC of confirmed-dead app code, ~5.9k LOC of completed one-off scripts, several accidentally committed junk files, and ~530–620 MB of reclaimable disk** (stale venvs, a 50 MB log, scripts/output).

Recommended order: **Phase 0 Python fixes → cleanup PR → golden corpus → optional Rust matcher crate.**

---

## 1. What the system is (architecture recap)

- FastAPI + SQLAlchemy 2.0 (sync psycopg2) + Postgres on Railway; `railway.json` predeploy runs `alembic upgrade head` (65 migrations). Entry: `uvicorn app.main:app`, ~30 routers.
- ~61k LOC in `app/` (largest: `chat/` 14.7k, `contrib/` 10.3k, `admin/` 5.4k), ~17.3k in `scripts/` (80+ scripts), ~61k LOC tests (324 files, 2,827 test functions).
- Chat pipeline: normalize → intent classifier (regex) → hint extractor (LLM API) → entity matcher (rapidfuzz over ~2,200 names, 5-min TTL in-memory index) → Tier 1 (deterministic templates) / Tier 2 (SQL + templates, `tier2_db_query.py` 1,113 LOC) / Tier 3 (Claude API, grounded).
- 25+ scrapers (BeautifulSoup/httpx; 2 require Playwright for captcha/JS sites), ingest reconciler with fuzzy matching, event dedup, Postgres FTS search with SQLite fallback.
- Heavy deps: anthropic, openai, playwright (~300 MB), bs4, rapidfuzz (C++), pillow, pdfplumber, pytesseract, boto3.

### Where time actually goes per chat request

| Stage | Cost | Rust-addressable? |
|---|---|---|
| normalize + intent classify | µs–low ms | Technically yes, pointless |
| hint extractor (LLM API) | **100s of ms–seconds** | **No** |
| entity matcher scan (~2,200 rows, rapidfuzz C++) | low tens of ms | Partially — the win is algorithmic (prefilter/index), not language |
| Tier 2 SQL | DB round-trips | **No** (Postgres does the work) |
| Tier 3 Claude call | **seconds** | **No** |

Realistic end-user latency gain from a Rust matcher: low single-digit % on Tier 3 paths, maybe 10–30% on already-fast Tier 1 hits. The batch/ingest side (dedup) is where the real CPU waste lives — see §2.

---

## 2. Performance findings (verified)

### P1 — HIGH: brute-force O(N) fuzzy dedup on every event ingest
`app/events/dedup.py:60–87` (`resolve_venue_entity_id`) — **verified in code**: loops over *every* active Entity running `fuzz.token_sort_ratio`, then falls through to scanning *every* active Provider for address `partial_ratio ≥ 85`. Same pattern in `app/contrib/ingest_reconciler.py:131–141` (`_contact_match_entity_id` does `db.query(Provider).filter(is_active).all()` per payload).
**Fix (Python, days):** exact normalized-name dict first; load entities once per scrape batch instead of per event; or push candidate narrowing into SQL with `pg_trgm`. This is also the best Rust candidate — but the algorithmic fix delivers most of the win in either language.

### P2 — HIGH: entity-matcher catalog rebuild spike
`app/chat/entity_matcher.py:327–447` — first request in each 5-min TTL window pays ~50–150 ms rebuilding the ~2,200-row index (4 DB queries + repeated normalization).
**Fix:** warm at startup in the lifespan handler; refresh on a background schedule instead of on-demand; `lru_cache` on `_needles_for_canonical`; consider extending TTL.

### P3 — MEDIUM: N+1 queries on category landing pages
`app/api/routes/category_pages.py:1130–1135` — `build_card_view_model(db, ent.id)` called per entity (~50 entities ⇒ ~50+ queries per page). Providers also re-fetched in `_apply_python_filters` (≈781–789) *and* `rank_inputs_for_category` (≈588).
**Fix:** bulk-fetch providers for all entity IDs once, pass the map through. Est. −100–300 ms on category pages.

### P4 — MEDIUM: missing composite indexes
Hot filters with no composite index: `(providers.entity_id, is_active, draft)`, `(events.date, entity_id)`. One small alembic migration (needs Casey's approval per CLAUDE.md prod-migration rule).

### P5 — LOW: misc
Disclosure-render regexes compiled at call time (`app/chat/disclosure_render.py` ~154) — move to module level. Repeated trade-tag regex scans per candidate in entity matcher — memoize. Static category config and temperature reads re-fetched per request — tiny TTL caches. Module-level regex compilation elsewhere is already done correctly.

### Bonus correctness find
`app/events/scrapers/ical_parse.py:32–41` — `TZID` param is parsed but **ignored**, and `Z`-suffixed UTC values are parsed to *naive* datetimes via `strptime(...%SZ)`. A live timezone-correctness smell, fixable in ~5 Python lines. (Timezone naive/aware mixups are a recurring bug class in this repo — Backlog #27, #41.)

---

## 3. Dead code & stale artifacts

### 3a. Confirmed-dead app modules (verified: zero imports anywhere)

| Module | LOC | Confidence |
|---|---|---|
| `app/core/program_search.py` | 242 | **High** — zero references (grep-verified); superseded by tier2 intent pipeline |
| `app/core/dedupe.py` | 74 | **High** — `find_duplicate` (embedding dedupe) never imported (grep-verified) |
| `app/events/view_model.py` | 24 | High — shim; all callers import `provider_queries` directly |
| `app/home/browse_tiles.py` | 97 | Med-High — only kept alive by `tests/test_phase6_homepage.py`; superseded by sandstone home. Delete module + test together |
| `app/contrib/lhcaz_aquatic.py` | 280 | Medium — deliberately retained HTML fallback after the 2026-05-22 disable_aquatic ship; **ask before removing** |

### 3b. Tracked junk (needs a small PR)
Accidentally committed files: `h` (captured pager output), `cripts.voice_battery.grade --judge-model gpt-4.1-mini` (mangled command became a filename), `test_sync_check.tmp`, `test_write_check.tmp`, `.split_backup/` (9 frozen pre-refactor copies, 120 KB — history already has them), `palette-options.html` + `redesign-mockup.html` (mockups superseded by shipped sandstone templates). ~8 root-level session/handoff `.md` files are candidates to move under `docs/`.

### 3c. Reclaimable disk (~530–620 MB, all untracked/gitignored — zero git risk)

| Item | Size |
|---|---|
| Stale venvs: `.venv-p4` (195 MB), `.venv-test` (94 MB), `.venv-linux` (92 MB), `.venv-launch` (60 MB) — verify which of `.venv-linux`/`.venv-linux-new` (36 MB) the sandbox still uses | ~440 MB |
| `backfill_photo_urls.log` (49.7 MB, verified) + other root `*.log` | ~52 MB |
| `scripts/output/` (confirm `places_pull/enrichment_raw.jsonl` not needed for liveness reruns) | 55 MB |
| `data/events.db.bak-*` backups | ~18 MB |
| `outputs/` (964 files), `tmp/`, `mockups/`, root `_*.cmd`/report CSVs | ~25 MB |

### 3d. Scripts triage (scripts/, 82 entries)
- **Keep (production/CI-wired, ~2.1k LOC):** `run_scrapes.py`, gas/golakehavasu/river-scene/parks-rec pulls, `post_deploy_smoke.py`, `cross_source_dedup_audit.py`, alert dispatch, `expire_past_events.py`, etc.
- **Keep (dev tooling, ~3.5k LOC):** voice battery, cost analysis, diagnostics, dupe reports.
- **Archive or delete (~30 scripts, ~5.9k LOC):** completed backfills (matching logs at root prove execution), River Scene cleanup pair, the 2026-06-03 merge wave, phase-numbered verify harnesses, `golakehavasu_dedup_audit.py` (superseded per its own docstring). The AZ regulatory verifiers (~2.1k LOC) and Places/OSM loaders (~3.3k LOC) are re-runnable — archive to `scripts/archive/` rather than delete.
- **Broken:** `run_query_battery.py` (306 LOC) — documented broken since 2026-04-29 (targets legacy `/chat`, 404s). Fix (Backlog #12) or delete.

### 3e. Git metadata cruft (needs Casey's go)
`.git/` holds corruption-incident relics (`HEAD.corrupt*`, `index.*.bak`, phantom lock), **56 local branches** including typo branches (`chore`, `feat`, `fix`) and 21 ephemeral agent branches, 8 prunable worktrees. `git worktree prune` + branch cleanup + `gc` would recover part of the 150 MB `.git`.

### 3f. Tests: very clean
Only 1 stale unconditional skip (`test_phase4_ingest_client_interface.py:345`); 4 legitimate environment-gated skips; no xfails or commented-out tests.

---

## 4. Rust feasibility — component by component

| Subsystem | Suitability | Why / crates | Verdict |
|---|---|---|---|
| Entity matcher (`entity_matcher.py`, 1,049 LOC) | **Medium-high** | Pure `(query, rows) → score`; CPU-bound; well-tested. But ~600 LOC of tuned heuristics must reproduce rapidfuzz semantics bit-for-bit. Crates: `rapidfuzz` (Rust port, same algorithms), `regex`, `pyo3` | **The one good candidate.** PyO3 module; Python keeps DB + TTL cache |
| Event dedup (`events/dedup.py`, 129 LOC) | Medium | Shares scoring core with matcher; right fix is indexing, not language | Fold into same crate, *after* the Python algorithmic fix |
| Ingest reconciler | Low | Logic trivial (6-line haversine); cost is full-table SQL scans; merge policy churns | Don't convert; fix the SQL |
| Intent classifier / normalizer | Low | µs-fast; regexes edited frequently — Rust adds recompile to every heuristic tweak | Don't (port normalizer only *inside* the matcher crate so both sides agree) |
| Scrapers (25+, BeautifulSoup/Playwright) | **None** | Bottleneck is network + upstream drift; most-churned code in repo (10 consecutive GasBuddy fix commits); Playwright/captcha flows have no mature Rust peer | **Do not convert** |
| iCal parsing | Low | 107 LOC stdlib; has a tz bug — fix in Python | Don't |
| Search/FTS, ranking | None | Postgres does the work; tantivy = different product decision | Don't |
| Tier 2 query builder (1,113 LOC) | None | SQLAlchemy composition with documented byte-stable output contracts; max regression surface, zero CPU win | Don't |
| Tier 3 / hint extractor (LLM) | None | Latency is the API; Python SDKs are the first-class ones | Don't |
| Auth | None–Low | Porting working bcrypt/jose code is pure security-regression risk | Don't |
| Admin HTML, alerts, digest, photos, portal | None | IO-bound, product-copy churn; OCR/PDF deps have no Rust parity | Don't |
| API layer (FastAPI) / DB layer (SQLAlchemy + alembic) | None short of full rewrite | `alembic upgrade head` *is* the prod deploy gate — highest blast radius in the repo | Only under strategy (c), which is rejected |

### Strategy options

**(a) PyO3/maturin extension for hot spots — recommended ceiling.** One crate `havasu_match` exposing `normalize()`, `best_match()`, `score_title_pair()`. Python keeps everything stateful. Build prebuilt manylinux + Windows wheels in GitHub Actions (`maturin-action`), pin in requirements — Railway's pip-only nixpacks build stays untouched; do **not** put a Rust toolchain in the auto-deploy path. Feature-flag `ENTITY_MATCHER_IMPL=rust|python`, Python kept as permanent fallback. Effort: 3–6 weeks incl. parity harness. Honest caveat: rapidfuzz is already C++, so expect ~10 ms → ~1–3 ms on the scan — real but invisible next to Tier 3's seconds. A trigram prefilter in Python likely delivers comparable wall-clock for zero toolchain cost.

**(b) Sidecar Rust service — not justified.** Network hop eats the ~10 ms you're saving; second Railway service doubles the deploy-hazard surface; catalog sync becomes a distributed-cache-invalidation problem (a brand-new bug class). Only revisit if dedup batch volume grows enough to want independent scaling.

**(c) Full rewrite (axum + sqlx + askama) — do not do.** 6–12 months solo to parity. Killers: 2,827 tests pinning exact strings ("byte-stable" formatting contracts, HALT-3 validator, graded voice batteries) — none port mechanically; alembic-to-sqlx migration is a one-way door on the prod DB; Playwright/pdfplumber/pytesseract have no Rust parity so you'd keep a Python sidecar anyway; scrapers break monthly and need interpreter-speed iteration during the entire rewrite. Probability of causing more regressions than the entire historical bug count: high.

### Bug-reduction honesty check (scored against this repo's actual git log + BACKLOG.md)

Rust **would** have prevented: the naive/aware datetime `TypeError` family (Backlog #27/#41 — `chrono` makes these compile errors, though #41 is already fixed); the `call_with_retry` signature mismatch swallowed by retry logic (compile error — but `mypy --strict` also catches it).

Rust would **not** have prevented: every fuzzy-threshold false positive (Backlog #44/#46/#47/#50/#52, the voice-battery wave — tuning, identical in any language); all scraper breakage (upstream drift); alembic parallel-heads and schema drift (process); LLM confabulation, template copy drift, data quality (product). **Roughly one bug class is decisively Rust-preventable; one is Rust-or-mypy-preventable; the four biggest are neither.** `mypy --strict` on `app/chat/` and `app/events/` buys the largest available slice of "Rust-style" safety for near-zero cost.

---

## 5. Recommended phased roadmap

**Phase 0 — Python wins first (1–2 weeks).** Gate: pytest green, ruff clean, prod metrics same or better.
1. Fix O(N) dedup: exact-name dict + batch entity loading + SQL/`pg_trgm` prefilter (`events/dedup.py`, `ingest_reconciler.py`).
2. Fix category-page N+1s (bulk provider prefetch) and add the composite indexes (alembic migration → PR → Casey approves).
3. Warm/schedule the entity-matcher index; pre-compile disclosure regexes.
4. Fix the iCal TZID/naive-Z bug.
5. Add `mypy --strict` (at least `app/chat/`, `app/events/`) to CI.
6. **This is the honest benchmark: if it removes the pain, stop here.**

**Cleanup PR (parallel, low risk).** Delete untracked debris (logs, stale venvs, scripts/output, DB backups); one PR to untrack the junk files + `.split_backup/` + the two mockup HTMLs; remove the 4 confirmed-dead modules (+ `test_phase6_homepage.py`); archive completed one-off scripts; decide on `run_query_battery.py` and `lhcaz_aquatic.py` (ask items); git housekeeping (worktree prune, branch cleanup) with Casey's go.

**Phase 1 — golden corpus (1 week).** Freeze the ~2,200-name catalog snapshot + a query corpus (test queries, voice batteries, HALT-3 specs, sampled `query_log` rows). Record Python matcher outputs `(best_canon, best_score, second_score, near_match, ambiguous)` as golden JSON; same for dedup title pairs.

**Phase 2 — `havasu_match` PyO3 crate (2–3 weeks).** Gate: 100% golden parity within ±0.01, all 2,827 tests green under `ENTITY_MATCHER_IMPL=rust`. Port normalize + guard chain + scoring loop; verify rapidfuzz-rs numeric parity on the corpus (don't assume). CI: differential test on every PR; wheels via GitHub Actions; Railway build untouched.

**Phase 3 — shadow then flip (1–2 weeks).** Ship flag-off; run Rust in shadow in prod (compute both, log divergence, serve Python). Flip via env var — instantly revertible without a deploy. Gate: N days zero divergence.

**Phase 4 — extend to dedup scoring (1 week). Then stop.** Re-evaluate only if a future workload (5k intent-phrase dataset, much larger catalog) makes CPU the measured bottleneck again.

Every phase: feature branch + PR per CLAUDE.md; the Python implementation is never deleted — it is the permanent fallback and the executable spec.

---

## 6. Key file citations

`app/events/dedup.py:60–87` (O(N) scans, verified) · `app/contrib/ingest_reconciler.py:131–141` · `app/chat/entity_matcher.py:327–447` (TTL rebuild), 870–1011 (scoring loop) · `app/api/routes/category_pages.py:588, 781–789, 1130–1135` (N+1) · `app/chat/disclosure_render.py:~154` · `app/events/scrapers/ical_parse.py:32–41` (tz bug) · `app/core/program_search.py`, `app/core/dedupe.py`, `app/events/view_model.py`, `app/home/browse_tiles.py` (dead, grep-verified) · `railway.json` (alembic predeploy) · `nixpacks.toml` (pip-only build) · `docs/BACKLOG.md` (#12, #27, #41, #44–#52).
