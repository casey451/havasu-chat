# Cursor dispatch prompt — Phase 7.5.3 (F-gap validator/eval polish)

> **What this is:** a paste-ready dispatch wrapper for a fresh Cursor chat to close three low-priority F-gaps left open by the Phase 7.5 production-divergence post-mortem. F1 generalizes a fake-entity whitelist (`entity_intent.py`) with a structural heuristic; F4 tightens 7 over-loose `/contribute` substring asserts in two test files; F5 lets the about-gate accept conversational lead-ins (`unified_router.py`). Genuine polish — not a hot fix.
>
> **Operator:** open a fresh Cursor chat. Paste the entire content of this file (everything below the horizontal rule) as the first message. Cursor takes the work end-to-end through §12 and returns a final report. Do NOT add other context — the wrapper is self-contained.
>
> **Pre-positioned by:** Cowork primary, 2026-05-21. Companion: `outputs/phase_7_5_3_validator_polish_design_memo.md` (audit-amended; F1 call-order reorder is explicitly scoped).
>
> **Estimated effort:** 2-3 hour Cursor session (~150 LOC + ~15 tests).

---

# Phase 7.5.3 — F-gap polish dispatch

You are picking up the havasu-chat project to close three low-severity gaps (F1, F4, F5) carved out of the Phase 7.5 post-mortem. Phases 7.5.1, 7.5.2, and 7.6 have shipped; F1/F4/F5 were deferred. The fixes are pre-validated in the companion design memo. Your job: land the patches + tests + verify each fix has a red→green test.

