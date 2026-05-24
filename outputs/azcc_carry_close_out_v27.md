# AZCC carry close-out -- v27 (2026-05-24)

> **What this is:** Autonomous Cowork pass following the v26 Chrome MCP
> probe. Goal: push everything that does not require operator input to
> done. Outputs are a spot-check report, a design-doc sync edit, and a
> ready-to-run operator probe script for Q1/Q2.
>
> **TL;DR:**
> - **Shipped code spot-check: GREEN.** All 8 shipped unit tests verified
>   pass-through to actual behavior; 4 extra coverage cases (HttpOnly/
>   SameSite pass-through, bad-input safety, lazy pytesseract import)
>   also pass. 28/28 total.
> - **Commit `47d45e3` verified:** is HEAD of `main`, matches dispatch
>   spec, signature regression test asserts the public contract.
> - **Design doc synced:** v23 doc now carries v26 amendment marking Q5
>   and Q6 CLOSED with pointers, and a new Section 8 summary.
> - **Operator probe script delivered:** `scripts/azcc_q1_q2_operator_probe.py`
>   -- headed Playwright tool that captures full cookie scope (Q2) and
>   runs a timed TTL probe (Q1) at default 5/15/30/60/120 min marks, with
>   crash-safe JSON report writing.
> - **Open items now exactly 2:** Q1 cookie TTL + Q2 cookie scope, both
>   operator-paced, both non-blocking. ~15 min of operator time + a
>   captcha solve fully closes them.

---

## Section A -- Tasks attempted vs done

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Ground-truth repo and referenced files | DONE | All referenced files exist; v26 carry's claims match the actual files. |
| 2 | Spot-check shipped solver against v26 findings | DONE | See Section B. |
| 3 | Verify commit `47d45e3` and CI state | DONE | Commit is HEAD of `main`; commit message matches dispatch spec; touched files match. |
| 4 | Update v23 design doc to mark Q5/Q6 closed | DONE | Inline edit + new Section 8 amendment summary. |
| 5 | Draft Q1/Q2 operator probe script | DONE | `scripts/azcc_q1_q2_operator_probe.py` (305 LOC), CLI tested. |
| 6 | Write v27 close-out carry | DONE | This document. |
| 7 | Final verification (diff review, link check) | DONE | See Section E. |

---

## Section B -- Shipped solver spot-check (28/28 PASS)

Ran a direct-import unit harness (bypassing pytest's conftest, which needs
Python 3.11+ for `datetime.UTC` -- sandbox has 3.10). Harness lives at
`outputs/_v27_solver_unit_check.py` and exercises the same public surface
as `tests/test_azcc_captcha_solver.py` plus four extra cases.

| Category | Cases | Result |
|----------|-------|--------|
| `_parse_session_cookies` empty / malformed / valid | 3 | PASS |
| `_parse_session_cookies` existing-domain-preserved | 1 | PASS |
| `_parse_session_cookies` HttpOnly/SameSite/Secure/Expires pass-through | 1 | PASS |
| `is_tesseract_enabled` env truthy/falsy matrix | 10 | PASS |
| `get_max_retries` default/clamp-to-5/floor-at-1/garbage/explicit-5 | 5 | PASS |
| `solve_captcha_image` tiny garbage / bad b64 / empty / None | 4 | PASS |
| Soft-fail shape constant | 1 | PASS |
| Public signature regression `fetch_azcc_entity_search(client, name, search_url, county)` | 2 | PASS |
| `import app.contrib.azcc_towing_client` does NOT pull `pytesseract` | 1 | PASS |
| **Total** | **28** | **28 PASS** |

### B.1 Specific v26 carry claims verified against code

