# Cursor dispatch prompt — Phase 7.7 (tier-2 honest empty listing on open_now zero-rows)

> **What this is:** a paste-ready dispatch wrapper for a fresh Cursor chat to close the residual q03 UX issue that survived Phase 7.6. The 7.6 shortcut (`_OPEN_NOW_LISTING_RE` in `app/chat/tier2_business_shortcut.py`) now fires deterministically and bypasses the Haiku parser — latency dropped 23s → 4s. But prod restaurants are populated **without** `hours_structured` / `google_hours` data, so the Python-side `open_now` filter at `tier2_db_query.py:1092-1099` drops every row. `tier2_handler.try_tier2_with_usage` then falls through to the LLM parser path which still routes to tier-3 with a `golakehavasu.com` redirect. Phase 7.7 closes that fallback with a deterministic tier-2 honest-empty-listing template — instant response, zero LLM tokens, honest about the data gap.
>
> **Operator:** open a fresh Cursor chat. Paste the entire content of this file (everything below the horizontal rule) as the first message. Cursor takes the work end-to-end through §11 and returns a final report. Do NOT add any other context — the wrapper is self-contained.
>
> **Pre-positioned by:** Cowork primary, 2026-05-20. Companion: `outputs/phase_7_7_honest_empty_listing_design_memo.md` (full scoping + rejected-alternative rationale).
>
> **Estimated effort:** ~1-1.5h Cursor session (~30-50 LOC + 4-6 tests).

---

# Phase 7.7 — Tier-2 honest empty listing dispatch

You are picking up the havasu-chat project to add a deterministic honest-empty-listing reply to `tier2_handler.try_tier2_with_usage`. Phase 7.6 made the shortcut deterministic; this lane closes the residual tier-3 cascade that fires when the shortcut's filters return zero rows because the catalog lacks hours data.

