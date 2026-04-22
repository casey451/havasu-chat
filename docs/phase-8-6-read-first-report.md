# Phase 8.6 — Full regression pass (read-first plan)

**Date:** 2026-04-22  
**HEAD (pre-flight):** `8de25ce` (Phase 8.5)  
**Read-first only:** planning and inventory. No voice battery, no smoke test, no manual walkthrough, no code edits, no commit.

---

## Pre-flight results

| Check | Result |
|--------|--------|
| `git log -1` | `8de25ce` — **PASS** |
| `git status` | Clean except `?? docs/phase-9-scoping-notes-2026-04-22.md` — **PASS** (per spec) |
| `.\.venv\Scripts\python.exe -m pytest -q` | **794 passed** (+3 subtests), ~7 min — **PASS** |
| `pytest --collect-only` | **794 tests collected** (matches) |

**Skipped tests:** No `pytest.mark.skip` / `skipif` / `xfail` found in `tests/`. (Optional **`@pytest.mark.integration`** markers exist—`pytest.ini` documents them as optional; default `pytest -q` still collects and runs them unless you use `-m "not integration"`.)

---

## 1. Inventory by verification category (A–D)

### A — Automated test suite (Category A)

| Item | Detail |
|------|--------|
| **Command** | `.\.venv\Scripts\python.exe -m pytest -q` (from repo root) |
| **Expected** | 794 passed (current baseline at HEAD) |
| **Scope** | Full unit/integration suite; does not cover subjective voice quality or end-to-end browser UX. |

**Optional (not required for 8.6 if full run passes):** `pytest -m integration` to isolate real-API tests—only if you explicitly want a narrower slice; 8.6 A should be the same command as pre-flight unless you are debugging a category.

---

### B — Voice battery (55-sample paid audit) (Category B)

| Script | `scripts/run_voice_audit.py` |
|--------|------------------------------|
| **Purpose** | Phase 6.1.2+ runner: discovers **Tier 1 matrix** samples from the local DB, adds **25 Tier 3** query payloads (`_TIER3_QUERIES`), **6 reference** (§8.5/§8-style) samples, runs `route()`-shaped work + Anthropic `prompts/voice_audit.txt` audits, emits **PASS / MINOR / FAIL / ERROR** per sample. Total audited count is **typically 55** when the usual matrix is auditable; Tier 1 row count is **data-dependent** (`discover_tier1_matrix`). |
| **Invocation (dry, no spend)** | `.\.venv\Scripts\python.exe scripts/run_voice_audit.py` or `... run_voice_audit.py --dry-run` — enumerates sample counts, **tier1 not auditable** list, and **~USD upper bound**; no API calls. |
| **Invocation (paid)** | `... run_voice_audit.py --execute --confirm` (add `--yes` to skip the interactive y/N after cost line). **Requires** `ANTHROPIC_API_KEY` in the environment. Optional: `DATABASE_URL` (else app default). **Refuses** if estimate &gt; **`_HARD_CEILING_USD` (2.0)**. |
| **Model** | `claude-haiku-4-5-20251001` (per script) |
| **Input source** | Local SQLite (or configured DB) seed + fixed Tier 3 / reference lists in script |
| **Output** | `scripts/voice_audit_results_YYYY-MM-DD.json` (date from runner), containing `meta`, `summary` (totals, PASS/MINOR/FAIL/ERROR), `samples`, `verdicts` |
| **Local vs prod** | **Entirely local** (DB + direct Anthropic API). Does **not** need Railway. |
| **Other script (different scope)** | `scripts/run_voice_spotcheck.py` — **20** queries, default **`--base` = production** (`https://havasu-chat-production.up.railway.app`), writes `scripts/output/voice_spotcheck_*.md`; optional `railway run` for `chat_logs` correlation. This is a **separate** diagnostic/Phase 4.4 tool **not** equivalent to the 55-sample `run_voice_audit` matrix. For **Flavor C 8.6** as specified, **primary = `run_voice_audit.py`**. |

**Baseline in repo (exists):**

- `scripts/voice_audit_results_2026-04-21.json`  
  - **summary.total_audited:** 55  
  - **summary:** PASS 51, MINOR 1, FAIL 3, ERROR 0  
  - **meta.git_sha:** `b5f6be15237cad4abf82dcb51a4ffe7a17dc00d0` (**not** current `8de25ce`)  
  - **meta.estimated_usd_upper_bound_pre_run:** ~0.34 (actual usage in `meta.tier3_generation_usage_tokens` also recorded)  
