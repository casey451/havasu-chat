# Phase 6.4.1 — Recommended-entity capture for `prior_entity` (delivery report)

**Status:** Implementation complete on working tree; **commit intentionally not made** — owner approval per `docs/phase-6-4-1-cursor-prompt.md` completion workflow.

## What shipped

- **`app/chat/entity_matcher.py`**
  - **`EntityMatch`** frozen dataclass: `name`, `type` (always `"provider"` for this phase), `id` (resolved `Provider.id` when present, else canonical name string — same fallback as `record_entity`).
  - **`extract_catalog_entities_from_text(text, db)`** — normalizes `text`, iterates the same in-memory `_rows` cache as `match_entity` (via `refresh_entity_matcher`), scores each canonical’s needle set with `rapidfuzz.fuzz.token_set_ratio`, keeps hits with score **strictly > 75** (parity with `match_entity`), dedupes by canonical name, returns sorted list for stable ordering.
  - **`_provider_id_for_name`** — private helper for id resolution.
- **`app/chat/unified_router.py`** — After a **successful** `_handle_ask` return (not on the exception path at lines 357–367), when `raw_sid` and `current_turn` are set and `tier_used in ("2", "3")`, call `extract_catalog_entities_from_text(text, db)`; if **exactly one** match, `record_entity(raw_sid, name, current_turn, db)`. **Precedence:** existing user-named `record_entity` (lines 306–310) still runs **before** `_handle_ask`; this block runs **after**, so recommended capture **overwrites** `prior_entity` when it fires.

**Out of scope (per owner):** Program titles and event names — **provider names only** for 6.4.1.

## Pre-flight recap

- Extraction approach **(a)** — new function over existing cache; no substring `match_entity` loop.
- Router hook, `raw_sid` / `current_turn`, precedence, and plain `str` Tier 2/3 responses — as accepted in pre-flight (`docs/phase-6-4-1-preflight-report.md`).

## Tests

| Area | File | Notes |
| --- | --- | --- |
| Matcher unit tests | `tests/test_entity_matcher.py` | New class `ExtractCatalogEntitiesFromTextTests`: one provider, two providers, empty text, no mentions, duplicate canonical in text. |
| Router integration | `tests/test_prior_entity_router.py` | Tier 3 single capture; Tier 3 two providers leaves manual prior unchanged; Tier 3 zero mentions; Tier 2 single; overwrite across turns; duplicate name in response; precedence overwrite user-named same turn; e2e pronoun + Tier 1 after Tier 3 Altitude stub. |

**Pytest:** `.\.venv\Scripts\python.exe -m pytest -q` → **726 passed**, **0 failed** (baseline was **713** after test-hygiene commit; **+13** tests).

## Voice spot-check

- **Command:** `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py --base http://127.0.0.1:8765`
- **Result:** `Smoke test: OK`; output: `scripts/output/voice_spotcheck_2026-04-21T23-08.md`
- **Note:** Report includes a **chat_logs row count mismatch** warning (0 rows vs expected 20) for the spot-check session — environment/logging detail; responses were returned for the 20-query battery. **Automated PASS/MINOR/FAIL counts** are not produced by this script; owner should confirm **≥ 19/1/0** against the markdown transcript if required for sign-off.

## Manual verification (owner)

Not run in this agent pass. Suggested checks from the Phase 6.4.1 prompt:

1. Fresh session → open-ended Tier 3 recommendation naming **one** catalog provider → follow-up “what time does it open?” binds to that provider when hours exist in catalog.
2. Fresh session → recommendation naming **multiple** providers → follow-up should stay ambiguous / concierge clarifies.
3. Fresh session → explicit Altitude (or other) query → follow-up still works (user-named path unchanged aside from overwrite rule when Tier 2/3 text also matches exactly one provider).

## Docs

- **`docs/known-issues.md`** — Removed open item for recommended-entity gap; added **Resolved** entry pointing here.
- **`docs/phase-6-4-session-memory-report.md`** — Known gap section updated to point to this report and 6.4.1 closure.

## Files changed (list)

- `app/chat/entity_matcher.py`
- `app/chat/unified_router.py`
- `tests/test_entity_matcher.py`
- `tests/test_prior_entity_router.py`
- `docs/known-issues.md`
- `docs/phase-6-4-session-memory-report.md`
- `docs/phase-6-4-1-recommended-entity-capture-report.md` (this file)

## Deviations / follow-ups

- **Provider-only:** Program and event titles are intentionally not scanned; a future phase could extend `EntityMatch` / extraction if product needs pronouns to bind to non-provider catalog objects.
- **Voice gate:** Relies on owner confirmation of numeric voice score if the repo’s spot-check script does not emit 19/1/0 automatically.

## Suggested commit message (when approved)

`Phase 6.4.1: recommended-entity capture for prior_entity`
