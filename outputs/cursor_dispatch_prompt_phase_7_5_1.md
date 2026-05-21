# Cursor dispatch prompt — Phase 7.5.1 (prod-divergence fix)

> **What this is:** a paste-ready dispatch wrapper for a fresh Cursor chat to fix three distinct production bugs that escaped Phase 7.5's 22/22 local-validator PASS at SHA `b701759`. All three were discovered 2026-05-19 during the Lane H post-Railway-recovery flag-flip smoke check.
>
> **Operator:** open a fresh Cursor chat. Paste the entire content of this file (everything below the horizontal rule) as the first message. Cursor takes the work end-to-end through §12 and returns a final report. Do NOT add any other context — the wrapper is self-contained.
>
> **Pre-positioned by:** Cowork primary, 2026-05-19. Companion: `outputs/phase_7_5_prod_divergence_investigation.md` (full findings record).
>
> **Estimated effort:** 2-4 hours Cursor session.

---

# Phase 7.5.1 — Production divergence fix dispatch

You are picking up the havasu-chat project to fix three production bugs that escaped Phase 7.5's 22/22 PASS at SHA `b701759`. The bugs are documented below with full diagnostic context; the fix designs are pre-validated by three parallel investigations. Your job is to land the patches + tests + verify the bugs reproduce-then-fix in the local validator.

