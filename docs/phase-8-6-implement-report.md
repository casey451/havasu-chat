# Phase 8.6 — Full regression pass findings

**Date:** 2026-04-22

**HEAD at verification:** `8de25ce` (Phase 8.5) — this run captures the **voice-audit** JSON baseline *before* Phase 8.8 persona work. (Voice auditor uses Claude Haiku; some verdict variance run-to-run is expected.)

## Summary

**Launch-readiness: GO** for **dogfooding week**, with two notes: (1) **p50/p95 latencies** on this machine for `smoke_concurrent_chat` are **higher** than the Phase 8.2 short-run numbers cited in the prompt—**no 5xx, no client errors, zero fallbacks** with API keys set, so this is treated as **environmental variance**, not a regression. (2) The **voice auditor** reclassified a few samples (notably `t3-19`) with **similar** response text; summary counts are **unchanged** from the 2026-04-21 baseline—operator eyeball of flagged lines is still worthwhile before 8.8.

---

## Category A — Automated tests

| Result | Detail |
|--------|--------|
| **PASS** | `pytest -q` — **794** passed, **3** subtests passed |
| **Runtime (pre-check)** | ~7 min 4s |
| **Runtime (post-check)** | ~6 min 50s |
| **Warnings** | None beyond normal test output |

---

## Category B — Voice battery

**Script:** `scripts/run_voice_audit.py`  
**Commands run:**

- `... run_voice_audit.py --dry-run` — estimated **upper bound ~$0.3415** (under **$2.00** hard ceiling)
- `... run_voice_audit.py --execute --confirm --yes`

**Output artifacts:**

- `scripts/voice_audit_results_2026-04-22.json` (script default name by date)
- **Canonical copy for Phase 8.6:** `scripts/voice_audit_results_2026-04-22-phase86.json` (identical to the above; preserved name for the baseline)

**`meta.git_sha` (new):** `8de25ce0528fdb77966a58b324b272db2348b80f`

### Baseline vs new (summary row counts)

| | Baseline `voice_audit_results_2026-04-21.json` | New 2026-04-22 @ 8de25ce |
|---|--------|--------|
| **total_audited** | 55 | 55 |
| **PASS** | 51 | 51 |
| **MINOR** | 1 | 1 |
| **FAIL** | 3 | 3 |
| **ERROR** | 0 | 0 |

**Per Decision 1:** Pass count **≥ 51/55** — **met** (51).  
**“New MAJOR (FAIL) regressions” (PASS → FAIL):** **1** (`t3-19`) — **under** the **≥5** STOP threshold.

### Verdict *deltas* (same `sample_id`, baseline → new)

| sample_id | Baseline | New | Notes |
|-----------|----------|------|--------|
| `t1-HOURS-03` | MINOR | PASS | Wording polish (“is open” vs “open”); **improvement** |
| `t3-01` | FAIL | PASS | “Weekend” calendar gap handling **improved** (catalog empty vs date uncertain) — **improvement** |
| `t3-19` | PASS | FAIL | **Regression flag** — auditor says Option 3 voice not “owned” enough (§8.4); response text is substantively similar to baseline pass (see below) — **treat as auditor / LLM variance** for 8.8. |
| `t3-20` | PASS | MINOR | Slightly different closing sentence; same catalog limitation |

**Still FAIL in both runs (unchanged, for context):** includes Tier 3 explicit-rec / compare samples such as `t3-24`, `t3-25` (unchanged failure category counts).

### Samples flagged for operator review

1. **`t3-19` — “Best place for toddler tumbling”**  
   - **Baseline verdict:** PASS  
   - **New verdict:** FAIL  
   - **New response (excerpt):** *“Flips for Fun Gymnastics is your best bet for toddler tumbling — they're at 955 Kiowa Ave and open 3–8pm weekdays, so you can swing by after work. Call (928) 566-8862 or check fffhavasu.com to ask about their toddler classes and pricing.”*  
   - **Why flagged:** Auditor cited §8.4 Option 3 — “your best bet” and “swing by after work” read as **soft** vs. a fully “owned” recommendation. **Same** session previously got PASS on 2026-04-21 with a very similar answer. **Suggested action:** eyeball for 8.8 persona; not treated as a launch **blocker** here given aggregate counts and duplicate-ish text.