| v26 carry claim | Code location | Verdict |
|-----------------|---------------|---------|
| `get_max_retries` cap is `max(1, min(n, 5))` | `_azcc_captcha_solver.py:37` | EXACT MATCH |
| 800 ms wait outside Angular debounce window | `azcc_towing_client.py:165` (`page.wait_for_timeout(800)` after refresh click) | CONFIRMED -- v26 C.2 measured debounce < 5 ms; 800 ms is 160x margin |
| `_parse_session_cookies()` pass-through preserves cookie attrs | `azcc_towing_client.py:243-270` | CONFIRMED -- only `domain` and `path` get defaults, and only when BOTH `domain` and `url` are absent |
| Lazy `pytesseract` import | `_azcc_captcha_solver.py:67` (inside `solve_captcha_image`, not module-top) | CONFIRMED -- import-time check shows `pytesseract not in sys.modules` after `import app.contrib.azcc_towing_client` |

### B.2 Minor finding (not actionable)

`_parse_session_cookies` only defaults `path="/"` when also defaulting
`domain`. A hand-crafted cookie dict with `domain` set but no `path` would
fail Playwright's `add_cookies` validation (Playwright requires either
`url` OR both `domain`+`path`). In practice this never bites: the
`scripts/azcc_seed_cookie.py` helper uses `context.cookies()` which always
returns dicts with both `domain` and `path` populated, so operator-pasted
output always satisfies Playwright's requirements. Not worth fixing
defensively.

---

## Section C -- Design doc sync (edits to `outputs/azcc_captcha_unblock_design_2026_05_24_v23.md`)

Three precise edits, all preserving the existing structure:

1. **Header status block** -- added v26 amendment line pointing at
   `outputs/azcc_q5_q6_probe_v26.md` and shipped commit `47d45e3`.
2. **Section 1 captcha-surface table** -- image-size row updated to
   "~7.3 KB decoded PNG (~9.8 KB data URL) -- v26 measured"; image-dimensions
   row notes v26 DOM confirmation.
3. **Section 6 open-questions table** -- Q5 and Q6 marked `ANSWERED (v26)`
   with pointers to the probe doc's relevant sections. Existing v25-net
   summary line preserved; new v26-net summary line added.
4. **New Section 8** -- "v26 amendment summary" mirroring the Section 7
   v25 amendment format: side-by-side table of v25 status vs v26
   measurement vs resolution, shipped-commit pointer, post-v26 status.
5. **Final paragraph** -- updated to note Section 8 amendment was applied
   and that path (c) is SHIPPED.

After edits, the doc still cleanly reads as "design doc with two
amendments stacked on top," matching the v25 amendment pattern. No
content was deleted, only added or sharpened.

---

## Section D -- Operator probe script (`scripts/azcc_q1_q2_operator_probe.py`)

Sibling to `scripts/azcc_seed_cookie.py`. Where the seed helper just
dumps the cookie line for `.env` paste, this probe additionally:

1. **Q2: captures full cookie attribute set** via `context.cookies()` at
   solve time, including `httpOnly`, `secure`, `sameSite`, `expires`,
   `domain`, `path`. Also samples `Set-Cookie` response headers across
   the entire solve flow via `page.on("response", ...)` so any
   server-set scope is visible.

2. **Q1: runs timed TTL re-probes** by issuing `fetch()` calls from
   inside the browser context (so credentials cookies ride along) to
   `https://api-azbusinessconnectonline.azcc.gov/api/Captcha/generate`
   at default minute marks 5, 15, 30, 60, 120. Classification logic:
   `alive` if 200 + body > 1 KB, `stale_auth` if 401/403, `rate_limited`
   if 429, `unexpected:<status>` otherwise.

### D.1 Crash-safety design notes

- Report is written to disk **after every probe**, not just at the end.
  A 2-hour script that crashes at T+90 min still leaves a JSON with the
  T+5, T+15, T+30, T+60 results.
- `SIGINT` (Ctrl+C) is trapped: whatever has been collected to that
  point is flushed before exit, exit code 0 with `ended_reason: ctrl-c-*`.
- Q2 cookie capture happens immediately on solve detect; even if the
  operator Ctrl+C's during the wait between intervals, Q2 is preserved.

### D.2 CLI

