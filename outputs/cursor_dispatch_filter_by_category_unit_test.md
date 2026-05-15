# Cursor Dispatch — `filter_by_category` unit test (`scripts/places_load.py`)

> **Operator note:** paste the fenced block below into a fresh Cursor chat. This is a
> small, bounded test-only task (~20 min) — `filter_by_category` in `scripts/places_load.py`
> (shipped in commit `7455848`) has no unit test, and `tests/` is outside the Phase 5
> chat's file scope. **Dispatch this before the Phase 5.2 "On the Water" `places_load`
> run** — 5.2 is the first per-category load to actually exercise `--category` against a
> non-empty DB, so the filter wants coverage before then.
>
> **Why pre-staged now:** the function and its `DISCOVERY_CATEGORY_TO_DOMAINS` resolution
> are fresh from the Phase 5.1 scrape-phase review. Capturing the dispatch now means 5.2
> just pastes it.
>
> **Scope lock (gotcha #18):** creates `tests/test_places_load.py` ONLY. No source
> changes — `filter_by_category` is correct as shipped; this is pure coverage.
> Strict-disjoint from the parallel Phase 6 lane.

---

```
You are a Cursor session adding a unit test for the havasu-chat project (a Lake Havasu
City local-business directory). This is a TEST-ONLY task — no source code changes.

## §0 Baseline + reads

1. `git log --oneline -8` — confirm origin is on the post-`d34d4c3` chain. If unfamiliar
   commits appear, the parallel Phase 6 chat pushed — pull origin/main first.
2. `git status` — clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — record the baseline collected count.
4. Read these before writing anything:
   - `scripts/places_load.py` — focus on `filter_by_category()` (~lines 76-93), the
     function under test, and how `main()` calls it (~lines 293-295)
   - `app/contrib/google_places_scraper.py` — the `DISCOVERY_CATEGORY_TO_DOMAINS` dict
     (~lines 79-91); note `eat-drink -> {food_drink}` (single domain) and
     `health-wellness-care -> {health_medical, fitness_sports}` (multi-domain)
   - `tests/test_phase5_osm_overpass_load.py` — a sibling scripts/ test, for style/imports
   - `tests/conftest.py` — existing fixtures, in case any are useful (likely none needed —
     `filter_by_category` is pure, takes a list of dicts, touches no DB and no network)

## §1 What `filter_by_category` does

    def filter_by_category(rows, category_slug):
        domains = DISCOVERY_CATEGORY_TO_DOMAINS.get(category_slug)
        if domains is None:
            known = ", ".join(sorted(DISCOVERY_CATEGORY_TO_DOMAINS))
            raise SystemExit(f"Unknown --category {category_slug!r}. Expected one of: {known}")
        return [r for r in rows if r.get("_first_seen_domain", "") in domains]

It resolves a Tier-1 category slug to one or more discovery-domain values via
`DISCOVERY_CATEGORY_TO_DOMAINS`, then keeps only rows whose `_first_seen_domain` is in
that set. It exists so a per-category load stays scoped even though the shared
`enrichment_enriched.jsonl` carries rows from multiple domains' scrapes.

## §2 The test — create `tests/test_places_load.py`

Import `filter_by_category` from `scripts.places_load`. Pure function — build small
in-memory lists of dict rows; no DB, no network, no fixtures, no mocking required.

Cover, at minimum:
- **Single-domain slug scopes correctly:** `eat-drink` keeps only rows with
  `_first_seen_domain == "food_drink"`, drops rows from other domains
  (e.g. `lake_recreation`).
- **Multi-domain slug keeps all mapped domains:** `health-wellness-care` keeps rows
  from BOTH `health_medical` and `fitness_sports`, drops others.
- **Rows missing `_first_seen_domain` are dropped:** a row with no `_first_seen_domain`
  key falls out (the `.get(..., "")` default is not in any domain set).
- **Unknown slug raises `SystemExit`:** `filter_by_category(rows, "not-a-category")`
  raises `SystemExit`, and the message contains "Expected one of:" and lists known
  slugs. Use `pytest.raises(SystemExit)`.
- **Empty input returns empty list** for a valid slug.
- **Non-mutation:** the returned list is a new list; the input rows list is not mutated.

Keep row dicts minimal — just `_first_seen_domain` plus maybe a `place_id` for identity
assertions. Don't over-build fixtures.

After writing: `python -m pytest -q tests/test_places_load.py` (new tests pass) +
`python -m pytest -q` (full suite stays green, count = baseline + your new tests) +
`python -m ruff check tests/test_places_load.py` (clean).

## §3 What NOT to do

1. Do NOT modify `scripts/places_load.py` or any source file — `filter_by_category` is
   correct as shipped (`7455848`); this is coverage only.
2. Do NOT edit `app/contrib/google_places_scraper.py` — `DISCOVERY_CATEGORY_TO_DOMAINS`
   is the contract you're testing against, not changing.
3. Do NOT touch anything outside `tests/test_places_load.py`.
4. No schema migrations, no DB setup — the function is pure.

## §4 Close-out (§13)

Report: §13.1 what changed, §13.2 files touched, §13.3 pytest delta + ruff status,
§13.4 deviations + rationale, §13.5 operator commit instructions (PowerShell-safe `-m`
body — no embedded double-quotes per gotcha #16). HALT after — single bounded task,
one commit.
```

---

## Operator instructions

1. Confirm the working tree is clean Windows-side before pasting (and that the drift #5
   commit `d34d4c3` is pushed, so Cursor's baseline read is accurate).
2. Paste the fenced block into a fresh Cursor chat. Single bounded task — one HALT, one commit.
3. Review the new test file, then commit with Cursor's suggested PowerShell-safe body.

After this lands, the `filter_by_category` carry-forward (handoff §5) is cleared and the
Phase 5.2 `places_load --category` step has filter coverage behind it.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`d34d4c3`,
2026-05-15). Lives at `outputs/cursor_dispatch_filter_by_category_unit_test.md` —
brand-new `outputs/` file, safe under the parallel-chat scope lock. Pre-stages the
`filter_by_category` unit-test carry-forward so Phase 5.2 dispatches it directly.*