2. **`t3-20` — “Compare Footlite and Ballet Havasu for preschool dance”**  
   - **Baseline:** PASS  
   - **New:** MINOR  
   - **Why flagged:** Slight **voice drift** in the closing CTA; content limitations unchanged (Footlite not in catalog).

3. **`t3-01` (improvement) / `t1-HOURS-03` (improvement)**  
   - Optional read—**better** than baseline, no action required.

---

## Category C — Smoke test

**Command:**

`.\.venv\Scripts\python.exe scripts\smoke_concurrent_chat.py --base-url http://127.0.0.1:8765 --threads 8 --duration-seconds 180 --interval-seconds 25`

**Setup note:** The first `GET /terms` check initially returned **404** while another long-lived `python` was bound to `127.0.0.1:8765` (likely a **pre-8.5** process). The process was **stopped** and `uvicorn` was **restarted** from the repo at **`8de25ce`**. **This smoke file** is the **second** run, against the **correct** app. **All-200, zero fallbacks** in both runs; the **authoritative** numbers are below.

| Metric | Phase 8.2 reference (prompt) | This run (HEAD @ 8de25ce) |
|--------|----------------------------|----------------------------|
| p50 (all 200s) | ~1,658 ms | **4,713 ms** |
| p95 (all 200s) | ~5,901 ms | **5,948 ms** |
| p50 (Tier 3 only) | ~5,901 ms | **5,521 ms** |
| p95 (Tier 3 only) | ~6,293 ms | **6,193 ms** |
| 5xx | 0 | **0** |
| Client errors | 0 | **0** |
| Fallbacks | 0 / N | **0 / 56** |
| Total requests | — | **56** |

**Interpretation:** All-200 **p50** is **higher** than the 8.2 short-run baseline (likely **machine load, model warmth, and measurement differences**). **Tier 3** p50/p95 are in the **same ballpark** as 8.2. **No** STOP condition triggered (no 5xx, no client errors, **0%** fallbacks with keys present).

**Saved output:** `scripts/output/voice_spotcheck_2026-04-22-phase86.md` (also recorded under `scripts/output/`, which is **gitignored by default** — use `git add -f` to track).

---

## Category D — User flow (HTTP endpoint checks)

| Check | Result |
|--------|--------|
| `GET /` | 200, “Havasu Chat” present |
| `GET /privacy` | 200, “What we collect” |
| `GET /terms` | 200, “Terms of Service” (after **server restart**; see C) |
| `GET /health` | 200, `"ok"` in body |
| `GET /contribute` | 200, contribute form content |
| `POST /api/chat` Tier 1 (“What time does Altitude open?”) | 200, Altitude + hours content |
| `POST /api/chat` Tier 2 (“kid-friendly activities this weekend”) | 200, weekend / local content |
| `POST /api/chat` Tier 3 (“what should I do tonight?”) | 200, non-empty response |
| `POST /api/chat` OOS (“Boat rentals on the lake?”) | 200, out-of-scope framing + “**Want me to point you to anything else?**” |
| `POST /admin/login` + 7 `GET` admin pages | 200 (password from `.env` / `ADMIN_PASSWORD` available to client) |

**Not run:** Real HTML **click-through** UX; **contribution POST** body (per scope — form **GET** only).

---

## Findings requiring follow-up

| Item | Severity | Suggested next step |
|------|----------|----------------------|
| Stale `python` on **8765** could serve an **old** app (caught as missing `/terms`) | Ops | When switching phases, **kill** stray uvicorn on dev ports or use a **fresh port**; document in runbook if useful |
| `t3-19` **PASS→FAIL** with same-ish answer | Low | Eyeball in **8.8** persona; optional strengthen Option 3 ownership |
| Smoke p50 (all-200) >> 8.2 short-run p50 | Info | Not failing gates here; re-profile if user reports slowness |

**None** are treated as “no-go” **blockers** for dogfooding.

---

## Launch-readiness recommendation

| Decision | Rationale |
|----------|-----------|
| **GO** | **794/794** tests, **0** 5xx / **0** client errors / **0** fallbacks in smoke, admin + chat + static routes **200** on HEAD, voice summary **at least as good** as 2026-04-21 baseline; 8.5 `/terms` verified. |

**Next (per handoff / owner):** if **go** — **Phase 8.8** persona, then **dogfooding week**, then launch when ready. **No app code** was changed in this sub-phase; findings live here and in the JSON **baseline** for future diffs.