**File scope (gotcha #18 disjointness):** This dispatch ONLY touches `app/chat/entity_intent.py`, `app/chat/unified_router.py`, two test files in `tests/`, and optionally one new test file. Do NOT touch `app/chat/halt3_validator.py`, `app/chat/halt3_eval_set.yaml`, or `app/chat/tier2_business_shortcut.py` — those belong to 7.5.2 / 7.6. §9 enumerates the closed set.

**Cadence:** Stop at the §12 boundary. Do NOT git-commit. The operator commits after reviewing your diff.

---

## §0 Boot prereqs (verify BEFORE any edits)

Working directory: `C:\Users\casey\projects\havasu-chat`. For any Python invocation, use the venv: `.\.venv\Scripts\python.exe ...` from project root.

This dispatch assumes **Phase 7.5.1, Phase 7.5.2, AND Phase 7.6 have all shipped** on `origin/main`. If any of those three commit subjects are missing from recent commits, HALT and report.

Run all seven checks. HALT and report if any diverge:

```powershell
# 1. origin/main tip — pin should be c81f0d0 (post-7.5.2 ledger commit) OR a
#    newer SHA if 7.6 has merged. Record the actual tip SHA for §12.
git log -1 --format="%h %s" origin/main

# 2. Recent commits — expect to see 7.5.1 (fd695d2), 7.5.2 (64799d5), and
#    possibly 7.6 in the last ~10 commits:
git log -10 --format="%h %s" origin/main

# 3. Alembic single head c9d0e1f2a3b4 (unchanged across 7.5.x / 7.6):
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current

# 4. Pytest baseline — post-7.5.2 was ~2193; if 7.6 shipped, ~2196-2198.
#    Record the actual count for §12 delta math:
.\.venv\Scripts\python.exe -m pytest --collect-only -q | Select-Object -Last 3

# 5. HALT 3 validator 30/30 PASS at HEAD (post-7.5.2 baseline):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator

# 6. Phase 7.5.1 integration tests still GREEN:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3

# 7. RED baselines — F1/F4/F5 each have a "should fail today" probe:

# F1 RED: a structurally-fake query the marker whitelist misses.
.\.venv\Scripts\python.exe -c "from app.chat.entity_intent import query_mentions_fake_entity_marker; print('F1 RED:', query_mentions_fake_entity_marker('Tell me about Joe 9999 Tavern Place'))"
# Expected today: prints "F1 RED: False" (whitelist misses non-marker fabrication).

# F4 RED: confirm the substring assertion sites read as substring-only today:
Select-String -Path tests\test_gap_template_contribute_link.py -Pattern 'assert "/contribute" in r.response' -SimpleMatch | Measure-Object | Select-Object Count
Select-String -Path tests\test_phase38_gap_and_hours.py -Pattern 'assert "/contribute" in r.response' -SimpleMatch | Measure-Object | Select-Object Count
# Expected today: 3 in test_gap_template_contribute_link.py, 4 in test_phase38_gap_and_hours.py = 7 sites.

# F5 RED: lead-in clauses defeat the about-gate today.
.\.venv\Scripts\python.exe -c "from app.chat.unified_router import _about_gate_query_eligible; print('F5 RED bare:', _about_gate_query_eligible('tell me about Totally Fake Business XYZ 404')); print('F5 RED lead-in:', _about_gate_query_eligible('Hey, tell me about Totally Fake Business XYZ 404'))"
# Expected today: bare=True, lead-in=False (the bug).
```

Expected:
- SHA `c81f0d0` (or post-7.6 newer SHA).
- Both `fd695d2` (7.5.1) and `64799d5` (7.5.2) present in `git log -10`.
- Alembic head `c9d0e1f2a3b4` (single).
- Pytest collected count recorded.
- Validator outputs `cited_coverage=100% missing_confab_max=0.00 all_passed=True` with 30+ rows passing.
- All three 7.5.1 integration tests PASS.
- F1 RED prints `False` (whitelist miss). F4 RED prints `3` and `4`. F5 RED prints `bare: True` and `lead-in: False`.

**If any check diverges, HALT and report.** Do not proceed with edits.

---

## §1 The three bugs

### F1 — `query_mentions_fake_entity_marker` is a hand-written whitelist

**Location:** `app/chat/entity_intent.py:89-93` (regex constant), `:141-143` (function).

```python
# entity_intent.py:89-93 — current
_FAKE_ENTITY_MARKER_RE = re.compile(
    r"\b(?:zzz|fake|fabricated|imaginary|nonexistent|totally\s+fake|"
    r"random\s+place|missing|404|99999|888|777|555|xyz)\b",
    re.IGNORECASE,
)

# entity_intent.py:141-143 — current
def query_mentions_fake_entity_marker(query: str) -> bool:
    """True when the user named an obviously non-catalog test/missing entity."""
    return bool(_FAKE_ENTITY_MARKER_RE.search(query or ""))
```

The regex is a literal allow-list of the markers our own eval-set queries use to flag fake entities. Real fabricated business names from real users (e.g. `"Joe's Lake Tavern"`) contain none of these tokens and slip past the marker probe entirely. Defense-in-depth gap — not currently producing user-visible failures, but exactly the shape an adversarial probe would exploit.

### F4 — gap-template tests assert substring presence, not full template

**Location: 7 sites total** —
- `tests/test_gap_template_contribute_link.py:35,45,55` (3 sites; DATE/LOCATION/HOURS).
- `tests/test_phase38_gap_and_hours.py:90,143,246,310` (4 sites; parametrized gap, near-match, q22 misroute, HTTP-shape).

Each assertion has the shape `assert "/contribute" in r.response` — fires on any response containing that substring anywhere. A future regression emitting a malformed gap (`"call (928) 555-0199 or use /contribute"` from a tier-3 confab) trivially passes. Test-quality regression risk, not a current bug.

### F5 — about-gate patterns anchored at start-of-string only

**Location:** `app/chat/unified_router.py:113-119` (`_ABOUT_GATE_STRICT_PATTERNS`), `:122-125` (`_WHAT_IS_ENTITY_RE`).

```python
# unified_router.py:113-119 — current
_ABOUT_GATE_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*tell\s+me\s+(?:more\s+)?about\b", re.I),
    re.compile(r"^\s*(?:can\s+you\s+)?describe\b", re.I),
    re.compile(r"^\s*who(?:'s|\s+is)\b", re.I),
    re.compile(r"^\s*(?:any\s+)?info(?:rmation)?\s+(?:on|about)\b", re.I),
    re.compile(r"^\s*what(?:'s|\s+is)\s+\S+\s+like\b", re.I),
)

# unified_router.py:122-125 — current
_WHAT_IS_ENTITY_RE = re.compile(
    r"^\s*what(?:'s|\s+is)\s+(?!the\s+weather|the\s+time|the\s+date|today)",
    re.I,
)
```

Every pattern is anchored `^\s*`. A query like `"Hey, tell me about X"` or `"Quick question — describe X"` fails every pattern despite being semantically identical to bare `"tell me about X"`. Phase 7.5.1 closed q07's bare shape; F5 is the same bug surface with a conversational lead-in. Defense-in-depth.

---

## §2 The fix design

### Fix F1 — augment whitelist with structural heuristic + REORDER call sites

**Touch points:**
- `app/chat/entity_intent.py` — add 2 module-level regex constants + helper `_looks_structurally_fake`; extend `query_mentions_fake_entity_marker` to call it on whitelist miss.
- **`app/chat/unified_router.py:282-302` (`_unknown_entity_about_gate`) — REORDER REQUIRED.** The marker probe at line 288 currently runs BEFORE `match_entity` (line 295) and `find_near_match` (line 297). With the F1 heuristic added, `mdshrkbrwry` would fire the consonant-run rule and short-circuit BEFORE rapidfuzz at `entity_intent.py:245-257` ever runs — regressing the Mudshark Brewery typo case. Move the marker probe to run AFTER both `match_entity` and `find_near_match` return None.
- **`app/chat/unified_router.py:651-655` (second call site in `_enrich_entity_from_db`)** — review for same regression risk; if `mdshrkbrwry` enters this path, apply matching reorder. `mdshrkbrwry` is ≤4 tokens so the `< 5 tokens` short-circuit in `_looks_structurally_fake` already protects it here — but verify by tracing.

**Step F1.a — Add module-level regex + helper in `entity_intent.py`.**

Insert these constants near the other regex constants (after `_BEST_CATEGORY_RE` at line ~138):

```python
# Phase 7.5.3 F1 — structural heuristic for unmarked fabricated entity names.
# Catches "Joe 9999 Tavern" (digit density) and "zzznonexistent" (consonant
# run) shapes the _FAKE_ENTITY_MARKER_RE whitelist misses. Skipped on short
# queries (< 5 tokens) to avoid false-positives on legitimate short entity
# names like "Heat Hotel hours" or "phone for mdshrkbrwry" (the rapidfuzz
# typo escape hatch in near_match_subject_overlaps must still take precedence
# for the latter — call-order reorder in unified_router._unknown_entity_about_gate
# ensures match_entity + find_near_match run first).
_HIGH_DIGIT_DENSITY_RE = re.compile(r"\b[A-Za-z]+\s*\d{3,}\b")
_CONSONANT_RUN_RE = re.compile(r"\b[bcdfghjklmnpqrstvwxyz]{4,}", re.I)


def _looks_structurally_fake(query: str) -> bool:
    """Best-effort detector for fabricated entity names without marker tokens.

    Returns True when the query contains either:
      - a token with high digit density (e.g. "Business 4042", "XYZ 555")
      - a token with a 4+ consecutive-consonant run (e.g. "zzznonexistent")

    Skipped on queries with < 5 tokens to avoid false-positives on short
    legitimate entity references ("Heat Hotel", "phone for mdshrkbrwry").
    """
    q = (query or "").strip()
    if len(q.split()) < 5:
        return False
    if _HIGH_DIGIT_DENSITY_RE.search(q):
        return True
    if _CONSONANT_RUN_RE.search(q):
        return True
    return False
```

Then extend `query_mentions_fake_entity_marker` at line 141-143:

```python
def query_mentions_fake_entity_marker(query: str) -> bool:
    """True when the user named an obviously non-catalog test/missing entity.

    Phase 7.5.3 F1: whitelist regex still handles eval markers (xyz / 404 / etc.).
    Structural heuristic in _looks_structurally_fake catches unmarked
    fabrications (digit-density + consonant-run shapes) on queries >= 5 tokens.
    """
    if _FAKE_ENTITY_MARKER_RE.search(query or ""):
        return True
    return _looks_structurally_fake(query or "")
```

**Step F1.b — Reorder call sequence in `_unknown_entity_about_gate` (`unified_router.py:282-302`).**

Current (line numbers per HEAD at SHA `c81f0d0`):

```python
    try:
        from app.chat.entity_intent import (
            near_match_subject_overlaps,
            query_mentions_fake_entity_marker,
        )

        if query_mentions_fake_entity_marker(raw):        # line 288 — MOVE THIS
            return _UNKNOWN_ENTITY_GAP

        from app.chat.entity_matcher import find_near_match, match_entity

        if db is not None:
            refresh_entity_matcher(db)
            if match_entity(raw, db) is not None:         # line 295
                return None
            near = find_near_match(raw, db)               # line 297
            if near is not None and near_match_subject_overlaps(raw, near[0]):
                return None  # plausible "did you mean" — defer to existing path
    except Exception:
        logging.exception("_unknown_entity_about_gate: matcher probe failed")
        return None

    return _UNKNOWN_ENTITY_GAP
```

After reorder:

```python
    try:
        from app.chat.entity_intent import (
            near_match_subject_overlaps,
            query_mentions_fake_entity_marker,
        )
        from app.chat.entity_matcher import find_near_match, match_entity

        if db is not None:
            refresh_entity_matcher(db)
            if match_entity(raw, db) is not None:
                return None
            near = find_near_match(raw, db)
            if near is not None and near_match_subject_overlaps(raw, near[0]):
                return None  # plausible "did you mean" — defer to existing path

        # Phase 7.5.3 F1: marker probe runs AFTER matcher + near-match so the
        # consonant-run heuristic cannot regress legitimate typo near-matches
        # like "mdshrkbrwry" -> Mudshark Brewery (rapidfuzz in
        # near_match_subject_overlaps must take precedence).
        if query_mentions_fake_entity_marker(raw):
            return _UNKNOWN_ENTITY_GAP
    except Exception:
        logging.exception("_unknown_entity_about_gate: matcher probe failed")
        return None

    return _UNKNOWN_ENTITY_GAP
```

**Step F1.c — Review `_enrich_entity_from_db` (`unified_router.py:649-661`).**

```python
def _enrich_entity_from_db(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    session: dict | None,
    current_turn: int | None,
) -> IntentResult:
    from app.chat.entity_intent import (
        is_category_open_now_listing,
        query_mentions_fake_entity_marker,
    )
    from app.chat.tier2_business_shortcut import try_business_listing_shortcut

    if query_mentions_fake_entity_marker(query or ""):        # line 655
        return replace(intent_result, entity=None)
    ...
```

This call site runs BEFORE `match_entity` at line 665 — same shape as the original `_unknown_entity_about_gate`. The Mudshark Brewery typo case `"phone for mdshrkbrwry"` is 3 tokens — the `< 5 tokens` short-circuit in `_looks_structurally_fake` already protects it. **Verify** by running the existing `test_near_match_typo_returns_did_you_mean` regression at `tests/test_phase38_gap_and_hours.py:108` after applying F1.a. If it still passes, no reorder needed here. If it fails, apply the same reorder pattern.

**Rejected alternative:** LLM-based fake-entity classifier. Rejected because it would re-introduce LLM nondeterminism into the deterministic guard layer — exactly the failure mode 7.5.1 worked to remove.

### Fix F4 — full-template equality + `tier_used == "gap_template"`

**Touch points (7 sites):**

| File | Line | Current | Replacement |
|---|---|---|---|
| `tests/test_gap_template_contribute_link.py` | 35 | `assert "/contribute" in r.response` | full template eq + tier check |
| `tests/test_gap_template_contribute_link.py` | 45 | `assert "/contribute" in r.response` | full template eq + tier check |
| `tests/test_gap_template_contribute_link.py` | 55 | `assert "/contribute" in r.response` | full template eq + tier check |
| `tests/test_phase38_gap_and_hours.py` | 90 | `assert "/contribute" in r.response` | full template eq + tier check |
| `tests/test_phase38_gap_and_hours.py` | 143 | `assert "/contribute" in r.response` | tier check; near-match path uses tier1 prefix |
| `tests/test_phase38_gap_and_hours.py` | 246 | `assert "/contribute" in r.response` | full template eq + tier check |
| `tests/test_phase38_gap_and_hours.py` | 310 | `assert "/contribute" in (body.get("response") or "")` | full template eq + tier check (HTTP body) |

**Strategy:** import the `_GAP_TAIL` constant from `unified_router` (this is the shared `"or add it at /contribute"` tail used by every gap template at `unified_router.py:251-258`) and assert both that the response **ends** with `_GAP_TAIL` AND that `r.tier_used == "gap_template"`. The `tier_used` check is the cheapest catch — any response that contains `/contribute` but is NOT actually the gap-template tier (e.g. a tier-3 LLM confab that mentions /contribute) fails.

**Sample replacement** (for `test_gap_template_contribute_link.py:35`):

```python
# Before
assert "/contribute" in r.response

# After
from app.chat.unified_router import _GAP_TAIL
assert r.tier_used == "gap_template"
assert r.response.rstrip().endswith(_GAP_TAIL)
assert "/contribute" in r.response  # keep — guards the imported constant itself
```

**Special case — line 143** (`tests/test_phase38_gap_and_hours.py`): this is the near-match typo case (`mdshrkbrwry → Mudshark Brewery`). The response is a Tier 1 answer prefix + a soft escape hatch — NOT the bare gap template — so the equality form does not apply. Replace with:

```python
# Line 143 — keep substring check, add tier_used + structural shape:
assert r.tier_used == "gap_template"
assert "/contribute" in r.response
assert "different place" in r.response.lower()  # already present at line 144
```

(Line 143 already asserts substring + the line below asserts `"different place"`. Add the `tier_used` line; document why this site differs in §12.4.)

**Special case — line 310** (HTTP test): response lives at `body.get("response")`. Apply equality against `_GAP_TAIL` on `body["response"]`:

```python
# Before
assert "/contribute" in (body.get("response") or "")

# After
from app.chat.unified_router import _GAP_TAIL
resp = body.get("response") or ""
assert resp.rstrip().endswith(_GAP_TAIL)
assert "/contribute" in resp
```

**Verify `_GAP_TAIL` is the right import.** Inspect `unified_router.py` near lines 250-258 to confirm `_GAP_TAIL` is the canonical tail constant. If the templates use a different shared constant, use that instead. If templates are duplicated as inline string literals (no shared constant), import the per-sub-intent body constant or fall back to asserting against the literal returned by `_catalog_gap_response` — choose the lightest reproduce-the-template path.

**Rejected alternative:** snapshot files. Rejected because the templates are short Python string literals; importing the constant and equality-checking is lighter than introducing a snapshot mechanism.

### Fix F5 — lead-in prefix on all about-gate patterns

**Touch points:**
- `app/chat/unified_router.py:113-119` — all 5 `_ABOUT_GATE_STRICT_PATTERNS` members.
- `app/chat/unified_router.py:122-125` — `_WHAT_IS_ENTITY_RE`.

**Strategy:** introduce a module-level `_LEAD_IN_PREFIX` regex fragment that matches up to 40 chars of a lead-in clause followed by punctuation (`,`, `—`, or `-`). The fragment is prepended to each pattern in place of the existing `^\s*` anchor (the new prefix already starts with `^\s*`).

**Before / After — `_ABOUT_GATE_STRICT_PATTERNS` (lines 113-119):**

```python
# Before — current
_ABOUT_GATE_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*tell\s+me\s+(?:more\s+)?about\b", re.I),
    re.compile(r"^\s*(?:can\s+you\s+)?describe\b", re.I),
    re.compile(r"^\s*who(?:'s|\s+is)\b", re.I),
    re.compile(r"^\s*(?:any\s+)?info(?:rmation)?\s+(?:on|about)\b", re.I),
    re.compile(r"^\s*what(?:'s|\s+is)\s+\S+\s+like\b", re.I),
)

# After — Phase 7.5.3 F5
# Optional lead-in clause: up to 40 chars of letters/spaces/comma/apostrophe/dash
# followed by a comma, em-dash, or dash, then whitespace.
# Captures "Hey, ", "Quick question — ", "OK, so ", etc.
_LEAD_IN_PREFIX = r"^\s*(?:[a-z][a-z\s,'-]{0,40}[,—\-]\s+)?"

_ABOUT_GATE_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_LEAD_IN_PREFIX + r"tell\s+me\s+(?:more\s+)?about\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"(?:can\s+you\s+)?describe\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"who(?:'s|\s+is)\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"(?:any\s+)?info(?:rmation)?\s+(?:on|about)\b", re.I),
    re.compile(_LEAD_IN_PREFIX + r"what(?:'s|\s+is)\s+\S+\s+like\b", re.I),
)
```

**Before / After — `_WHAT_IS_ENTITY_RE` (lines 122-125):**

```python
# Before
_WHAT_IS_ENTITY_RE = re.compile(
    r"^\s*what(?:'s|\s+is)\s+(?!the\s+weather|the\s+time|the\s+date|today)",
    re.I,
)

# After
_WHAT_IS_ENTITY_RE = re.compile(
    _LEAD_IN_PREFIX + r"what(?:'s|\s+is)\s+(?!the\s+weather|the\s+time|the\s+date|today)",
    re.I,
)
```

**Definition placement.** `_LEAD_IN_PREFIX` must be defined ABOVE `_ABOUT_GATE_STRICT_PATTERNS` (i.e. before line 113). Place it just above the `_ABOUT_GATE_STRICT_PATTERNS` block with a short comment explaining the shape.

**Rejected alternative:** drop the start-of-string anchor entirely. Rejected because mid-sentence `"the description says 'tell me about your services'"` would wrongly fire. The lead-in prefix narrows the relaxation to a documented punctuation-anchored shape.

---

## §3 Red-test prep (BEFORE applying fixes)

Each fix must have a failing test that passes after the fix. The Mudshark Brewery negative-regression for F1 is **non-negotiable** — it's the load-bearing test that proves F1's heuristic doesn't break legitimate typo near-matches.

### F1 red tests — new unit-test file

Create `tests/test_entity_intent_structural_heuristic.py` (NEW file):

```python
"""Unit tests for Phase 7.5.3 F1: _looks_structurally_fake heuristic and the
generalized query_mentions_fake_entity_marker behavior.

Red tests (would FAIL against pre-7.5.3 code where the function is a pure
whitelist regex): structurally fabricated names without marker tokens.

Green tests: real entities — including typo-shaped real entities — must NOT
trigger the heuristic. The Mudshark Brewery typo case is the load-bearing
negative-regression — F1 must not steal it from the rapidfuzz escape hatch in
near_match_subject_overlaps.
"""
from __future__ import annotations

import unittest

from app.chat.entity_intent import (
    _looks_structurally_fake,
    query_mentions_fake_entity_marker,
)


class LooksStructurallyFakeTests(unittest.TestCase):

    # ------- Positive: structurally-fake shapes (RED before F1) -------

    def test_high_digit_density_token_flagged(self) -> None:
        self.assertTrue(
            _looks_structurally_fake("Tell me about Joe 9999 Tavern Place")
        )

    def test_consonant_run_flagged(self) -> None:
        self.assertTrue(
            _looks_structurally_fake("Tell me about zzznonexistent fancy venue")
        )

    def test_long_query_with_consonant_run_flagged(self) -> None:
        self.assertTrue(
            _looks_structurally_fake("Where is xkcdbzzz Restaurant in Lake Havasu")
        )

    # ------- Negative regressions (must stay False) -------

    def test_mudshark_brewery_typo_not_flagged(self) -> None:
        # Phase 7.5.3 F1 load-bearing negative regression. mdshrkbrwry has a
        # 4-consonant run but the query is < 5 tokens so the short-circuit
        # protects it. The rapidfuzz escape hatch in
        # near_match_subject_overlaps must take precedence.
        self.assertFalse(_looks_structurally_fake("phone for mdshrkbrwry"))

    def test_heat_hotel_not_flagged(self) -> None:
        self.assertFalse(_looks_structurally_fake("Heat Hotel hours"))

    def test_short_query_skipped(self) -> None:
        # < 5 tokens — short-circuit.
        self.assertFalse(_looks_structurally_fake("zzznonexistent venue"))

    def test_empty_query_returns_false(self) -> None:
        self.assertFalse(_looks_structurally_fake(""))


class QueryMentionsFakeEntityMarkerTests(unittest.TestCase):

    # ------- Whitelist path preserved -------

    def test_xyz_marker_still_flagged(self) -> None:
        self.assertTrue(
            query_mentions_fake_entity_marker(
                "Tell me about Totally Fake Business XYZ 404"
            )
        )

    def test_zzz_marker_still_flagged(self) -> None:
        self.assertTrue(
            query_mentions_fake_entity_marker("about zzznonexistent venue")
        )

    # ------- Heuristic path (RED before F1) -------

    def test_unmarked_digit_density_flagged_via_heuristic(self) -> None:
        # No whitelist token; relies on _looks_structurally_fake.
        self.assertTrue(
            query_mentions_fake_entity_marker(
                "Tell me about Joe 9999 Tavern Place"
            )
        )

    # ------- Negative regressions -------

    def test_mudshark_brewery_typo_not_flagged(self) -> None:
        # Same load-bearing assertion at the function-level.
        self.assertFalse(
            query_mentions_fake_entity_marker("phone for mdshrkbrwry")
        )

    def test_heat_hotel_not_flagged(self) -> None:
        self.assertFalse(
            query_mentions_fake_entity_marker("rating for Heat Hotel")
        )

    def test_short_real_entity_not_flagged(self) -> None:
        self.assertFalse(query_mentions_fake_entity_marker("hours for Mudshark"))


if __name__ == "__main__":
    unittest.main()
```

Run BEFORE applying §4 fix: `.\.venv\Scripts\python.exe -m pytest tests/test_entity_intent_structural_heuristic.py -xvs`.

Expected pre-F1: import error on `_looks_structurally_fake` (function doesn't exist yet) OR — if you import the function name with `getattr` first — the three positive heuristic tests FAIL. The Mudshark Brewery negative tests should PASS today regardless (they're guarding against regression, not asserting the fix).

### F4 red prep — temporary template corruption

F4 changes existing assertions, not new test files. To verify the new (tightened) assertions actually catch malformed gap templates, do a temporary red-then-green:

1. After applying F4, **temporarily** corrupt one gap-template constant in `unified_router.py` (e.g. change `_GAP_TAIL = "..."` to drop the `/contribute` link or append a stray token).
2. Run the F4 test suite — must FAIL.
3. Restore the constant — must PASS.

Document this round-trip in §12.3. Do NOT commit the corruption.

### F5 red test — lead-in clause about-gate

Add to `tests/test_phase7_halt3_validation.py` (APPEND new test functions; do NOT modify existing tests — Phase 7.5.2 owns the existing surface). Use the `test_q07_...` pattern at the bottom of that file as the template:

```python
def test_f5_lead_in_clause_enters_about_gate(db: Session) -> None:
    """Phase 7.5.3 F5: conversational lead-in clauses must not defeat the
    about-gate. Pre-fix: 'Hey, tell me about X' bypasses the gate and falls
    through to tier-3 LLM. Post-fix: the lead-in is absorbed by _LEAD_IN_PREFIX
    and the gate fires identically to bare 'tell me about X'.
    """
    from unittest.mock import patch
    from app.chat.unified_router import route

    def _tier3_should_not_be_called(*args, **kwargs):
        raise AssertionError(
            "tier-3 LLM invoked for F5 lead-in shape — _LEAD_IN_PREFIX failed"
        )

    queries = [
        "Hey, tell me about Totally Fake Business XYZ 404",
        "Quick question — describe Totally Fake Business XYZ 404",
        "OK so, what is Totally Fake Business XYZ 404",
    ]
    with patch(
        "app.chat.unified_router.answer_with_tier3",
        side_effect=_tier3_should_not_be_called,
    ):
        for q in queries:
            r = route(q, f"sess-f5-{abs(hash(q)) % 10000}", db)
            assert r.tier_used == "gap_template", (
                f"Expected gap_template for {q!r}, got {r.tier_used}. "
                f"Response: {r.response}"
            )


def test_f5_about_gate_query_eligible_lead_in_positive() -> None:
    """Unit-level: _about_gate_query_eligible must accept lead-in shapes."""
    from app.chat.unified_router import _about_gate_query_eligible

    assert _about_gate_query_eligible("Hey, tell me about Heat Hotel")
    assert _about_gate_query_eligible("Quick question — describe Heat Hotel")
    assert _about_gate_query_eligible("OK so, what is Heat Hotel")
    # Bare shapes still fire (no regression):
    assert _about_gate_query_eligible("tell me about Heat Hotel")
    assert _about_gate_query_eligible("describe Heat Hotel")


def test_f5_about_gate_no_overmatch_on_mid_sentence() -> None:
    """Negative: mid-sentence 'tell me about' inside a quoted string does NOT fire.
    The lead-in prefix requires punctuation; quoted-context drift should miss."""
    from app.chat.unified_router import _about_gate_query_eligible

    assert not _about_gate_query_eligible(
        "the description says 'tell me about your services' is the legit?"
    )
```

Run BEFORE applying §6 fix: `.\.venv\Scripts\python.exe -m pytest tests/test_phase7_halt3_validation.py -k "f5_" -xvs`.

Expected pre-F5: `test_f5_lead_in_clause_enters_about_gate` FAILS (tier-3 gets called); `test_f5_about_gate_query_eligible_lead_in_positive` FAILS (lead-in returns False); `test_f5_about_gate_no_overmatch_on_mid_sentence` PASSES today (bug is over-narrow, not over-broad).

If any positive-RED test PASSES prematurely, F5 has already been fixed or the test doesn't reproduce — investigate before proceeding.

---

## §4 Apply Fix F1 (entity_intent.py heuristic + unified_router.py reorder)

Edit `app/chat/entity_intent.py` per §2 Fix F1, step F1.a.

Edit `app/chat/unified_router.py` per §2 Fix F1, step F1.b (call-order reorder in `_unknown_entity_about_gate`).

After the edits:

```powershell
# 1. F1 unit tests PASS:
.\.venv\Scripts\python.exe -m pytest tests/test_entity_intent_structural_heuristic.py -xvs

# 2. Mudshark Brewery typo regression still PASS (load-bearing for F1 safety):
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_near_match_typo_returns_did_you_mean -xvs

# 3. Phase 7.5.1 q07 integration test still PASS (gate still fires on marker queries):
.\.venv\Scripts\python.exe -m pytest tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3 -xvs

# 4. Phase 7.5.1 q22 integration test still PASS (near-match overlaps unchanged):
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape -xvs
```

**All four checks must PASS.** If Mudshark Brewery fails, the F1 heuristic stole the typo case — verify the call-order reorder in `_unknown_entity_about_gate` landed correctly, then verify `_enrich_entity_from_db` per step F1.c.

---

## §5 Apply Fix F4 (tighten 7 substring assertions)

Edit `tests/test_gap_template_contribute_link.py` at lines 35, 45, 55 per §2 Fix F4.

Edit `tests/test_phase38_gap_and_hours.py` at lines 90, 143, 246, 310 per §2 Fix F4. **Line 143 is the special case** (near-match path — tier1 prefix, no full template equality).

After the edits:

```powershell
# 1. All 7 site files pass:
.\.venv\Scripts\python.exe -m pytest tests/test_gap_template_contribute_link.py tests/test_phase38_gap_and_hours.py -xvs

# 2. Round-trip RED-then-GREEN: temporarily corrupt _GAP_TAIL in unified_router.py
#    (e.g. drop "/contribute" from the string), run the tests — must FAIL —
#    then restore. Document outcome in §12.3.
```

All F4 sites must PASS. The corruption round-trip is your proof that the tightened assertion actually catches structural breakage. Do NOT commit the corruption.

---

## §6 Apply Fix F5 (lead-in prefix on about-gate)

Edit `app/chat/unified_router.py` per §2 Fix F5:
1. Define `_LEAD_IN_PREFIX` above `_ABOUT_GATE_STRICT_PATTERNS` (around line 112).
2. Prepend `_LEAD_IN_PREFIX` to all 5 `_ABOUT_GATE_STRICT_PATTERNS` members.
3. Prepend `_LEAD_IN_PREFIX` to `_WHAT_IS_ENTITY_RE`.

After the edits:

```powershell
# 1. F5 red tests now GREEN:
.\.venv\Scripts\python.exe -m pytest tests/test_phase7_halt3_validation.py -k "f5_" -xvs

# 2. Phase 7.5.1 q07 bare-shape test still PASS (no regression on bare path):
.\.venv\Scripts\python.exe -m pytest tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3 -xvs

# 3. Phase 7.5.2 adversarial q24-q30 still PASS (lead-in shouldn't regress
#    the validator's adversarial rows):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
```

All three checks must PASS. If validator regresses on q24-q30, the lead-in prefix is over-matching one of the adversarial probe shapes — narrow the prefix's `[a-z\s,'-]{0,40}` span or add an exclusion.

---

## §7 Acceptance verification

Run all six checks. ALL must pass before §12.

```powershell
# 1. HALT 3 validator still 30/30 PASS (no validator-row changes from 7.5.3):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
# Expected: cited_coverage=100% missing_confab_max=0.00 all_passed=True

