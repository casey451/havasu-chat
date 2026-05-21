# Cursor dispatch prompt — Phase 7.6 (tier-2 OPEN_NOW listing shortcut)

> **What this is:** a paste-ready dispatch wrapper for a fresh Cursor chat to close the residual q03 production divergence: `"what restaurants are open now"` reaches tier-2 on dev (via Phase 7.5.1's `is_category_open_now_listing` router probe) but still cascades to tier-3 on prod (~23s latency) because the tier-2 **LLM parser** (Haiku, `temperature=0.3`) returns `fallback_to_tier3=True` or sub-threshold confidence. Path A from `outputs/phase_7_6_tier2_llm_parser_design_memo.md` extends `try_business_listing_shortcut` with a deterministic `_OPEN_NOW_LISTING_RE` regex — zero LLM tokens, no parser variance.
>
> **Operator:** open a fresh Cursor chat. Paste the entire content of this file (everything below the horizontal rule) as the first message. Cursor takes the work end-to-end through §12 and returns a final report. Do NOT add any other context — the wrapper is self-contained.
>
> **Pre-positioned by:** Cowork primary, 2026-05-20. Companion: `outputs/phase_7_6_tier2_llm_parser_design_memo.md` (full scoping + Path B rejection rationale).
>
> **Estimated effort:** 30-45 min Cursor session (~80-150 LOC + tests).

---

# Phase 7.6 — Tier-2 OPEN_NOW listing shortcut dispatch

You are picking up the havasu-chat project to extend the tier-2 business-listing shortcut so `"what restaurants are open now"` (and sibling shapes) bypass the Haiku parser entirely. Phase 7.5.1 stopped the **gap-template** misroute; this lane stops the **tier-3 cascade** that still happens when the LLM parser refuses or low-confidence-fails on prod.

**File scope (gotcha #18 disjointness):** This dispatch ONLY touches `app/chat/tier2_business_shortcut.py` + `tests/test_tier2_business_shortcut.py` + optionally `tests/test_tier2_handler.py`. Do NOT touch `unified_router.py`, `entity_intent.py`, `tier2_handler.py`, `tier2_parser.py`, `halt3_validator.py`, or `halt3_eval_set.yaml`. The wrapper enumerates expected files in §9.

**Cadence:** Stop at the §12 boundary. Do NOT git-commit. The operator commits after reviewing your diff.

---

## §0 Boot prereqs (verify BEFORE any edits)

Working directory: `C:\Users\casey\projects\havasu-chat`. For any Python invocation, use the venv: `.\.venv\Scripts\python.exe ...` from project root.

This dispatch assumes **Phase 7.5.1 AND Phase 7.5.2 have already shipped** on `origin/main`. Phase 7.5.1 landed the routing fixes (`near_match_subject_overlaps`, `is_category_open_now_listing` probe, `_unknown_entity_about_gate`). Phase 7.5.2 hardened the HALT 3 validator (G1–G4 + q24–q30) and likely pinned q03 to `expected_tier: tier2`. If either phase has NOT shipped, HALT and report — this lane follows both.

Run all six checks. HALT and report if any diverge:

```powershell
# 1. origin/main tip is the post-7.5.2 SHA (NOT pinned — inspect recent commits for
#    "phase7.5.1" and "phase7.5.2" subjects; record the actual tip SHA for §12):
git log -8 --format="%h %s" origin/main

# 2. Alembic single head c9d0e1f2a3b4 (unchanged across 7.5.x)
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current

# 3. Pytest baseline — post-7.5.2 count (record exact number for §12 delta math):
.\.venv\Scripts\python.exe -m pytest --collect-only -q | Select-Object -Last 3

# 4. HALT 3 validator passes at HEAD (30/30 if 7.5.2's q24-q30 landed; 23/23 minimum):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator

# 5. Phase 7.5.1 integration tests still GREEN:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3

# 6. RED baseline — the shortcut does NOT yet match q03 (this is what Phase 7.6 fixes):
.\.venv\Scripts\python.exe -c "from app.chat.tier2_business_shortcut import try_business_listing_shortcut; f=try_business_listing_shortcut('what restaurants are open now'); print('filters=', f)"
```

Expected:
- Post-7.5.2 SHA visible in log (both 7.5.1 and 7.5.2 commit subjects present in last ~8 commits).
- Alembic head `c9d0e1f2a3b4` (single).
- Pytest collected count recorded (likely ~2190+ post-7.5.2 — use actual number).
- Validator outputs `cited_coverage=100% missing_confab_max=0.00 all_passed=True`.
- All three 7.5.1 integration tests PASS.
- Check #6 prints `filters= None` — if non-None, either Phase 7.6 already landed or the baseline changed; HALT and report.

**If any check diverges, HALT and report.** Do not proceed with edits.

---

## §1 The bug — residual q03 (tier-2 LLM-parser divergence)

**Query:** `what restaurants are open now`

**Production symptom (post-7.5.1):** User-visible response is still the honest-no-data / `/contribute` gap shape OR a tier-3 LLM answer — **not** a cited tier-2 restaurant list. Latency ~23s (Haiku attempt + tier-3 cascade). Catalog probe confirms 20+ restaurant entities exist (`/api/search?q=restaurant` returns rows + `next_cursor`).

**What Phase 7.5.1 fixed:** `is_category_open_now_listing` probe in `_catalog_gap_response` (`unified_router.py` ~lines 198-202) prevents the **gap-template** from firing when the query matches the category+open-now pattern. Local routing: `tier=2 disc=cited` with a real list.

**What Phase 7.5.1 did NOT fix:** `try_business_listing_shortcut` at `app/chat/tier2_business_shortcut.py:256-290` still returns `None` for this shape — verified on both local and prod. The query then enters `try_tier2_with_usage` → `tier2_parser.parse` (Anthropic Haiku, `max_tokens=300`, `temperature=0.3`). Prod completions diverge from dev:

| Prod parser outcome | Handler behavior (`tier2_handler.py:171-186`) |
|---|---|
| `fallback_to_tier3=True` | Returns `(None, …)` → router cascades to tier-3 |
| `parser_confidence < 0.7` | Same cascade |
| `category=null`, only `open_now=true` | Post-fetch category filter drops all rows → empty → cascade |
| `category="restaurant"` but post-fetch `_category_match_provider` mismatch | Empty rows on prod catalog tag distribution → cascade |

Evidence: same input, same code path, different LLM output → divergence vector is the **parser call**, not the DB layer.

**Why the Haiku parser misses this shape:** `prompts/tier2_parser.txt` OPEN_NOW few-shots are softer recommendation phrasings (`"Where can I grab dinner right now?"`, `"Anywhere open for a workout this late?"`). `"what restaurants are open now"` is a **category listing** with `open_now`, not a recommendation — no few-shot teaches that shape.

**Metric blind spot:** `try_tier2_with_usage` returns `(None, None, None, None)` on every fallback path; the router records `llm_tokens_used=0` from tier-2 even when Haiku was billed. The 23s latency contains real Haiku work the metric understates.

### Root-cause chain (ranked, from design memo)

1. **H1 — Haiku non-determinism on borderline shape (most likely).** Parser refuses or low-confidence-fails on prod.
2. **H2 — Timeout/retry then tier-3 cascade (likely).** Date-context prepend doubles prompt length.
3. **H3 — Category-slug normalization on prod `google_primary_category` strings (less likely).** Ruled out as dominant cause; spot-check if integration tests seed realistic tags.

### Path B rejected

A deterministic category-keyword fallback **after** the LLM parser returns `None` was considered and rejected: second decision point, hard to test, shadows legitimate tier-3 disambiguation. Path A's regex is narrow enough to fail closed.

---

## §2 The fix design (Path A — extend the shortcut)

**Recommend Path A** from `outputs/phase_7_6_tier2_llm_parser_design_memo.md`: extend `try_business_listing_shortcut` with `_OPEN_NOW_LISTING_RE` evaluated **before** `_LISTING_PREFIX.match`. On match, return `Tier2Filters(category=<extracted>, open_now=True, parser_confidence=0.9, fallback_to_tier3=False)`. Reuse existing `_EVENT_SHAPE_TOKENS` guard and 3-word category cap.

**No changes** to `tier2_handler.py` — existing shortcut wiring at lines 158-169 already passes filters through `tier2_db_query.query`, which honors `open_now` (Python filter post-SQL at `tier2_db_query.py:1092-1099`).

**No changes** to `unified_router.py` — the 7.5.1 `is_category_open_now_listing` probe stays as belt-and-suspenders gap prevention.

### Step 2a — Add module-level regex + category normalization map

In `app/chat/tier2_business_shortcut.py`, after `_LISTING_PREFIX` (or adjacent to the other regex constants ~lines 37-70), add:

```python
# Phase 7.6 — "what restaurants are open now" category+open_now listings.
# Evaluated BEFORE _LISTING_PREFIX so these shapes never reach the Haiku parser.
# Tight: requires "what <category-noun> [are] open (now|right now)" end-anchored.
_OPEN_NOW_LISTING_RE = re.compile(
    r"^what\s+"
    r"(restaurants?|cafes?|coffee\s+shops?|bars?|"
    r"pharmacies|vets?|veterinarians?|stores?|shops?|gyms?)\s+"
    r"(?:are\s+)?open\s+(?:now|right\s+now)\s*$",
    re.IGNORECASE,
)

# Map captured noun phrase → canonical category string for Tier2Filters + SQL needles.
# Align with _category_needle_set / entity_intent._CATEGORY_OPEN_NOW_RE coverage.
_OPEN_NOW_CAPTURE_TO_CATEGORY: dict[str, str] = {
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "cafe": "cafe",
    "cafes": "cafe",
    "coffee shop": "coffee shop",
    "coffee shops": "coffee shop",
    "bar": "bar",
    "bars": "bar",
    "pharmacy": "pharmacy",
    "pharmacies": "pharmacy",
    "vet": "veterinarian",
    "vets": "veterinarian",
    "veterinarian": "veterinarian",
    "veterinarians": "veterinarian",
    "store": "store",
    "stores": "store",
    "shop": "shop",
    "shops": "shop",
    "gym": "gym",
    "gyms": "gym",
}


def _category_from_open_now_capture(raw: str) -> str:
    """Normalize the regex capture group to a canonical filter category."""
    key = (raw or "").strip().lower()
    return _OPEN_NOW_CAPTURE_TO_CATEGORY.get(key, key)
```

### Step 2b — Add early branch in `try_business_listing_shortcut`

At the top of `try_business_listing_shortcut` (after the empty-query guard, **before** `_LISTING_PREFIX.match`), insert the OPEN_NOW branch:

```python
    on = _OPEN_NOW_LISTING_RE.match(nq)
    if on is not None:
        category = _category_from_open_now_capture(on.group(1))
        category = _normalize_category_typos(category)
        low_padded = " " + category.lower()
        if any(tok in low_padded for tok in _EVENT_SHAPE_TOKENS):
            return None
        if len(category.split()) > 3:
            return None
        return Tier2Filters(
            category=category.lower(),
            open_now=True,
            parser_confidence=0.9,
            fallback_to_tier3=False,
        )
```

**Ordering invariant:** OPEN_NOW branch → existing `_LISTING_PREFIX` branch. Never reverse — a mis-ordered check could let listing-prefix logic steal open-now shapes.

### Regression risk (low)

- Regex requires **both** an allow-listed category noun **and** `open now` / `right now` phrasing — much tighter than `_LISTING_PREFIX`.
- `"what bars are open later"` won't match (no `now`/`right now`).
- `"what restaurants are open tonight"` won't match (`tonight` ∈ `_EVENT_SHAPE_TOKENS`).
- Empty provider rows still fall through to LLM path via existing `tier2_handler.py:167-169` logging — no worse than today.
- Existing shortcut parametrized tests should be unaffected (different predicate shape).

### Category synonym note (vets)

`tier2_synonyms.py` has no vet synonym group today. The allow-list includes `vets?|veterinarians?` → canonical `veterinarian`. Integration tests should seed providers with `google_primary_category` containing `veterinarian` (or `veterinary_care`) so `_category_match_provider` hits. If vet integration test fails on category match alone, note in §12 — do **not** expand scope to `tier2_synonyms.py` unless Cowork primary approves via §11.

---

## §3 Red-test prep (BEFORE applying the fix)

Confirm the baseline is red, then author tests that FAIL pre-fix and PASS post-fix.

**Step 3.1 — Confirm shortcut returns None for q03 at HEAD:**

```powershell
.\.venv\Scripts\python.exe -c "
from app.chat.tier2_business_shortcut import try_business_listing_shortcut
q = 'what restaurants are open now'
f = try_business_listing_shortcut(q)
assert f is None, f'Expected None pre-fix, got {f!r}'
print('RED baseline OK: shortcut returns None for q03')
"
```

Expected: prints `RED baseline OK`. If assertion fails, HALT.

**Step 3.2 — Author unit tests in `tests/test_tier2_business_shortcut.py`**

Add a new section after the existing `try_business_listing_shortcut` parametrized block (~line 90):

```python
# ---------------------------------------------------------------------------
# Phase 7.6 — OPEN_NOW + category listing shortcut (q03 fix)
# ---------------------------------------------------------------------------


def test_open_now_listing_shortcut_matches_q03() -> None:
    """q03 shape must match the deterministic shortcut (pre-fix: FAIL — returns None)."""
    filters = shortcut.try_business_listing_shortcut("what restaurants are open now")
    assert filters is not None
    assert filters.category == "restaurant"
    assert filters.open_now is True
    assert filters.parser_confidence >= 0.7
    assert filters.fallback_to_tier3 is False


def test_open_now_listing_shortcut_returns_filters_with_open_now_true() -> None:
    """Sibling shapes: optional 'are', 'right now', other allow-listed nouns."""
    cases = [
        ("what cafes are open now", "cafe", True),
        ("what pharmacies are open right now", "pharmacy", True),
        ("what vets are open now", "veterinarian", True),
        ("what coffee shops are open now", "coffee shop", True),
        ("what gyms are open now", "gym", True),
    ]
    for query, expected_cat, expected_open in cases:
        filters = shortcut.try_business_listing_shortcut(query)
        assert filters is not None, query
        assert filters.category == expected_cat, query
        assert filters.open_now is expected_open, query


def test_open_now_listing_skips_when_event_shape_present() -> None:
    """Temporal/event tokens defer to the LLM parser — 'tonight' is in _EVENT_SHAPE_TOKENS."""
    assert shortcut.try_business_listing_shortcut("what restaurants are open tonight") is None
    assert shortcut.try_business_listing_shortcut("what bars are open this weekend") is None


@pytest.mark.parametrize(
    "query",
    [
        "what restaurants are open later",       # no now/right now
        "what restaurants open",                 # missing temporal anchor
        "which restaurants are open now",        # wrong lead word (not 'what')
        "what is open now",                    # no category noun
        "find me a restaurant open now",       # listing-prefix shape, not open-now listing
    ],
)
def test_open_now_listing_shortcut_negative_shapes(query: str) -> None:
    """Conservative non-match — must not shadow tier-3 or listing-prefix paths."""
    # Pre-fix: all None anyway. Post-fix: must stay None.
    assert shortcut.try_business_listing_shortcut(query) is None
```

Run BEFORE applying §4:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -k "open_now_listing" -xvs
```

Expected: **FAIL** on `test_open_now_listing_shortcut_matches_q03` (and likely the parametrized positive cases). Negative-shape tests may PASS (already None). If q03 test PASSES before the fix, HALT — baseline changed.

---

## §4 Apply the shortcut fix

Edit `app/chat/tier2_business_shortcut.py` per §2 (steps 2a + 2b).

After the edit:

```powershell
# Unit tests green:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -k "open_now_listing" -xvs

# Sanity — q03 capture:
.\.venv\Scripts\python.exe -c "
from app.chat.tier2_business_shortcut import try_business_listing_shortcut
f = try_business_listing_shortcut('what restaurants are open now')
assert f and f.category == 'restaurant' and f.open_now
print('OK', f)
"
```

All open-now listing tests should PASS.

---

## §5 Integration test — `try_tier2_with_usage` zero tokens

Add to `tests/test_tier2_business_shortcut.py` (reuse existing `db_session` fixture and `_insert_test_providers` helper at ~lines 220-249) OR add one focused test to `tests/test_tier2_handler.py` if that file already has a cleaner open-now + hours fixture pattern (`tests/test_tier2_open_now.py` is the reference for `hours_structured` seeding).

**Preferred location:** `tests/test_tier2_business_shortcut.py` next to `test_handler_uses_shortcut_zero_tokens` — keeps Slice D wiring tests together.

```python
def test_handler_open_now_listing_shortcut_zero_tokens(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """q03 end-to-end: shortcut → query(open_now=True) → deterministic render, zero tokens.

    Mocks wall-clock so hours_structured provider counts as open. Does NOT call Anthropic.
    """
    from datetime import datetime
    from app.chat import tier2_db_query
    from app.contrib.hours_helper import LAKE_HAVASU_TZ

    monkeypatch.setattr(
        tier2_db_query,
        "_now_lake_havasu",
        lambda: datetime(2026, 6, 15, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ),  # Monday noon
    )
    ids = _insert_test_providers(
        db_session,
        [
            {
                "name": "Tier2OpenNow Miguel's",
                "category": "food_drink",
                "google_primary_category": "restaurant",
                "google_categories": ["restaurant", "food"],
                # hours_structured must cover the monkeypatched weekday
            },
            {
                "name": "Tier2OpenNow Closed Diner",
                "category": "food_drink",
                "google_primary_category": "restaurant",
                "google_categories": ["restaurant"],
            },
        ],
    )
    # Patch hours onto inserted rows — _insert_test_providers may not set hours_structured;
    # set explicitly after insert if your helper doesn't accept it:
    try:
        from app.db.models import Provider
        for pid in ids:
            row = db_session.get(Provider, pid)
            if row and "OpenNow Miguel" in (row.provider_name or ""):
                row.hours_structured = {"monday": [{"open": "09:00", "close": "23:00"}]}
            elif row and "Closed Diner" in (row.provider_name or ""):
                row.hours_structured = {"monday": [{"open": "18:00", "close": "19:00"}]}
        db_session.commit()

        text, used, in_t, out_t = tier2_handler.try_tier2_with_usage(
            "what restaurants are open now"
        )
        assert text is not None, "shortcut+open_now should produce a listing"
        assert used == 0, f"expected zero tokens (no Haiku), got {used}"
        assert in_t == 0
        assert out_t == 0
        assert "Tier2OpenNow Miguel" in text
        # Closed provider should be filtered out by open_now post-fetch.
        assert "Closed Diner" not in text
    finally:
        for pid in ids:
            row = db_session.get(Provider, pid)
            if row is not None:
                db_session.delete(row)
        db_session.commit()
```

**Adapt as needed:** if `_insert_test_providers` cannot carry `hours_structured`, extend the helper locally in this test file only (do not refactor unrelated tests). Read `tests/test_tier2_open_now.py:58-80` for the canonical hours JSON shape.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py::test_handler_open_now_listing_shortcut_zero_tokens -xvs
```

Must PASS. If zero rows return and handler falls through to LLM (tokens > 0 or `text is None`), debug category needles + `google_primary_category` on the fixture before proceeding.

**Optional router-level confirmation (read-only, no edits):**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 -xvs
```

Should still PASS — 7.5.1 test asserts gap-template is skipped; 7.6 makes the tier-2 path deterministic.

---

## §6 Existing regression check

The full Slice D shortcut suite must remain green — Phase 7.6 must not break listing-prefix extraction, typo normalization, or event-shape deferrals.

```powershell
# Full shortcut module:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -q

# Existing zero-token barber integration (regression anchor):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py::test_handler_uses_shortcut_zero_tokens -xvs

# Event-shape deferral still works for listing prefix:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py::test_shortcut_returns_none_for_non_listing_shapes -xvs
```

All must PASS.

---

## §7 Acceptance verification

Run all five checks. ALL must pass before §12.

```powershell
# 1. HALT 3 validator still all-pass (count depends on 7.5.2 eval rows):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
# Expected: cited_coverage=100% missing_confab_max=0.00 all_passed=True
# q03 should PASS with tier=2 if 7.5.2 pinned expected_tier: tier2

# 2. Full pytest suite — count should grow by ~6-8 from new tests:
.\.venv\Scripts\python.exe -m pytest -q

# 3. Phase 7.6 unit + integration tests:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_tier2_business_shortcut.py -k "open_now_listing or handler_open_now_listing"

# 4. Phase 7.5.1 q03 router test non-regression:
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 -xvs

# 5. Ruff clean on touched files:
.\.venv\Scripts\python.exe -m ruff check `
    app/chat/tier2_business_shortcut.py `
    tests/test_tier2_business_shortcut.py
```

**If any check fails, HALT and investigate.** Do not proceed to §12.

---

## §8 Optional prod-smoke note (operator, not Cursor)

After ship, the operator should re-run the Lane H prod probe:

```powershell
Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/chat" -Method POST -Body (@{q="what restaurants are open now"} | ConvertTo-Json) -ContentType "application/json"
```

Expected: tier-2 cited list (or honest empty listing if no rows pass `open_now` filter), **not** tier-3 prose, latency ≪ 23s. This is out of scope for the Cursor session — note result in §12.8 if the operator reports back.

---

## §9 File scope (gotcha #18 disjointness)

**Modified files (closed set):**
- `app/chat/tier2_business_shortcut.py` (add `_OPEN_NOW_LISTING_RE`, `_OPEN_NOW_CAPTURE_TO_CATEGORY`, `_category_from_open_now_capture`, early branch in `try_business_listing_shortcut`)

**Modified test files:**
- `tests/test_tier2_business_shortcut.py` (unit tests + integration test per §3–§5)

**Optionally modified (only if integration test fits better there):**
- `tests/test_tier2_handler.py` (single test moved from business_shortcut file — prefer keeping in `test_tier2_business_shortcut.py`)

**Do NOT touch:**
- `app/chat/unified_router.py` — 7.5.1 `is_category_open_now_listing` probe stays
- `app/chat/entity_intent.py` — `is_category_open_now_listing` unchanged
- `app/chat/tier2_handler.py` — wiring already correct
- `app/chat/tier2_parser.py` / `prompts/tier2_parser.txt` — Path A bypasses parser
- `app/chat/halt3_validator.py` / `app/chat/halt3_eval_set.yaml` — validator lane is 7.5.2; q03 tier pin is already there
- `app/chat/tier2_synonyms.py` — unless §11 deviation approved for vet recall
- Phase 7.5.2 validator tests, Phase 6.5 / Phase 8 / Phase 9 surfaces
- Any other dispatch wrapper under `outputs/`

**Parallel-eligibility:** Zero file overlap with Phase 7.5.2 (`halt3_validator.py`, `halt3_eval_set.yaml`). Could have run concurrently; sequencing recommendation was ship 7.5.2 first so q03 `expected_tier: tier2` is measurable in CI.

---

## §10 What NOT to do

- **Do NOT git-commit.** Stop at §12. The operator commits after reviewing your diff.
- **Do NOT touch `unified_router.py` or remove the 7.5.1 probe.** Belt-and-suspenders gap prevention is still valuable if the shortcut returns None (empty rows, unhandled shape).
- **Do NOT implement Path B** (post-parser deterministic fallback). One decision point only.
- **Do NOT broaden `_OPEN_NOW_LISTING_RE`** beyond the allow-listed nouns in §2 without §11 approval. `"what places are open now"` is intentionally out of scope.
- **Do NOT add Anthropic calls or change `tier2_parser` temperature/prompt** — defeats the purpose.
- **Do NOT change `render_business_listing`** to mention open-now in the header unless you discover users can't tell open listings from generic listings (unlikely; out of scope).
- **Do NOT add an alembic migration.** No schema changes.
- **Do NOT modify `halt3_eval_set.yaml`** — q03 row already exists; 7.5.2 handles tier pinning.

---

## §11 If you find a substantive deviation

Per the project's working agreement Rule 4 (deviation discipline):

- Small in-scope deviations (e.g., regex anchor tweak; adding `bakeries` to allow-list; extending `_insert_test_providers` with `hours_structured` kwarg) — proceed with judgment; note in §12.
- Substantive deviations (touching `tier2_synonyms.py` for vet recall; changing `tier2_handler.py` shortcut fall-through; editing `halt3_eval_set.yaml`; adding LLM few-shots instead of regex) — STOP and report. Cowork primary will decide.

---

## §12 Final report (you MUST emit this; do not commit)

Emit a structured report covering:

### §12.1 Diffs
- Full unified diff of all modified files (use `git diff` output)
- Confirm no files outside §9 scope were touched

### §12.2 Acceptance checks
For each check in §7, paste the actual output line(s). Confirm PASS for each. Record pytest collected count delta vs §0 baseline.

### §12.3 Per-fix verification

| Fix | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| q03 shortcut match | `test_open_now_listing_shortcut_matches_q03` | Same test post-fix | ☐ |
| open_now flag | `test_open_now_listing_shortcut_returns_filters_with_open_now_true` | Same test post-fix | ☐ |
| event deferral | `test_open_now_listing_skips_when_event_shape_present` | Pre+post PASS (None) | ☐ |
| zero-token E2E | `test_handler_open_now_listing_shortcut_zero_tokens` | Same test post-fix | ☐ |
| 7.5.1 router | `test_q03_what_restaurants_open_now_reaches_tier2` | Non-regression PASS | ☐ |
| Validator | `python -m app.chat.halt3_validator` all-pass | q03 tier=2 if pinned | ☐ |
| Slice D regression | `tests/test_tier2_business_shortcut.py` full file | All PASS | ☐ |

### §12.4 Substantive findings
- Did vet/pharmacy category matching work with fixtures only, or did you need a synonym-group change?
- Did `render_business_listing` need any tweak for open-now listings?
- Any bugs in existing code noticed but not fixed (out of scope)?
- Anything the wrapper didn't anticipate.

### §12.5 File scope confirmation
Paste output of `git status --short` confirming only §9-listed files modified.

### §12.6 Recommended commit subject
Suggest a commit subject line. Default:

```
feat(phase7.6): tier-2 OPEN_NOW listing shortcut -- q03 bypasses Haiku parser via _OPEN_NOW_LISTING_RE; open_now=True deterministic filters; +unit/integration tests; 7.5.1 router probe retained
```

### §12.7 Open carries
- Prod smoke latency + tier routing after deploy (§8).
- If 7.5.2 left q03 at `expected_tier: any`, recommend pinning to `tier2` in a follow-up eval patch (out of scope here).
- Vet synonym group in `tier2_synonyms.py` if recall gaps surface in chat_logs.
- Broader `"what <noun> are open now"` coverage (e.g. `pizza places`, `hotels`) — future phase if metrics show demand.

---

End of wrapper. Now go.