```
python scripts/azcc_q1_q2_operator_probe.py
python scripts/azcc_q1_q2_operator_probe.py --intervals 5,15,30,60,120
python scripts/azcc_q1_q2_operator_probe.py --intervals 1,2,5 --out-dir /tmp
```

Default schedule is 5/15/30/60/120 min, giving a ~2-hour total runtime
(operator can run it in background; browser sits idle between probes).
For a quick smoke run, `--intervals 1,2,5` gives 5-minute total.

### D.3 What the operator does

1. `pip install playwright && playwright install chromium` (if not already).
2. `python scripts/azcc_q1_q2_operator_probe.py`
3. Browser opens. Type a business name, solve captcha, click Verify.
4. Script auto-detects success, prints Q2 cookie table to stdout,
   begins TTL re-probe loop.
5. Walk away. Come back in 2 hours (or sooner -- intermediate results
   stream to the JSON file after every probe).
6. JSON report lands at
   `outputs/azcc_q1_q2_operator_probe_<UTC-stamp>.json`.

### D.4 What we will learn

| Question | Probe signal | Decision impact |
|----------|--------------|-----------------|
| Q1: cookie TTL | First `stale_auth` / `unexpected` classification tells us where the cliff is | Sets the verifier batch-chunking strategy. If TTL >= 60 min, current ~100-row passes fit. If TTL < 30 min, we need either chunked passes or a re-seed-mid-pass strategy. |
| Q2: cookie scope | Cookie attribute table + `Set-Cookie` capture | Confirms whether `_parse_session_cookies()` pass-through is delivering the right scope. If `httpOnly: true` and `sameSite: Strict`, Playwright `context.add_cookies` should still work, but the seed helper output format may need adjustment. |

### D.5 Why this is safe to run now