- Second file: `scripts/voice_audit_results_2026-04-21-phase614-verify.json` (archival / phase-specific label—treat as historical).

**Conclusion (baseline for 8.6-implement):** A **prior run exists** to compare *qualitatively* (verdict distribution, which samples regressed), but the **git SHA is stale**. Recommended approach:

- Treat **this 8.6 run** (at `8de25ce` or then-current HEAD) as the **new canonical baseline** for **future** comparisons once accepted.  
- **Diff** new JSON to `voice_audit_results_2026-04-21.json` in a file comparison or small script: flag **any sample that moves from PASS→MINOR/FAIL/ERROR** or new ERRORs.  
- **Seed/data gaps** (e.g. Tier 1 `branch_present_not_auditable` rows) are **expected** per script docstring; document them as **data limitations**, not necessarily code bugs.

**Rough cost (B):** dry-run prints estimate; 2025-04-21 meta showed sub-**$0.35** upper bound for that run; re-run at HEAD may differ slightly with matrix size. Hard ceiling **$2.00** aborts `--execute` if estimate is too high.

---

### C — Concurrent smoke test (Category C)

| Script | `scripts/smoke_concurrent_chat.py` |
|--------|-------------------------------------|
| **Purpose** | **Local** `POST /api/chat` under **8** concurrent threads, mixed Tier 1/2/3 *style* queries, records **p50/p95** latency, counts **5xx**, **client errors** (e.g. timeouts), **fallback** responses (body equals `tier3_handler.FALLBACK_MESSAGE`). |
| **Prereq** | **Dev server** on e.g. `http://127.0.0.1:8000` — e.g. `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. **Server env** should have **`ANTHROPIC_API_KEY`** and **`OPENAI_API_KEY`** if you want Tier 2/3 to hit real models; otherwise expect higher **fallback** rate (script docstring: informative, not failure by itself for smoke *logic*, but 8.6 C pass criteria should use keys for apples-to-apples vs prior performance). |
| **Default args** | `--threads 8` (each worker runs `--duration-seconds` long loop), `--duration-seconds 180`, `--interval-seconds 25.0` |
| **Smaller / faster run (for quick check)** | e.g. `--threads 4 --duration-seconds 30 --interval-seconds 5` (not a formal baseline; use for sanity only). For **8.2-comparable** numbers, match whatever was used in the 8.2 handback; **defaults** match `docs/runbook.md` (8 thread × ~3 min). |
| **Output** | **Stdout** only (no JSON file in script) — copy terminal output into **8.6 implement report** |
| **Prod?** | **No** — script targets `--base-url` (default local). **No Railway required.** |

**Reference baseline (Phase 8.2 — from implementation notes / owner prompt, not re-run here):**

- All-200: **p50 ~1.6s, p95 ~5.9s** (ms in script output)  
- Tier 3 only: **p50 ~5.9s, p95 ~6.3s**  
- **0** 5xx, **0** client errors, **0** fallbacks *under the conditions of that run* (keys, warm, etc.)  

8.6-implement should re-run with **the same** `--base-url` / key setup as the baseline run when possible, then compare.

---

### D — Manual user-flow walkthrough (Category D)

| Flow | Route / action | What to verify | Notes / documentation |
|------|----------------|----------------|------------------------|
| **Chat: Tier 1** | `GET /` → send: e.g. “What are the hours for Havasu Lanes?” (or other seeded **provider** with hours) | Direct factual answer, **no** avoidable “what do you mean?” follow-up; hours/phone present if that’s what was asked | Mirror Tier 1 patterns in `smoke_concurrent_chat._TIER1` and seed. |
| **Chat: Tier 2** | Same UI → e.g. “What kid-friendly activities are there in Lake Havasu this weekend?” | Filtered / list-style response; **Option 2 or 3** *voice* (concrete list, not vague hedge) | Align with `smoke_concurrent_chat._TIER2` style. |
| **Chat: Tier 3** | e.g. “I have one day in town—what’s worth my time at the lake?” (from smoke `_TIER3` or similar) | **Tier 3** behavior: picks direction, not “it depends on everything” without a recommendation | Script uses similar Tier 3 set. |
| **Chat: out of scope** | e.g. “Where can I rent a boat on the lake?” (or “boat rentals”) | Curated out-of-scope / bridge response per **8.0.4 / 8.7** intent (trailing follow-up, no fake catalog) | Do **not** require exact string—assert **no hallucinated listing** and **safe redirect** tone. |
| **Session memory** | Two turns in same browser session: first answer references an entity, second “What time does *that* place open?” (or use hinting follow-up) | Hints or context carry; no crash | Depends on `OPENAI_API_KEY` for hint path; document if key missing. |
| **Contribute** | `GET /contribute` → submit **test** business with **real URL** (Places enrichment) | 200 on submit, row in **`contributions`** with pending status; optional email empty OK | `GOOGLE_PLACES_API_KEY` and contributed URL that resolves help enrichment. Label name/description “test” for cleanup. |
| **Admin login** | `GET /admin` or `/admin/login` → `POST` password | `ADMIN_PASSWORD` in **server** env; cookie session | If password unset locally, **login fails** — document as setup gap. |
| **Admin: pending contribution** | `/admin/contributions` → open detail, **Approve** (or workflow your deploy uses) | No 500; contribution leaves queue or shows approved path | **Requires** contribution from prior step. |
| **Admin: catalog sanity** (optional) | After approve: spot-check catalog/permalink or provider appears as expected | Matches product expectations for approved entity | Defer if heavy. |
| **Admin: static admin pages** | `GET` **200** for: `/admin/analytics`, `/admin/feedback`, `/admin/contributions`, `/admin/mentioned-entities`, `/admin/categories` (nav: `app/admin/nav_html.py`) | HTML loads, no 500, no obvious broken layout | All cookie-protected after login. |
| **Static: privacy / terms** | `GET /privacy`, `GET /terms` | 200, markdown rendering, `caseylsolomon@gmail.com` visible, TODO comments in source if present | 8.5 ToS. |
| **Footer from index** | `GET /` → check links to `/privacy`, `/terms` | 200 on followed links (or at least `href` present) | 8.5. |

**Documentation:** Suggest **copy-paste** of **first ~500 chars** of assistant `response` into implement report, plus **tier_used** if visible in devtools/network JSON, or browser screenshot. For admin, one line “200 OK, saw pending row #N” is enough for pass.

**STOP-and-ask if:** `ADMIN_PASSWORD` or API keys are missing in the environment the operator actually uses; **8.6-implement** only documents and either proceeds with a partial D or reschedules after env is fixed.

---

## 2. Proposed pass / fail criteria (8.6-implement)

| Cat | **Pass** | **Fail (document + defer fix)** |
|-----|----------|----------------------------------|
| **A** | 794/794 green (same as pre-flight) | Any failure or error exit |
| **B** | New JSON: **0 ERROR** verdicts; **FAIL** count not worse than last baseline (ideally 0 new FAIL; if data-gap rows change counts, note); operator spot-check: no egregious voice regression on **random 5** PASS lines vs prior file; **meta.git_sha** recorded = HEAD | Worse **FAIL/ERROR** totals without explainable data-gap; or obvious systematic voice breakage |
| **C** | **0** 5xx, **0** client/transport errors; p50/p95 within **~20–30%** of 8.2 or prior run (same args + keys); **fallback** rate **0** *if* keys and DB match prior intent—if keys missing, **document** and treat fallback spike as **environmental**, not a product fail | Non-zero 5xx; massive latency regression without cold-start explanation; hung script |
| **D** | Each row in the table **works** with no 500, no broken critical UI, responses plausible | Any 500, wrong redirect, or contribute stuck outside env limits |

**8.6 scope = verification, not fix.** Failures get a **“Findings / follow-up sub-phases”** line, not same-day code changes, unless the owner explicitly expands scope.

---

## 3. Baselines (summary)

| Kind | Exists? | Notes |
|------|---------|--------|
| Voice audit JSON | **Yes** | `2026-04-21` file; SHA not current. Use for diff + establish **new** baseline this run. |
| Smoke p50/p95 | **From 8.2 handback** | Re-run to refresh; not stored as machine file in repo. |
| 120-query `battery_results.json` | **Yes (scripts/)** | **Not** the 55-sample voice audit; optional separate regression, out of 8.6’s stated Flavor C unless owner adds it. |

---

## 4. Setup prerequisites (by category)

| Category | Env / process | Data |
|----------|---------------|------|
| **A** | venv, pytest | None; SQLite tests use test DBs |
| **B** | `ANTHROPIC_API_KEY`, DB migrated (`alembic upgrade head`), dev seed or real DB with providers/events | `discover_tier1_matrix` may skip rows |
| **C** | Uvicorn + `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` (recommended) on **server** | N/A |
| **D** | Uvicorn; `ADMIN_PASSWORD` for admin; `GOOGLE_PLACES_API_KEY` for full contribute enrichment; API keys for chat | Seed data; one test contribution row; optional DB cleanup of test rows after dogfooding |

**Smoke test (C)** does **not** require production or Railway.

**Voice spotcheck** (`run_voice_spotcheck.py`) is **not** a substitute for the 55-sample audit; if used as extra signal, it hits **default production**—call out as **separate** risk/scope.

---

## 5. Estimated time and cost (full 8.6-implement)

| Block | Time (order of magnitude) | Cost |
|--------|---------------------------|------|
| **A** | ~7 min | $0 |
| **B** dry-run | 1–2 min | $0 |
| **B** execute + diff + human spot-check | ~15–45 min wall (model + review; 55 auditable samples) | ~**$0.30–$0.50** (historical; confirm dry-run line) **if** under hard ceiling |
| **C** (default 8×180s) | **~3–4 min** of wall **after** server warm (threads run in parallel) + setup | $0 (local) |
| **C** (short sanity run) | ~1 min | $0 |
| **D** | **~30–45 min** careful, **~20 min** if rushed | $0 |
| **Report writing** | ~20–30 min | — |
| **Total** | **~1.5–2.5 h** one session, or **split** A+C first session, B+D second | Mostly Anthropic for B |

**One session vs split:** **Recommended split:** (1) **A + C + D (without long Tier 3 chat tests)** in one sitting; (2) **B** in a separate sitting when you accept token spend. Alternatively **all in one morning** if keys and server are already warm.

---

## 6. Proposed `docs/phase-8-6-implement-report.md` structure

Use this as the 8.6-implement deliverable (fill in during/after runs):

```markdown
# Phase 8.6 — Full regression pass findings

