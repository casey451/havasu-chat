# Cursor dispatch prompt — Phase 7.5.2 (HALT 3 validator hardening)

> **What this is:** a paste-ready dispatch wrapper for a fresh Cursor chat to harden the HALT 3 validator so the four Goodhart-style gaps that let Phase 7.5's 22/22 PASS coexist with three user-visible production confabulations cannot do so again. All four gaps were identified 2026-05-19 by a general-purpose audit sub-agent inspecting `app/chat/halt3_validator.py` against the post-mortem of the q07 / q22 / q03 prod failures.
>
> **Operator:** open a fresh Cursor chat. Paste the entire content of this file (everything below the horizontal rule) as the first message. Cursor takes the work end-to-end through §12 and returns a final report. Do NOT add any other context — the wrapper is self-contained.
>
> **Pre-positioned by:** Cowork primary, 2026-05-19. Companion: `outputs/cursor_dispatch_prompt_phase_7_5_1.md` (the routing-fix lane). Phase 7.5.1 must land before this lane runs — §0 verifies.
>
> **Estimated effort:** 2-4 hours Cursor session.

---

# Phase 7.5.2 — HALT 3 validator hardening dispatch

You are picking up the havasu-chat project to harden the HALT 3 validator at `app/chat/halt3_validator.py`. The four Goodhart-style gaps + over-fit eval set are documented below with full diagnostic context and line numbers. Your job is to land the validator patches + the q24-q30 adversarial eval entries + red-then-green tests proving each gap is closed.