- Hits one residential IP (operator's machine), not the Railway egress
  that the AZCC verifier batch will use.
- Probes one captcha endpoint at ~1 request per probe interval -- well
  below the v26 measured throttle ceiling of 5 req/sec.
- Makes zero writes to the repo or to AZCC -- read-only from AZCC's
  perspective.
- Writes only to `outputs/` (or `--out-dir`); no committed files touched.

---

## Section E -- Final verification

### E.1 Diff review

```
outputs/azcc_captcha_unblock_design_2026_05_24_v23.md   |  M (5 hunks, +30 -3)
outputs/azcc_carry_close_out_v27.md                     |  A (this file)
scripts/azcc_q1_q2_operator_probe.py                    |  A (305 LOC)
outputs/_v27_solver_unit_check.py                       |  A (test harness, ~150 LOC)
```

No edits to `app/contrib/azcc_towing_client.py`, `_azcc_captcha_solver.py`,
`scripts/azcc_seed_cookie.py`, `requirements.txt`, `nixpacks.toml`,
`Dockerfile`, or any other shipped code. The v26 ship is preserved
byte-for-byte.

### E.2 Link / reference check

| Reference | Target | Resolves? |
|-----------|--------|-----------|
| v27 carry -> v26 carry | `outputs/azcc_q5_q6_probe_v26.md` | YES (exists) |
| v27 carry -> v25 findings | `outputs/azcc_derisk_findings_2026_05_24_v25.md` | YES (exists) |
| v27 carry -> v22 recon | `outputs/chrome_mcp_captcha_recon_v22.md` | YES (exists) |
| v27 carry -> v26 cursor brief | `outputs/cursor_dispatch_azcc_captcha_unblock_2026_05_24_v26.md` | YES (exists) |
| v27 carry -> shipped solver | `app/contrib/_azcc_captcha_solver.py` | YES (exists, 85 LOC, verified) |
| v27 carry -> operator probe | `scripts/azcc_q1_q2_operator_probe.py` | YES (created in this carry, 305 LOC, --help works) |
| v23 doc (v26-amend) -> operator probe | `scripts/azcc_q1_q2_operator_probe.py` | YES |
| v23 doc -> shipped commit | `47d45e3f48bfe9e0eafc24f8013829562d7de0fe` | YES (git log confirmed) |

### E.3 Residual open items

| Item | Owner | Effort | Blocking? |
|------|-------|--------|-----------|
| Q1 cookie TTL | Operator (run probe script) | ~5 min active + ~2 hr elapsed | NO |
| Q2 cookie scope (HttpOnly/SameSite) | Operator (run same probe script -- Q2 is captured in phase 1) | ~5 min active | NO |
| Post-ship Railway log review (D.1 caveat from v26) | Whoever does next prod-traffic review | ~10 min | NO -- only matters if 429s appear |
| Lift `get_max_retries` hard cap from 5 to 9 | Code change in `_azcc_captcha_solver.py:37` | ~1 line | NO -- only if cookie path proves unreliable AND OCR success needs +20 pts |

Note that Q1 and Q2 are answered by a SINGLE operator probe run -- the
script captures both in one session. So the effective remaining workload
is one 5-minute operator action that spawns a 2-hour background probe.

---

## Section F -- Inventory state post-v27

**v23 design doc open questions (post-v27):**

| Q | Status | Pointer |
|---|--------|---------|
| Q1 cookie TTL | OPEN, operator-paced | `scripts/azcc_q1_q2_operator_probe.py` |
| Q2 cookie scope | OPEN, operator-paced | `scripts/azcc_q1_q2_operator_probe.py` (same run) |
| Q3 Tesseract version pin | CLOSED (v25) | `outputs/azcc_derisk_findings_2026_05_24_v25.md` |
| Q4 Railway deploy-tier impact | DOWNGRADED (v25) | -- flag-gated, deferred |
| Q5 refresh rate-limit | CLOSED (v26) | `outputs/azcc_q5_q6_probe_v26.md` Section C |
| Q6 image dimensions | CLOSED (v26) | `outputs/azcc_q5_q6_probe_v26.md` Section B |

**Carries (post-v27):**

| Carry | Status | Notes |
|-------|--------|-------|
| #4 v25 carry (Q5/Q6 Chrome MCP probe) | CLOSED v26 | -- |
| #5 v27 close-out (spot-check + doc sync + operator probe handoff) | CLOSED v27 | This carry. |
| #6 v27 carry (Q1/Q2 operator probe) | OPEN, XS | Single operator action; script ready. |

---

## Section G -- Sources

- v22 Chrome MCP recon: `outputs/chrome_mcp_captcha_recon_v22.md`
- v23 design doc (v25 + v26 amendments): `outputs/azcc_captcha_unblock_design_2026_05_24_v23.md`
- v25 findings (Tesseract 23-25%/try): `outputs/azcc_derisk_findings_2026_05_24_v25.md`
- v26 Chrome MCP probe (Q5/Q6 close): `outputs/azcc_q5_q6_probe_v26.md`
- v26 cursor dispatch brief: `outputs/cursor_dispatch_azcc_captcha_unblock_2026_05_24_v26.md`
- Shipped solver: `app/contrib/_azcc_captcha_solver.py`
- Shipped client patch: `app/contrib/azcc_towing_client.py`
- Operator seed helper: `scripts/azcc_seed_cookie.py`
- Operator Q1/Q2 probe (NEW v27): `scripts/azcc_q1_q2_operator_probe.py`
- Solver unit-check harness (NEW v27): `outputs/_v27_solver_unit_check.py`
- Shipped commit: `47d45e3f48bfe9e0eafc24f8013829562d7de0fe` on `main`, CI #429

---

*Authored 2026-05-24 v27 by Cowork primary, autonomous pass following
user instruction "get everything done we can." ~45 min wall time:
~10 min ground-truthing the repo + reading dispatch/design/carry docs,
~10 min spot-check (install pytest deps, write direct-import harness,
run 28 cases, verify all pass), ~5 min v23 doc edits, ~15 min operator
probe script + smoke test, ~10 min v27 carry writing. ZERO repo
commits required for this work to stand on its own; ZERO production
code touched. Two operator carries (Q1 TTL, Q2 cookie scope) reduced
to one 5-min action via the unified probe script.*


---

## Section H -- Post-probe finding (added 2026-05-24 after Q1/Q2 operator run)

**Operator ran `scripts/azcc_q1_q2_operator_probe.py`. Two findings landed:**

1. **Q2 cookie scope captured.** Five cookies: two `_ga*` (analytics on `.azcc.gov`), two `ai_*` (Application Insights on `arizonabusinesscenter.azcc.gov`), and -- the surprise -- **`session_id` on `core-prod.askalden.io`**. AZCC public business search delegates session/auth to a third-party identity provider (Alden). None of the cookies are HttpOnly; SameSite is Lax/None; `session_id` has a 7-day client-side expiry.

2. **Q1 dead on arrival -- path (c) cookie-primary is broken.** Smoke test: paste captured cookies into `.env`, call `fetch_azcc_entity_search(name="TOWING")`. Result: `cookie_primed` log fires (cookies loaded into Playwright context), but the captcha modal STILL appears and the client soft-fails. Operator follow-up: in the same browser where the captcha was solved, a SECOND search to a different name (e.g., "PLUMBING") ALSO triggered a fresh captcha modal. **AZCC uses per-request captcha gating, not per-session.** There is no session state to restore; cookie-priming cannot help by construction.

**Bonus: real production bug surfaced and patched.** `app/contrib/azcc_towing_client.py` had `extra={"name": query, ...}` in four `logger.info/warning` sites. `name` is a reserved `LogRecord` attribute and raises `KeyError("Attempt to overwrite 'name' in LogRecord")` on Python 3.14. This means EVERY captcha-blocked event (the current production path 100% of the time) crashes the verifier instead of soft-failing. Renamed `name` -> `query` in all four sites. Shipped in this same commit.

### Implications for the v23 design doc

- **Path (c) cookie-primary recommendation is OBSOLETE.** Code still ships (and soft-fails harmlessly), but the cookie branch is now dead code in practice. Don't remove it -- it's behind an env var that's empty by default, so it has zero production cost.
- **Path (a) Tesseract OCR is now the only viable unblock.** v25 measured 23-25%/try; v26 measured no rate-limit so 9-15 retry rolls are feasible. To activate, install Tesseract binary on Railway image (nixpacks aptPkgs) AND set `AZCC_TESSERACT_ENABLED=1`. Also consider lifting the `get_max_retries` hard cap from 5 to 10-15 for ~90-99% effective success.
- **Q1 (cookie TTL) and Q2 (cookie scope) are now closed but moot.** Closed by the probe run; moot because cookies don't restore anything.

### Decision: PARKED

Operator ruled (2026-05-24): "we don't need to focus on registry right now, google business pages are enough. we can add this in later."

**Parking inventory:**

| Item | State | Resume path |
|------|-------|-------------|
| Shipped code (commit 47d45e3 + logging fix) | DEPLOYED, soft-fails harmlessly on captcha | No action -- verifier counts skipped_no_match for AZCC rows. |
| Cookie path | Dead code, harmless | Leave behind env var. No need to remove. |
| OCR path | Code shipped, flag default-off, binary not installed | To activate: (1) `apt-get install tesseract-ocr` in Dockerfile/nixpacks, (2) set `AZCC_TESSERACT_ENABLED=1`, (3) consider lifting `get_max_retries` cap. Expected lift: ~54-93% AZCC match rate depending on retry cap. |
| v23 design doc | v26-amended; Section 8 mentions "cookie-primary SHIPPED" | When unparking, read this Section H to learn why that recommendation is stale. |
| Operator probe script | Captures Q2 in one run; Q1 in this design is moot | Keep -- useful diagnostic if AZCC behavior ever changes. |

### Sources

- Operator probe report: `outputs/azcc_q1_q2_operator_probe_20260524T215503Z.json`
- Smoke test that proved cookies don't prime: `fetch_azcc_entity_search(name="TOWING")` returned 0 rows with `cookie_primed` log + crash on `captcha_blocked` (pre-patch) or clean soft-fail (post-patch).
- Second-search-needs-second-captcha confirmation: operator in-browser observation.