**File scope (gotcha #18 disjointness):** This dispatch ONLY touches `app/chat/*.py` + `tests/test_*.py` files + `app/chat/halt3_eval_set.yaml`. Do NOT touch templates, routes, conditions, alerts, or any Phase 6.5 / Phase 8 surface. The wrapper enumerates expected files in §9.

**Cadence:** Stop at the §12 boundary. Do NOT git-commit. The operator commits after reviewing your diff.

---

## §0 Boot prereqs (verify BEFORE any edits)

Working directory: `C:\Users\casey\projects\havasu-chat`. For any Python invocation, use the venv: `.\.venv\Scripts\python.exe ...` from project root.

Run all four checks. HALT and report if any diverge:

```powershell
# 1. origin/main tip should be f18f709 (or newer chore commit if subsequent landed)
git log -1 --format="%h %s" origin/main

# 2. Alembic single head c9d0e1f2a3b4
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current

# 3. Pytest baseline 2166 collected
.\.venv\Scripts\python.exe -m pytest --collect-only -q | Select-Object -Last 3

# 4. HALT 3 validator 22/22 PASS at HEAD (the broken baseline — passes despite prod bugs)
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
```

Expected: SHA `f18f709`, alembic head `c9d0e1f2a3b4` (single), pytest 2166 collected, validator outputs `cited_coverage=100% missing_confab_max=0.00 all_passed=True`.

**If any check diverges, HALT and report.** Do not proceed with edits.

---

## §1 The three bugs — full diagnostic context

Phase 7.5 shipped at SHA `b701759` with HALT 3 validator at 22/22 PASS. Production smoke check 2026-05-19 (post-Railway-recovery, `FEATURE_FLAG_DISCLOSURE_RENDERER=true`) revealed three distinct user-visible failures on the exact queries Phase 7.5 was supposed to fix. All three persist even with the flag reverted to `false` because (per `app/chat/disclosure_render.py:1-26`) the flag actually controls **sponsored-content disclosure rendering** (FTC compliance for ads), NOT anti-confabulation routing. The Phase 7.5 anti-confab fixes are always-on regardless of the flag.

### Bug 1 — q07 (pure LLM confabulation)

**Query:** `Tell me about Totally Fake Business XYZ 404`

**Production response:**
> "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu. If there is one, let me know with a URL and I'll pass it along. **Their listed number is (928) 502-4001 -- recommend calling to confirm.**"

**Probe evidence:** `Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/search?q=502-4001"` returns `{"results": []}`. No catalog entity has phone `502-4001`. The LLM invented a Lake-Havasu-area-code phone number for a business that doesn't exist.

**Why validator passes:** `_I_DONT_KNOW_RE` at `app/chat/halt3_validator.py:21-31` matches "I'm not aware" via the `i'?m\s+not\s+aware` pattern Phase 7.5 added. Both `_classify_disclosure_path` (line 85) and `_confabulation_rate` (line 103) short-circuit to PASS on this match. Body confabulation never inspected.

**Local routing on the same query:** `tier=3 disc=i_dont_know` — falls through to tier-3 LLM. Local LLM happens to produce a clean "I'm not aware" response without the body confabulation. Same code, non-deterministic LLM output, prod LLM produces the body confabulation.

**Root cause:** q07 classifies as `sub_intent=OPEN_ENDED` (no Tier-1 INTENT_PATTERNS hit). `_catalog_gap_response` returns None at line 142 because `OPEN_ENDED` is not in `_GAP_TIER1_FACTUAL`. `_handle_ask` runs: tier-1 None → no LLM router → tier-2 None → `answer_with_tier3()` invoked with no entity grounding → LLM confabulates with honest prefix. Phase 7.5's regex tightening didn't stop the LLM; it taught the LLM to prepend an honest-sounding phrase to satisfy the validator.

### Bug 2 — q22 (misroute to real-but-wrong entity via fail-open guard)

**Query:** `rating for Fabricated Hotel Name 555`

**Production response:**
> "Heat Hotel has a 4.5-star Google rating (406 reviews). If you meant a different place, /contribute can add the right listing."

**Probe evidence:** `Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/search?q=Heat+Hotel"` returns a real entity:
```json
{"entity_id": "aba6ec4a-0426-4a1f-a881-be030733dca7", "slug": "heat-hotel", "name": "Heat Hotel", ...}
```

The 4.5 stars + 406 reviews are real catalog data attached to the actual Heat Hotel entity.

**Local routing on the same query:** `tier=gap_template disc=i_dont_know` — clean gap template. Local DB doesn't have Heat Hotel; no near-match candidate; bug doesn't reproduce locally.

**Root cause:** `near_match_subject_overlaps` at `app/chat/entity_intent.py:158-164` is **fail-open** for every non-`where is X` query. The implementation:

```python
def near_match_subject_overlaps(query: str, canonical_name: str) -> bool:
    """True when the query subject shares a token with the near-match name."""
    subjects = near_match_subject_tokens(query)
    if not subjects:
        return True                                              # ← BUG: fail-open
    name_tokens = frozenset(re.findall(r"[a-z]+", (canonical_name or "").lower()))
    return bool(subjects & name_tokens)
```

`near_match_subject_tokens` at `entity_intent.py:144-155` ONLY matches `where(?:'s|\s+is|\s+are)\s+(?:the\s+)?...` patterns. For literally any other query shape (RATING_LOOKUP, PHONE_LOOKUP, HOURS_LOOKUP, OPEN_NOW, etc.) it returns an empty frozenset → `near_match_subject_overlaps` short-circuits to `True` → the misroute sails through. q22 hits this because "rating for Fabricated Hotel Name 555" doesn't start with "where is".

**Single call site:** `unified_router.py:184` inside `_catalog_gap_response`. Used in fail-open mode — returning False means "don't trust the near-match." Tightening only changes the outcome when a near-match exists but the subject doesn't overlap. Safe to tighten.

### Bug 3 — q03 (routing divergence; LLM-parser variance)

**Query:** `what restaurants are open now`

**Production response:**
> "I don't have those hours in the catalog yet. Add it at /contribute or share the name and a link..."

**Probe evidence:** `Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/search?q=restaurant"` returns 20 entities + `next_cursor` indicating more. The catalog has plenty of restaurants; the chat just isn't reaching them.

**Local routing on the same query:** `tier=2 disc=cited` — produces a real restaurant list. Bug doesn't reproduce locally.

**Root cause analysis:** `try_business_listing_shortcut` at `app/chat/tier2_business_shortcut.py` is **pure** (regex/string logic only — no DB, no env-var). Returns `None` for "what restaurants are open now" on BOTH local and prod (verified). The divergence is downstream in tier-2's LLM-parser path (`tier2_parser.parse` — Anthropic Haiku call): different completions yield different parsed filters yielding different result rows.

**The fix is upstream of the divergence.** `is_category_open_now_listing` already exists at `app/chat/entity_intent.py:116-119` and returns True for "restaurants...open now" via pure regex. Adding a probe of this function in `_catalog_gap_response` next to the existing `try_business_listing_shortcut` probe sidesteps the LLM-parser variance entirely.

---

## §2 The fix design

Three code changes + tests + one eval-set addition. Designed by three parallel sub-agent investigations Cowork ran 2026-05-19. The designs are pre-validated.

### Fix 1 — Tighten `near_match_subject_overlaps` (q22)

**File:** `app/chat/entity_intent.py`

Replace lines 144-164 with content-token-aware subject extraction + category-word stoplist + rapidfuzz typo escape hatch. The escape hatch preserves the existing `phone for mdshrkbrwry → Mudshark Brewery and Public House` near-match regression (`tests/test_phase38_gap_and_hours.py:108`).

```python
# Add module-level constants near top of entity_intent.py (after existing imports):

_CATEGORY_TOKENS: frozenset[str] = frozenset({
    # lodging
    "hotel", "motel", "inn", "resort", "lodge", "suites", "hostel",
    # eat/drink
    "restaurant", "cafe", "coffee", "bar", "grill", "diner", "bistro",
    "kitchen", "pizzeria", "brewery", "pub", "tavern", "eatery",
    # retail
    "store", "shop", "shoppe", "market", "mart", "boutique",
    # services / health
    "salon", "spa", "studio", "gym", "clinic", "hospital", "pharmacy",
    "dental", "dentist", "doctor", "vet", "veterinary",
    # places
    "park", "trail", "center", "centre", "plaza", "mall", "lanes",
    # legal-suffix noise
    "service", "services", "company", "co", "inc", "incorporated",
    "llc", "ltd", "group", "corp", "corporation", "the",
    # locale (Havasu-specific stopwords already used by entity_matcher)
    "lake", "havasu", "city", "arizona", "az",
})

_SUBJECT_LEAD_RE = re.compile(
    r"^\s*(?:"
    r"rating|ratings|star\s+rating|google\s+rating|"
    r"reviews?|review\s+count|how\s+many\s+(?:stars?|reviews?)|"
    r"phone|phone\s+number|contact|number|"
    r"address|location|located|"
    r"hours?|business\s+hours|when\s+(?:does|is)|what\s+time|"
    r"website|site|url|link|"
    r"where(?:'s|\s+is|\s+are)?(?:\s+the)?|where\s+can\s+i\s+find|"
    r"is|are|"
    r"how\s+is(?:\s+the)?|how\s+are\s+the\s+reviews?"
    r")\s+(?:for\s+|of\s+|at\s+)?",
    re.IGNORECASE,
)


def _general_subject_tokens(query: str) -> frozenset[str]:
    """Extract content tokens from any query shape (not just 'where is X')."""
    q = (query or "").lower().strip()
    if not q:
        return frozenset()
    q = _SUBJECT_LEAD_RE.sub("", q, count=1)
    q = q.strip(" ?.!,")
    tokens = re.findall(r"[a-z0-9]+", q)
    return frozenset(
        t for t in tokens
        if len(t) >= 2 and t not in _CATEGORY_TOKENS
    )


# Replace existing near_match_subject_overlaps at lines 158-164:

def near_match_subject_overlaps(query: str, canonical_name: str) -> bool:
    """True when the query and the near-match canonical share at least one
    *content* token — i.e. a token that isn't a generic category word.

    Tightened (q22 fix 2026-05-19): the previous implementation returned True
    whenever the query wasn't shaped like 'where is X'. That fail-open default
    let queries such as 'rating for Fabricated Hotel Name 555' pair with the
    near-match canonical 'Heat Hotel' even though the only overlap is the
    category word 'hotel'. The new guard:

      1. Extracts subject tokens from any query shape (strips Tier-1 intent
         leads, drops _CATEGORY_TOKENS, requires length >= 2).
      2. Extracts the same content-only token set from the canonical name.
      3. Returns True only when they share at least one content token.
      4. Typo escape hatch: a single long query token (>= 6 chars) is
         partial-ratio-fuzzed against name tokens >= 5 chars at threshold 80
         to preserve severe-typo near-matches (e.g. 'mdshrkbrwry' ~ 'mudshark').

    When the query has no content tokens at all (all category words), falls
    back to permissive True — at that point the user hasn't named a specific
    entity, and the near-match's caller is free to surface the closest catalog
    row.
    """
    q_subjects = _general_subject_tokens(query)
    if not q_subjects:
        return True  # query is all category words — preserve original behavior

    name_tokens = frozenset(
        t for t in re.findall(r"[a-z0-9]+", (canonical_name or "").lower())
        if len(t) >= 2 and t not in _CATEGORY_TOKENS
    )
    if not name_tokens:
        # canonical is all category words (e.g. "The Hotel") — fall back to the
        # raw-token overlap so we don't lose legitimate matches.
        raw_name_tokens = frozenset(re.findall(r"[a-z0-9]+", (canonical_name or "").lower()))
        return bool(q_subjects & raw_name_tokens)

    if q_subjects & name_tokens:
        return True

    # Typo escape hatch: a single long query token may be a misspelling of a
    # name token (e.g. mdshrkbrwry ~ mudshark, hotell ~ hotel).
    try:
        from rapidfuzz import fuzz
        for qt in q_subjects:
            if len(qt) < 6:
                continue
            for nt in name_tokens:
                if len(nt) < 5:
                    continue
                if fuzz.partial_ratio(qt, nt) >= 80:
                    return True
    except ImportError:
        pass

    return False


# KEEP existing near_match_subject_tokens — it's still used by the location-shape
# extractor for "where is the X" queries. Don't delete or modify it.
```

### Fix 2 — Add `is_category_open_now_listing` probe to `_catalog_gap_response` (q03)

**File:** `app/chat/unified_router.py`

In `_catalog_gap_response()` (around line 142), after the existing `try_business_listing_shortcut` probe at lines 150-156, add a parallel probe of `is_category_open_now_listing`:

```python
    # Existing try_business_listing_shortcut probe (around line 150-156):
    try:
        from app.chat.tier2_business_shortcut import try_business_listing_shortcut

        if try_business_listing_shortcut(raw) is not None:
            return None
    except Exception:
        logging.exception("_catalog_gap_response: shortcut probe failed")

    # NEW: q03 fix 2026-05-19 — for OPEN_NOW + category-plural queries
    # like "what restaurants are open now", defer to tier-2 even when the
    # business-listing shortcut returns None. This sidesteps tier-2-LLM-parser
    # variance that causes the gap path to fire on prod despite a populated
    # restaurant catalog.
    try:
        from app.chat.entity_intent import is_category_open_now_listing

        if is_category_open_now_listing(raw):
            return None
    except Exception:
        logging.exception("_catalog_gap_response: category-open-now probe failed")
```

Insert AFTER the existing `try_business_listing_shortcut` probe, BEFORE the near-match probe (which starts around line 158-202).

### Fix 3 — Add `_unknown_entity_about_gate` helper (q07)

**File:** `app/chat/unified_router.py`

Add a new module-level constant + helper, then call the helper from `route()` BEFORE `_catalog_gap_response` is invoked.

**Step 3a — Add module-level constants** (near top of `unified_router.py`, after existing `_GAP_TIER1_FACTUAL`):

```python
# q07 fix 2026-05-19 — "tell me about X" patterns route to deterministic gap
# template when X doesn't resolve to a catalog entity. Without this, q07-style
# queries fall through to tier-3 LLM which confabulates with an honest prefix.
_ABOUT_ENTITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*tell\s+me\s+(?:more\s+)?about\b", re.I),
    re.compile(r"^\s*(?:can\s+you\s+)?describe\b", re.I),
    re.compile(r"^\s*what(?:'s|\s+is)\s+(?!the\s+weather|the\s+time|the\s+date|today)", re.I),
    re.compile(r"^\s*who(?:'s|\s+is)\b", re.I),
    re.compile(r"^\s*(?:any\s+)?info(?:rmation)?\s+(?:on|about)\b", re.I),
    re.compile(r"^\s*what(?:'s|\s+is)\s+\S+\s+like\b", re.I),
)

_UNKNOWN_ENTITY_GAP = (
    "I don't have that one in the catalog. "
    "If it's a real Lake Havasu business, share the name plus a URL "
    "(Google Business page or official site) and I'll pass it along — "
    "or add it at /contribute."
)
```

**Step 3b — Add helper function** (somewhere near `_catalog_gap_response`):

```python
def _unknown_entity_about_gate(
    query: str,
    intent_result: IntentResult,
    db: Session | None = None,
) -> str | None:
    """Pre-tier-3 gate: 'tell me about X' patterns with no catalog match
    short-circuit to a deterministic gap template, never invoking tier-3 LLM.

    q07 fix 2026-05-19. Returns the gap string when the pattern fires; None
    otherwise (caller proceeds with normal _handle_ask flow).
    """
    raw = (query or "").strip()
    if not any(p.search(raw) for p in _ABOUT_ENTITY_PATTERNS):
        return None
    if (intent_result.entity or "").strip():
        return None  # we have a real entity — let tier 1/2/3 handle it

    # Fake-marker fast path — confab markers (XYZ, 404, fake, fabricated, etc.)
    # bypass the near-match probe entirely. q07 hits this path.
    try:
        from app.chat.entity_intent import (
            query_mentions_fake_entity_marker,
            near_match_subject_overlaps,
        )
        if query_mentions_fake_entity_marker(raw):
            return _UNKNOWN_ENTITY_GAP

        # Otherwise: only fire when matcher AND near-matcher both reject.
        from app.chat.entity_matcher import match_entity, find_near_match

        if db is not None:
            refresh_entity_matcher(db)
            if match_entity(raw, db) is not None:
                return None
            near = find_near_match(raw, db)
            if near is not None and near_match_subject_overlaps(raw, near[0]):
                return None  # plausible "did you mean" — defer to existing path
    except Exception:
        logging.exception("_unknown_entity_about_gate: matcher probe failed")
        return None

    return _UNKNOWN_ENTITY_GAP
```

**Step 3c — Wire the helper into `route()`.** Find the spot in `route()` where `mode == "ask"` branches and `_catalog_gap_response` is called. Add the `_unknown_entity_about_gate` call BEFORE `_catalog_gap_response`. If it returns non-None, short-circuit through `_finish(... tier_used="gap_template")`. Use the same shape as the existing `gap_text` short-circuit (search for `gap_text` in `route()` to find it; the new gate's emission should mirror it exactly).

Audit your wiring carefully: the gate must run inside `mode == "ask"` only, after `intent_result` is computed but before `_handle_ask` / `_catalog_gap_response` / tier-3 fallback. Verify by tracing q07 through `route()` step-by-step.

### Fix 4 — Add q23 eval entry

**File:** `app/chat/halt3_eval_set.yaml`

Append after the existing q22 entry:

```yaml
- id: q23
  query: "Tell me about Totally Fake Business XYZ 404 -- phone please"
  expected_tier: any
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Phase 7.5.1 prod-divergence regression — tighter probe of q07's honest-prefix + fake-phone shape. Includes 'phone please' so even if classification regresses to PHONE_LOOKUP the gap template still fires."
```

---

## §3 Red-test prep (BEFORE applying fixes)

The bugs DON'T reproduce in the local validator because dev fixtures don't include Heat Hotel + the prod LLM. We must first add a Heat Hotel fixture so q22 reproduces, then verify q07 + q03 also reproduce (q03 via the existing tier-2-LLM variance; q07 via the LLM path producing a confab body — may or may not reproduce locally depending on LLM nondeterminism).

**Step 3.1 — Identify the test-DB seeding pattern.**

Read these files to understand how the project seeds test fixtures:
- `tests/conftest.py` — top-level pytest fixtures
- `tests/test_phase38_gap_and_hours.py` — has Heat-Hotel-adjacent test patterns (`test_near_match_typo_returns_did_you_mean` at line 108)
- `tests/test_phase7_halt3_validation.py` — existing HALT 3 validator tests; this is where q07's integration test goes

**Step 3.2 — Author a new integration test in `tests/test_phase38_gap_and_hours.py`** that seeds Heat Hotel + verifies the current (broken) behavior:

```python
def test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape(db: Session) -> None:
    """Reproduces the prod q22 regression: 'rating for Fabricated Hotel Name 555'
    misroutes to Heat Hotel via near-match because near_match_subject_overlaps
    is fail-open for non-'where is X' queries.

    Marked xfail BEFORE Fix 1 lands. After Fix 1, remove xfail and the assertion
    becomes the green test.
    """
    from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher
    from app.chat.unified_router import route
    from app.db.models import Provider

    inserted_ids: list[str] = []
    try:
        p = Provider(
            provider_name="Heat Hotel",
            category="lodging",
            source="google_places",
            google_place_id="test_heat_hotel_q22",
            is_active=True,
            draft=False,
            google_rating=4.5,
            google_review_count=406,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        inserted_ids.append(p.id)

        refresh_entity_matcher(db)

        r = route("rating for Fabricated Hotel Name 555", "sess-q22-red", db)

        # GREEN test: after Fix 1 lands, the misroute must not happen.
        assert "Heat Hotel" not in r.response, (
            "near_match_subject_overlaps still fail-open — Heat Hotel surfaced "
            "for a clearly-fake query 'Fabricated Hotel Name 555'. "
            f"Response was: {r.response}"
        )
        assert "4.5" not in r.response
        assert "/contribute" in r.response
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        reset_entity_matcher()
```

Run it BEFORE applying Fix 1: `.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape -xvs`

Expected: **FAIL** with `Heat Hotel` substring present in response. If it doesn't FAIL, the bug doesn't reproduce locally even with the fixture — investigate `find_near_match`'s scoring against just one fixture row before proceeding.

**Step 3.3 — Author a q03 integration test** (in same file):

```python
def test_q03_what_restaurants_open_now_reaches_tier2(db: Session) -> None:
    """Reproduces the prod q03 regression: 'what restaurants are open now'
    hits the gap-template path instead of tier-2 listing when tier-2's LLM
    parser returns None / low-confidence filters.

    The fix is upstream — is_category_open_now_listing probe in
    _catalog_gap_response — so the test asserts gap-template is NOT returned.
    """
    from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher
    from app.chat.unified_router import route
    from app.db.models import Provider
    from unittest.mock import patch

    inserted_ids: list[str] = []
    try:
        for i, name in enumerate(["Bad Miguel's", "Denny's", "Mario's Italian"]):
            p = Provider(
                provider_name=name,
                category="eat-drink",
                source="google_places",
                google_place_id=f"test_restaurant_q03_{i}",
                is_active=True,
                draft=False,
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            inserted_ids.append(p.id)

        refresh_entity_matcher(db)

        # Force tier-2 LLM parser to return None (mimics prod variance):
        with patch("app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)):
            r = route("what restaurants are open now", "sess-q03-red", db)

        # GREEN test: after Fix 2, the gap-template path must be skipped via
        # is_category_open_now_listing probe.
        assert "/contribute" not in r.response, (
            "Gap-template fired despite category-open-now listing pattern. "
            "is_category_open_now_listing probe missing or not wired. "
            f"Response was: {r.response}"
        )
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        reset_entity_matcher()
```

**Step 3.4 — Author a q07 integration test** (in `tests/test_phase7_halt3_validation.py`):

```python
def test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3(db: Session) -> None:
    """Reproduces the prod q07 regression: 'Tell me about Totally Fake Business
    XYZ 404' falls through to tier-3 LLM which confabulates with honest prefix.

    Fix 3 (_unknown_entity_about_gate) intercepts this before tier-3 invocation.
    After fix, tier_used == 'gap_template' and response is the deterministic
    _UNKNOWN_ENTITY_GAP string — no LLM call.
    """
    from app.chat.unified_router import route
    from unittest.mock import patch

    # Mock tier-3 to fail loudly if reached — proves the gate fires.
    def _tier3_should_not_be_called(*args, **kwargs):
        raise AssertionError(
            "tier-3 LLM invoked for q07 — _unknown_entity_about_gate failed to intercept"
        )

    with patch("app.chat.unified_router.answer_with_tier3", side_effect=_tier3_should_not_be_called):
        r = route("Tell me about Totally Fake Business XYZ 404", "sess-q07-red", db)

    assert r.tier_used == "gap_template", f"Expected gap_template tier, got {r.tier_used}"
    assert "don't have that one in the catalog" in r.response, (
        f"Expected _UNKNOWN_ENTITY_GAP template. Got: {r.response}"
    )
```

Run all three red tests BEFORE applying any fixes. ALL THREE should FAIL. If any PASS prematurely, the test isn't actually reproducing the bug — investigate before proceeding.

---

## §4 Apply Fix 1 (q22 near_match_subject_overlaps)

Edit `app/chat/entity_intent.py` per §2 Fix 1.

After the edit:

```powershell
# 1. q22 red test should now PASS:
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape -xvs

# 2. Existing typo near-match regression should still PASS:
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_near_match_typo_returns_did_you_mean -xvs
```

**Add unit tests** at `tests/test_near_match_subject_overlaps.py` (NEW file):

```python
"""Unit tests for app.chat.entity_intent.near_match_subject_overlaps.

Red tests (q22 fix 2026-05-19): a fake-entity query that happens to share a
category word with a real catalog row must not pass the near-match guard.

Green tests: legitimate typo near-matches still pass.
"""
from __future__ import annotations

import unittest

from app.chat.entity_intent import (
    near_match_subject_overlaps,
    near_match_subject_tokens,
)


class NearMatchSubjectOverlapsTests(unittest.TestCase):

    # ------- Red tests (would FAIL against pre-fix code) -------

    def test_q22_fabricated_hotel_vs_real_hotel_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps(
                "rating for Fabricated Hotel Name 555", "Heat Hotel"
            )
        )

    def test_fake_restaurant_vs_real_restaurant_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps(
                "hours for ZZZ Imaginary Restaurant", "Heat Restaurant"
            )
        )

    def test_fake_gym_vs_real_gym_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps("phone for Fake 999 Gym", "Iron Gym")
        )

    def test_only_category_word_in_query_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps("rating for nowhere hotel", "Heat Hotel")
        )

    # ------- Green tests (legitimate typo near-matches) -------

    def test_typo_heat_hotell_passes(self) -> None:
        self.assertTrue(near_match_subject_overlaps("rating for Heat Hotell", "Heat Hotel"))

    def test_typo_heat_hote_passes(self) -> None:
        self.assertTrue(near_match_subject_overlaps("rating for Heat Hote", "Heat Hotel"))

    def test_severe_typo_mudshark_passes(self) -> None:
        self.assertTrue(
            near_match_subject_overlaps(
                "phone for mdshrkbrwry", "Mudshark Brewery and Public House"
            )
        )

    def test_partial_name_match_passes(self) -> None:
        self.assertTrue(
            near_match_subject_overlaps("phone for mudshark", "Mudshark Brewery and Public House")
        )

    # ------- Behavior preservation tests -------

    def test_where_is_library_still_works(self) -> None:
        self.assertEqual(near_match_subject_tokens("where is the library"), frozenset({"library"}))

    def test_empty_query_returns_true(self) -> None:
        self.assertTrue(near_match_subject_overlaps("", "Heat Hotel"))

    def test_all_category_words_in_query_falls_back_to_true(self) -> None:
        self.assertTrue(near_match_subject_overlaps("rating for the hotel", "Heat Hotel"))


if __name__ == "__main__":
    unittest.main()
```

Run them: `.\.venv\Scripts\python.exe -m pytest tests/test_near_match_subject_overlaps.py -xvs`. All 11 should PASS.

---

## §5 Apply Fix 2 (q03 is_category_open_now_listing probe)

Edit `app/chat/unified_router.py` per §2 Fix 2.

After the edit:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 -xvs
```

Should PASS. If it FAILs, verify `is_category_open_now_listing("what restaurants are open now")` returns True (it should — read `entity_intent.py:116-119` if you need to refresh).

---

## §6 Apply Fix 3 (q07 _unknown_entity_about_gate)

Edit `app/chat/unified_router.py` per §2 Fix 3 (steps 3a, 3b, 3c).

**For Step 3c (wiring into `route()`), read `route()` carefully first.** Find the existing `gap_text` short-circuit (search for `gap_text` in the file). Your new gate's emission must mirror that pattern exactly: same `_finish()` call signature, `tier_used="gap_template"`, same chat-log shape. The wrapper does not pin the exact line number because `route()` evolves; use the existing `gap_text` short-circuit as your reference template.

After the edit:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3 -xvs
```

Should PASS. The mock `_tier3_should_not_be_called` proves the gate intercepts before tier-3 invocation.

---

## §7 Acceptance verification

Run all five checks. ALL must pass before §12.

```powershell
# 1. HALT 3 validator still 22/22 PASS (the q23 entry will hit the new gate):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
# Expected: cited_coverage=100% missing_confab_max=0.00 all_passed=True
# Should see q23 PASS with tier=gap_template

# 2. Full pytest suite — should be 2150+ (was 2150 at b701759; new tests add)
.\.venv\Scripts\python.exe -m pytest -q
# Expected: 2160+ passed + 2 skipped

# 3. Three red tests now GREEN:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3

# 4. New unit tests pass:
.\.venv\Scripts\python.exe -m pytest tests/test_near_match_subject_overlaps.py -xvs

# 5. Ruff clean on all touched files:
.\.venv\Scripts\python.exe -m ruff check `
    app/chat/entity_intent.py `
    app/chat/unified_router.py `
    app/chat/halt3_eval_set.yaml `
    tests/test_phase38_gap_and_hours.py `
    tests/test_phase7_halt3_validation.py `
    tests/test_near_match_subject_overlaps.py
```

**If any check fails, HALT and investigate.** Do not proceed to §12.

---

## §8 Existing regression check

The `test_near_match_typo_returns_did_you_mean` in `tests/test_phase38_gap_and_hours.py:108` must still pass — it's the regression that proved the typo escape hatch works (`phone for mdshrkbrwry → Mudshark Brewery`). Run it explicitly:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase38_gap_and_hours.py::test_near_match_typo_returns_did_you_mean -xvs
```

Must PASS.

---

## §9 File scope (gotcha #18 disjointness)

Modified files (closed set):
- `app/chat/entity_intent.py` (add _CATEGORY_TOKENS, _SUBJECT_LEAD_RE, _general_subject_tokens; replace near_match_subject_overlaps)
- `app/chat/unified_router.py` (add _ABOUT_ENTITY_PATTERNS, _UNKNOWN_ENTITY_GAP, _unknown_entity_about_gate; wire into route(); add is_category_open_now_listing probe in _catalog_gap_response)
- `app/chat/halt3_eval_set.yaml` (append q23)

New files:
- `tests/test_near_match_subject_overlaps.py`

Modified test files:
- `tests/test_phase38_gap_and_hours.py` (add q22 + q03 integration tests)
- `tests/test_phase7_halt3_validation.py` (add q07 integration test)

**Do NOT touch:**
- `app/chat/halt3_validator.py` — validator hardening is a separate Phase 7.5.2 lane (will dispatch later)
- `app/chat/tier2_business_shortcut.py` — pure function; not the divergence
- `app/chat/tier3_handler.py` — no changes needed
- `app/chat/intent_classifier.py` — no changes needed
- Any Phase 6.5 surfaces (`home.html`, themed tiles, conditions strip)
- Any Phase 8a surfaces (`app/conditions/`, `app/alerts/`)
- Any Phase 9 surfaces (events, RRULE)
- `outputs/cursor_dispatch_prompt_phase_8.md` or any other dispatch wrapper
- Any docs (`docs/maintainability/*.md`, `docs/STATE.md`) — Cowork primary updates these post-ship

---

## §10 What NOT to do

- **Do NOT git-commit.** Stop at §12. The operator commits after reviewing your diff.
- **Do NOT touch `halt3_validator.py`.** The validator's 4 Goodhart gaps (G1: catalog-mention shortcut; G2: only proper-noun probes; G3: honest-prefix shortcut; G4: expected_tier=any) are a SEPARATE Phase 7.5.2 dispatch. This dispatch focuses on the routing fixes only.
- **Do NOT add new dependencies.** `rapidfuzz` is already a project dep (verified via `.venv\Lib\site-packages\rapidfuzz-3.14.3.dist-info`).
- **Do NOT add an alembic migration.** No schema changes.
- **Do NOT modify `disclosure_render.py` or `FEATURE_FLAG_DISCLOSURE_RENDERER` semantics.** That flag controls sponsored-content disclosure (FTC compliance), NOT the anti-confab routing. Orthogonal concern.
- **Do NOT broaden `_ABOUT_ENTITY_PATTERNS`** beyond the six listed regexes. The patterns are anchored at start-of-query for a reason — mid-query "tell me about" or "describe" could legitimately be follow-up turns in a conversation that shouldn't fire the gate.
- **Do NOT change `_CATEGORY_TOKENS` to exclude `hotel` / `restaurant` / etc.** The whole point of the q22 fix is that "Hotel" alone isn't enough to confirm a near-match.

---

## §11 If you find a substantive deviation

Per the project's working agreement Rule 4 (deviation discipline):

- Small in-scope deviations (e.g., a regex tweak; choosing list-vs-tuple) — proceed with your judgment; note in §12.
- Substantive deviations (touching a file not in §9; changing a test fixture pattern; adding a dependency) — STOP and report. Cowork primary will decide.

---

## §12 Final report (you MUST emit this; do not commit)

Emit a structured report covering:

### §12.1 Diffs
- Full unified diff of all modified files (use `git diff` output)
- Confirm no files outside §9 scope were touched

### §12.2 Acceptance checks
For each check in §7, paste the actual output line. Confirm PASS.

### §12.3 Per-fix verification
| Fix | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| 1 (q22) | `test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape` | Same test post-fix | ☐ |
| 2 (q03) | `test_q03_what_restaurants_open_now_reaches_tier2` | Same test post-fix | ☐ |
| 3 (q07) | `test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3` | Same test post-fix | ☐ |
| Validator | `python -m app.chat.halt3_validator` 22/22 PASS pre + 23/23 PASS post (with q23) | | ☐ |
| Regression | `test_near_match_typo_returns_did_you_mean` still PASS | | ☐ |
| Unit tests | `test_near_match_subject_overlaps.py` 11/11 PASS | | ☐ |

### §12.4 Substantive findings
Anything surprising you encountered. Bugs in the existing code you noticed but didn't fix (because out of scope). Things the wrapper didn't anticipate.

### §12.5 File scope confirmation
Paste output of `git status --short` confirming only §9-listed files modified.

### §12.6 Recommended commit subject
Suggest a commit subject line. Default:
```
feat(phase7.5.1): close prod-divergence routing bugs -- near_match_subject_overlaps fail-open closed (q22); is_category_open_now_listing probe added (q03); _unknown_entity_about_gate added (q07); +1 eval entry (q23); 3 integration tests + 11 unit tests; validator hardening deferred to Phase 7.5.2
```

### §12.7 Open carries
Anything that should become a V1.5 carry or a future dispatch concern.

---

End of wrapper. Now go.