**File scope (gotcha #18 disjointness):** This dispatch ONLY touches `app/chat/tier2_handler.py` + `tests/test_tier2_handler.py`. Do NOT touch `app/chat/tier2_business_shortcut.py` (Phase 7.6 surface), `unified_router.py`, `halt3_validator.py`, `halt3_eval_set.yaml`, `tier2_parser.py`, or `tier2_db_query.py`. The wrapper enumerates expected files in §8.

**Cadence:** Stop at the §11 boundary. Do NOT git-commit. The operator commits after reviewing your diff.

---

## §0 Boot prereqs (verify BEFORE any edits)

Working directory: `C:\Users\casey\projects\havasu-chat`. For any Python invocation, use the venv: `.\.venv\Scripts\python.exe ...` from project root.

This dispatch assumes **Phase 7.6 has shipped** on `origin/main` (`975e83f` code + `19b6c8f` docs + `44ca1c6` ledger entries). The floor SHA is `19b6c8f` (post-7.6 docs); the actual tip at dispatch time should be `44ca1c6` or later (ledger commit Casey pushed). Verify the actual tip:

Run all six checks. HALT and report if any diverge:

```powershell
# 1. origin/main tip is post-7.6 (floor: 19b6c8f for docs, 44ca1c6 for ledger).
#    Inspect recent commits for "phase7.6" subjects (code + docs). Record the actual tip SHA for §11.
git log -10 --format="%h %s" origin/main

# 2. Phase 7.6 code SHIPPED check — _OPEN_NOW_LISTING_RE must exist in shortcut module:
.\.venv\Scripts\python.exe -c "from app.chat.tier2_business_shortcut import _OPEN_NOW_LISTING_RE; print('7.6 shortcut present:', _OPEN_NOW_LISTING_RE.pattern[:40])"

# 3. Alembic single head c9d0e1f2a3b4 (unchanged across 7.5.x + 7.6):
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current

# 4. Pytest baseline — post-7.6 count (record exact number for §11 delta math; floor ~2202):
.\.venv\Scripts\python.exe -m pytest --collect-only -q | Select-Object -Last 3

# 5. HALT 3 validator still 30/30 all-pass:
.\.venv\Scripts\python.exe -m app.chat.halt3_validator

# 6. RED baseline — confirm the shortcut fires AND the handler falls through to None when
#    the open_now filter drops all rows. This is what Phase 7.7 fixes.
#    (Run against the dev DB; the shortcut + mocked-empty-rows pattern reproduces the prod issue.)
.\.venv\Scripts\python.exe -c "
from unittest.mock import patch
from app.chat.tier2_handler import try_tier2_with_usage
with patch('app.chat.tier2_handler.tier2_db_query.query', return_value=[]):
    out = try_tier2_with_usage('what restaurants are open now')
print('RED baseline (pre-fix):', out)
assert out == (None, None, None, None), f'Expected fallback tuple, got {out!r}'
print('RED baseline OK: shortcut hits, rows empty, handler returns None tuple (cascades to tier-3)')
"
```

Expected:
- Post-7.6 SHA visible in log (`975e83f` + `19b6c8f` + `44ca1c6` or later commit subjects present).
- Check #2 prints `7.6 shortcut present: ^what\s+(restaurants?|cafes?|coffee\s+s` (or similar regex prefix). If ImportError or AttributeError, Phase 7.6 has NOT shipped — HALT.
- Alembic head `c9d0e1f2a3b4` (single).
- Pytest collected count recorded (floor ~2202 — record actual).
- Validator outputs `cited_coverage=100% missing_confab_max=0.00 all_passed=True`.
- Check #6 prints `RED baseline OK` — handler returns `(None, None, None, None)` when shortcut fires but rows are empty.

**If any check diverges, HALT and report.** Do not proceed with edits.

---

## §1 The bug — residual q03 (tier-3 cascade on open_now zero-rows)

**Query:** `what restaurants are open now`

**Production symptom (post-7.6):** Latency dropped 23s → 4s (Phase 7.6 win — shortcut bypasses Haiku parser). But user-visible response is still a tier-3 LLM cascade with a `golakehavasu.com` redirect, NOT a tier-2 honest reply. The `try_tier2_with_usage` token counters report `(None, None, None, None)` and the router cascades to tier-3.

**Three-probe prod diagnostic (2026-05-20)** confirmed the chain:

1. `_OPEN_NOW_LISTING_RE` matches q03 → returns `Tier2Filters(category="restaurant", open_now=True, parser_confidence=0.9, fallback_to_tier3=False)`. **Verified.**
2. `tier2_db_query.query` is reached. Provider branch (`_query_providers_orm`) finds restaurants by category. **Verified.**
3. Python-side `open_now` filter at `tier2_db_query.py:1092-1099` runs `effective_hours_structured(p) AND is_open_at(hs, now_local)` against each row.
4. **Prod catalog restaurants lack `hours_structured` / `google_hours` data.** Every row is filtered out → `prov_orm = []` → `_merge_simple([], [], []) = []`.
5. `tier2_handler.try_tier2_with_usage` first hits the SHORTCUT zero-rows fall-through (lines 167-169) — `render_business_listing([], "restaurant")` returns `None` (no provider rows to format), then proceeds to the LLM-parser path which itself returns `(None, None, None, None)` at line 184. **Verified.**
6. Router cascades to tier-3 → 4s LLM call → generic `golakehavasu.com` reply.

**Phase 7.7 fix:** intercept the zero-rows state at both fall-through points and emit a deterministic honest-empty template instead of cascading. Zero LLM tokens, instant response, honest about the data gap.

**Independent of the V1.5 hours-data backfill** — even after the backfill ships, this template serves as graceful degradation for sparse-hours categories (vets, seasonal businesses, newly added providers).

### Phase 7.6 review (do NOT modify)

The Phase 7.6 shortcut at `app/chat/tier2_business_shortcut.py:75-106, 299-323` is correct and shipped. Phase 7.7 is strictly downstream — the shortcut keeps firing; only the handler's response on shortcut+zero-rows changes.

---

## §2 The fix design (Path A — honest empty listing template)

**Recommend Path A** from `outputs/phase_7_7_honest_empty_listing_design_memo.md`: add a deterministic template constant in `tier2_handler.py`, build a small helper that pluralizes the category and renders the template body, and insert two ~3-line conditionals — one in the shortcut zero-rows branch and one in the LLM-parser zero-rows branch — that emit the template when `open_now=True AND category is not None`.

**No schema change.** `Tier2Filters` is unchanged. The rejected alternative (a `from_shortcut` flag on `Tier2Filters`) is documented in the design memo §2; do not implement it.

**No changes** to `tier2_business_shortcut.py`, `tier2_db_query.py`, `tier2_parser.py`, or `unified_router.py`.

### Step 2a — Add template constant + helper at the top of `tier2_handler.py`

In `app/chat/tier2_handler.py`, after the `TIER2_CONFIDENCE_THRESHOLD = 0.7` line (~line 22), add:

```python
# Phase 7.7 — honest empty listing for open_now zero-rows.
# Fires when the user asked for currently-open <category> AND the catalog has rows
# matching the category BUT zero rows survive the open_now filter (typically because
# hours_structured / google_hours data is missing). Deterministic, zero LLM tokens.
_OPEN_NOW_EMPTY_LISTING_TEMPLATE = (
    "I have {category_label} in the Lake Havasu catalog, but I don't have "
    "current hours data for them yet — so I can't tell you which are open "
    "right now. Try https://www.golakehavasu.com/ for a hours-aware listing, "
    "or share a Google Business page at /contribute and I'll fill the gap."
)


def _open_now_empty_listing(category: str) -> str:
    """Render the honest empty listing for a single ``category`` (e.g. "restaurant").

    Pluralizes via :func:`tier2_business_shortcut._pluralize_for_header` so the
    label reads naturally for one-word ("restaurants") and two-word ("coffee
    shops") categories alike.
    """
    label = tier2_business_shortcut._pluralize_for_header(category or "places")
    return _OPEN_NOW_EMPTY_LISTING_TEMPLATE.format(category_label=label)
```

`_pluralize_for_header` is already imported transitively via the module-level `from app.chat import tier2_business_shortcut` at line 11. Cross-module call to a `_underscored` helper is acceptable here — it's the same package and the helper is stable (Phase 7.6 surface).

### Step 2b — Add conditional in the SHORTCUT zero-rows branch

In `try_tier2_with_usage`, replace lines 158-169 with the version that adds the Phase 7.7 conditional between the existing `render_business_listing` non-None return and the fall-through log:

```python
    shortcut_filters = tier2_business_shortcut.try_business_listing_shortcut(q)
    if shortcut_filters is not None:
        rows = tier2_db_query.query(shortcut_filters, ctx=chat_ctx)
        text = tier2_business_shortcut.render_business_listing(
            rows, shortcut_filters.category or ""
        )
        if text is not None:
            logging.info("tier2_handler: business-listing shortcut hit (zero tokens)")
            return text, 0, 0, 0
        # Phase 7.7 — honest empty listing. The shortcut matched the user-intent
        # shape, the catalog has rows matching the category, but the open_now
        # filter dropped them all (no hours_structured / google_hours). Emit a
        # deterministic tier-2 reply instead of falling through to the LLM.
        if shortcut_filters.open_now and shortcut_filters.category:
            logging.info(
                "tier2_handler: open_now zero-rows; emitting honest empty listing (shortcut path)"
            )
            return _open_now_empty_listing(shortcut_filters.category), 0, 0, 0
        # Shortcut matched the shape but returned no provider rows — fall through to the
        # LLM path so the user still gets a useful answer.
        logging.info("tier2_handler: shortcut shape matched but no provider rows; falling through")
```

### Step 2c — Add conditional in the LLM-PARSER zero-rows branch

In `try_tier2_with_usage`, replace lines 183-186 (`rows = tier2_db_query.query(filters, ctx=chat_ctx)` + the `if len(rows) == 0:` block) with:

```python
    filters = _normalize_tier2_filters_from_query(q, filters)
    rows = tier2_db_query.query(filters, ctx=chat_ctx)
    if len(rows) == 0:
        # Phase 7.7 — same honest empty listing also applies to parser-built
        # filters with the q03 shape (open_now + explicit category). The LLM
        # parser sometimes sets open_now=True with category=None for shapes
        # like "anywhere open right now"; those continue to fall through to
        # tier-3 as today.
        if filters.open_now and filters.category:
            logging.info(
                "tier2_handler: parser-path open_now zero-rows; emitting honest empty listing"
            )
            pi, po = (p_in or 0), (p_out or 0)
            return _open_now_empty_listing(filters.category), pi + po, pi, po
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None
```

**Token accounting note:** the parser-path version carries the Haiku parser tokens through (`pi + po`, `pi`, `po`) rather than reporting zero. The parser call already happened — hiding the spend as zero would understate the metric. The shortcut path reports `(0, 0, 0)` because no LLM call was made.

### Ordering invariant

In step 2b, the SHORTCUT-path empty-listing check goes AFTER the `render_business_listing` non-None return and BEFORE the fall-through log. Never reverse — a non-empty render must always win.

In step 2c, the PARSER-path empty-listing check goes inside the existing `if len(rows) == 0:` block (the only zero-rows branch in that section). The condition guard (`filters.open_now and filters.category`) ensures it only fires for the q03 shape.

### Regression risk (low)

- Both new conditionals are gated on `open_now=True AND category is not None` — the q03 shape and its siblings. No effect on any other tier-2 query.
- The shortcut-path conditional only runs when `render_business_listing` returned `None` (no provider rows). Other shortcut shapes that have rows are unaffected.
- The parser-path conditional only runs inside the existing zero-rows branch. The previous `return None, None, None, None` fall-through is preserved when the q03-shape condition fails.
- HALT 3 validator: q03 row may shift from `tier_used=3` to `tier_used=2`. Confirm the validator's q03 entry tolerates this (likely already pinned to `tier2` post-7.5.2; verify in §5).

---

## §3 Red-test prep (BEFORE applying the fix)

Confirm the baseline is red, then author tests that FAIL pre-fix and PASS post-fix.

**Step 3.1 — Confirm handler returns None tuple for q03 with empty rows at HEAD:**

```powershell
.\.venv\Scripts\python.exe -c "
from unittest.mock import patch
from app.chat.tier2_handler import try_tier2_with_usage
with patch('app.chat.tier2_handler.tier2_db_query.query', return_value=[]):
    out = try_tier2_with_usage('what restaurants are open now')
assert out == (None, None, None, None), f'Expected fallback tuple, got {out!r}'
print('RED baseline OK: handler returns None tuple → router cascades to tier-3')
"
```

Expected: prints `RED baseline OK`. If the assertion fails, HALT — baseline changed.

**Step 3.2 — Author unit tests in `tests/test_tier2_handler.py`**

Add a new section at the end of the file:

```python
# ---------------------------------------------------------------------------
# Phase 7.7 — honest empty listing on open_now zero-rows (q03 UX fix)
# ---------------------------------------------------------------------------


def test_open_now_empty_listing_helper_pluralizes() -> None:
    """The helper must pluralize one-word and two-word categories naturally."""
    from app.chat.tier2_handler import _open_now_empty_listing

    assert "restaurants" in _open_now_empty_listing("restaurant")
    assert "coffee shops" in _open_now_empty_listing("coffee shop")
    assert "pharmacies" in _open_now_empty_listing("pharmacy")
    assert "Lake Havasu catalog" in _open_now_empty_listing("restaurant")
    assert "/contribute" in _open_now_empty_listing("restaurant")
    assert "golakehavasu.com" in _open_now_empty_listing("restaurant")


def test_shortcut_open_now_zero_rows_returns_honest_empty_listing() -> None:
    """q03 shortcut path: shortcut fires, DB returns zero rows, handler emits template (no LLM)."""
    with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
        text, total, tin, tout = try_tier2_with_usage("what restaurants are open now")
    assert text is not None
    assert "restaurants" in text
    assert "current hours data" in text
    assert total == 0  # zero LLM tokens — shortcut path
    assert tin == 0
    assert tout == 0


def test_parser_path_open_now_zero_rows_returns_honest_empty_listing() -> None:
    """Parser-built filters with the q03 shape also fire the template (carries parser tokens)."""
    f = Tier2Filters(
        parser_confidence=0.9,
        category="restaurant",
        open_now=True,
        fallback_to_tier3=False,
    )
    # Bypass the shortcut by submitting a query the shortcut won't match
    # (so the parser path is reached).
    with patch("app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut", return_value=None):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 12, 5)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
                text, total, tin, tout = try_tier2_with_usage("anywhere good for dinner that's open right now")
    assert text is not None
    assert "restaurants" in text
    # Parser tokens carried through honestly:
    assert tin == 12
    assert tout == 5
    assert total == 17


def test_parser_path_open_now_no_category_still_cascades() -> None:
    """LLM parser sets open_now=True with category=None (recommendation shape): NO template fires."""
    f = Tier2Filters(
        parser_confidence=0.9,
        category=None,
        open_now=True,
        fallback_to_tier3=False,
    )
    with patch("app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut", return_value=None):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 12, 5)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
                text, _, _, _ = try_tier2_with_usage("anywhere open right now")
    assert text is None  # cascades to tier-3 as before


def test_shortcut_open_now_with_rows_still_renders_listing() -> None:
    """Sanity: when rows DO survive the open_now filter, the existing listing render wins."""
    rows = [{"type": "provider", "name": "Open Diner", "address": "1 Main", "phone": "555-1"}]
    with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=rows):
        text, total, _, _ = try_tier2_with_usage("what restaurants are open now")
    assert text is not None
    assert "Open Diner" in text
    assert "current hours data" not in text  # template did NOT fire
    assert total == 0  # shortcut path is zero-token


def test_non_open_now_zero_rows_still_returns_none() -> None:
    """Non-open_now zero-rows path is unchanged (no template, falls through)."""
    f = Tier2Filters(
        parser_confidence=0.9,
        category="nonexistent_xyz",
        open_now=False,
        fallback_to_tier3=False,
    )
    with patch("app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut", return_value=None):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 1, 1)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
                text, total, _, _ = try_tier2_with_usage("find me a nonexistent_xyz")
    assert text is None  # original behavior preserved
    assert total is None
```

Run BEFORE applying §4:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_handler.py -k "open_now_empty_listing or open_now_zero_rows or open_now_no_category or non_open_now_zero_rows or open_now_with_rows" -xvs
```

Expected pre-fix:
- `test_open_now_empty_listing_helper_pluralizes` — **FAIL** (`AttributeError`: helper doesn't exist).
- `test_shortcut_open_now_zero_rows_returns_honest_empty_listing` — **FAIL** (`text` is `None`).
- `test_parser_path_open_now_zero_rows_returns_honest_empty_listing` — **FAIL** (`text` is `None`).
- `test_parser_path_open_now_no_category_still_cascades` — **PASS** pre-fix (already `None`). Confirms the negative case.
- `test_shortcut_open_now_with_rows_still_renders_listing` — **PASS** pre-fix (listing render works).
- `test_non_open_now_zero_rows_still_returns_none` — **PASS** pre-fix (existing fall-through behavior).

If any of the expected-FAIL tests PASS pre-fix, HALT — baseline changed.

---

## §4 Apply the fix

Edit `app/chat/tier2_handler.py` per §2 (steps 2a + 2b + 2c).

After the edit:

```powershell
# Unit tests green:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_handler.py -k "open_now_empty_listing or open_now_zero_rows or open_now_no_category or non_open_now_zero_rows or open_now_with_rows" -xvs

# Sanity — q03 end-to-end (mocked rows-empty):
.\.venv\Scripts\python.exe -c "
from unittest.mock import patch
from app.chat.tier2_handler import try_tier2_with_usage
with patch('app.chat.tier2_handler.tier2_db_query.query', return_value=[]):
    out = try_tier2_with_usage('what restaurants are open now')
text, total, tin, tout = out
assert text is not None and 'restaurants' in text and 'current hours data' in text
assert total == 0 and tin == 0 and tout == 0
print('OK — q03 honest empty listing fires (zero tokens):', repr(text[:80]))
"
```

All Phase 7.7 tests should PASS.

---

## §5 Acceptance verification

Run all five checks. ALL must pass before §11.

```powershell
# 1. HALT 3 validator still 30/30 all-pass:
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
# Expected: cited_coverage=100% missing_confab_max=0.00 all_passed=True
# q03 may shift from previous tier=2 (Phase 7.6 cited list) to tier=2 with the
# new honest-empty body — validator should still PASS if its q03 expectation is
# `expected_tier: tier2` (likely; verify and report in §11). If the validator
# pins q03 to a specific text fragment that no longer matches, surface the
# mismatch in §11.4 — do NOT edit halt3_eval_set.yaml (Phase 7.5.2 surface).

# 2. Full pytest suite — count should grow by 6 from new tests:
.\.venv\Scripts\python.exe -m pytest -q

# 3. Phase 7.7 tests:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_handler.py -k "open_now_empty_listing or open_now_zero_rows or open_now_no_category or non_open_now_zero_rows or open_now_with_rows" -xvs

# 4. Phase 7.6 q03 router non-regression — shortcut still fires deterministically:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -k "open_now_listing" -xvs

# 5. Phase 7.5.1 q07 + q22 integration tests still PASS (regression check on routing):
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3

# 6. Ruff clean on touched files:
.\.venv\Scripts\python.exe -m ruff check `
    app/chat/tier2_handler.py `
    tests/test_tier2_handler.py
```

**If any check fails, HALT and investigate.** Do not proceed to §11.

---

## §6 Existing regression check

The full tier-2 test surface must remain green — Phase 7.7 must not break the existing shortcut, parser, or formatter wiring.

```powershell
# Full handler module:
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_handler.py -q

# Full shortcut module (Phase 7.6 surface):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -q

# Open-now filter regression (Phase 5.6 surface):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_open_now.py -q

# Existing zero-rows fall-through tests still consistent (some may have shifted assertion
# style — read the diff carefully if any fail):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_handler.py::test_no_db_rows_returns_none -xvs
```

All must PASS. `test_no_db_rows_returns_none` uses `category="nonexistent_xyz_12345"` with `open_now=False` (default) — that's the non-q03-shape path, still expected to return None. If that test starts failing, the Phase 7.7 condition guards are too loose — re-read §2c.

---

## §7 Prod-smoke note (operator, not Cursor)

After Cursor reports SUCCESS + Casey commits + Railway deploys:

```powershell
Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/chat" -Method POST -Body (@{q="what restaurants are open now"} | ConvertTo-Json) -ContentType "application/json"
```

Expected:
- `tier_used = "2"` (handler now returns a tier-2 reply instead of cascading).
- Response body contains `"current hours data"` and `"/contribute"` and `"golakehavasu.com"`.
- Response body does NOT contain a tier-3-style LLM redirect prose.
- Latency: <500ms (deterministic template, no LLM call).

Out of scope for the Cursor session — note operator result in §11.8 if reported back.

---

## §8 File scope (gotcha #18 disjointness)

**Modified files (closed set):**
- `app/chat/tier2_handler.py` (add `_OPEN_NOW_EMPTY_LISTING_TEMPLATE`, `_open_now_empty_listing`, two conditional inserts in `try_tier2_with_usage`)

**Modified test files:**
- `tests/test_tier2_handler.py` (six new unit tests per §3.2)

**Do NOT touch:**
- `app/chat/tier2_business_shortcut.py` — Phase 7.6 surface; the shortcut + `_pluralize_for_header` are imported, never modified. **The Phase 7.6 regex stays exactly as-is.**
- `app/chat/tier2_db_query.py` — the open_now Python-side filter at line 1092-1099 is the upstream cause; do NOT change it (V1.5 hours backfill is the real fix; Phase 7.7 is graceful degradation).
- `app/chat/tier2_parser.py` / `prompts/tier2_parser.txt` — Phase 7.7 doesn't touch the parser.
- `app/chat/unified_router.py` — Phase 7.5.1 / 7.5.3 surface. The new template lives in `tier2_handler.py` (per design memo §4), NOT co-located with `_UNKNOWN_ENTITY_GAP`.
- `app/chat/halt3_validator.py` / `app/chat/halt3_eval_set.yaml` — Phase 7.5.2 / 7.5.4 surface. Do NOT edit even if q03's expected text needs updating; surface the mismatch in §11.4 and let the operator decide.
- Phase 6.5 / Phase 8 / Phase 9 surfaces.
- Any other dispatch wrapper under `outputs/`.

**Parallel-eligibility:**
- Zero overlap with Phase 7.5.3 Cursor wrapper (`entity_intent.py` + `unified_router.py` for F1/F5).
- Zero overlap with Phase 7.5.4 (`halt3_validator.py` + `halt3_eval_set.yaml`).
- Zero overlap with Phase 8a (`app/conditions/*`).
- Parallel-eligible with all queued lanes.

---

## §9 What NOT to do

- **Do NOT git-commit.** Stop at §11. The operator commits after reviewing your diff.
- **Do NOT add a `from_shortcut` flag to `Tier2Filters`.** The rejected alternative is documented in the design memo §2. The `open_now=True AND category is not None` signal is sufficient — both shortcut-built and parser-built filters with that shape fire the template, which is the intended behavior.
- **Do NOT backfill hours data.** That is the V1.5 carry. Phase 7.7 is graceful degradation, not the data fix.
- **Do NOT modify the Phase 7.6 regex `_OPEN_NOW_LISTING_RE` or the shortcut function.** The shortcut keeps firing exactly as it does today. Phase 7.7 is strictly downstream.
- **Do NOT edit `halt3_eval_set.yaml`** even if q03's expected text fragment needs updating — surface the mismatch in §11.4 instead.
- **Do NOT add a count query** to the template body (e.g. "I have 18 restaurants…"). The design memo §5(c) rejects this — keep the indefinite plural ("I have restaurants…") for now.
- **Do NOT broaden the trigger** to fire on `open_now=False` or `category=None` paths. The guard is intentionally tight.
- **Do NOT add Anthropic calls.** Defeats the purpose.
- **Do NOT add an alembic migration.** No schema change.

---

## §10 If you find a substantive deviation

Per the project's working agreement Rule 4 (deviation discipline):

- Small in-scope deviations (e.g., reword the template body for voice consistency; adjust the log message; add one more parametrized case to the helper test) — proceed with judgment; note in §11.
- Substantive deviations (touching the Phase 7.6 regex; adding a count query; co-locating the template in `unified_router.py`; threading a new `Tier2Filters` field; changing `tier2_db_query.py`'s open_now filter) — STOP and report. Cowork primary will decide.

---

## §11 Final report (you MUST emit this; do not commit)

Emit a structured report covering:

### §11.1 Diffs
- Full unified diff of all modified files (use `git diff` output).
- Confirm no files outside §8 scope were touched.

### §11.2 Acceptance checks
For each check in §5, paste the actual output line(s). Confirm PASS for each. Record pytest collected count delta vs §0 baseline (expected +6).

### §11.3 Per-fix verification

| Fix | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| Helper exists + pluralizes | `test_open_now_empty_listing_helper_pluralizes` | Same test post-fix | ☐ |
| Shortcut-path empty listing | `test_shortcut_open_now_zero_rows_returns_honest_empty_listing` | Same test post-fix | ☐ |
| Parser-path empty listing | `test_parser_path_open_now_zero_rows_returns_honest_empty_listing` | Same test post-fix | ☐ |
| Recommendation-shape cascades | `test_parser_path_open_now_no_category_still_cascades` | Pre+post PASS (None) | ☐ |
| Listing-with-rows unchanged | `test_shortcut_open_now_with_rows_still_renders_listing` | Pre+post PASS | ☐ |
| Non-open_now unchanged | `test_non_open_now_zero_rows_still_returns_none` | Pre+post PASS | ☐ |
| Validator | `python -m app.chat.halt3_validator` all-pass | 30/30 PASS | ☐ |
| 7.6 regression | `tests/test_tier2_business_shortcut.py -k open_now_listing` | All PASS | ☐ |
| 7.5.1 regression | `test_q22_fake_hotel_misroutes...` + `test_q07_tell_me_about_fake_entity...` | All PASS | ☐ |

### §11.4 Substantive findings
- Did the HALT 3 validator's q03 expectation tolerate the new template body, or did it pin a specific text fragment that no longer matches? (Do NOT edit the eval set — surface the mismatch.)
- Did `_pluralize_for_header` from `tier2_business_shortcut.py` cover all expected category labels, or did the helper need a local fallback for an edge case?
- Did the parser-path token accounting (carrying `pi + po` through) cause any downstream metric test to fail?
- Any bugs in existing code noticed but not fixed (out of scope)?
- Anything the wrapper didn't anticipate.

### §11.5 File scope confirmation
Paste output of `git status --short` confirming only §8-listed files modified.

### §11.6 Recommended commit subject
Suggest a commit subject line. Default:

```
feat(phase7.7): tier-2 honest empty listing on open_now zero-rows -- q03 stops cascading to tier-3 when hours data missing; deterministic template, zero LLM tokens; fires for both shortcut-built and parser-built filters with open_now=True AND category set; +6 unit tests; Phase 7.6 surface untouched
```

### §11.7 Open carries
- Prod smoke after deploy (§7) — operator to verify `tier_used=2`, body contains "current hours data", latency <500ms.
- V1.5 hours-data backfill (the real fix) — Phase 7.7 is graceful degradation; once hours data lands, the template will fire less often but still cover sparse-hours categories.
- If validator q03 expectation needs an update to match the new body, follow-up patch in a separate phase (Phase 7.5.4 or later).

### §11.8 Optional operator notes
Reserved for operator to fill in post-deploy if smoke results land before Cursor session closes.

---

End of wrapper. Now go.
