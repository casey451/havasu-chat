# Phase 6.1.2 — Completion summary

**Date:** 2026-04-21  
**Status:** Delivered (no commit until owner approves).

## What landed

### 1. Updated proposal — `docs/phase-6-1-2-audit-runner-proposal.md`

- Reference set is **6** (adds **ref-8.8-commit** + **ref-8.9-high**; drops **ref-8.5-low-b**).
- Totals **~56–71** payloads; cost band text adjusted; **Next step** points to 6.1.3 for paid `--execute`.

### 2. New runner — `scripts/run_voice_audit.py`

- **Tier 1:** DB-driven `try_tier1` matrix (10 sub-intents; `TIME_LOOKUP` = hours + program paths where possible). Failures append **`branch_present_not_auditable`** with the agreed log stem.
- **Tier 3:** All **25** `unified_router.route` queries from the proposal.
- **Reference:** **6** frozen §8 payloads.
- **Default:** `--dry-run` when `--execute` is not passed (safe).
- **`--execute --confirm`:** builds Tier 3 responses, then Haiku audits with `prompts/voice_audit.txt`, one JSON retry then **ERROR**, **`$2.00`** estimate abort, output **`scripts/voice_audit_results_<YYYY-MM-DD>.json`**, **`git_sha`** + **`future_live_events_null_provider_count`** in `meta`.
- **Docstring:** `DATE_LOOKUP` / `NEXT_OCCURRENCE` not auditable ⇒ treat as **seed/data gap** in **6.1.3** (aligned with §1b / `provider_id` linkage).

### 3. Delivery report — `docs/phase-6-1-2-audit-runner-report.md`

- Describes scope, behavior, 6.1.3 handoff, and embeds the **`--dry-run`** transcript.

### 4. `--dry-run` counts (representative, upgraded local DB)

| Bucket | Count |
|--------|------:|
| Tier 1 auditable | **17** |
| Tier 1 not auditable | **0** |
| Tier 3 | **25** |
| Reference | **6** |
| **Voice audit payloads** | **48** |

Upper-bound cost estimate printed by the runner: **~$0.33** (under **$2.00** ceiling).

If SQLite was behind ORM, run **`python -m alembic upgrade head`** so `hours_structured` exists.

## Git

Nothing committed or pushed; owner can say **“approved, commit and push”** when ready.

## Files to review

- `docs/phase-6-1-2-audit-runner-proposal.md`
- `docs/phase-6-1-2-audit-runner-report.md`
- `scripts/run_voice_audit.py`

## Reproduce dry-run

```powershell
.\.venv\Scripts\python.exe scripts/run_voice_audit.py --dry-run
```

On Windows, use `PYTHONIOENCODING=utf-8` if the console mangles § or dashes.

## Phase boundary

- **6.1.2** — runner + dry-run proof (this deliverable).
- **6.1.3** — `--execute --confirm` paid audit + narrative voice report.