# 2. Full pytest suite — count grows by ~15 (F1 unit tests + F5 tests):
.\.venv\Scripts\python.exe -m pytest -q
# Expected: baseline + ~15 new tests, 0 failures

# 3. Per-fix red→green confirmation:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_entity_intent_structural_heuristic.py `
    tests/test_phase7_halt3_validation.py -k "f5_"

# 4. Phase 7.5.1 integration tests non-regression:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3 `
    tests/test_phase38_gap_and_hours.py::test_near_match_typo_returns_did_you_mean

# 5. F4 tightened tests pass:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_gap_template_contribute_link.py `
    tests/test_phase38_gap_and_hours.py

# 6. Ruff clean on touched files:
.\.venv\Scripts\python.exe -m ruff check `
    app/chat/entity_intent.py `
    app/chat/unified_router.py `
    tests/test_gap_template_contribute_link.py `
    tests/test_phase38_gap_and_hours.py `
    tests/test_phase7_halt3_validation.py `
    tests/test_entity_intent_structural_heuristic.py
```

**If any check fails, HALT and investigate.** Do not proceed to §12.

---

## §8 Regression check (Phase 7.5.1 + 7.5.2 + 7.6 non-regression)

The F1/F4/F5 polish must not regress any prior phase's fixes. Run these explicit anchor tests:

```powershell
# Phase 7.5.1 — q07/q22/q03 routing fixes + near-match typo:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase38_gap_and_hours.py::test_near_match_typo_returns_did_you_mean `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3 `
    tests/test_near_match_subject_overlaps.py