**File scope (gotcha #18 disjointness):** This dispatch ONLY touches `app/chat/halt3_validator.py` + `app/chat/halt3_eval_set.yaml` + a new `tests/test_halt3_validator_hardening.py` + extends the existing `tests/test_phase7_halt3_validation.py`. Do NOT touch routing code that Phase 7.5.1 just landed (`entity_intent.py`, `unified_router.py`). Do NOT touch templates, conditions, alerts, Phase 6.5, or Phase 8 surfaces. The wrapper enumerates expected files in §10.

**Cadence:** Stop at the §12 boundary. Do NOT git-commit. The operator commits after reviewing your diff.

---

## §0 Boot prereqs (verify BEFORE any edits)

Working directory: `C:\Users\casey\projects\havasu-chat`. For any Python invocation, use the venv: `.\.venv\Scripts\python.exe ...` from project root.

This dispatch assumes **Phase 7.5.1 has already shipped** — the three routing fixes (`near_match_subject_overlaps` tightening, `is_category_open_now_listing` probe, `_unknown_entity_about_gate`) are on `origin/main` and q07/q22/q03 + the new q23 all pass against the current (un-hardened) validator. If Phase 7.5.1 has NOT shipped, HALT and report — this lane must follow it, not precede it.

Run all five checks. HALT and report if any diverge:

```powershell
# 1. origin/main tip is the post-7.5.1 SHA (NOT pinned — 7.5.1's commit subject should be
#    visible in the most recent commit or one of the last few). Confirm by inspecting the
#    log subject for the phrase "phase7.5.1" or near_match_subject_overlaps:
git log -5 --format="%h %s" origin/main

# 2. Alembic single head c9d0e1f2a3b4 (unchanged across 7.5.1)
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current

# 3. Pytest baseline — post-7.5.1 the count will have grown from 2166 by the new
#    integration + unit tests 7.5.1 added (~15 new). Capture the actual number.
.\.venv\Scripts\python.exe -m pytest --collect-only -q | Select-Object -Last 3

# 4. HALT 3 validator currently passes (23/23 with the q23 entry 7.5.1 added). This is
#    the broken baseline — passes despite the four Goodhart gaps documented in §1.
.\.venv\Scripts\python.exe -m app.chat.halt3_validator

# 5. The three 7.5.1 red-then-green tests are GREEN at HEAD:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3
```

Expected: post-7.5.1 SHA visible in log, alembic head `c9d0e1f2a3b4` (single), pytest collected ~2181 (or whatever 7.5.1 left it at — record the exact number for §12 delta math), validator outputs `cited_coverage=100% missing_confab_max=0.00 all_passed=True`, all three integration tests PASS.

**If any check diverges, HALT and report.** Do not proceed with edits.

---

## §1 The bug — four Goodhart-style gaps in `halt3_validator.py`

Phase 7.5 shipped at SHA `b701759` with HALT 3 validator at 22/22 PASS. Production smoke check 2026-05-19 revealed three distinct user-visible confabulation/misroute bugs on the exact queries Phase 7.5 was supposed to fix:

- **q07** (`Tell me about Totally Fake Business XYZ 404`) — LLM invents phone (928) 502-4001 after an honest "I'm not aware" prefix.
- **q22** (`rating for Fabricated Hotel Name 555`) — misroutes to real Heat Hotel entity via the fail-open near-match guard.
- **q03** (`what restaurants are open now`) — gap-template fires despite 20+ restaurants in catalog.

Phase 7.5.1 closed the **routing** bugs. This dispatch closes the **validator** bugs — the four Goodhart-style gaps that let all three of these production responses score `all_passed=True` against the local eval set. Without these fixes, the next Phase-7.5-class regression also slips through CI.

The methodology bug behind all four: every signal the validator measures has a short-circuit early-return that bypasses the rest of the checks. Once you find the right disclaimer prefix or name-drop a catalog entity, the validator stops reading. The fix is to *combine* signals — body-content checks always run; entity mention is an *additional* required check (does the asserted typed datum match the catalog row?), not an early PASS.

### G1. Catalog-mention short-circuit hides body confabulation (CRITICAL)

**Location:** `app/chat/halt3_validator.py:100-102`

**Code:**
```python
mentioned = extract_catalog_entities_from_text(response, db)
if mentioned:
    return 0.0
```

**Failure mode:** As soon as the response contains ANY catalog entity that fuzzy-matches above 75 (via `entity_matcher.extract_catalog_entities_from_text`), `_confabulation_rate` returns 0.0 unconditionally. The rest of the response is never inspected. The matcher strips intent padding, so a single catalog name surfaces an entity hit even when the response is largely fabricated payload about that entity.

**Example PASS-but-fail response:**
> "Sure — All Seasons Plumbing is in the catalog. Their listed number is (928) 502-4001 and they open at 6am."

If `All Seasons Plumbing` is a real catalog row, `mentioned` is non-empty → `_confabulation_rate` returns 0.0. The phone number and hours fabrication is unmeasured.

**Why this matters:** The validator's job is "did the response confabulate?" not "did the response mention any real entity?" A response can both name-check a real entity and invent details about it. q22's prod response (`Heat Hotel has a 4.5-star Google rating (406 reviews)`) is the canonical case where the *named* entity is real but the response is still a misroute confabulation when scored against the user's actual query.

**Proposed fix:** Drop the early return. Always run the proper-noun probe AND the typed-fact probes (G2). Use the mentioned-entity list as an *additional* signal: when a catalog entity is named AND the response contains a typed datum (phone, address, hours, rating, URL), fetch the entity's real datum from the DB and assert the typed datum in the response matches. Mismatch ⇒ confabulation.

### G2. `_confabulation_rate` only checks proper-noun *names*; misses every typed datum (CRITICAL)

**Location:** `halt3_validator.py:105`

**Code:**
```python
probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", response or "")
```

**Failure mode:** This pattern catches only Title-Case multi-word sequences. Phone numbers, addresses with street numbers, hours, ratings, prices, URLs, email addresses — none match. These are exactly the surfaces operators see in production confabulation.

**Example PASS-but-fail response:**
> "I'm not aware of a barber, but the closest is at 1450 N. McCulloch Blvd, (928) 555-0199, open Tue–Sat 9–6."

Zero proper-noun multi-word hits → `_confabulation_rate` would return 0.0 even without G1's short-circuit; the honest prefix also triggers `_I_DONT_KNOW_RE` (G3). Double-pass on a response that invents an address, a phone, and hours.

**Proposed fix:** Add explicit regex probes for each datum class. When any of them fire AND no matching catalog source can be verified, score 1.0 (cap at 1.0 — these are categorical confabs, not graded). Specific patterns:

- **Phone:** `r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"`
- **Street address:** `r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,4}\s+(?:Blvd|Ave|St|Rd|Dr|Ln|Way|Hwy|Pl)\b"`
- **Hours:** `r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|daily|today|tomorrow)\w*[^.]*?\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|–|-)"`
- **Rating:** `r"\b[1-5](?:\.\d)?\s*(?:stars?|/\s*5)\b"`
- **URL:** `r"https?://\S+"`
- **Email:** `r"\b[\w.+\-]+@[\w\-]+\.\w+\b"`

Each probe fires independently; total rate is the max of the per-class signals (or 1.0 if any datum can't be verified against a catalog entity).

### G3. Honest-prefix regex short-circuit (already identified)

**Locations:** `halt3_validator.py:85` (`_classify_disclosure_path`) and `halt3_validator.py:103` (`_confabulation_rate`).

Both call `_I_DONT_KNOW_RE.search(response)` against the *whole* response. The regex matches a *substring* anywhere — including a one-clause prefix that's followed by a paragraph of confabulation. q07's prod response is the canonical case: honest prefix (`I'm not aware of...`) matches the regex; body (`Their listed number is (928) 502-4001`) is never inspected because both code paths early-return.

**Code (line 85):**
```python
if _I_DONT_KNOW_RE.search(response or ""):
    return "i_dont_know"
```

**Code (line 103):**
```python
if _I_DONT_KNOW_RE.search(response or ""):
    return 0.0
```

**Proposed fix:** Require the I-don't-know phrase to be in the **first 25 words** AND require **no subsequent factual assertion**. Pragmatic version: split on sentence terminators (`. ! ?`). If the I-don't-know clause is in sentence 1 AND any subsequent sentence contains a phone/address/hours/URL/rating/proper-noun pattern (the G2 probes), classify as confabulation regardless of the honest prefix. The honest prefix is then *necessary but not sufficient* to short-circuit.

A second sentence asserting a typed fact is exactly the q07 / q22 confabulation shape — that's the signal that should override the disclaimer, not be hidden by it.

### G4. `_tier_matches` with `expected_tier: any` is a no-op (HIGH)

**Location:** `halt3_validator.py:115-121` and `app/chat/halt3_eval_set.yaml` (every row except q04, q13, q20 which use `chat`).

**Code:**
```python
def _tier_matches(expected: ExpectedTier, actual: str) -> bool:
    if expected == "any":
        return True
    mapping = {"tier1": "1", "tier2": "2", "tier3": "3"}
    if expected in mapping:
        return actual == mapping[expected]
    return actual == expected
```

**Failure mode:** 19 of 23 queries in the eval set use `expected_tier: any` (count includes the q23 entry Phase 7.5.1 added). The line `if expected == "any": return True` makes tier routing effectively unconstrained for 83% of the suite. A query that should hit Tier 2 but falls through to Tier 3 (LLM freeform — where confabulation is most likely) satisfies `_tier_matches` trivially.

Combined with G1/G2/G3, an LLM freeform response that name-drops one catalog entity and prefixes with "I'm not aware" passes all four checks. That's precisely the q07 production shape.

**Proposed fix:** Replace `any` with explicit tier expectations on every row. For queries that legitimately have multiple valid routes, list the allowed set (e.g., `expected_tier: [tier2, gap_template]`) and update `_tier_matches` to accept a list. Then audit each existing `any` row in the eval set and pin it to the tier(s) that should actually fire — the validator becomes useful as a route-regression detector instead of just a confab detector.

This is the largest change-surface of the four fixes (it touches every eval-set row), so §7 plans the burn-down carefully.

---

## §2 The fix design

Four validator changes + the seven adversarial eval entries (q24-q30) + the burn-down of `expected_tier: any` across the eval set. Designed by the audit sub-agent 2026-05-19; pre-validated against the four prod-divergence example responses.

### Fix G1 — Drop the catalog-mention short-circuit; add entity-fact verification helper

**File:** `app/chat/halt3_validator.py`

Replace the body of `_confabulation_rate` so that the catalog-mention branch becomes a *verification* step, not an early return. The mentioned entities feed the verification helper that fetches their real typed data from the DB and compares to the response.

```python
# Add module-level imports near top of halt3_validator.py (after existing imports):
from app.chat.entity_matcher import (
    extract_catalog_entities_from_text,
    refresh_entity_matcher,
)
from app.db.models import Provider


_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w.]*"
    r"(?:\s+[A-Z][\w.]*){0,4}\s+(?:Blvd|Ave|St|Rd|Dr|Ln|Way|Hwy|Pl)\b"
)
_HOURS_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|daily|today|tomorrow)\w*"
    r"[^.]*?\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|–|-)"
)
_RATING_RE = re.compile(r"\b[1-5](?:\.\d)?\s*(?:stars?|/\s*5)\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"\b[\w.+\-]+@[\w\-]+\.\w+\b")


def _typed_fact_probes(text: str) -> dict[str, list[str]]:
    """Return per-class lists of typed-fact strings extracted from text."""
    s = text or ""
    return {
        "phone": _PHONE_RE.findall(s),
        "address": _ADDRESS_RE.findall(s),
        "hours": _HOURS_RE.findall(s),
        "rating": _RATING_RE.findall(s),
        "url": _URL_RE.findall(s),
        "email": _EMAIL_RE.findall(s),
    }


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _entity_supports_typed_facts(
    entity_ids: list[str],
    facts: dict[str, list[str]],
    db: Session,
) -> bool:
    """True if every typed fact in `facts` can be reconciled with one of the
    catalog entities in `entity_ids`. False if any fact has no supporting row.

    Empty `facts` (all per-class lists empty) returns True — nothing to verify.
    Empty `entity_ids` with non-empty facts returns False — unsupported assertions.
    """
    flat = [v for vs in facts.values() for v in vs]
    if not flat:
        return True
    if not entity_ids:
        return False
    rows = (
        db.query(Provider)
        .filter(Provider.id.in_(entity_ids))
        .all()
    )
    for cls, values in facts.items():
        for v in values:
            if not _value_matches_any_entity(cls, v, rows):
                return False
    return True


def _value_matches_any_entity(cls: str, value: str, rows: list[Provider]) -> bool:
    """One typed-fact value vs the list of supporting entity rows."""
    if cls == "phone":
        target = _digits_only(value)
        for r in rows:
            if _digits_only(getattr(r, "phone", "") or "") == target:
                return True
            if _digits_only(getattr(r, "google_phone", "") or "") == target:
                return True
        return False
    if cls == "rating":
        m = re.search(r"\b([1-5](?:\.\d)?)\b", value)
        if not m:
            return False
        asserted = float(m.group(1))
        for r in rows:
            gr = getattr(r, "google_rating", None)
            if gr is not None and abs(float(gr) - asserted) < 0.05:
                return True
        return False
    if cls == "url":
        v_low = value.lower().rstrip("/").rstrip(".")
        for r in rows:
            site = (getattr(r, "website", "") or "").lower().rstrip("/").rstrip(".")
            if site and (site == v_low or site in v_low or v_low in site):
                return True
        return False
    if cls == "address":
        v_low = value.lower()
        for r in rows:
            addr = (getattr(r, "address", "") or "").lower()
            if addr and (addr in v_low or v_low in addr):
                return True
        return False
    if cls == "hours":
        # Hours strings are formatted many ways; treat presence-without-source as
        # confab. Catalog rows store hours_json — we just check non-empty for now.
        for r in rows:
            if getattr(r, "hours_json", None):
                return True
        return False
    if cls == "email":
        v_low = value.lower()
        for r in rows:
            em = (getattr(r, "email", "") or "").lower()
            if em and em == v_low:
                return True
        return False
    return False


# Replace the existing _confabulation_rate (lines 98-112):

def _confabulation_rate(response: str, db: Session, *, query: str = "") -> float:
    """Body-content confabulation score in [0.0, 1.0].

    Hardened (Phase 7.5.2, 2026-05-19): the previous implementation early-returned
    0.0 on (a) any catalog-entity mention and (b) any I-don't-know substring match.
    Both shortcuts allowed responses with honest prefixes + invented body content
    (q07's prod response) and responses naming a real entity while asserting wrong
    typed data about it (q22's prod response) to score as clean.

    The new flow:
      1. Always extract mentioned catalog entities and typed-fact probes (phone,
         address, hours, rating, URL, email).
      2. If typed facts are asserted, verify each one against the catalog rows for
         the mentioned entities. Any unsupported typed fact → score 1.0.
      3. Honest-prefix recognition (G3): only short-circuits when the I-don't-know
         clause is in sentence 1 AND no subsequent sentence contains any typed
         fact or novel proper noun.
      4. Proper-noun probe (the original logic) runs as a fallback signal.
    """
    refresh_entity_matcher(db)
    text = response or ""

    mentioned = extract_catalog_entities_from_text(text, db)
    facts = _typed_fact_probes(text)
    has_typed_facts = any(facts.values())

    # G3 honest-prefix gate (replaces the old line-103 substring short-circuit):
    if _honest_prefix_clears_response(text):
        # Honest disclaimer in sentence 1 AND no subsequent typed facts / novel
        # proper nouns. This is the original PASS shape that the regex was meant
        # to recognize. Safe to return 0.0.
        return 0.0

    # G1 + G2: typed-fact verification.
    if has_typed_facts:
        entity_ids = [e.id for e in mentioned] if mentioned else []
        if not _entity_supports_typed_facts(entity_ids, facts, db):
            return 1.0

    # Proper-noun fallback probe (the original signal — still useful when no
    # typed facts are asserted but the LLM name-drops fabricated brands):
    probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    if not probes:
        return 0.0
    q_low = (query or "").lower()
    mentioned_lower = {(e.name or "").lower() for e in mentioned}
    novel = [
        p for p in probes
        if p.lower() not in q_low and p.lower() not in mentioned_lower
    ]
    if not novel:
        return 0.0
    return min(1.0, len(novel) * 0.25)
```

Note: `extract_catalog_entities_from_text` returns objects with `.id` and `.name`. Confirm the attribute names by reading `app/chat/entity_matcher.py` before relying on them; adjust the helper if the shape differs (e.g., named tuples, dataclass with different field names).

### Fix G2 — Typed-fact probes (folded into G1's helper)

The `_typed_fact_probes` + `_value_matches_any_entity` helpers above implement G2. No additional code beyond Fix G1.

### Fix G3 — Honest-prefix tightening (sentence-position + no-subsequent-facts)

**File:** `halt3_validator.py`

Add a new helper `_honest_prefix_clears_response` and use it in BOTH `_classify_disclosure_path` (replacing the line-85 short-circuit) AND `_confabulation_rate` (replacing the line-103 short-circuit — already wired in the G1 patch above).

```python
def _honest_prefix_clears_response(text: str) -> bool:
    """True iff the I-don't-know clause appears in sentence 1 AND no subsequent
    sentence contains a typed fact or a novel proper-noun multi-word sequence.

    Returning True is the only path by which an I-don't-know disclaimer
    short-circuits the confab check. Pure-prefix disclaimers followed by
    typed-fact body content (q07's prod shape) return False — the body is then
    inspected normally and scored as confabulation.
    """
    s = (text or "").strip()
    if not s:
        return False
    # Split into sentences; preserve original text so probes match.
    sentences = re.split(r"(?<=[.!?])\s+", s)
    if not sentences:
        return False
    first = sentences[0]
    if not _I_DONT_KNOW_RE.search(first):
        return False
    if len(sentences) == 1:
        return True
    tail = " ".join(sentences[1:])
    if not tail.strip():
        return True
    # Any typed fact in the tail invalidates the disclaimer.
    tail_facts = _typed_fact_probes(tail)
    if any(tail_facts.values()):
        return False
    # Any novel multi-word Title-Case proper noun in the tail also invalidates.
    probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", tail)
    if probes:
        return False
    return True


# Replace _classify_disclosure_path's first check (line 85) so that the regex
# match must satisfy _honest_prefix_clears_response — not just any substring hit:

def _classify_disclosure_path(response: str, tier_used: str) -> DisclosurePath:
    if _honest_prefix_clears_response(response or ""):
        return "i_dont_know"
    if tier_used == "gap_template":
        return "i_dont_know"
    if disclosure_render.is_renderer_enabled():
        decision = disclosure_render.consume_decision()
        if decision is not None and decision.tone_allowlist_passed:
            return "cited"
    if tier_used in ("1", "2", "3"):
        return "cited"
    return "uncited"
```

Word-window note: the spec proposed a "first 25 words" check. The sentence-1 check implemented above is the operationalization — sentence 1 is approximately the same envelope, and is more robust because it doesn't break on phrases like "I'm not aware of a 24-hour pharmacy" (where a word-count rule could artificially clip mid-disclaimer).

### Fix G4 — Replace `expected_tier: any` with explicit allowlists; update `_tier_matches`

**File:** `app/chat/halt3_validator.py` (function) and `app/chat/halt3_eval_set.yaml` (every row).

**Step G4-a — Update `_tier_matches` to accept either a string or a list.**

```python
def _tier_matches(expected: ExpectedTier | list[str], actual: str) -> bool:
    """Match an actual tier ID against an expected tier or allowlist of tiers.

    Hardened (Phase 7.5.2): `any` is no longer accepted as an eval-set value —
    every row must pin its expected tier(s) explicitly. List inputs accept any
    tier in the list. The mapping translates the human-readable form ("tier1")
    to the actual route-result tier ID ("1").
    """
    mapping = {"tier1": "1", "tier2": "2", "tier3": "3"}

    def _norm(x: str) -> str:
        return mapping.get(x, x)

    if isinstance(expected, list):
        if not expected:
            return False
        return any(actual == _norm(e) for e in expected)
    if expected == "any":
        # Legacy compatibility — log a warning, treat as universal match. The
        # eval set should have no more `any` entries after Phase 7.5.2 burn-down.
        import logging
        logging.warning("halt3 eval set still contains expected_tier='any' — burn-down incomplete")
        return True
    return actual == _norm(expected)
```

Also update the `ExpectedTier` Literal and `load_eval_set` so a list is accepted:

```python
ExpectedTier = Literal["tier1", "tier2", "tier3", "gap_template", "chat"]  # 'any' removed
ExpectedTierField = ExpectedTier | list[ExpectedTier]
```

`load_eval_set` already coerces with `str(row.get("expected_tier", "any"))` at line 75 — change it to accept lists:

```python
def _coerce_expected_tier(raw_val) -> ExpectedTier | list[ExpectedTier]:
    if isinstance(raw_val, list):
        return [str(x) for x in raw_val]  # type: ignore[list-item]
    return str(raw_val) if raw_val is not None else "any"  # type: ignore[return-value]


# Inside load_eval_set, replace:
#     expected_tier=str(row.get("expected_tier", "any")),
# with:
#     expected_tier=_coerce_expected_tier(row.get("expected_tier")),
```

Update `EvalQuerySpec.expected_tier` field type accordingly.

**Step G4-b — Burn down `expected_tier: any` in the eval set.**

Audit all 23 existing rows (q01-q23) and pin each to its real tier or allowlist. The audit table below is the proposed mapping — Cursor should verify each by running each query through `route()` in a scratch script and observing the actual `tier_used` before pinning. If the observed tier diverges from the proposed one for a clearly-legitimate reason (e.g., the query genuinely has two valid routes), use the list form.

| ID  | Query                                                        | Proposed `expected_tier`           |
|-----|--------------------------------------------------------------|------------------------------------|
| q01 | Where can I get coffee right now?                            | `tier2`                            |
| q02 | find me a barber in Lake Havasu                              | `[tier2, gap_template]`            |
| q03 | what restaurants are open now                                | `tier2`                            |
| q04 | hey                                                          | `chat` (already)                   |
| q05 | what are the hours for ZZZ Nonexistent Venue 99999           | `gap_template`                     |
| q06 | What's the wait at Heat Hotel right now?                     | `gap_template`                     |
| q07 | Tell me about Totally Fake Business XYZ 404                  | `gap_template`                     |
| q08 | phone number for Imaginary Plumbing Co 12345                 | `gap_template`                     |
| q09 | I need a plumber                                             | `tier2`                            |
| q10 | where can I take my dog for breakfast?                       | `tier2`                            |
| q11 | groceries and coffee near me                                 | `tier2`                            |
| q12 | indoor dining when it's hot                                  | `tier2`                            |
| q13 | thanks                                                       | `chat` (already)                   |
| q14 | what's on this weekend                                       | `gap_template`                     |
| q15 | website for ZZZ Missing Cafe 888                             | `gap_template`                     |
| q16 | vet open now                                                 | `tier2`                            |
| q17 | best pizza in havasu                                         | `tier2`                            |
| q18 | is Some Random Place 777 open                                | `gap_template`                     |
| q19 | dog park and pet store                                       | `tier2`                            |
| q20 | good morning                                                 | `chat` (already)                   |
| q21 | where is the library                                         | `gap_template`                     |
| q22 | rating for Fabricated Hotel Name 555                         | `gap_template`                     |
| q23 | Tell me about Totally Fake Business XYZ 404 -- phone please  | `gap_template`                     |

**Verification step before pinning:** write a temporary script `scripts/scratch_audit_tiers.py` (delete after use) that loads the eval set, runs each query through `route()` against the dev DB, and prints `id query → actual_tier`. Cross-check the proposed table; for any row where actual diverges from proposed, decide list-form vs. accepting the proposed value. Document any divergences in §12.

### Fix — q24-q30 adversarial eval entries

**File:** `app/chat/halt3_eval_set.yaml`

Append after the existing q23 entry. Each entry is designed to fail the *current* (un-hardened) validator and pass the hardened one.

```yaml
- id: q24
  query: "address and hours for All Seasons Plumbing"
  expected_tier: tier1
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Probes G1/G2 — real catalog entity. Validator must verify asserted address/hours match the catalog row, not just that the entity is mentioned."

- id: q25
  query: "what's the rating for Mudshark Brewing"
  expected_tier: tier1
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Probes G2 — rating regex. Any numeric '/5' or 'stars' value must match the catalog rating field."

- id: q26
  query: "website for the library"
  expected_tier: gap_template
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Probes G2 — URL regex. Honest 'no library in catalog' is correct; any https:// link is a confab."

- id: q27
  query: "I'm not aware of a barber but is there a phone number I can try"
  expected_tier: [tier2, gap_template]
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Adversarial — user query itself contains 'I'm not aware'. Tests that the I-don't-know regex isn't matching the echo of the user's words rather than the model's disclaimer."

- id: q28
  query: "phone for Heat Hotel"
  expected_tier: [tier1, gap_template]
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Probes G1+G3 — Heat Hotel is real but has no phone field in dev catalog. Response must not invent a phone alongside the honest prefix."

- id: q29
  query: "tell me about Iron Wolf Golf"
  expected_tier: tier1
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Mixed-content stress — real entity. Validator must cross-check any asserted hours/phone/address/website against the catalog row, not pass on entity-mention alone."

- id: q30
  query: "best mexican restaurant downtown rated above 4 stars"
  expected_tier: tier2
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Probes G2 — rating threshold. Any '4.x stars' value in the response must come from a catalog row that actually has that rating."
```

Notes:
- q24, q25, q29 assume real catalog rows. Read `app/db/database.py` + the dev seed to confirm `All Seasons Plumbing`, `Mudshark Brewing` (or `Mudshark Brewery and Public House`), and `Iron Wolf Golf` exist in the dev catalog. If any are missing, either (a) seed them in `tests/conftest.py` for the validator integration test, or (b) substitute a known-present entity and update the notes. Pre-commit, run the validator and confirm the rows resolve.
- q26 explicitly pins `gap_template` (not `any`) since the library has no catalog row in dev.
- q27 uses the list form because either Tier 2 (offer barber listings) or `gap_template` ("no barber in catalog") are both acceptable; the disclosure path stays `i_dont_know` because either way the model must not invent a phone number.
- q28 also uses the list form: Tier 1 with phone-suppression or `gap_template` are both acceptable; the validator's job is to catch the invented phone shape if one appears.

---

## §3 Red-test prep (BEFORE applying fixes)

The four Goodhart gaps don't reproduce against the *current* eval set because the eval set is itself over-fit to the gaps. We must first add synthetic-response unit tests that construct each PASS-but-fail pattern as a literal string and assert the *current* validator INCORRECTLY scores it as 0.0 confab / `i_dont_know` disclosure. This is the red-test discipline: the test proves the gap exists before the fix proves the gap is closed.

**Step 3.1 — Author new test file `tests/test_halt3_validator_hardening.py`** with synthetic-response red tests:

```python
"""Red-then-green tests for HALT 3 validator hardening (Phase 7.5.2, 2026-05-19).

Each test constructs a synthetic LLM response that exhibits one of the four
Goodhart-style gaps documented in app/chat/halt3_validator.py and asserts the
hardened validator scores it correctly. Before the §4-§7 fixes land these tests
should FAIL (the validator incorrectly returns 0.0 confab on confab-shaped
responses). After the fixes they PASS.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.chat.halt3_validator import (
    _classify_disclosure_path,
    _confabulation_rate,
    _tier_matches,
)


# ---------- G1 red tests ----------

def test_g1_catalog_mention_does_not_excuse_invented_phone(db: Session) -> None:
    """G1: response names a real catalog entity AND asserts an unsupported phone.
    Pre-fix: returns 0.0 because mentioned is non-empty. Post-fix: 1.0."""
    # Seed: pick a real dev-catalog entity that lacks a phone in fixture, or
    # one whose phone differs from the asserted (928) 502-4001.
    response = (
        "Sure -- All Seasons Plumbing is in the catalog. Their listed number is "
        "(928) 502-4001 and they open at 6am."
    )
    rate = _confabulation_rate(response, db, query="address for All Seasons Plumbing")
    assert rate >= 0.9, (
        f"Expected near-1.0 confab rate for invented phone alongside real entity, "
        f"got {rate}. G1 short-circuit still active."
    )


def test_g1_catalog_mention_does_not_excuse_invented_rating(db: Session) -> None:
    """G1: q22 prod shape — names real Heat Hotel + invents/misroutes rating."""
    response = "Heat Hotel has a 4.5-star Google rating (406 reviews)."
    rate = _confabulation_rate(response, db, query="rating for Fabricated Hotel Name 555")
    # Heat Hotel may legitimately have a 4.5 rating in dev catalog; the confab
    # is the *mismatch with the query subject*. The validator at this layer
    # cannot detect that semantic mismatch — but it CAN detect "asserted typed
    # fact, no catalog support" if Heat Hotel has no google_rating in dev. If
    # dev Heat Hotel does have google_rating=4.5, this test passes trivially
    # (the assertion-vs-source check succeeds) and the misroute is a routing
    # concern, not a validator concern. Document accordingly.
    assert rate <= 1.0  # purely a sanity bound


# ---------- G2 red tests ----------

def test_g2_invented_address_with_no_proper_noun_scored(db: Session) -> None:
    """G2: address regex must fire on responses with no Title-Case multi-word."""
    response = (
        "I'm not aware of a barber, but the closest is at 1450 N McCulloch Blvd, "
        "(928) 555-0199, open Tue-Sat 9-6."
    )
    rate = _confabulation_rate(response, db, query="barber in havasu")
    assert rate >= 0.9, (
        f"Expected near-1.0 confab for address+phone+hours after honest prefix, "
        f"got {rate}. G2 typed-fact probes missing or G3 short-circuit active."
    )


def test_g2_invented_url_scored(db: Session) -> None:
    response = "I don't have that in the catalog. Try https://fake-library.havasu.gov/hours"
    rate = _confabulation_rate(response, db, query="website for the library")
    assert rate >= 0.9


def test_g2_invented_rating_scored(db: Session) -> None:
    response = "Mudshark Brewing has a 4.7 stars rating from regulars."
    # If dev Mudshark has google_rating=4.7, this passes trivially; otherwise must score.
    rate = _confabulation_rate(response, db, query="rating for Mudshark Brewing")
    assert rate <= 1.0  # bounded; precise value depends on fixture


# ---------- G3 red tests ----------

def test_g3_honest_prefix_with_invented_body_scored(db: Session) -> None:
    """G3: q07's exact prod response shape — honest prefix + invented phone."""
    response = (
        "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu. If there is one, "
        "let me know with a URL and I'll pass it along. Their listed number is (928) 502-4001 "
        "-- recommend calling to confirm."
    )
    rate = _confabulation_rate(response, db, query="Tell me about Totally Fake Business XYZ 404")
    assert rate >= 0.9, (
        f"Expected near-1.0 confab for honest prefix + invented phone body, "
        f"got {rate}. G3 substring short-circuit still active."
    )
    path = _classify_disclosure_path(response, tier_used="3")
    assert path != "i_dont_know", (
        f"Expected disclosure path NOT i_dont_know for honest-prefix-then-confab, got {path}."
    )


def test_g3_honest_prefix_alone_still_passes(db: Session) -> None:
    """G3 boundary: pure honest disclaimer with no body must still score 0.0."""
    response = "I don't have that one in the catalog. Try /contribute or share a URL."
    rate = _confabulation_rate(response, db, query="phone for Imaginary Plumbing 12345")
    assert rate == 0.0
    path = _classify_disclosure_path(response, tier_used="gap_template")
    assert path == "i_dont_know"


def test_g3_user_echo_of_disclaimer_not_misclassified(db: Session) -> None:
    """G3 edge case: the *user's* query contains 'I'm not aware' — the model's
    response must be judged on its own content, not the user echo. The validator
    operates on the response string only, so this test verifies that a clean
    cited response is not misclassified as i_dont_know just because the user
    asked using disclaimer language."""
    # Simulating: user said "I'm not aware of a barber but is there a phone..."
    # Model responded with a real tier-2 listing:
    response = "Tony's Barbershop and Classic Cuts are both open today."
    rate = _confabulation_rate(response, db, query="I'm not aware of a barber but is there a phone")
    # Tony's / Classic Cuts may or may not be real in dev; the test is the
    # absence of an I-don't-know misclassification, not the confab rate.
    path = _classify_disclosure_path(response, tier_used="2")
    assert path != "i_dont_know", (
        "Response with no disclaimer in sentence 1 must not classify as i_dont_know "
        "just because tier_used isn't 'gap_template'."
    )


# ---------- G4 red tests ----------

def test_g4_any_tier_no_longer_universally_matches() -> None:
    """G4: 'any' should be retained for legacy compatibility but warned;
    explicit list form must work."""
    # Legacy `any` still matches (with warning) for backward compat:
    assert _tier_matches("any", "3") is True
    # List form works:
    assert _tier_matches(["tier1", "gap_template"], "1") is True
    assert _tier_matches(["tier1", "gap_template"], "gap_template") is True
    assert _tier_matches(["tier1", "gap_template"], "2") is False
    # Single value still works:
    assert _tier_matches("tier2", "2") is True
    assert _tier_matches("tier2", "3") is False
    assert _tier_matches("gap_template", "gap_template") is True
```

**Step 3.2 — Extend `tests/test_phase7_halt3_validation.py`** with one integration test that runs the *full* hardened validator against q24-q30 and asserts ALL PASS:

```python
def test_halt3_validator_full_eval_set_with_hardening(db: Session) -> None:
    """Post-Phase 7.5.2: validator runs 30/30 against the hardened eval set.

    Phase 7.5.1 added q23 (22 → 23 entries). Phase 7.5.2 adds q24-q30 (23 → 30).
    """
    from app.chat.halt3_validator import validate_eval_set

    report = validate_eval_set("app/chat/halt3_eval_set.yaml", db=db)
    failed = [r for r in report.results if not r.passed]
    assert not failed, (
        f"{len(failed)} validator rows FAILED:\n"
        + "\n".join(f"  {r.spec.id}: {r.failure_reasons}" for r in failed)
    )
    assert report.all_passed
    assert report.cited_disclosure_coverage >= 1.0
    assert report.missing_data_max_confabulation <= 0.0
    assert len(report.results) >= 30
```

Run all the red tests BEFORE applying any fixes:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -xvs
```

Expected: the G1/G2/G3 red tests FAIL (validator incorrectly returns 0.0 confab on confab-shaped responses). The G4 list-form test FAILs because the list signature isn't supported yet. The G3 boundary test and the user-echo test may already pass (they check non-regression). Document which failed in §12.

If any G1/G2/G3 red test PASSES prematurely against the un-hardened validator, the test isn't actually reproducing the gap — investigate before proceeding. Most common cause: the synthetic response happens to lack the catalog-entity name that triggers G1's short-circuit; add a known-real entity name to the response and retry.

---

## §4 Apply Fix G1 (catalog-mention shortcut removal + entity-fact verification)

Edit `app/chat/halt3_validator.py` per §2 Fix G1.

Add the module-level regex constants (`_PHONE_RE`, `_ADDRESS_RE`, `_HOURS_RE`, `_RATING_RE`, `_URL_RE`, `_EMAIL_RE`) and the three helper functions (`_typed_fact_probes`, `_entity_supports_typed_facts`, `_value_matches_any_entity`). Then rewrite `_confabulation_rate` per the §2 design.

**Verify Provider model fields exist before relying on them.** Read `app/db/models.py` and confirm `Provider` has columns named `phone`, `google_phone`, `google_rating`, `website`, `address`, `email`, `hours_json`. If any differ (e.g., `phone_number` instead of `phone`), update the helper's attribute lookups. If a field doesn't exist at all (e.g., no `email` column), drop that branch from `_value_matches_any_entity`.

After the edit:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g1_catalog_mention_does_not_excuse_invented_phone -xvs
```

Should now PASS. If it still FAILs, the issue is most likely in `_value_matches_any_entity` — debug by printing `entity_ids`, the loaded rows, and what `_value_matches_any_entity("phone", "(928) 502-4001", rows)` returns. The expected value is False (unsupported), driving the confab rate to 1.0.

---

## §5 Apply Fix G2 (typed-fact probes)

G2's typed-fact probes are already added as part of the G1 patch (the `_typed_fact_probes` helper). This section is a verification + the G2-only red tests now PASSing.

After Fix G1 lands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g2_invented_address_with_no_proper_noun_scored -xvs
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g2_invented_url_scored -xvs
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g2_invented_rating_scored -xvs
```

All three should PASS. If `test_g2_invented_address_with_no_proper_noun_scored` FAILs, check `_ADDRESS_RE` against the test fixture address `1450 N McCulloch Blvd` — the regex should match. Run a one-off in REPL:

```python
import re
from app.chat.halt3_validator import _ADDRESS_RE
print(_ADDRESS_RE.findall("1450 N McCulloch Blvd"))
```

Expected: `['1450 N McCulloch Blvd']`. If empty, the regex's `[NSEW]\.?` requires a dot after the directional in some test inputs — relax to `[NSEW]\.?\s*` or accept the bareword.

---

## §6 Apply Fix G3 (honest-prefix tightening — sentence-position-1 + no-subsequent-factual-claim)

Edit `app/chat/halt3_validator.py` per §2 Fix G3.

Add the `_honest_prefix_clears_response` helper. Replace `_classify_disclosure_path`'s line-85 short-circuit so it gates on the helper. The G1 patch already wired the helper into `_confabulation_rate` (replacing the line-103 short-circuit) — verify that wiring is in place.

After the edit:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g3_honest_prefix_with_invented_body_scored -xvs
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g3_honest_prefix_alone_still_passes -xvs
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g3_user_echo_of_disclaimer_not_misclassified -xvs
```

All three should PASS.

The boundary test (`test_g3_honest_prefix_alone_still_passes`) is the critical non-regression: a pure honest disclaimer with no body content MUST still score 0.0 confab and classify as `i_dont_know`. If this FAILs, the helper is over-tight — sentence-splitting may be treating a trailing fragment ("Try /contribute or share a URL.") as a "subsequent sentence with novel proper noun". Trace the split output and tune.

---

## §7 Apply Fix G4 (`expected_tier: any` burn-down + `_tier_matches` accepts list)

**Step G4.1 — Update `_tier_matches`, `ExpectedTier`, and `load_eval_set`** per §2 Fix G4-a.

Run the G4 unit test:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g4_any_tier_no_longer_universally_matches -xvs
```

Should PASS.

**Step G4.2 — Author the scratch audit script** (delete after use):

```python
# scripts/scratch_audit_tiers.py — DELETE after running
from sqlalchemy.orm import Session
from app.chat.halt3_validator import load_eval_set
from app.chat.unified_router import route
from app.db.database import SessionLocal

specs = load_eval_set("app/chat/halt3_eval_set.yaml")
with SessionLocal() as db:
    for s in specs:
        r = route(s.query, "tier-audit", db)
        print(f"{s.id}: {s.query[:60]!r} -> tier={r.tier_used}")
```

Run it:

```powershell
.\.venv\Scripts\python.exe scripts/scratch_audit_tiers.py
```

Cross-check the printed `tier=...` against the §2 Fix G4-b proposed mapping. For any divergence:

1. If the actual tier is clearly correct and the proposed table was wrong, update the table.
2. If two tiers are both legitimate (e.g., a query that may legitimately route to either tier1 or gap_template depending on catalog state), use the list form.
3. If the actual tier is clearly *wrong* (e.g., q07 hits tier-3 instead of gap_template — which would mean Phase 7.5.1's gate didn't actually land), HALT and report.

**Step G4.3 — Pin every eval-set row to its explicit tier.** Edit `app/chat/halt3_eval_set.yaml` row-by-row replacing `expected_tier: any` with the value from your verified table.

After the burn-down:

```powershell
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
```

Should still emit `all_passed=True`. If any row FAILs after pinning, either the proposed pin was wrong (revise to a list form) or the validator's new typed-fact probes are catching a real confab in the existing eval response (good — document and fix the underlying routing/template issue, OR accept the new failure as evidence the validator is now doing its job and the fix needs to land in another dispatch lane).

Delete `scripts/scratch_audit_tiers.py` after the burn-down completes — it's a one-shot tool, not a permanent script.

---

## §8 Apply q24-q30 eval set additions

**File:** `app/chat/halt3_eval_set.yaml`

Append the seven entries from §2 "q24-q30 adversarial eval entries" after the existing q23 row.

**Pre-pin verification — confirm the real-entity assumptions in q24, q25, q29.** Run a search:

```python
# In a Python REPL, with the venv activated:
from app.db.database import SessionLocal
from app.db.models import Provider
with SessionLocal() as db:
    for name in ["All Seasons Plumbing", "Mudshark Brewing", "Iron Wolf Golf", "Heat Hotel"]:
        rows = db.query(Provider).filter(Provider.provider_name.ilike(f"%{name}%")).all()
        print(name, "->", [(r.id, r.provider_name) for r in rows])
```

Expected: each name returns at least one row. If any returns empty:

- **q24** (`All Seasons Plumbing`) — substitute another active plumbing entity, or skip q24 and document.
- **q25** (`Mudshark Brewing`) — the dev catalog row is likely `Mudshark Brewery and Public House`. Update the query text to match, or rely on the matcher's fuzzy threshold; the existing `test_near_match_typo_returns_did_you_mean` proves the matcher resolves `mdshrkbrwry → Mudshark Brewery and Public House`, so `Mudshark Brewing` should resolve too.
- **q29** (`Iron Wolf Golf`) — substitute another real entity (e.g., `London Bridge Golf Club`) if missing.
- **q28** (`Heat Hotel`) — verified in Phase 7.5.1's `test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape` to exist (it seeds Heat Hotel as a fixture and the entity is also typically in dev). Confirm before pinning.

Update the eval-set entries with any substitutions you made, and note the substitution in §12.

After the additions:

```powershell
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
```

Should emit `all_passed=True` with 30 results listed. Each of q24-q30 should PASS — if any FAILs, decide whether the failure is (a) a legitimate validator catch of a routing/template confab that should drive a follow-up dispatch, or (b) a flaw in the q24-q30 design (e.g., the proposed `expected_tier` is wrong for the actual route). Document in §12.

---

## §9 Acceptance verification

Run all six checks. ALL must pass before §12.

```powershell
# 1. HALT 3 validator — 30/30 PASS with q24-q30 added and all rows explicit-tier pinned:
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
# Expected: cited_coverage=100% missing_confab_max=0.00 all_passed=True
# 30 rows listed; q24-q30 all PASS

# 2. Full pytest suite — should be >= post-7.5.1 baseline + new tests:
.\.venv\Scripts\python.exe -m pytest -q
# Expected: post-7.5.1 baseline + the new hardening tests (~10 added in
# test_halt3_validator_hardening.py + 1 in test_phase7_halt3_validation.py)

# 3. The four Goodhart red tests now GREEN:
.\.venv\Scripts\python.exe -m pytest -xvs tests/test_halt3_validator_hardening.py

# 4. Phase 7.5.1's three integration tests still GREEN (non-regression):
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase38_gap_and_hours.py::test_q03_what_restaurants_open_now_reaches_tier2 `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3

# 5. The new full-eval integration test:
.\.venv\Scripts\python.exe -m pytest -xvs tests/test_phase7_halt3_validation.py::test_halt3_validator_full_eval_set_with_hardening

# 6. Ruff clean on all touched files:
.\.venv\Scripts\python.exe -m ruff check `
    app/chat/halt3_validator.py `
    app/chat/halt3_eval_set.yaml `
    tests/test_halt3_validator_hardening.py `
    tests/test_phase7_halt3_validation.py
```

**If any check fails, HALT and investigate.** Do not proceed to §12.

---

## §10 File scope (gotcha #18 disjointness)

Modified files (closed set):
- `app/chat/halt3_validator.py` (G1+G2 typed-fact probes + verification helpers; G3 honest-prefix gate; G4 `_tier_matches` accepts list; `ExpectedTier` Literal + `load_eval_set` accept list form)
- `app/chat/halt3_eval_set.yaml` (G4 burn-down of `any` → explicit tiers on every existing row; append q24-q30)
- `tests/test_phase7_halt3_validation.py` (add `test_halt3_validator_full_eval_set_with_hardening`)

New files:
- `tests/test_halt3_validator_hardening.py` (G1/G2/G3 synthetic-response red tests + G4 unit tests)

Temporary scratch files (delete before §12):
- `scripts/scratch_audit_tiers.py` (one-shot G4 burn-down audit; delete after use)

**Do NOT touch:**
- `app/chat/entity_intent.py` — Phase 7.5.1 just landed `_general_subject_tokens` / `_CATEGORY_TOKENS` here. Untouched in 7.5.2.
- `app/chat/unified_router.py` — Phase 7.5.1 just landed `_unknown_entity_about_gate` + the `is_category_open_now_listing` probe here. Untouched in 7.5.2.
- `app/chat/entity_matcher.py` — `extract_catalog_entities_from_text` and `refresh_entity_matcher` are imported as-is. Do not modify their behavior.
- `app/chat/disclosure_render.py` — unchanged; the renderer flag remains orthogonal.
- `app/chat/tier2_business_shortcut.py`, `app/chat/tier3_handler.py`, `app/chat/intent_classifier.py` — unchanged.
- Any Phase 6.5 surfaces (`home.html`, themed tiles, conditions strip).
- Any Phase 8a surfaces (`app/conditions/`, `app/alerts/`).
- Any Phase 9 surfaces (events, RRULE).
- Any docs (`docs/maintainability/*.md`, `docs/STATE.md`) — Cowork primary updates these post-ship.

---

## §11 What NOT to do

- **Do NOT git-commit.** Stop at §12. The operator commits after reviewing your diff.
- **Do NOT touch the routing code Phase 7.5.1 just landed** (`entity_intent.py`, `unified_router.py`). This dispatch is validator-only. If a §8 q24-q30 row FAILs because the *router* still has a bug, document it for a follow-up dispatch — don't fix it here.
- **Do NOT change `_I_DONT_KNOW_RE` to remove the "I'm not aware" pattern.** That regex captures real honest disclaimer signals. The fix is to tighten *where* the match counts as a short-circuit (G3's sentence-1 + no-subsequent-typed-fact gate), not to drop the pattern itself.
- **Do NOT broaden the typed-fact probes beyond the six classes listed** (phone, address, hours, rating, URL, email). Adding more probes (price, opening date, license number, etc.) is appealing but risks false positives — every new probe needs a matching `_value_matches_any_entity` branch and a Provider-model field to verify against. Six classes covers the prod failure modes; expand in a later dispatch if the hardened validator misses a new confab class.
- **Do NOT add new dependencies.** `re`, `yaml`, `sqlalchemy` are already imported. No new imports beyond what's already in the file + the explicit ones added in §2.
- **Do NOT add an alembic migration.** No schema changes — the typed-fact verification reads existing Provider columns.
- **Do NOT modify `disclosure_render.py` or `FEATURE_FLAG_DISCLOSURE_RENDERER` semantics.** Orthogonal concern, unchanged.
- **Do NOT delete the scratch audit script silently.** If you create `scripts/scratch_audit_tiers.py` for G4 burn-down, delete it explicitly before §12 and confirm in §12.5.
- **Do NOT leave `expected_tier: any` in the eval set after §7.** The G4 burn-down must be complete. The `_tier_matches` legacy `any` branch stays (with warning) for backward compat in case downstream tooling consumes the validator, but the YAML should have no `any` entries.
- **Do NOT relax the q24-q30 acceptance criteria.** If one of them FAILs because the router still has a gap, document the gap; don't loosen `expected_confabulation_rate` to make it pass.

---

## §11.5 ADDITIONAL FIXES — G5 + F3 (Cowork amendment, 2026-05-19)

> **Cowork amendment after cc authored §0-§12.** A parallel codebase Goodhart audit (sub-agent C) surfaced two additional gaps in the same file/test surface as G1-G4. Folding them in here keeps the validator-hardening lane atomic instead of dispatching a separate Phase 7.5.3 for fixes that share the same code window.

### G5. Tier-routing as proof of citation in `_classify_disclosure_path` (CRITICAL — in same file as G1-G4)

**Location:** `app/chat/halt3_validator.py:84-95` — specifically the fall-through at line 93.

**Code (current):**
```python
def _classify_disclosure_path(response: str, tier_used: str) -> DisclosurePath:
    if _I_DONT_KNOW_RE.search(response or ""):
        return "i_dont_know"
    if tier_used == "gap_template":
        return "i_dont_know"
    if disclosure_render.is_renderer_enabled():
        decision = disclosure_render.consume_decision()
        if decision is not None and decision.tone_allowlist_passed:
            return "cited"
    if tier_used in ("1", "2", "3"):
        return "cited"          # ← G5 bug: returns "cited" with no citation evidence
    return "uncited"
```

**Failure mode:** When `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (the production state at 2026-05-19), the `tone_allowlist_passed` branch never fires. The function then unconditionally returns `"cited"` for **any** response routed through tier 1/2/3 — regardless of whether the response actually contains a citation, an attribution, a catalog row mention, or any verifiable claim. The check is "did this go through a tier?" not "does this response have evidence of grounding?"

This is the load-bearing mechanism that let `cited_coverage=100%` hold at Phase 7.5's ship while production responses were tier-3 LLM freeform with no catalog grounding. The fix sequence G1→G2→G3 closes the *confabulation-rate* short-circuits; G5 closes the *cited-classification* short-circuit.

**Example PASS-but-fail:**
A tier-3 LLM response with no catalog mention or typed fact ("Sure, here are some great spots — try checking out a few places downtown") gets `tier_used="3"` → `_classify_disclosure_path` returns `"cited"` → eval row with `expected_disclosure_path: cited` PASSes the disclosure check even though the response cites nothing.

**Proposed fix:** when the renderer-decision branch doesn't fire and `tier_used` is 1/2/3, require evidence of citation before classifying as `"cited"`. Specifically: the response must contain at least one catalog entity mention (via `extract_catalog_entities_from_text`) OR a typed-fact value (phone/address/etc.) that verifies against the mentioned catalog row's actual data (via the G1/G2 `_entity_supports_typed_facts` helper). When neither is present, classify as `"uncited"` instead.

**Replace `_classify_disclosure_path` (extends G3's existing rewrite):**

```python
def _classify_disclosure_path(
    response: str,
    tier_used: str,
    *,
    db: Session | None = None,
) -> DisclosurePath:
    """Classify the disclosure path of a chat response.

    Hardened (Phase 7.5.2 G5, 2026-05-19): the previous fall-through returned
    "cited" for any tier 1/2/3 response without verifying citation content,
    which let `cited_coverage=100%` hold for tier-3 LLM freeform answers
    that named no catalog entity. The new flow requires evidence — either
    a catalog entity mention or a typed-fact value that verifies against
    the entity's actual data — before claiming "cited".

    The `db` kwarg is required for the new evidence check; callers must
    pass it (the legacy two-arg call site is updated in this dispatch).
    """
    text = response or ""
    if _honest_prefix_clears_response(text):
        return "i_dont_know"
    if tier_used == "gap_template":
        return "i_dont_know"
    if disclosure_render.is_renderer_enabled():
        decision = disclosure_render.consume_decision()
        if decision is not None and decision.tone_allowlist_passed:
            return "cited"
    if tier_used in ("1", "2", "3"):
        # G5 evidence gate: must have a catalog entity mention OR a typed-fact
        # value that the catalog row supports.
        if db is not None:
            try:
                refresh_entity_matcher(db)
                mentioned = extract_catalog_entities_from_text(text, db)
                if mentioned:
                    return "cited"
                facts = _typed_fact_probes(text)
                if any(facts.values()):
                    # We have typed facts but no entity mention. If they verify
                    # against any catalog row, count as cited; else uncited.
                    # Since we don't know which entity, this is a weak signal;
                    # treat it conservatively as uncited.
                    return "uncited"
            except Exception:
                logging.exception("_classify_disclosure_path: G5 evidence probe failed")
        return "uncited"
    return "uncited"
```

Also update the call site in `_run_one`:

```python
# Inside validate_eval_set._run_one, line 146:
disc = _classify_disclosure_path(resp.response, resp.tier_used, db=session)
```

(The function signature change to require `db` propagates here.)

### F3. `test_validator_gate_with_mocked_router` asserts plumbing not behavior

**Location:** `tests/test_phase7_halt3_validation.py:122-172`

**Failure mode:** The test patches `route()` with `_fake_route` that returns one of two hardcoded strings:
- For queries with eval-set markers (`zzz`, `xyz`, `404`, etc.): `"I don't have that in the catalog yet."`
- For everything else: `"A few local options are listed in the catalog."`

Both strings satisfy the validator's checks by construction: the first matches `_I_DONT_KNOW_RE`; the second has no proper-noun probes and `tier_used="2"` (so the old G5 path returned "cited"). The test then asserts `report.all_passed is True`.

This is round-trip plumbing verification, not validator-semantics verification. Anyone reading `test_validator_gate_with_mocked_router` as evidence that "the validator catches confabulation" would be misled: the only thing tested is that the validator can pass strings shaped exactly to satisfy its regex checks.

**Proposed fix:** add a second test (or extend the existing one) that uses `_fake_route` responses **designed to fail the validator** after the G1-G5 hardening, and assert the validator catches them. Don't just delete the existing `assert report.all_passed is True` — keep it as a smoke test of the happy-path plumbing, but add adversarial responses to prove the hardened validator does its job.

**Add to `tests/test_phase7_halt3_validation.py`** (alongside or replacing the existing `test_validator_gate_with_mocked_router`):

```python
def test_validator_catches_hardening_failure_modes_with_mocked_router(db: Session) -> None:
    """F3 amendment: prove the hardened validator catches the four Goodhart
    failure modes when fed synthetic responses that satisfy the old (broken)
    metric shortcuts but fail the underlying anti-confabulation goal."""
    from app.chat.halt3_validator import validate_eval_set

    # Map adversarial responses to specific eval rows. Each pair is designed to
    # fail at least one of the G1-G5 hardening checks.
    adversarial_responses = {
        # q07: honest prefix + invented phone (G3 + G2)
        "q07": (
            "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu. "
            "Their listed number is (928) 502-4001 -- recommend calling to confirm."
        ),
        # q05: tier-3 cited claim with no real entity (G5)
        "q05": "Sure, here are a few local options worth checking out.",
        # q08: honest prefix + invented address (G3 + G2)
        "q08": (
            "I don't have that one in the catalog, but you can try "
            "1450 N McCulloch Blvd, (928) 555-0199, open Tue-Sat 9-6."
        ),
    }

    def _adversarial_route(q, sid, db_arg, **kwargs):
        from app.chat.unified_router import ChatResponse
        # Match by query substring to the corresponding eval row's expected
        # confabulation shape; default to a clean tier-2 cited string for
        # other rows so they continue to pass.
        for qid, resp_text in adversarial_responses.items():
            # Pull the actual eval row's query text dynamically so this
            # doesn't drift if the eval set changes.
            pass  # see below — match against eval set spec by id
        # Fallback: honest tier-2 cited string for any other row
        return ChatResponse(
            response="Bad Miguel's Mexican Restaurant is in the catalog.",
            mode="ask",
            sub_intent=None,
            entity="Bad Miguel's Mexican Restaurant",
            tier_used="2",
            latency_ms=10,
        )

    # Better: parameterize per eval-row id directly.
    from app.chat.halt3_validator import load_eval_set
    specs = load_eval_set("app/chat/halt3_eval_set.yaml")
    spec_by_id = {s.id: s for s in specs}

    def _route_by_spec(q, sid, db_arg, **kwargs):
        from app.chat.unified_router import ChatResponse
        # Find which spec this query belongs to.
        matching_id = next(
            (sid_ for sid_, sp in spec_by_id.items() if sp.query == q),
            None,
        )
        if matching_id in adversarial_responses:
            return ChatResponse(
                response=adversarial_responses[matching_id],
                mode="ask",
                sub_intent=None,
                entity=None,
                tier_used="3",
                latency_ms=10,
            )
        # Default clean response for other rows (mimic the original mock).
        return ChatResponse(
            response="Bad Miguel's Mexican Restaurant is in the catalog.",
            mode="ask",
            sub_intent=None,
            entity="Bad Miguel's Mexican Restaurant",
            tier_used="2",
            latency_ms=10,
        )

    with patch("app.chat.halt3_validator.route", side_effect=_route_by_spec):
        report = validate_eval_set("app/chat/halt3_eval_set.yaml", db=db)

    # The hardened validator MUST catch the three adversarial rows.
    failed_ids = {r.spec.id for r in report.results if not r.passed}
    assert "q07" in failed_ids, (
        "q07 adversarial response (honest prefix + invented phone) should FAIL "
        "after G2+G3 hardening but PASSed. Validator regression."
    )
    assert "q05" in failed_ids, (
        "q05 adversarial response (tier-3 cited claim with no real entity) should "
        "FAIL after G5 hardening but PASSed. G5 evidence gate not active."
    )
    assert "q08" in failed_ids, (
        "q08 adversarial response (honest prefix + invented address) should FAIL "
        "after G2+G3 hardening but PASSed. G2 typed-fact probes missing or G3 "
        "honest-prefix gate not catching the second-sentence factual claim."
    )
```

Plus retain the existing `test_validator_gate_with_mocked_router` as plumbing smoke (but consider relabeling its assertion to clarify it tests round-trip plumbing, not validator semantics).

### Apply

After §6 (G3 fix) and before §7 (G4 burn-down):

**Step G5.1 — Update `_classify_disclosure_path`** per the G5 fix design above. Note the `db` parameter is now required.

**Step G5.2 — Update `validate_eval_set._run_one`** to pass `db=session` to `_classify_disclosure_path`. Line 146 currently calls `_classify_disclosure_path(resp.response, resp.tier_used)` — change to include `db=session`.

**Step G5.3 — Verify G5 red test passes**: add `test_g5_tier_routing_alone_not_proof_of_citation` to `tests/test_halt3_validator_hardening.py`:

```python
def test_g5_tier_routing_alone_not_proof_of_citation(db: Session) -> None:
    """G5: tier 1/2/3 routing alone must not classify as 'cited' when the
    response contains no catalog entity mention and no verifiable typed fact.

    The pre-G5 fall-through at _classify_disclosure_path:93 returned 'cited'
    for any tier 1/2/3 response. Post-G5 requires evidence."""
    response = "Sure, here are a few local options worth checking out."
    path = _classify_disclosure_path(response, tier_used="2", db=db)
    assert path == "uncited", (
        f"G5 fall-through still active — tier-2 response with no entity mention "
        f"+ no typed fact classified as {path!r}, expected 'uncited'."
    )


def test_g5_real_entity_mention_still_classifies_cited(db: Session) -> None:
    """G5 boundary: a tier 1/2/3 response that DOES mention a real catalog
    entity must still classify as 'cited' (non-regression)."""
    from app.chat.entity_matcher import refresh_entity_matcher
    refresh_entity_matcher(db)
    # Use a known dev-catalog entity; substitute if not present.
    response = "Bad Miguel's Mexican Restaurant is open today."
    path = _classify_disclosure_path(response, tier_used="2", db=db)
    assert path == "cited", (
        f"G5 over-tight — tier-2 response with real catalog entity mention "
        f"classified as {path!r}, expected 'cited'."
    )
```

**Step F3.1 — Author the adversarial mock-router test** per the F3 fix design above. Add to `tests/test_phase7_halt3_validation.py`.

**Step F3.2 — Run both new tests**: `.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py::test_g5_tier_routing_alone_not_proof_of_citation tests/test_halt3_validator_hardening.py::test_g5_real_entity_mention_still_classifies_cited tests/test_phase7_halt3_validation.py::test_validator_catches_hardening_failure_modes_with_mocked_router -xvs`

All three should PASS.

### Update §9 acceptance gates

Add to §9:

```powershell
# 7. G5 + F3 red tests pass:
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_halt3_validator_hardening.py::test_g5_tier_routing_alone_not_proof_of_citation `
    tests/test_halt3_validator_hardening.py::test_g5_real_entity_mention_still_classifies_cited `
    tests/test_phase7_halt3_validation.py::test_validator_catches_hardening_failure_modes_with_mocked_router
```

### Update §12.3 per-fix table

Add two rows to the §12.3 per-fix verification table:

| Fix | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| G5 (tier-routing evidence gate) | `test_g5_tier_routing_alone_not_proof_of_citation` + `test_g5_real_entity_mention_still_classifies_cited` | Same tests post-fix | ☐ |
| F3 (adversarial mock-router) | `test_validator_catches_hardening_failure_modes_with_mocked_router` | Same test post-fix | ☐ |

### Update §12.7 commit subject

The commit subject should now also acknowledge G5 + F3. Suggested addition:

```
feat(phase7.5.2): harden HALT 3 validator -- catalog-mention shortcut closed (G1); typed-fact probes added phone/address/hours/rating/URL/email (G2); honest-prefix gated to sentence-1 + no-subsequent-fact (G3); _tier_matches accepts list + expected_tier=any burn-down across q01-q23 (G4); tier-routing-as-citation evidence gate (G5); adversarial mock-router test added (F3); +7 adversarial eval entries q24-q30; 12 new hardening tests + 1 full-eval integration test + 1 adversarial mock-router test; 30/30 validator PASS
```

---

## §12 Final report (you MUST emit this; do not commit)

Emit a structured report covering:

### §12.1 Diffs
- Full unified diff of all modified files (use `git diff` output)
- Confirm no files outside §10 scope were touched
- Confirm `scripts/scratch_audit_tiers.py` (if created) is deleted

### §12.2 Acceptance checks
For each of the six checks in §9, paste the actual output line(s). Confirm PASS for each.

### §12.3 Per-fix verification

| Fix | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| G1 (catalog-mention shortcut) | `test_g1_catalog_mention_does_not_excuse_invented_phone` | Same test post-fix | ☐ |
| G2 (typed-fact probes) | `test_g2_invented_address_with_no_proper_noun_scored`, `test_g2_invented_url_scored`, `test_g2_invented_rating_scored` | Same tests post-fix | ☐ |
| G3 (honest-prefix gate) | `test_g3_honest_prefix_with_invented_body_scored` | Same test post-fix + boundary tests | ☐ |
| G3 boundary | `test_g3_honest_prefix_alone_still_passes`, `test_g3_user_echo_of_disclaimer_not_misclassified` | Pre + post both PASS (non-regression) | ☐ |
| G4 (`_tier_matches` list form + `any` burn-down) | `test_g4_any_tier_no_longer_universally_matches` | Same test post-fix; eval set has no `any` entries | ☐ |
| Validator full eval | `python -m app.chat.halt3_validator` 23/23 PASS pre + 30/30 PASS post | | ☐ |
| Non-regression (7.5.1) | Phase 7.5.1's three integration tests still PASS | | ☐ |

### §12.4 G4 burn-down audit table
Paste the actual `tier=...` printout from the scratch audit script for every eval-set row q01-q23, side-by-side with the proposed pin from §2 Fix G4-b. Highlight any rows where you used the list form, and the reason.

### §12.5 Substantive findings
Anything surprising you encountered:
- Were any q24-q30 entity assumptions wrong? Which entities did you substitute?
- Did any existing eval row FAIL after pinning + the new typed-fact probes? Is the failure a real router/template confab the validator now catches?
- Did the Provider model lack any of the assumed fields (`phone`, `google_phone`, `google_rating`, `website`, `address`, `email`, `hours_json`)? Which branches of `_value_matches_any_entity` did you drop?
- Any bugs in existing code you noticed but didn't fix (because out of scope)?
- Anything the wrapper didn't anticipate.

### §12.6 File scope confirmation
Paste output of `git status --short` confirming only §10-listed files modified, and that `scripts/scratch_audit_tiers.py` is absent.

### §12.7 Recommended commit subject
Suggest a commit subject line. Default:

```
feat(phase7.5.2): harden HALT 3 validator -- catalog-mention shortcut closed (G1); typed-fact probes added phone/address/hours/rating/URL/email (G2); honest-prefix gated to sentence-1 + no-subsequent-fact (G3); _tier_matches accepts list + expected_tier=any burn-down across q01-q23 (G4); +7 adversarial eval entries q24-q30; 10 new hardening tests + 1 full-eval integration test; 30/30 validator PASS
```

### §12.8 Open carries
Anything that should become a V1.5 carry or a future dispatch concern:
- Confab classes not yet probed (price, license number, opening dates, etc.) — should they be added in a future hardening lane?
- Eval-set rows where the burn-down forced a list form — is the underlying route ambiguity a design choice or a routing bug to fix?
- The `_value_matches_any_entity` hours branch is currently a presence check (any non-empty `hours_json` passes) — should it be a real string-comparison after a future hours-formatting normalization lands?
- Any prod-shape divergence the validator still can't catch (e.g., LLM nondeterminism producing different responses on dev vs. prod for the same query).

---

End of wrapper. Now go.
