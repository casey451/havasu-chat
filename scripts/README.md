# Scripts

Operational CLI tools, test fixtures, and run-output conventions for `havasu-chat`.

## Directory convention

| Path | Status | What goes here |
|------|--------|----------------|
| `scripts/*.py` | Tracked | Permanent CLI tools, run on demand. |
| `scripts/fixtures/` | Tracked | Test fixtures (HTML, XML, etc.) used by `tests/` and ingestion code paths. |
| `scripts/confabulation_eval_results/baselines/` | Tracked | Canonical eval baselines for regression compare. |
| `scripts/confabulation_eval_results/*` (other) | Gitignored | Ephemeral eval runs (dryruns, dated runs). |
| `scripts/output/` | Gitignored | Generic dump zone for ad-hoc tool outputs. New CLIs should write here by default. |
| `scripts/__pycache__/` | Gitignored | Python bytecode. |

`scripts/battery_results.json` and the four `scripts/voice_audit_results_2026-04-*.json` files are **legacy tracked outputs** — written directly into `scripts/` before the `scripts/output/` convention existed. Disposition decision (move to `scripts/baselines/<tool>/`, move to `scripts/output/` and `git rm`, or `git rm` outright) queued in Backlog #20.

## Tracked CLI tools (alphabetical)

- **`analyze_chat_costs.py`** — Token-cost analysis from `chat_logs` data.
- **`approve_pending_river_scene.py`** — Approves pending River Scene contributions; promotes to live catalog rows.
- **`backfill_river_scene_urls.py`** — Backfills `source_url` on River Scene events. See `docs/maintainability/river_scene_backfill_*.md` runbooks.
- **`cleanup_non_river_scene.py`** — Purges non–River-Scene catalog rows from production DB. Used by the 2026-04 RS-only cleanup; see `docs/maintainability/non_river_scene_cleanup.md`.
- **`confabulation_eval.py`** — Confabulation eval CLI. Writes to `scripts/confabulation_eval_results/<timestamp>/` by default (gitignored at the top level; `baselines/` subtree is tracked). See `docs/confabulation-eval-runbook.md`.
- **`diagnose_search.py`** — Batch queries against the live app. May write `diagnose_output.txt` to `scripts/` (legacy path; migration queued in Backlog #19).
- **`extract_tier3_queries.py`** — Extracts Tier 3 queries from chat logs.
- **`measure_hint_extractor_tokens.py`** — Measures token cost of `hint_extractor` calls.
- **`river_scene_pull.py`** — Thin wrapper over `app.contrib.river_scene_pull.run_pull` for CLI use.
- **`run_manual_phase64_verify.py`** — Manual Phase 6.4 verification harness.
- **`run_query_battery.py`** — 120-query production battery. **BROKEN** post-H1 (2026-04-29) — POSTs to legacy `/chat` which returns 404. Retargeting to `/api/chat` queued as Backlog #12.
- **`run_voice_audit.py`** — Voice-audit batch run. Writes to `scripts/voice_audit_results_<date>.json` (legacy path; migration queued in Backlog #19). Anthropic boilerplate not yet using consolidated `app/core/llm_messages` helper (Backlog #16).
- **`run_voice_spotcheck.py`** — Lighter voice spotcheck.
- **`smoke_concurrent_chat.py`** — Phase 8.2 local concurrent smoke for `POST /api/chat` (8 threads × ~3 min). Start `uvicorn` first; not a production stress test.
- **`smoke_phase52_contributions.py`** — Phase 5.2 contributions smoke.
- **`verify_queries.py`** — Short live spot-check against production.

## Notes for new tools

- Default output path for new CLIs: `scripts/output/<tool_name>_<timestamp>.<ext>`. The directory is gitignored, so accidentally-created files won't end up tracked.
- If a tool produces canonical baseline data (regression compare reference), put it under `scripts/baselines/<tool_name>/`. This subtree doesn't exist yet — first ship that adds tracked baseline data is responsible for creating it and updating this README.
- Document each new CLI here in alphabetical order with a one-line purpose plus any known caveats (broken state, pending refactor, etc.).
