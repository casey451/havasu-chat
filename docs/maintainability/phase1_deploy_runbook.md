# Phase 1 Deploy Runbook — Operator-facing

**Last updated:** 2026-05-08 (Phase 1 keystone close)
**Reader assumes:** Railway operator, comfortable with `git`, no prior insider knowledge of the Phase 1 internal architecture required.
**Companion docs:** [`docs/runbook.md`](../runbook.md) (general ops); [`docs/maintainability/disclosure_renderer_spec.md`](disclosure_renderer_spec.md) §7 (spec-side rollout schedule); [`docs/maintainability/confidence_tier_integration_spec.md`](confidence_tier_integration_spec.md) §7 (same); strategy doc `ask-hava-detailed-plan.docx` (off-tree).

This runbook walks an operator through committing, deploying, verifying, and incrementally flipping the three Phase 1 feature flags. **Local tooling (Windows):** prefer the project venv — `.\.venv\Scripts\python.exe` (plain `python` on Windows can hit the Store stub). PowerShell / `curl.exe` conventions per the existing [`docs/runbook.md`](../runbook.md).

---

## Table of contents

1. [What landed in Phase 1](#1-what-landed-in-phase-1)
2. [Pre-deploy local verification](#2-pre-deploy-local-verification)
3. [Commit and push](#3-commit-and-push)
4. [Post-deploy verification (Railway)](#4-post-deploy-verification-railway)
5. [Rollback if any §4 check fails](#5-rollback-if-any-4-check-fails)
6. [Flag-flip rollout](#6-flag-flip-rollout)
   - [§6.1 Audience-signal persistence (no env var)](#61-audience-signal-persistence-no-env-var)
   - [§6.2 `FEATURE_FLAG_CONFIDENCE_TIER`](#62-feature_flag_confidence_tier)
   - [§6.3 `FEATURE_FLAG_DISCLOSURE_RENDERER`](#63-feature_flag_disclosure_renderer)
7. [Pre-existing test failures (heads-up for the next session)](#7-pre-existing-test-failures-heads-up-for-the-next-session)
8. [Operator scripts ready to run](#8-operator-scripts-ready-to-run)
9. [What's NOT in Phase 1](#9-whats-not-in-phase-1)
10. [Open follow-ups (worth tracking)](#10-open-follow-ups-worth-tracking)

---

## 1. What landed in Phase 1

Phase 1 of the strategy doc (`ask-hava-detailed-plan.docx`) is the keystone code work for visitor-mode preparation, sponsored-disclosure integrity, and confidence-tier voice fidelity. Seventeen lanes shipped 2026-05-08 across four resolved backlog items (#37, #40, #41, #42, #43). Headline deliverables: a deterministic sponsored-block renderer (`app/chat/disclosure_render.py`) wired into the Tier 3 path; a per-row confidence-tier classifier (`app/chat/confidence_tier.py`) wired into both Tier 2 (LLM formatter) and Tier 3 (context block); per-request audience classification (`visitor` / `local` / `ambiguous`) persisted to `chat_logs.audience_signal`; four `UI data correctness` fixes on `/home`; a `URGENT_NOW` sub_intent; a timezone-aware migration for verification + sponsor temporal columns plus a `TZAwareDateTime` `TypeDecorator`. The full Phase 1 surface is **149+ tests passing**.

**Feature flags shipped in Phase 1 (current default state):**

| Flag | Default | Effect when unset |
|---|---|---|
| `FEATURE_FLAG_DISCLOSURE_RENDERER` | unset → off | Sponsored-block renderer is callable but never invoked from Tier 3. Production responses are byte-identical to pre-Phase-1 LLM-only output. |
| `FEATURE_FLAG_CONFIDENCE_TIER` | unset → off | Confidence-tier classifier is callable but never invoked from Tier 2 / Tier 3. No `confidence_hedge` annotations reach the LLM; no post-LLM phone-enforcement runs. |
| Audience-signal persistence | always on, gated on column | Lane S3 computes `audience_signal` on every request; Lane S1 added `chat_logs.audience_signal`. Persistence is automatic when the column exists. No env var required. |

**Holding rule for §6:** all three flags ship in the OFF state. Behavior in production after the §3 deploy is byte-identical to behavior immediately before the deploy. Any rollout decisions are deferred to §6.

---

## 2. Pre-deploy local verification

Run these on a clean Windows checkout with the venv active. Each step is mandatory; treat any red as "do not push."

### 2.1 Run the combined Phase 1 test surface

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_home_queries.py `
  tests/test_home_queries_lane_a.py `
  tests/test_audience_signal.py `
  tests/test_disclosure_render.py `
  tests/test_disclosure_render_integration.py `
  tests/test_confidence_tier.py `
  tests/test_confidence_tier_integration_tier2.py `
  tests/test_confidence_tier_integration_tier3.py `
  tests/test_chat_route_audience_forwarding.py `
  tests/test_tier3_handler.py `
  tests/test_tier3_organic_context_wiring.py `
  tests/test_urgent_now_sub_intent.py `
  tests/test_tier3_phone_enforcement.py `
  tests/test_tz_aware_datetime.py `
  -q
```

**Expect: 149+ passed.** If any of these fail, halt and triage before pushing — they cover the Phase 1 keystone surface and any failure here is shipped-this-session work, not pre-existing.

### 2.2 Confirm the Alembic head

```powershell
.\.venv\Scripts\python.exe -m alembic heads
```

**Expect:** `b4c5d6e7f8a9 (head)` (Lane S1.1 — timezone-aware temporal columns). The always-aware switch (Backlog #41a-followup, shipped 2026-05-08) is a SQLAlchemy-layer change with no migration, so the head does NOT advance. Anything older than `b4c5d6e7f8a9` means the migration chain is incomplete on this checkout.

### 2.3 Round-trip the migration chain

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
```

**Expect:** clean downgrade then clean upgrade with no errors. If you see `duplicate column name: slot` mid-upgrade, the local dev DB is partially-migrated from prior work — wipe `events.db` (or reset `DATABASE_URL` to a fresh SQLite file) and retry.

### 2.4 Manual `/home` smoke check at three times of day

This is the cross-cutting acceptance check for the four UI-data-correctness lanes (A/B/C + Sponsor migration restore). Reproduce locally by `set TZ=America/Phoenix` and using `freezegun` if you want to spoof the clock — or just spot-check live across the day.

| Time of day (Lake Havasu local) | What to verify on `/home` |
|---|---|
| **Morning (~07:00)** | Heading reads `Today` (not `Tonight`). No event with `start_time` before `now` shows up — i.e. zero pre-dawn / overnight events leak through. |
| **Midday (~12:00)** | Heading still `Today`. Same pre-dawn check. |
| **Evening (~17:00)** | Heading reads `Tonight`. Events whose `start_time` is before 16:00 today are filtered out. |

**Cross-cutting (any time of day):**

- **Zero raw enum slugs** in body text. No `general_contractor`, `boat_repair`, `real_estate` displayed verbatim in the Spotlight or "New on Hava" cards. Every category renders as a sentence-case label (`General contractor`, `Real estate`, etc.).
- **Zero `(NXX) 555-01XX` placeholder phones** displayed as tappable `tel:` links. If a row's only phone is a placeholder, the Spotlight footer shows `Phone on profile` (gray, non-link).
- **Zero labelled-field dumps** in event blurbs. No `Date:`, `Venue:`, `Organizer:`, `Categories:` lines leak through to user-visible prose.

### 2.5 Confirm the working tree is clean

```powershell
git status
```

**Expect:** clean working tree apart from the staged Phase 1 changes you're about to commit. Untracked artifacts under `relay/` are gitignored and expected (per `relay/README.md`); any other untracked file is a smell — review before commit.

---

## 3. Commit and push

Suggested commit messages, grouped by ship boundary. Each commit is a coherent slice; you can squash if your workflow prefers a single-commit ship, but keep the slice naming so the BACKLOG ship-log entries remain traceable.

```powershell
git add app/home/queries.py app/home/router.py app/home/mock_data.py `
        app/templates/home.html app/static/styles/home.css `
        scripts/cleanup/null_placeholder_phones.py scripts/cleanup/logs/.gitkeep `
        alembic/versions/2a3b4c5d6e7f_evolve_sponsors_for_four_tier_inventory.py `
        tests/test_home_queries.py tests/test_home_queries_lane_a.py pyproject.toml
git commit -m "feat(home): UI data correctness pass -- fixes #1-#4"
```

```powershell
git add app/chat/disclosure_render.py app/chat/tier3_handler.py app/chat/unified_router.py `
        tests/test_disclosure_render.py tests/test_disclosure_render_integration.py `
        tests/test_tier3_organic_context_wiring.py tests/fixtures/disclosure_regression_golden.json
git commit -m "feat(chat): disclosure renderer module + Tier 3 integration + organic_context wiring"
```

```powershell
git add app/chat/confidence_tier.py app/chat/tier2_formatter.py app/chat/context_builder.py `
        prompts/tier2_formatter.txt prompts/system_prompt.txt `
        tests/test_confidence_tier.py tests/test_confidence_tier_integration_tier2.py `
        tests/test_confidence_tier_integration_tier3.py tests/test_tier3_phone_enforcement.py
git commit -m "feat(chat): confidence-tier classifier + Tier 2 + Tier 3 integration + phone enforcement"
```

```powershell
git add app/chat/audience_signal.py app/api/routes/chat.py app/db/chat_logging.py `
        tests/test_audience_signal.py tests/test_chat_route_audience_forwarding.py
git commit -m "feat(chat): audience signal logging + API route forwarding (+ chat_logging WARN cleanup, 2026-05-08)"
```

```powershell
git add app/chat/intent_classifier.py app/chat/disclosure_render.py `
        tests/test_urgent_now_sub_intent.py
git commit -m "feat(chat): URGENT_NOW sub_intent for emergency-urgent placement regime"
```

```powershell
git add alembic/versions/f7e8d9c0b1a2_add_verification_and_audience_columns.py `
        alembic/versions/b4c5d6e7f8a9_timezone_aware_temporal_columns.py `
        app/db/models.py app/db/types.py tests/test_tz_aware_datetime.py `
        app/chat/context_builder.py
git commit -m "feat(db): schema additions migration + timezone-aware columns + TZAwareDateTime TypeDecorator + #41a-followup always-aware on read"
```

```powershell
git add docs/maintainability/disclosure_renderer_spec.md `
        docs/maintainability/confidence_tier_integration_spec.md `
        docs/maintainability/phase1_deploy_runbook.md `
        docs/BACKLOG.md docs/STATE.md
git commit -m "docs: Phase 1 specs (disclosure renderer + confidence-tier integration) + lessons-learned"
```

(Adjust the file lists to match your local diff — these are anchored on the canonical Lane scope. If you're squashing, use a single `feat: Phase 1 keystone close (lanes A/B/C, S1, S1.1, S2, S3, S3.1, X1, X2, X2.1, CT1, CT2.A, CT2.B, CT2.B.1, #41a, #43)` message.)

### 3.1 Push to `main`

```powershell
git push origin main
```

**Railway auto-deploys on push to `main`.** No manual deploy step. Watch the Railway dashboard: project → service → Deployments. The new build will compile and roll over inside ~3–5 minutes typical.

### 3.2 CI verification

Per `WORKING_AGREEMENT.md`:

```powershell
gh run list --branch main --limit 1 --json conclusion,headSha,databaseId
```

**Expect:** the most recent run's `conclusion` is `success`, `headSha` matches your push, and `databaseId` is fresh. If `conclusion` is `failure` or `null` (still running), wait for the run to settle before proceeding to §4.

---

## 4. Post-deploy verification (Railway)

Run these against production after Railway shows the deploy is green. **All four checks must pass before any flag-flip in §6.**

### 4.1 Health endpoint

```powershell
curl.exe -sS -i "https://havasu-chat-production.up.railway.app/health"
```

**Expect:** HTTP 200, JSON body `{"status":"ok","db_connected":true,"event_count":<n>}`. If `db_connected` is `false`, the app deployed but lost DB connectivity — open Railway Postgres status before chasing app-only bugs.

### 4.2 Production-DB Alembic head matches local

There are two ways to confirm. Pick the one your team uses; if neither is set up, fall back to the SQL inspection at the bottom of this section.

**Option A — Alembic against the Railway DB URL** (preferred):

```powershell
$env:DATABASE_URL = "<paste Railway Postgres URL here>"
.\.venv\Scripts\python.exe -m alembic heads
Remove-Item env:DATABASE_URL
```

**Expect:** `b4c5d6e7f8a9 (head)`. **Do not log the URL** anywhere; unset the env var as soon as you're done.

**Option B — SQL inspection via `psql`**:

```sql
SELECT version_num FROM alembic_version;
```

**Expect:** a single row, `version_num = 'b4c5d6e7f8a9'`.

If the production head lags behind local (e.g. shows `f7e8d9c0b1a2` or older), the deploy didn't run migrations. Check Railway logs for the migration step; the app boots run-on-startup migrations via standard Alembic plumbing.

### 4.3 Live `/home` smoke check on the production URL

Repeat the §2.4 three-time-of-day pass on `https://havasu-chat-production.up.railway.app/home`. Same checklist:

- Heading reads `Today` before 16:00 Lake Havasu local, `Tonight` after.
- Zero pre-dawn events under either heading.
- Zero raw enum slugs in body text.
- Zero `(NXX) 555-01XX` placeholder phones rendered as tappable links.
- Zero labelled-field dumps in event blurbs.

Run this **at all three windows** (morning / midday / evening) — the 16:00 boundary is the only one that's clock-dependent, and you only see it cross live.

### 4.4 Live `POST /api/chat` smoke

A generic-category query exercises the Tier-2-fallback and Tier 3 paths. With both Phase 1 flags off, the response should be byte-identical to pre-deploy behavior.

```powershell
$body = '{"message":"find a plumber","session_id":"smoke-1"}'
curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
  -H "Content-Type: application/json" `
  --data-binary $body
```

**Expect:** HTTP 200, response shape unchanged from pre-deploy. **No `Sponsored:` text in the body** (flag is off). **No `(as of last week)` or `(recommend calling to confirm)` parentheticals** (flag is off). The response should read like Hava's pre-Phase-1 voice.

If any of §4.1–§4.4 fails, jump to §5.

---

## 5. Rollback if any §4 check fails

Phase 1 ships as a series of commits on `main`. Rollback is `git revert` over the range, then push. The Railway auto-deploy on push handles the cutover.

### 5.1 Identify the range

The Phase 1 ship boundary is everything after the last green commit. From the local tree:

```powershell
git log --oneline --since="2026-05-08 00:00 -0700"
```

The earliest hash in that list is the start of the range. Call the earliest `<phase1_first>` and `HEAD` the last.

### 5.2 Revert

```powershell
git revert --no-edit <phase1_first>^..HEAD
git push origin main
```

The `^` notation includes the first hash in the range. If your shell parses `^` (PowerShell does not, but `bash`-via-Git-Bash will need quoting), wrap it: `"$phase1_first^..HEAD"`.

### 5.3 Force-push only if the auto-deploy has wedged

`git revert` produces forward commits — no force-push needed in the normal case. **Only force-push** (`git push --force-with-lease origin main`) if the revert series itself fails CI and you need to drop it surgically; in that case, communicate the force-push first and prefer `--force-with-lease` over `--force` to avoid clobbering concurrent commits.

### 5.4 Re-run §4 against the reverted state

After the revert deploy is green, repeat §4.1–§4.4. If §4.4 now reads byte-identical to pre-Phase-1 behavior, the rollback is complete.

---

## 6. Flag-flip rollout

This is the operationally important section. The three flags flip in order. Flip one, observe, then flip the next — never two on the same day unless you're confident in the prior flag's bake.

### 6.1 Audience-signal persistence (no env var)

Already gated on column existence; Lane S1 shipped the column and Lane S3 + S3.1 shipped the classifier and the FastAPI forwarding. **Persistence is automatic** the moment the deploy lands — no Railway env var needed.

**What to verify after §4 is clean:**

1. **Confirm `chat_logs.audience_signal` exists in production.** Via `psql`:

   ```sql
   SELECT column_name, data_type
   FROM information_schema.columns
   WHERE table_name = 'chat_logs' AND column_name = 'audience_signal';
   ```

   **Expect:** one row with `column_name = 'audience_signal'`, `data_type = 'character varying'` (or similar). If the row is empty, Lane S1's migration `f7e8d9c0b1a2` didn't apply — go back to §4.2.

2. **Verify a few new chat_logs rows post-deploy carry non-null `audience_signal`.** Send a chat through the production UI or `/api/chat`, then:

   ```sql
   SELECT id, audience_signal, mode, created_at
   FROM chat_logs
   WHERE created_at >= now() - interval '5 minutes'
     AND role = 'user'
   ORDER BY created_at DESC
   LIMIT 5;
   ```

   **Expect:** at least one row where `audience_signal IN ('visitor', 'local', 'ambiguous')`. If every row reads `NULL`, either (a) the column exists but the WARN-once defensive path tripped (check `app/db/chat_logging.py` warn log), or (b) the FastAPI forwarding (Lane S3.1) didn't deploy. In case (b), §5 the audience-signal commit specifically.

3. **Verify the geo bucket isn't pinned to `unknown`.** Lane S3.1 is the difference between `geo_bucket="unknown"` (every request before the lane) and real CDN-header-driven buckets. There's no separate column for `geo_bucket` — it's an internal step inside `audience_signal.classify_audience` — but the visitor/local/ambiguous distribution should reflect actual visitor geography. After ~24 hours of traffic, run:

   ```sql
   SELECT audience_signal, COUNT(*) AS n
   FROM chat_logs
   WHERE created_at >= now() - interval '24 hours'
     AND audience_signal IS NOT NULL
   GROUP BY audience_signal;
   ```

   **Expect:** a non-trivial fraction of `local` rows (Lake Havasu locals are a real share of traffic). If 100% of rows are `ambiguous`, the FastAPI forwarding is suspect.

**No env-var rollback for this flag.** Persistence reverts only if you (a) drop the column (don't) or (b) revert Lane S3 / S3.1 commits via §5. If audience-signal data turns out wrong but isn't harming users (it's logging-only, not behavior-driving in Phase 1), prefer to leave it on and triage at the classifier in `app/chat/audience_signal.py`.

---

### 6.2 `FEATURE_FLAG_CONFIDENCE_TIER`

Flip second. Tier 2 + Tier 3 LLM paths begin annotating rows with confidence-hedge fragments and post-processing for LOW-tier phone enforcement. Both tiers light up together — the spec recommends 4–6 weeks of CT2.A flag-on observability before CT2.B in a phased world, but since CT2.A and CT2.B both shipped this session, you flip them together. Watch the response register on a sample of LOW-classified rows.

**Set in Railway env vars:**

```
FEATURE_FLAG_CONFIDENCE_TIER=true
```

Save → Railway redeploys. Wait for green.

**What to watch:**

- Tier 2 LLM-formatter responses now include `confidence_hedge` instructions in the prompt. The prompt edit in `prompts/tier2_formatter.txt` adds an `EXCEPTION (confidence_hedge)` clause; the LLM is instructed to inline the canonical fragment near the relevant fact and never paraphrase.
- HIGH-tier rows speak plainly (no hedge fragment).
- MEDIUM-tier rows include the literal `as of last week`.
- LOW-tier rows include the literal `recommend calling to confirm` plus the row's phone (deterministic post-processor `_enforce_low_tier_phone` runs after the LLM if the LLM omits both).

**Verification:**

A live `POST /api/chat` with a query that hits a known stale row exercises the LOW path. Pick a Provider whose `last_verified_at` is `> 30 days old` or `NULL`; pick a query that resolves to that Provider in Tier 2 or Tier 3.

```powershell
$body = '{"message":"<query that hits a known-stale row>","session_id":"ct-smoke-1"}'
curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
  -H "Content-Type: application/json" `
  --data-binary $body
```

**Expect (Tier 2 LOW path):** response body contains the literal `recommend calling to confirm` or `Their listed number is <phone> -- recommend calling to confirm.` (the canonical fallback the post-processor emits when the LLM dropped both the phone and the hedge).

**Expect (Tier 3 LOW path):** same `recommend calling to confirm` fragment surfaced near the Provider's facts. The Tier 3 post-processor (Lane CT2.B.1) shares semantics with Tier 2's `_enforce_low_tier_phone`.

**Expect (HIGH tier rows):** no hedge fragment. No drift in voice. Hava reads plainly.

**Hedge-leakage check** (manual, post-bake):

```sql
SELECT id, message, tier_used, created_at
FROM chat_logs
WHERE role = 'assistant'
  AND created_at >= now() - interval '24 hours'
  AND (message ILIKE '%recommend calling to confirm%'
       OR message ILIKE '%as of last week%')
ORDER BY created_at DESC
LIMIT 50;
```

Sample 10–20 rows manually. **Confirm:** every flagged row corresponds to a query whose retrieval set contained at least one MEDIUM/LOW row. If a hedge appears on a response whose retrieval set was all HIGH, that's hedge leakage — report and consider §6.2 rollback.

**Rollback:** unset (or set `=false`) the Railway env var → redeploy. Tier 2 + Tier 3 revert to byte-identical pre-CT2 behavior. **No DB migration to roll back, no prompt-file rollback** (the EXCEPTION clauses in `prompts/tier2_formatter.txt` and `prompts/system_prompt.txt` are no-ops when the flag is off because the field they reference is never written into the LLM context).

---

### 6.3 `FEATURE_FLAG_DISCLOSURE_RENDERER`

Flip third — only after CT2 has baked at least a few days and the §6.2 hedge-leakage check is clean. Sponsored placement begins appearing in chat responses for SPONSOR-eligible queries.

**Set in Railway env vars:**

```
FEATURE_FLAG_DISCLOSURE_RENDERER=true
```

Save → Railway redeploys. Wait for green.

**What to watch:**

- **Sponsored placement appears for SPONSOR-eligible queries.** The renderer reads `Sponsor` rows where `status='live'` (and, for emergency-urgent, `verified_fields_present=true`).
- **Disclosure word always reads literally `Sponsored`** — no drift to `Featured` / `Partner` / `Recommended`. The module constant `DISCLOSURE_WORD = "Sponsored"` in `app/chat/disclosure_render.py` is the single source of truth.
- **Three placement regimes (per `disclosure_renderer_spec.md` §1.2):**

  | Regime | Trigger | Behavior |
  |---|---|---|
  | `SPECIFIC_QUALITY` | Specific-quality queries (e.g. *"Best plumber for older Toyotas"*) | **No sponsored block.** Renderer suppresses. |
  | `GENERIC_CATEGORY` | Generic-category queries (e.g. *"I need a plumber"*) | Block injected **after the first sentence** of LLM response. |
  | `EMERGENCY_URGENT` | Emergency / urgent / "right now" queries (e.g. *"plumber right now"*) | Block **prepended** to LLM response — *provided* organic Provider rows exist. Without them, the block suppresses. Lane #43 widened the sub_intent classifier to catch the "right now" / "urgent" / "ASAP" / "emergency" / "immediately" phrasing pattern. |

**Verification:**

> **Phase 1 scope note:** of the three regimes above, only `EMERGENCY_URGENT` and `SPECIFIC_QUALITY` have production sub_intent triggers in Phase 1. `GENERIC_CATEGORY` is wired in `disclosure_render.select_placement_regime` but is reserved for `{GENERAL_QUESTION, RECOMMENDATION, DISCOVERY}` sub_intents which are not emitted by `intent_classifier._ask_sub_intent` until **Lane X3 (Phase 2)** lands. So in Phase 1 the operator should expect `EMERGENCY_URGENT` to render and `GENERIC_CATEGORY` queries to fall through to LLM-only output. Smoke #1 below is the explicit no-render check that documents this; smoke #3 is the positive case.

1. **Generic-category query** — should NOT include the literal `Sponsored` in Phase 1 (regime is reserved for Phase 2 / Lane X3):

   ```powershell
   $body = '{"message":"I need a plumber","session_id":"dr-smoke-1"}'
   curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
     -H "Content-Type: application/json" `
     --data-binary $body
   ```

   **Expect:** response body does **not** contain `Sponsored`. The query classifies into a Tier-1 lookup or `OPEN_ENDED` sub_intent, neither of which maps to `GENERIC_CATEGORY` in Phase 1. If `Sponsored` appears here, the regime classifier is firing on an unexpected sub_intent — file as a bug, do not roll back.

2. **Specific-quality query** — should NOT include the literal:

   ```powershell
   $body = '{"message":"Best plumber for older Toyotas","session_id":"dr-smoke-2"}'
   curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
     -H "Content-Type: application/json" `
     --data-binary $body
   ```

   **Expect:** response body does **not** contain `Sponsored`. Pure LLM output. If `Sponsored` leaks into a SPECIFIC_QUALITY response, the regime classifier is misfiring — file as a bug, do not roll back unless it persists across more than one query.

3. **Emergency-urgent query** — should prepend `Sponsored:` block when organic Provider rows exist:

   ```powershell
   $body = '{"message":"plumber right now","session_id":"dr-smoke-3"}'
   curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
     -H "Content-Type: application/json" `
     --data-binary $body
   ```

   **Expect:** if the Provider catalog has rows whose name or category overlaps `plumber`, the response begins with the sponsored block. If not, the block suppresses and the response is LLM-only — that's by design (the renderer's `_eligible` check requires `bool(organic_rows)` for emergency-urgent per spec §1.3).

**Disclosure-word audit** (post-bake):

```sql
SELECT id, message, tier_used, created_at
FROM chat_logs
WHERE role = 'assistant'
  AND created_at >= now() - interval '24 hours'
  AND message ILIKE '%Sponsored%'
ORDER BY created_at DESC
LIMIT 50;
```

Sample 10–20 rows manually. **Confirm:**

- **Every flagged row uses the literal `Sponsored`.** If you see `Featured`, `Partner`, `Recommended`, `Promoted`, `Highlight`, `Spotlight`, etc. embedded in the body where the disclosure should be, that's drift. The renderer constant should be the only source — but the LLM may have emitted a near-synonym in adjacent prose; check that the disclosure block itself uses the literal.
- **Tone allowlist not violated.** The renderer's `_check_tone_allowlist` rejects sponsor copy with superlatives, marketing voice, comparatives, false scarcity. If a sponsored block makes it through with `best`, `top-rated`, `award-winning`, the allowlist failed open — file as a bug.

**Rollback:** unset (or set `=false`) the Railway env var → redeploy. Tier 3 reverts to LLM-only, no sponsored injection, no organic-context lookup. Cached LLM responses in `LlmResponseCache` are sponsor-free by construction (Lane X2 explicitly stores LLM text without sponsor injection so cache hits are clean on flag flip), so flipping back doesn't leave stale sponsored text in user-visible output.

---

## 7. Full suite status (heads-up for the next session)

**As of session close 2026-05-08, the full test suite is GREEN:** `1314 passed, 0 failed`. The 12 pre-existing failures the previous handoff referenced have all been closed by post-Phase-1-keystone work in the same session: a test-suite triage pass (6 fixes across `test_phase2_integration.py`, `test_phase8_10_river_scene.py`, `test_unified_router.py`), a cache-pollution autouse fixture in `test_phase2_integration.py`, the entity-matcher #44 near-match severe-typo fix in `app/chat/entity_matcher.py`, and the #41b cleanup of SQLite-naive temporal workarounds.

**Operator action:** treat any failure outside the §2.1 Phase 1 surface as a new regression, not a known-bad. The full-suite green is the reference baseline.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

**Expect:** `1314 passed` (or higher if new tests have been added since 2026-05-08).

**Known caveat — Backlog #46 (entity-matcher #44 connector-word bypass):** the #44 fix passes all 1314 tests but an independent code-reviewer + voice-battery investigation found two real production wrong-entity matches against the live 2,232-provider catalog: `"sloane number"` → `Number One Nails` (75.9), `"phone for addrss"` → `Ross Dress for Less` (72.7). These are not exercised by the current test suite. **Mitigations:** the affected query patterns are severe typos against needles containing 3-char connector words (`"and"`, `"the"`, `"for"`, `"jiu"`, `"bmx"`); not common queries. **Do not block deploy on this** — file Backlog #46 as the follow-up. See `docs/BACKLOG.md` for the full reproduction recipe and proposed fix.

---

## 8. Operator scripts ready to run

### 8.1 `scripts/cleanup/null_placeholder_phones.py` — Lane C cleanup

Idempotent cleanup that nulls out `(NXX) 555-01XX`-pattern phones on `providers.phone`. Lane C added the runtime suppression (the rendering layer hides placeholder phones); this script also nulls them at rest so the column is clean for any downstream use.

**Always dry-run first:**

```powershell
$env:DATABASE_URL = "<paste Railway Postgres URL here>"
.\.venv\Scripts\python.exe -m scripts.cleanup.null_placeholder_phones --dry-run
Remove-Item env:DATABASE_URL
```

**Expect:** the script writes a timestamped log file under `scripts/cleanup/logs/` listing every `Provider.id` whose `phone` matches the placeholder pattern. **No DB writes.** Review the log; spot-check a handful of rows by `id` to confirm they really do match the placeholder pattern (no false positives).

**Apply after approval:**

```powershell
$env:DATABASE_URL = "<paste Railway Postgres URL here>"
.\.venv\Scripts\python.exe -m scripts.cleanup.null_placeholder_phones --apply
Remove-Item env:DATABASE_URL
```

**Expect:** the script nulls every flagged `providers.phone` value, writes a second log (apply log) under `scripts/cleanup/logs/`, and reports the row count. **Idempotent** — re-running `--apply` after a successful run does nothing (no rows match).

**Backup before apply.** Railway Postgres "backup before destructive migration" rule applies here — confirm a recent backup exists or take a one-off `pg_dump` first.

### 8.2 `scripts/ingest/validate_enrichment_csv.py` + `scripts/ingest/ingest_enrichment_csv.py` — 50-business enrichment sprint

The Phase 1 schema additions (Lane S1: `Provider.last_verified_at` + `Provider.verification_method`) are now usable. The enrichment toolchain shipped 2026-05-08 lets the operator fill a CSV template, validate it, and idempotently upsert into the Provider catalog. Three artifacts:

- **`templates/enrichment/business_enrichment_template.csv`** — header-only CSV with the columns the operator must fill.
- **`templates/enrichment/README.md`** — operator-facing column-by-column documentation. Read this first.
- **`scripts/ingest/validate_enrichment_csv.py`** — standalone CLI; refuses to write anything. Runs row-by-row checks (NANP phone, `CATEGORY_LABELS` membership, ISO-8601 `last_verified_at` not in the future, 80–400-char Hava-voice description, basic email shape, `verification_method` enum membership). Prints PASS/FAIL per row, exits non-zero on any failure.
- **`scripts/ingest/ingest_enrichment_csv.py`** — standalone CLI; calls the validator first, then idempotently upserts into Provider keyed on case-insensitive `(provider_name, category)`. Sets `last_verified_at` + `verification_method` on every row. Has a `--dry-run` flag.

**Standard workflow:**

```powershell
# 1. Operator copies the template, fills it out
Copy-Item templates/enrichment/business_enrichment_template.csv .\my_enrichment_2026-05-09.csv

# 2. Validate first (no DB writes)
.\.venv\Scripts\python.exe -m scripts.ingest.validate_enrichment_csv .\my_enrichment_2026-05-09.csv

# 3. Dry-run the ingest (no DB writes)
.\.venv\Scripts\python.exe -m scripts.ingest.ingest_enrichment_csv .\my_enrichment_2026-05-09.csv --dry-run

# 4. Apply (writes to DB; reads $env:DATABASE_URL)
$env:DATABASE_URL = "<paste Railway Postgres URL here>"
.\.venv\Scripts\python.exe -m scripts.ingest.ingest_enrichment_csv .\my_enrichment_2026-05-09.csv
Remove-Item env:DATABASE_URL
```

**Tests:** `tests/test_enrichment_ingestion.py` — 16 passing covering all validator rejection branches plus insert / idempotent-update / dry-run.

**Known wrinkle — Backlog #45 (verification_method vocab mapping):** the operator-facing CSV vocab is `phone_call / in_person / web_form_submission / email_confirmation` for clarity. The DB CHECK constraint (migration `f7e8d9c0b1a2`) allows `manual / scraper / owner_confirmed / npi_registry / none`. The ingest script maps `phone_call`/`in_person` → `manual` and `web_form_submission`/`email_confirmation` → `owner_confirmed`. This is a lossy compression — phone vs in-person becomes indistinguishable in the DB. Acceptable for the first 50-business sprint; tracked as Backlog #45 (expand the CHECK constraint via new migration to preserve audit fidelity).

---

## 9. What's NOT in Phase 1

These are deferred to Phase 2 (or are operator-driven, not code) — flipping the §6 flags will **not** activate any of them.

- **Visitor-mode UI.** Audience signal logging is in place (Lane S3 + S3.1 + S1) but no UI changes ride on it. Phase 2 deliverable.
- **Tier 2 disclosure renderer integration (Lane X3).** Sponsored blocks render only on the Tier 3 path in Phase 1. Tier 2 (LLM formatter) does not call the disclosure renderer. Phase 2 deliverable per `disclosure_renderer_spec.md` §5.1.
- **Audience-signal-driven placement-regime selection (Backlog #39).** The disclosure renderer selects regime based on intent + sub_intent only — no audience input. Phase 2 deliverable; precondition is 4–6 weeks of `chat_logs.audience_signal` data and X1 + X2 in production with the flag on.
- **Phase 2 enrichment work** — 50 businesses, 30 tourism operators. **Operator-driven**, not code. Tracked separately in the strategy doc.
- **HALT 3 close-out review** — pending. Not a code lane; tracked in the project_index / BACKLOG.
- **Tier 2 catalog render hedging.** Deterministic event renderer (`tier2_catalog_render.py`) does not surface verification status, so hedges don't apply there. Out of scope per `confidence_tier_integration_spec.md` §5.
- **Age-aware hedge variance** ("verified yesterday" vs "verified two weeks ago"). Phase 1 ships the canonical-fragment-only model. Refinement is a future deliverable.
- **LLM rephrasing of canonical hedge fragments.** Disallowed by the spec. The post-processor enforces the literal.

---

## 10. Open follow-ups (worth tracking but not blocking flag-flip)

These are filed in `docs/BACKLOG.md` and are **not** flag-flip blockers. Track them for the next operator session.

- **Backlog #38 — `audience_signal.py::classify_audience` parameter naming.** OPEN, low priority. Parameter is named `request_time_utc` but is passed `now_lake_havasu()` (a Phoenix-tz aware datetime) and the bucket boundaries are local-clock semantics. Rename to `request_time_local` or `request_time` across `app/chat/audience_signal.py`, the call site in `app/chat/unified_router.py`, and `tests/test_audience_signal.py`. Anchored Edit only.

- **Backlog #41a / #41a-followup / #41b — RESOLVED 2026-05-08.** The TZAwareDateTime TypeDecorator now returns aware Lake-Havasu datetimes on read (#41a-followup); the `try/except TypeError` defensive workarounds in `confidence_tier.py`, `disclosure_render.py::_temporal_overlap`, `tier3_handler.py::_maybe_render_sponsored_block` were verified not load-bearing post-#41a-followup (#41b — no diff applied; working tree already matched target).

- **Backlog #45 — Expand `verification_method` CHECK constraint** (filed 2026-05-08). The enrichment ingest script (§8.2) compresses operator vocab into the existing five-value DB enum, losing audit fidelity (phone vs in-person becomes `manual` for both). Phase 2 cleanup: new migration that adds the operator vocab to the CHECK constraint while preserving backward compat with legacy values.

- **Backlog #46 — Entity matcher #44 connector-word bypass** (filed 2026-05-08, see §7 caveat). The `_best_partial_ratio_per_needle_token` helper in `app/chat/entity_matcher.py` produces real wrong-entity matches on severe-typo queries against needles containing 3-char connector words. Two confirmed live regressions: `"sloane number"` → `Number One Nails`; `"phone for addrss"` → `Ross Dress for Less`. Recommended fix per voice-battery agent: require matched needle word to be ≥ `len(query_token) - 2`, OR raise `_TYPO_PER_TOKEN_THRESHOLD` to 85 for short needle tokens. Spec/ship lane.

- **Backlog #2 — `_time_bucket_first_hits` and broad `span`.** OPEN, pre-Phase-1. Tracked in `BACKLOG.md`.

- **Backlog #18 — Repo hygiene & documentation hierarchy (PM phases A–D).** OPEN, pre-Phase-1.

- **Lane X3 — Tier 2 formatter integration of the disclosure renderer.** Deferred to Phase 2 per `disclosure_renderer_spec.md` §5.1, §9.

- **Homepage `DISCLOSURE_WORD` consistency pass.** Spotlight cards on `/home` still use the literal `Spotlight` badge; aligning to `DISCLOSURE_WORD` is a separate small ship. Filed in the Lane S2 ship-log.

- **Observability instrumentation for the disclosure renderer.** Log every render decision (regime, sponsor picked, tone pass/fail) to `chat_logs` as structured JSON or a new field. Phase 2 lever per spec §7.2.

---

## Appendix A — Quick reference: the three flags at a glance

| Flag | Default | What it gates | Rollback |
|---|---|---|---|
| Audience-signal persistence | always on (column-gated) | `chat_logs.audience_signal` writes | revert Lane S3 / S3.1 commits |
| `FEATURE_FLAG_CONFIDENCE_TIER` | unset → off | Per-row classification + `confidence_hedge` annotation in Tier 2 prompt; per-row hedge suffix in Tier 3 context block; post-LLM phone enforcement on both | unset env var → redeploy |
| `FEATURE_FLAG_DISCLOSURE_RENDERER` | unset → off | Sponsored block renders for GENERIC_CATEGORY (after first sentence) and EMERGENCY_URGENT (prepended, requires organic rows) on Tier 3 | unset env var → redeploy |

## Appendix B — Files that gate observability checks

- **`chat_logs` table** — every observability query in §6 runs against this table. Schema additions in Lane S1 (`f7e8d9c0b1a2`): `audience_signal` column. No other Phase 1 columns added.
- **`scripts/cleanup/logs/`** — Lane C cleanup script writes timestamped logs here. Gitkeep'd; logs themselves are not committed.
- **Railway Logs / Sentry** — for app-level WARN-once messages from `app/db/chat_logging.py` (audience-signal column missing) and from `app/chat/tier3_handler.py::_maybe_render_sponsored_block` (renderer raised, falling through to LLM-only). Both are non-blocking.

## Appendix C — Strategy doc cross-reference

The strategy doc (`ask-hava-detailed-plan.docx`, off-tree) defines Phase 1 as the keystone code work for visitor-mode preparation, sponsored-disclosure integrity, and confidence-tier voice fidelity. The three flags shipped this session are the operator levers for that scope. **Phase 2** picks up: visitor-mode UI, Tier 2 disclosure renderer integration, audience-signal-driven placement-regime selection, enrichment work (50 businesses + 30 tourism operators), homepage `DISCLOSURE_WORD` consistency pass, and observability instrumentation. **Phase 3** is the post-bake validation gate before any of those Phase 2 levers move to default-on.

---

*Phase 1 deploy runbook — `docs/maintainability/phase1_deploy_runbook.md`. Authored 2026-05-08 against the seventeen-lane Phase 1 close. Companion to `docs/runbook.md` (general ops); supersedes nothing.*
