# Redesign Phase 2 split & merge report (2026-05-08)

Session notes: Phase 2B migration fix, alembic verification, pytest, branch HEADs, Phase 1 merge to `main`, and opened PRs.

## Alembic

### Round-trip on a clean SQLite file — **PASS**

Used a temporary database:

```powershell
$env:DATABASE_URL = "sqlite:///$env:TEMP/havasu_alembic_roundtrip.sqlite"
```

Then:

- `python -m alembic upgrade head` → ends at **`2a3b4c5d6e7f (head)`**
- `python -m alembic downgrade 1a2b3c4d5e6f` → OK
- `python -m alembic upgrade head` → OK

Note: `alembic` alone may not be on `PATH` on Windows; use **`python -m alembic`**.

### Default `data/events.db`

First **`upgrade head`** failed with **`duplicate column name: slot`** because the table already had Phase 2B columns while **`alembic_version`** was still at **`1a2b3c4d5e6f`** (partial / manual application earlier).

Then **`alembic stamp 2a3b4c5d6e7f`** was applied while the Phase 2B migration existed on disk; after switching to **`main`** (which does not include that revision file), **`alembic`** could not resolve **`2a3b4c5d6e7f`**. **`alembic_version`** was corrected **directly in SQLite** back to **`1a2b3c4d5e6f`** so **`python -m alembic current`** works on **`main`**.

### Important caveat

The **`sponsors`** table **still has** columns such as **`slot`** (physical schema ahead of the stamped revision). After Phase 2B merges, a plain **`upgrade head`** on this DB may hit **duplicate column** again unless you **migrate from a fresh DB**, **`stamp`** appropriately on the branch that contains **`2a3b…`**, or otherwise reconcile schema vs revision.

---

## Pytest (`python -m pytest -q`)

Phase 2B **without** the test-drift branch had **13 failed, 1133 passed** (many assertion / voice-contract mismatches because **`tests/voice-copy-drift-cleanup`** was not in that history).

For a realistic baseline, **`origin/tests/voice-copy-drift-cleanup`** was merged **locally** into **`redesign/phase-2b-sponsor-schema-and-marquee`** **only to run tests**, then **`git reset --hard 3c55cf9`** removed that merge so nothing extra was pushed.

With that temporary merge: **`1135 passed`, `11 failed`**. **None** of the failures mention **sponsors**, **marquee**, or **migration** tracebacks.

### Failures (with failure type)

| Test | Type |
|------|------|
| `EntityMatcherNearMatchTests.test_severe_typo_returns_near_match` | `AssertionError` — near-match `None` |
| `test_oos_end_to_end_verbatim_redirect` × 3 | `AssertionError` — `mode` / `sub_intent` vs router (`chat` vs `ask`, `OPEN_ENDED` vs `OUT_OF_SCOPE`) |
| `test_placeholder_tier_for_non_chat_modes` | `AssertionError` — **`correction` vs `intake`** for tier |
| `test_tier3_timeout_triggers_graceful_fallback` | `AssertionError` — response vs **`FALLBACK_MESSAGE`** |
| `test_api_chat_tier3_graceful_when_llm_fails` | same |
| `test_api_chat_graceful_when_build_context_raises` | same |
| `test_near_match_typo_returns_did_you_mean` | `AssertionError` — expected entity name in gap reply |
| `test_river_scene_pull_auto_approval_sets_end_date_for_multi_day` | `AssertionError` — **`row is None`** / import count 0 |
| `test_render_multiple_events_header_and_numbered_prefixes` | `AssertionError` — catalog prefix vs **`startswith("2 events:…")`** |

That is **11 failures**, not ~6 — still **no sponsor/migration failures**, so push proceeded per the session rule.

---

## Branch HEADs (after `--force-with-lease` on Phase 2B)

| Branch | HEAD |
|--------|------|
| `origin/redesign/phase-2b-sponsor-schema-and-marquee` | `3c55cf9814af385d4ffabd79a0043b5ee1e62b12` |
| `origin/redesign/phase-2a-time-of-day-labels` | `bac6a2cff55ff2753474b9fce2f3fc57a427847b` |
| `origin/tests/voice-copy-drift-cleanup` | `a6840ce94d297cdb0e28cccfc5c575de9e1f4d35` |
| `origin/main` (after Phase 1 merge) | `398a6f5b1aa6091bb3b516bcbbab5ca36c2d17b7` |

Amended Phase 2B commit message: **Phase 2B: evolve Sponsor schema for 4-tier inventory + Marquee partial (per §B5.6)** at **`3c55cf9`**.

---

## Phase 1 on `main`

Merged cleanly with:

```bash
git merge --no-ff redesign/phase-1-hero-and-palette -m "Merge Phase 1: Ocean tide hero + content cleanup"
```

Pushed to **`origin/main`** (`2edffc0` → **`398a6f5`**). The merge brought in the Phase 1 branch tip, including **`b4f5ebb`** (“tests: update stale assertions…”), so **`main`** may already overlap part of **`tests/voice-copy-drift-cleanup`**.

---

## Pull requests opened (→ `main`)

- [PR #2](https://github.com/casey451/havasu-chat/pull/2) — `tests/voice-copy-drift-cleanup`
- [PR #3](https://github.com/casey451/havasu-chat/pull/3) — `redesign/phase-2a-time-of-day-labels`
- [PR #4](https://github.com/casey451/havasu-chat/pull/4) — `redesign/phase-2b-sponsor-schema-and-marquee`

---

## Follow-up

When working again on **`redesign/phase-2b-sponsor-schema-and-marquee`**, confirm **`data/events.db`** vs **`alembic_version`** so **`upgrade head`** does not hit **duplicate column** again (fresh DB or deliberate **`stamp`** on that branch).