**Date:** YYYY-MM-DD
**HEAD / git SHA:** …
**Operator:** …

## Summary

- One-paragraph: overall **go / go-with-notes / no-go** for **dogfooding week**, and why.

## A — Automated tests (pytest)

- Command run
- Result: pass/fail, time
- (If any failure) trace id / test name — **STOP**; defer fix

## B — Voice battery (`run_voice_audit.py`)

- Commands (`--dry-run` output summary; `--execute` if run)
- Output file path: `scripts/voice_audit_results_…json`
- Summary counts: total_audited, PASS, MINOR, FAIL, ERROR
- **Baseline used for comparison** (e.g. `voice_audit_results_2026-04-21.json`)
- **Diff highlights:** new/changed FAIL or ERROR; samples worth quoting
- Manual spot-check notes (5 samples)
- Cost: estimated vs actual (from meta) if available

## C — Concurrent smoke (`smoke_concurrent_chat.py`)

- **Exact** command line (base-url, threads, duration, interval)
- **Server** env: keys set Y/N
- Pasted or summarized stdout: p50, p95, 5xx, client errors, fallbacks
- Comparison to 8.2 baseline (within tolerance Y/N)
- Warnings (e.g. T3 p95 &gt; 20s) — context only

## D — Manual user flows

- Table: flow | result (pass/fail) | evidence (link/snippet) | notes
- Cover: Tier 1/2/3 chat, OOS, memory, contribute, admin list + approve, static pages, footer

## Findings requiring follow-up (deferred work)

- Bullet list — **no** fixes in 8.6; reference sub-phases

## Launch-readiness recommendation (dogfooding week)

- **Go / go-with-conditions / no-go**
- One sentence on conditions, if any
```

---

## 7. STOP / unusual findings from inspection

| Check | Outcome |
|--------|---------|
| `run_voice_audit.py` exists, wired to `prompts/voice_audit.txt` | OK |
| `smoke_concurrent_chat.py` local-only | OK |
| 55-sample baseline JSON present | **OK; SHA stale** — compare qualitatively + new baseline |
| `run_voice_spotcheck.py` = different tool (20 q, prod default) | **Flag** — do not conflate with B |
| Scripts not syntax-tested in this read-first | If **8.6-implement** hit import errors, **STOP** per prompt (do not fix in read-first) |
| `pytest` skip tests | **None** found for skip/skipif |

**No** STOP requiring owner decision from this file alone: proceed to 8.6-implement when approved.

---

*Report path: `docs/phase-8-6-read-first-report.md` (local, uncommitted).*