# Phase 7.5.2 — HALT 3 validator hardening (G1-G5 + F3 + adversarial q24-q30):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -xvs

# Phase 7.6 — tier-2 OPEN_NOW listing shortcut (if 7.6 shipped):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -k "open_now_listing" -xvs
```

All must PASS. If 7.6's `test_handler_open_now_listing_shortcut_zero_tokens` doesn't exist yet (7.6 not shipped), skip that line and note in §12.

---

## §9 File scope (gotcha #18 disjointness)

**Modified files (closed set):**
- `app/chat/entity_intent.py` — F1: add `_HIGH_DIGIT_DENSITY_RE`, `_CONSONANT_RUN_RE`, `_looks_structurally_fake`; extend `query_mentions_fake_entity_marker`.
- `app/chat/unified_router.py` — F1 call-order reorder in `_unknown_entity_about_gate` (lines 282-302); F5 `_LEAD_IN_PREFIX` + 6 pattern updates (lines 113-119, 122-125).
- `tests/test_gap_template_contribute_link.py` — F4: lines 35, 45, 55.
- `tests/test_phase38_gap_and_hours.py` — F4: lines 90, 143, 246, 310.
- `tests/test_phase7_halt3_validation.py` — F5: APPEND new test functions; do NOT modify existing tests (soft conflict with 7.5.2 which already extended this file).

**New files:**
- `tests/test_entity_intent_structural_heuristic.py` — F1 unit tests.

**Do NOT touch:**
- `app/chat/halt3_validator.py` — owned by Phase 7.5.2; no changes needed for F1/F4/F5.
- `app/chat/halt3_eval_set.yaml` — owned by Phase 7.5.2; no new eval rows needed (F1 is a guard layer, not an evaluable behavior; F4 is test-side; F5 is gate behavior already covered by existing q07 row).
- `app/chat/tier2_business_shortcut.py` — owned by Phase 7.6.
- `app/chat/entity_matcher.py`, `app/chat/intent_classifier.py`, `app/chat/tier2_handler.py`, `app/chat/tier3_handler.py` — out of scope.
- Phase 6.5 / Phase 8a / Phase 9 surfaces (`home.html`, `app/conditions/`, `app/alerts/`, event RRULE code).
- Any docs under `docs/` (`STATE.md`, `master_build_plan.md`, `docs/maintainability/*.md`) — Cowork primary updates these post-ship.
- Any other dispatch wrapper under `outputs/`.

**Soft conflict acknowledgment:** F5 tests are added to `tests/test_phase7_halt3_validation.py` which Phase 7.5.2 also extended. APPEND new test functions at the bottom — do NOT modify any test that existed before this dispatch. If you encounter a merge surprise, HALT and report.

---

## §10 What NOT to do

- **Do NOT git-commit.** Stop at §12.
- **Do NOT implement an LLM-based fake-entity classifier for F1.** Re-introduces nondeterminism into the deterministic guard layer.
- **Do NOT use a snapshot-test mechanism for F4.** Import the template constant and equality-check; the templates are short Python string literals.
- **Do NOT touch F2, F6, or F7.** F2 (catalog-mention pattern hardening) and F6/F7 (other watch items) are V1.5 carries; out of scope.
- **Do NOT broaden `_LEAD_IN_PREFIX`** beyond the documented 40-char punctuation-anchored shape. Mid-sentence drift must continue to miss.
- **Do NOT modify the existing `_FAKE_ENTITY_MARKER_RE` whitelist** for F1 — augment, do not replace. The eval-set markers still need to work via the whitelist fast-path.
- **Do NOT add new dependencies.** `rapidfuzz` is already in use; no other imports needed.
- **Do NOT add an alembic migration.** No schema changes.
- **Do NOT modify `app/chat/halt3_validator.py`, `app/chat/halt3_eval_set.yaml`, or `app/chat/tier2_business_shortcut.py`.** Phases 7.5.2 and 7.6 own those.

---

## §11 If you find a substantive deviation

Per the project's working agreement Rule 4 (deviation discipline):

- Small in-scope deviations (regex tweak; choosing list-vs-tuple; expanding F1 token shortlist; adjusting F4 import path if `_GAP_TAIL` isn't the right constant; widening `_LEAD_IN_PREFIX` punctuation set) — proceed with judgment; note in §12.
- Substantive deviations (touching a file not in §9; reordering `_enrich_entity_from_db` per F1.c; adding a synonym group; changing a test fixture pattern; adding a dependency) — STOP and report. Cowork primary will decide.

**§13 self-correction policy:** if mid-task you discover the wrapper is wrong about a line number, a constant name, or a call site — proceed with the corrected interpretation IF AND ONLY IF it preserves the file-scope disjointness in §9. Document every deviation in §12.4 with the wrapper's claim vs. what you found.

---

## §12 Final report (you MUST emit this; do not commit)

Emit a structured report covering:

### §12.1 Diffs
- Full unified diff of all modified files (use `git diff` output).
- Confirm no files outside §9 scope were touched.

### §12.2 Acceptance checks
For each check in §7, paste the actual output line(s). Confirm PASS for each. Record pytest collected count delta vs §0 baseline.

### §12.3 Per-fix red→green verification

| Fix | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| F1 (heuristic) | `test_entity_intent_structural_heuristic.py::LooksStructurallyFakeTests::test_high_digit_density_token_flagged` | Same test post-fix | ☐ |
| F1 (heuristic) | `test_entity_intent_structural_heuristic.py::QueryMentionsFakeEntityMarkerTests::test_unmarked_digit_density_flagged_via_heuristic` | Same test post-fix | ☐ |
| F1 (Mudshark safety) | `test_phase38_gap_and_hours.py::test_near_match_typo_returns_did_you_mean` | Non-regression PASS | ☐ |
| F4 (round-trip) | Temporarily corrupted `_GAP_TAIL` → 7 sites FAIL | Restored constant → all PASS | ☐ |
| F5 (about-gate lead-in) | `test_phase7_halt3_validation.py::test_f5_lead_in_clause_enters_about_gate` | Same test post-fix | ☐ |
| F5 (unit) | `test_phase7_halt3_validation.py::test_f5_about_gate_query_eligible_lead_in_positive` | Same test post-fix | ☐ |
| Validator | `python -m app.chat.halt3_validator` 30/30 PASS pre + post | | ☐ |
| Phase 7.5.1 | q07 + q22 + q03 + near-match-typo all PASS | Non-regression | ☐ |

### §12.4 Substantive findings
- F1.c: did `_enrich_entity_from_db` at `unified_router.py:649-661` need a reorder, or did the `< 5 tokens` short-circuit in `_looks_structurally_fake` already protect `"phone for mdshrkbrwry"`?
- F4: which constant ended up being the right import — `_GAP_TAIL` or a per-sub-intent template? Did line 143 require the special-case handling described in §2?
- F5: any adversarial q24-q30 row regress, and how did you narrow the prefix?
- Anything surprising in the wrapper's line-number claims (verify each against the actual file at HEAD).

### §12.5 File scope confirmation
Paste output of `git status --short` confirming only §9-listed files modified.

### §12.6 Recommended commit subject
Suggest a commit subject line. Default:

```
feat(phase7.5.3): F-gap polish -- F1 generalize fake-entity marker with structural heuristic (digit density + consonant run) + reorder _unknown_entity_about_gate so matcher/near-match run before marker probe (Mudshark typo regression preserved); F4 tighten 7 /contribute substring asserts to full-template equality + tier_used check; F5 _LEAD_IN_PREFIX allows conversational lead-ins on all 5 about-gate strict patterns + _WHAT_IS_ENTITY_RE; ~15 new tests; validator 30/30 non-regression
```

### §12.7 Open carries
- F2 (catalog-mention pattern hardening) — V1.5.
- F6/F7 (other low-priority gaps from the post-mortem) — V1.5.
- 7.5.4 watch items (G4 list promiscuity + template-echo sanitization audit) — separate dispatch when prioritized.
- Anything else the wrapper or memo didn't anticipate.

---

End of wrapper. Now go.
