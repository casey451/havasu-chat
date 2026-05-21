# Cursor dispatch prompt — Phase 7.5.4 (template-echo scrub tightening; watch item #2 only)

> **What this is:** a paste-ready dispatch wrapper for a fresh Cursor chat to close the highest-confidence exploitable surface in the HALT 3 validator that survived Phase 7.5.2 (commit `64799d5`). The 7.5.2 wrapper added three template-echo scrubs in `_sanitize_typed_facts` (`app/chat/halt3_validator.py:117-126`) so legitimate gap / tier-3 disclaimers wouldn't be scored as confabulation. The **rating scrub** at lines 123-126 wipes the ENTIRE `rating` typed-fact list when the response text (lowercased) contains any of three substrings — and one of those substrings (`"rating for"`) is literally the user-query phrase shape for q25. Any natural model echo of `"the rating for X is N.N stars"` has its rating extraction scrubbed BEFORE `_entity_supports_typed_facts` runs — confabulated rating values silently slip past the validator. The Lane G audit confirmed this is a real (not theoretical) hole. Phase 7.5.4 tightens all three scrubs to per-sentence anchored matches against template-disclaimer shapes, not user-echo substrings.
>
> **Operator:** open a fresh Cursor chat. Paste the entire content of this file (everything below the horizontal rule) as the first message. Cursor takes the work end-to-end through §11 and returns a final report. Do NOT add any other context — the wrapper is self-contained.
>
> **Pre-positioned by:** Cowork primary, 2026-05-20. Companion: `outputs/phase_7_5_4_validator_polish_watch_items_design_memo.md` (full scoping, both watch items audited, Lane G recommendation to ship watch item #2 ONLY).
>
> **Estimated effort:** ~1-1.5h Cursor session (~60-100 LOC + 5-7 tests). Polish lane, not a hot fix.

---

# Phase 7.5.4 — Template-echo scrub tightening dispatch

You are picking up the havasu-chat project to tighten three template-echo scrubs in the HALT 3 validator's `_sanitize_typed_facts` (and the `_is_platform_url` helper) so they anchor on template-disclaimer shapes per-sentence rather than whole-response substring matches. Phase 7.5.2 introduced the scrubs to defend legitimate gap-template responses; this lane closes the q25-shape exploit those scrubs accidentally opened.

**File scope (gotcha #18 disjointness):** This dispatch ONLY touches `app/chat/halt3_validator.py` + `tests/test_halt3_validator_hardening.py` (append-only). Do NOT touch `app/chat/halt3_eval_set.yaml` (the Lane G audit confirmed no YAML changes are needed for this lane). Do NOT touch any tier-2 / tier-3 / router surfaces. The wrapper enumerates expected files in §8.

**Watch item scope:** This lane is **watch item #2 only**. Watch item #1 (G4 list-promiscuity — multi-tier `expected_tier` lists for q02 + q27) is explicitly OUT OF SCOPE per the design memo's §4 honest-assessment recommendation: it is documentation-of-flake rather than behavioral tightening, and is dropped from this lane.

**Cadence:** Stop at the §11 boundary. Do NOT git-commit. The operator commits after reviewing your diff.

---

## §0 Boot prereqs (verify BEFORE any edits)

Working directory: `C:\Users\casey\projects\havasu-chat`. For any Python invocation, use the venv: `.\.venv\Scripts\python.exe ...` from project root.

This dispatch assumes **Phase 7.5.2 has shipped** (commit `64799d5`) and pins a floor SHA of `44ca1c6` (the post-7.6 ledger commit, current `origin/main` tip at authoring time). By the time you dispatch, Phase 7.5.3 (routing polish) and/or Phase 7.7 (honest empty listing) and/or Phase 8a (conditions infrastructure) may have ALSO shipped — that is fine. None of those lanes touch the validator scrub surface, and the scrub-tightening logic in this wrapper is independent of routing changes. Verify the actual `origin/main` tip at dispatch time and record it for §11.

Run all seven checks. HALT and report if any diverge:

```powershell
# 1. origin/main tip is at or after 44ca1c6 (post-7.6 ledger). Inspect recent commits
#    for "phase7.5.2" + "phase7.6" subjects (mandatory) and "phase7.5.3" / "phase7.7" /
#    "phase8a" subjects (optional — may also be present). Record the actual tip SHA for §11.
git log -12 --format="%h %s" origin/main

# 2. Phase 7.5.2 SHIPPED check — _PLATFORM_URL_MARKERS + _sanitize_typed_facts must exist
#    in the validator at the expected line numbers:
.\.venv\Scripts\python.exe -c "
import inspect
from app.chat import halt3_validator as v
src = inspect.getsource(v)
assert '_PLATFORM_URL_MARKERS' in src, '7.5.2 scrub block missing — HALT'
assert '_sanitize_typed_facts' in src, '7.5.2 _sanitize_typed_facts missing — HALT'
assert '_typed_fact_probes' in src, '7.5.2 _typed_fact_probes missing — HALT'
assert 'rating for' in src, '7.5.2 rating scrub substring missing — HALT'
assert 'open\\\\s+tomorrow' in src or 'open\\s+tomorrow' in src, '7.5.2 hours scrub regex missing — HALT'
print('7.5.2 scrub surface present')
"

# 3. Verify the exact line numbers haven't shifted since the design memo. The wrapper
#    pins line 50 for _PLATFORM_URL_MARKERS, 117-121 for the hours scrub, 123-126 for
#    the rating scrub. If a parallel lane shifted them by a few lines, that is fine —
#    record the actual line numbers from this check and re-anchor §2/§4 against them.
.\.venv\Scripts\python.exe -c "
from pathlib import Path
lines = Path('app/chat/halt3_validator.py').read_text(encoding='utf-8').splitlines()
for i, line in enumerate(lines, 1):
    if '_PLATFORM_URL_MARKERS = ' in line:
        print(f'_PLATFORM_URL_MARKERS at line {i}')
    if 'open\\\\s+tomorrow' in line or 'open\\s+tomorrow' in line:
        print(f'hours scrub regex at line {i}')
    if \"'rating for'\" in line or '\"rating for\"' in line:
        print(f'rating scrub gate at line {i}')
"

# 4. Alembic single head c9d0e1f2a3b4 (unchanged across 7.5.x + 7.6 + 7.7; 8a may
#    bump this — record what you see):
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current

# 5. Pytest baseline — post-7.6 floor is ~2202, may be higher if 7.5.3 / 7.7 / 8a
#    shipped first. Record exact number for §11 delta math:
.\.venv\Scripts\python.exe -m pytest --collect-only -q | Select-Object -Last 3

# 6. HALT 3 validator currently 30/30 all-pass (against the dev DB):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator

# 7. RED baseline — confirm the q25-shape rating-scrub exploit. The current scrub wipes
#    the entire rating list when the response contains "rating for" (substring, case-
#    insensitive). A confabulated rating echo of the user query has its rating value
#    scrubbed before _entity_supports_typed_facts sees it. This test FAILS at HEAD and
#    PASSES after the §2/§4 fix.
.\.venv\Scripts\python.exe -c "
from app.chat.halt3_validator import _typed_fact_probes
# Natural model echo of q25's prompt 'what's the rating for Mudshark Brewery'. The
# response asserts a rating but contains the user-echo phrase 'the rating for'. Current
# scrub: rating list wiped to []. Post-fix: rating list retains '4.7 stars' because the
# sentence does NOT contain a template-disclaimer pattern.
text = 'The rating for Mudshark Brewery is 4.7 stars based on 200+ reviews.'
facts = _typed_fact_probes(text)
print('RED baseline rating facts:', facts.get('rating'))
assert facts.get('rating') == [], (
    f'Expected rating list to be wiped by current whole-text scrub, got {facts.get(\"rating\")!r}. '
    'Baseline already tightened — HALT and re-audit scope.'
)
print('RED baseline OK: current scrub wipes rating list on user-echo, masking confab.')
"
```

Expected:
- origin/main tip at or after `44ca1c6` (record actual SHA; may be a later commit if 7.5.3 / 7.7 / 8a shipped).
- Check #2 prints `7.5.2 scrub surface present` (no ImportError or AssertionError).
- Check #3 prints three lines with the actual line numbers for the three scrub anchors. If line numbers differ from the §2 / §4 wrapper text (50 / 117-121 / 123-126), re-anchor your edits — the structural patches in §2 still apply.
- Alembic head `c9d0e1f2a3b4` (single; 8a may bump — record what you see, do not block on this if 8a shipped).
- Pytest collected count recorded (floor ~2202 post-7.6 — record actual).
- Check #6 outputs `cited_coverage=100% missing_confab_max=0.00 all_passed=True` (30/30 PASS).
- Check #7 prints `RED baseline OK` — current scrub demonstrably wipes the rating list on a q25-shape user-echo response. If the assertion fails, the scrub has already been tightened on `origin/main` (someone shipped 7.5.4 ahead of you) — HALT and report.

**If any check diverges, HALT and report.** Do not proceed with edits.

---

## §1 The bug — q25 rating-scrub exploit

**Query (q25):** `"what's the rating for Mudshark Brewery and Public House"` (`halt3_eval_set.yaml:161`)

**Production-flavored failure shape (theoretical, not yet observed):** the LLM emits a response that echoes the user's "rating for X" phrase and asserts a rating value, e.g.:

> *"The rating for Mudshark Brewery is 4.7 stars based on 200+ reviews. They're known for their craft beer."*

**Current scrub behavior** (`app/chat/halt3_validator.py:123-126`):

```python
low = (text or "").lower()
if out.get("rating") and (
    "rated above" in low or "stars in the catalog" in low or "rating for" in low
):
    out["rating"] = []
```

This is a **whole-text substring gate** with a **whole-list wipe**. The response above contains `"rating for"` as a substring (echoing the user query) → the entire `rating` list (including the asserted `"4.7 stars"`) is wiped → `_entity_supports_typed_facts` never sees the asserted rating → no confab is flagged even if Mudshark's actual `google_rating` is e.g. `4.5` (a 0.2-point fabrication slips past the validator).

**Per-scrub audit (all three from the Lane G memo):**

| Scrub | Location | Current shape | Risk |
|---|---|---|---|
| URL platform-marker | `_is_platform_url` at `:50` + `:109-111` (`golakehavasu.com`, `/contribute`) | Substring match anywhere in URL string | Low — adversarial only (`https://evil.example.com?ref=golakehavasu.com` would be scrubbed) |
| Hours `open tomorrow` | `_sanitize_typed_facts` at `:117-121` | Regex match `open\s+tomorrow` against EACH hours probe | Medium — `"Heat Hotel is open tomorrow Mon 8am to 5pm"` confab is scrubbed if the hours regex captures the `open tomorrow` portion |
| Rating whole-text gate | `_sanitize_typed_facts` at `:123-126` | Lowercased response contains any of three substrings → wipe **entire** rating list | **High — q25-shape user-echo exploit (load-bearing concern for this lane)** |

The hours and URL scrubs are also widened-substring (not anchored to template shape), but the rating scrub is the one with a real prompt in the eval set that hits the exploit shape. **Confirmed by Lane G audit as the highest-priority and most exploitable surface.**

### What 7.5.2 was protecting (do NOT break)

The scrubs exist for legitimate reasons:
- **q26** (`"website for the library"`) — gap template body emits `golakehavasu.com` + `/contribute` URLs. Those are template emissions, not confab. The URL scrub keeps them from being scored.
- **q30** (`"any restaurants rated above 4 stars"`) — user-query phrase `"rated above 4 stars"` echoes in the response. The rating scrub keeps the user-query echo from being scored as an invented rating.
- **q05 / q06** (hours gap templates) — gap-template phrasing includes `"can't say if X is open tomorrow"`. The hours scrub keeps the disclaimer phrase from being scored.

After the fix, the legitimate cases above must still pass the validator (30/30 invariant). The rest of the wrapper is structured to enforce that.

---

## §2 The fix design (Path A — sentence-anchored disclaimer patterns)

**Recommend Path A** from `outputs/phase_7_5_4_validator_polish_watch_items_design_memo.md` §2 (watch item #2): tighten each scrub from whole-text substring to **per-sentence anchored disclaimer patterns**. Keep the legitimate template-shape cases working; close the user-echo exploit.

**No new helpers in `_typed_fact_probes`.** Only `_is_platform_url` + `_sanitize_typed_facts` change. The consumer (`_typed_fact_probes` at `:130-142`) is unchanged.

### Step 2a — Tighten `_is_platform_url`

Replace the substring marker check at `:49-50` + `:109-111` with a compiled regex that anchors `golakehavasu.com` as a hostname (or subdomain) and `/contribute` as a path component starting at a `/` boundary and followed by `/`, end-of-URL, `?`, or `#`. Drop the `_PLATFORM_URL_MARKERS` tuple constant; it is replaced by the regex.

```python
# Phase 7.5.4 — tightened: anchored hostname + path-segment patterns.
# - golakehavasu.com must be the host (or subdomain): require '//' or '.' before it
#   and a '/', ':', or end-of-string after the TLD.
# - /contribute must be a path component: require it preceded by host or '/' and
#   followed by '/', '?', '#', or end-of-string (NOT a substring of /contribute-please).
_PLATFORM_URL_RE = re.compile(
    r"(?:^|//|\.)golakehavasu\.com(?:[/:?#]|$)"
    r"|(?:^|/)contribute(?:[/?#]|$)",
    re.IGNORECASE,
)


def _is_platform_url(url: str) -> bool:
    return bool(_PLATFORM_URL_RE.search(url or ""))
```

### Step 2b — Tighten the hours scrub (per-sentence)

Replace the `open\s+tomorrow` substring-anywhere check at `:117-121` with a sentence-level scrub: keep an hours probe only if NO sentence containing it ALSO matches a disclaimer pattern. The disclaimer pattern requires a hedging verb (`can't say`, `don't know`, `not sure`, `unclear`) co-occurring with `open tomorrow` in the same sentence.

```python
_HOURS_DISCLAIMER_PATTERNS = (
    re.compile(r"\b(?:can'?t|cannot)\s+say\b[^.!?]*\bopen\s+tomorrow\b", re.I),
    re.compile(r"\b(?:don'?t|do\s+not)\s+(?:know|have)\b[^.!?]*\bopen\s+tomorrow\b", re.I),
    re.compile(r"\b(?:not\s+sure|unclear)\b[^.!?]*\bopen\s+tomorrow\b", re.I),
)
```

### Step 2c — Tighten the rating scrub (per-sentence + per-value)

Replace the whole-text gate + whole-list wipe at `:123-126` with a per-sentence scrub: split the response into sentences, then for each captured rating value, scrub it ONLY IF it appears in a sentence that also matches one of the rating-disclaimer patterns. Keep `"rated above"` and `"stars in the catalog"` as anchors but only when co-occurring with a hedging phrase. Drop `"rating for"` as a standalone anchor — replace it with a tighter pattern requiring the response to ALSO contain `"don't have"` / `"no rating"` / `"not in the catalog"` in the same sentence.

```python
_RATING_DISCLAIMER_PATTERNS = (
    re.compile(
        r"\b(?:don'?t|do\s+not)\s+have\b[^.!?]*\brating\s+for\b",
        re.I,
    ),
    re.compile(
        r"\bno\s+rating\b[^.!?]*\b(?:for|on|available)\b",
        re.I,
    ),
    re.compile(
        r"\bnot\s+in\s+(?:the\s+)?catalog\b[^.!?]*\brating\s+for\b",
        re.I,
    ),
    re.compile(r"\bno\s+\w+(?:\s+\w+){0,4}\s+rated\s+above\b", re.I),
    re.compile(r"\b\d\s+stars?\s+in\s+the\s+catalog\b", re.I),
)
```

### Step 2d — Rewrite `_sanitize_typed_facts`

Replace the body at `:114-127` with:

```python
def _sanitize_typed_facts(text: str, facts: dict[str, list[str]]) -> dict[str, list[str]]:
    """Drop template-echo probes that are not business-confab signals.

    Phase 7.5.4: per-sentence scrubs anchored on template-disclaimer shapes.
    User-query echoes ("the rating for X is N.N stars", "X is open tomorrow at
    8am") are NOT scrubbed — only sentences that ALSO match a disclaimer
    pattern have their typed-fact values dropped.
    """
    out = {k: list(v) for k, v in facts.items()}
    sentences = re.split(r"(?<=[.!?])\s+", text or "")

    if out.get("hours"):
        kept_hours: list[str] = []
        for h in out["hours"]:
            in_disclaimer = False
            for s in sentences:
                if h in s and any(p.search(s) for p in _HOURS_DISCLAIMER_PATTERNS):
                    in_disclaimer = True
                    break
            if not in_disclaimer:
                kept_hours.append(h)
        out["hours"] = kept_hours

    if out.get("rating"):
        kept_rating: list[str] = []
        for r in out["rating"]:
            in_disclaimer = False
            for s in sentences:
                if r in s and any(p.search(s) for p in _RATING_DISCLAIMER_PATTERNS):
                    in_disclaimer = True
                    break
            if not in_disclaimer:
                kept_rating.append(r)
        out["rating"] = kept_rating

    return out
```

### Ordering invariant

- `_typed_fact_probes` already calls `_sanitize_typed_facts` after raw regex extraction — the call site at `:142` is unchanged.
- Sentence splitting MUST happen at the start of `_sanitize_typed_facts` so both hours and rating scrubs share the same sentence boundaries.
- The per-value `if r in s` check uses `in` (substring) deliberately — the rating regex captures e.g. `"4.7 stars"`, and the sentence text contains that string verbatim. False-positive risk is acceptable here (a one-letter overlap won't cause spurious scrubbing because the regex value is multi-char).

### Regression risk (low-medium)

- The hours disclaimer patterns require BOTH a hedging verb AND `open tomorrow` in the same sentence. q05/q06's gap-template phrasings include both. Verify in §5.
- The rating disclaimer patterns retain `"rated above"` / `"stars in the catalog"` shapes for q30. Verify q30 still PASS.
- The URL regex requires `golakehavasu.com` as host-or-subdomain and `/contribute` as a path component. q26's gap-template emits `https://www.golakehavasu.com/contribute` — both anchors fire → URL scrubbed. Verify q26 still PASS.
- If any of q05 / q06 / q26 / q30 regress to `passed=False` after the fix, the new disclaimer patterns are too tight — re-read §2b / §2c and widen the regex (e.g. add a missing hedging-verb synonym) until they pass while q25-exploit test still passes.

---

## §3 Red-test prep (BEFORE applying the fix)

Confirm the baseline is red, then author tests that FAIL pre-fix and PASS post-fix. Append all new tests to `tests/test_halt3_validator_hardening.py` (the Phase 7.5.2 file). **Do NOT modify the existing tests in that file** — append only.

**Step 3.1 — Confirm the q25 rating-scrub exploit reproduces at HEAD:**

This is the load-bearing RED baseline for this lane. The §0 check #7 already runs it; re-confirm via pytest collection that the test will be authored to assert the opposite of the current behavior:

```powershell
.\.venv\Scripts\python.exe -c "
from app.chat.halt3_validator import _typed_fact_probes
text = 'The rating for Mudshark Brewery is 4.7 stars based on 200+ reviews.'
facts = _typed_fact_probes(text)
assert facts.get('rating') == [], f'Pre-fix expected wipe, got {facts.get(\"rating\")!r}'
print('RED baseline confirmed: current scrub wipes rating list on q25 user-echo')
"
```

If this prints `RED baseline confirmed`, proceed with §3.2. If the assertion fails, the scrub has already been tightened — HALT and report.

**Step 3.2 — Append unit tests to `tests/test_halt3_validator_hardening.py`**

Add a new section at the end of the file:

```python
# ---------------------------------------------------------------------------
# Phase 7.5.4 — template-echo scrub tightening (watch item #2)
# ---------------------------------------------------------------------------


def test_rating_scrub_does_not_wipe_when_user_echo_only(db: Session) -> None:
    """q25-shape exploit: response echoes 'the rating for X is N.N stars' with NO
    template-disclaimer phrasing. Pre-fix: rating list wiped → confab undetected.
    Post-fix: rating value retained → if not in catalog, confab flagged."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "The rating for Mudshark Brewery is 4.7 stars based on 200+ reviews."
    facts = _typed_fact_probes(response)
    assert facts.get("rating") == ["4.7 stars"], (
        f"Expected rating value retained (no template-disclaimer in sentence), "
        f"got {facts.get('rating')!r}. Phase 7.5.4 tightening missing."
    )
    # End-to-end: if catalog rating for Mudshark differs, confab rate should be 1.0.
    rate = _confabulation_rate(response, db, query="what's the rating for Mudshark Brewery")
    # If Mudshark's actual catalog rating is e.g. 4.5, asserted 4.7 → mismatch → 1.0.
    # If catalog rating happens to be 4.7, confab is correctly NOT flagged (0.0).
    # Either is acceptable; the load-bearing assertion is that the value was NOT
    # silently scrubbed.
    assert rate in (0.0, 1.0), f"Expected definitive 0.0 or 1.0, got {rate}"


def test_hours_scrub_does_not_wipe_when_user_echo_only(db: Session) -> None:
    """Hours analogue: response asserts 'X is open tomorrow at 8am' with NO hedging.
    Pre-fix: hours probe wiped → confab undetected. Post-fix: retained → flagged."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "Heat Hotel is open tomorrow Mon 8am to 5pm at the marina."
    facts = _typed_fact_probes(response)
    assert facts.get("hours"), (
        f"Expected hours probe retained (no hedging-verb in sentence), got "
        f"{facts.get('hours')!r}. Hours scrub still too loose."
    )


def test_url_scrub_remains_for_legitimate_template_lines(db: Session) -> None:
    """Positive regression: gap-template URLs (golakehavasu.com / /contribute as
    path component) are still scrubbed. Don't over-tighten."""
    from app.chat.halt3_validator import _typed_fact_probes

    # Template emission from unified_router gap path:
    # NOTE: URLs intentionally end with `/` (not sentence period) because
    # `_URL_RE = https?://\S+` greedily captures trailing punctuation;
    # a trailing `.` would defeat the `[/?#]|$` boundary anchor on the
    # `/contribute` regex. Lane O audit caught this pre-dispatch.
    response = (
        "I don't have that one in the catalog. Try https://www.golakehavasu.com/ "
        "or share a Google Business page at https://example.com/contribute/ for more info."
    )
    facts = _typed_fact_probes(response)
    # Both URLs are platform-marker matches → scrubbed from the url list.
    assert facts.get("url") == [], (
        f"Expected platform URLs scrubbed, got {facts.get('url')!r}. "
        f"Phase 7.5.4 over-tightened the URL regex."
    )


def test_url_scrub_does_not_match_adversarial_substring(db: Session) -> None:
    """Negative: adversarial URL embedding the platform domain as a query param
    must NOT be scrubbed (it is a confab signal)."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "Check https://evil.example.com?ref=golakehavasu.com for the address."
    facts = _typed_fact_probes(response)
    assert facts.get("url") == ["https://evil.example.com?ref=golakehavasu.com"], (
        f"Expected adversarial URL retained, got {facts.get('url')!r}. "
        f"URL regex still too loose."
    )


def test_rating_scrub_still_fires_for_legitimate_disclaimer(db: Session) -> None:
    """Positive regression: q30-shape phrasing 'no X rated above 4 stars' is
    still scrubbed (template-disclaimer; not a confab signal)."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "I don't have any restaurants rated above 4 stars in the catalog."
    facts = _typed_fact_probes(response)
    assert facts.get("rating") == [], (
        f"Expected rating scrubbed inside template disclaimer, got "
        f"{facts.get('rating')!r}. Phase 7.5.4 over-tightened."
    )


def test_hours_scrub_still_fires_for_legitimate_disclaimer(db: Session) -> None:
    """Positive regression: q05/q06-shape phrasing "can't say if X is open
    tomorrow" is still scrubbed."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "I can't say if Mudshark is open tomorrow Mon 8am — try their website."
    facts = _typed_fact_probes(response)
    # Hours probe captured the 'Mon 8am' but the sentence has 'can't say ... open
    # tomorrow' → scrubbed.
    assert facts.get("hours") == [], (
        f"Expected hours scrubbed inside template disclaimer, got "
        f"{facts.get('hours')!r}. Phase 7.5.4 over-tightened."
    )


def test_rating_scrub_per_sentence_keeps_unrelated_value(db: Session) -> None:
    """Multi-sentence response: disclaimer in one sentence, confab in another.
    Per-sentence scrub keeps the confab value (only the disclaimer-sentence value
    is dropped). Verifies the per-sentence scope, not whole-list wipe."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = (
        "I don't have a rating for Imaginary Bistro in the catalog. "
        "But Heat Hotel has a 4.5 stars rating from regulars."
    )
    facts = _typed_fact_probes(response)
    # Both values were captured by _RATING_RE; the first sentence is a disclaimer
    # but contains no rating value (the regex needs '\b[1-5](?:\.\d)? stars'). The
    # second sentence has '4.5 stars' and is NOT a disclaimer → retained.
    assert "4.5 stars" in facts.get("rating", []), (
        f"Expected '4.5 stars' retained (non-disclaimer sentence), got "
        f"{facts.get('rating')!r}. Per-sentence scrub broken."
    )
```

Run BEFORE applying §4:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -k "rating_scrub or hours_scrub or url_scrub" -xvs
```

Expected pre-fix:
- `test_rating_scrub_does_not_wipe_when_user_echo_only` — **FAIL** (rating list wiped to `[]` by current whole-text gate).
- `test_hours_scrub_does_not_wipe_when_user_echo_only` — **FAIL** (hours probe scrubbed because `open\s+tomorrow` matches).
- `test_url_scrub_remains_for_legitimate_template_lines` — **PASS** (legitimate URLs already scrubbed by current substring match).
- `test_url_scrub_does_not_match_adversarial_substring` — **FAIL** (current substring match scrubs `?ref=golakehavasu.com` adversarially).
- `test_rating_scrub_still_fires_for_legitimate_disclaimer` — **PASS** (current scrub fires on `"rated above"` substring).
- `test_hours_scrub_still_fires_for_legitimate_disclaimer` — **PASS** (current scrub fires on `open\s+tomorrow`).
- `test_rating_scrub_per_sentence_keeps_unrelated_value` — **FAIL** (current whole-list wipe drops `"4.5 stars"` too because `"rating for"` appears in the first sentence).

Three of the seven tests should FAIL pre-fix. If the FAIL/PASS split differs, HALT — the baseline has shifted.

---

## §4 Apply the fix

Edit `app/chat/halt3_validator.py` per §2 (steps 2a + 2b + 2c + 2d).

**Step 4.1 — Replace `_PLATFORM_URL_MARKERS` + `_is_platform_url`**

At the line where `_PLATFORM_URL_MARKERS = (...)` is defined (verified at line ~50 in §0 check #3 — use the actual line number), remove the tuple constant AND the existing `_is_platform_url` body. Replace with the §2a `_PLATFORM_URL_RE` regex + tightened `_is_platform_url`.

**Step 4.2 — Add the disclaimer pattern tuples**

Above `_sanitize_typed_facts` (just before the existing definition at line ~114), insert the two new pattern-tuple constants per §2b and §2c (`_HOURS_DISCLAIMER_PATTERNS`, `_RATING_DISCLAIMER_PATTERNS`).

**Step 4.3 — Rewrite `_sanitize_typed_facts`**

Replace the body at the existing definition (lines ~114-127 — verified in §0 check #3) with the §2d per-sentence implementation.

**Step 4.4 — Verify no other call sites changed**

The consumer `_typed_fact_probes` at `:130-142` calls `_sanitize_typed_facts(s, raw)` — that signature is preserved. The other consumer `_is_platform_url` is called only inside `_typed_fact_probes` line 133 — that signature is also preserved.

After the edit:

```powershell
# Unit tests now green:
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -k "rating_scrub or hours_scrub or url_scrub" -xvs

# Spot-check the q25-shape exploit is closed:
.\.venv\Scripts\python.exe -c "
from app.chat.halt3_validator import _typed_fact_probes
text = 'The rating for Mudshark Brewery is 4.7 stars based on 200+ reviews.'
facts = _typed_fact_probes(text)
assert facts.get('rating') == ['4.7 stars'], f'Expected retained, got {facts!r}'
print('q25 exploit closed: rating value retained on user-echo')
"
```

All seven Phase 7.5.4 tests should PASS.

---

## §5 Acceptance verification

Run all six checks. ALL must pass before §11.

```powershell
# 1. HALT 3 validator still 30/30 all-pass (load-bearing — the scrub tightening must
#    not break the legitimate template-disclaimer cases for q05 / q06 / q26 / q30):
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
# Expected: cited_coverage=100% missing_confab_max=0.00 all_passed=True

# 2. q25 specifically — pre-existing behavior preserved on the legitimate gap-template
#    response shape (gap template fires when entity is not in catalog → disclosure_path
#    should remain "cited" or "i_dont_know", NEVER "uncited"):
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -q

# 3. All 7 new Phase 7.5.4 tests green:
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -k "rating_scrub or hours_scrub or url_scrub" -xvs

# 4. Full pytest suite — count should grow by 7 from new tests:
.\.venv\Scripts\python.exe -m pytest -q

# 5. Phase 7.5.2 regression — existing G1-G5 + F2/F3 tests still PASS:
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -q

# 6. Ruff clean on touched files:
.\.venv\Scripts\python.exe -m ruff check `
    app/chat/halt3_validator.py `
    tests/test_halt3_validator_hardening.py
```

**If check #1 fails (any of the 30 eval-set rows regresses):**
- Identify which row regressed and read its full response in the validator output.
- If a legitimate q05/q06 hours-disclaimer or q26 URL or q30 rating-disclaimer is now flagged as confab, the new disclaimer patterns are too tight. Widen the regex (e.g. add a missing hedging-verb synonym, or relax the path-component anchor for `/contribute`) until both q25 exploit test AND the regressed eval-set row pass.
- Do NOT edit `halt3_eval_set.yaml` (it is OUT of scope per §8). The scrub patterns must accommodate the existing eval-set responses.

**If any check fails for other reasons, HALT and report.** Do not proceed to §11.

---

## §6 Existing regression check

The full validator + chat surface must remain green — Phase 7.5.4 must not break Phase 7.5.1 / 7.5.2 / 7.6 / 7.7 / 8a routing wiring.

```powershell
# Full Phase 7.5.2 hardening test surface:
.\.venv\Scripts\python.exe -m pytest tests/test_halt3_validator_hardening.py -q

# Phase 7.5.1 q07 + q22 integration tests still PASS (regression check on routing):
.\.venv\Scripts\python.exe -m pytest -xvs `
    tests/test_phase38_gap_and_hours.py::test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape `
    tests/test_phase7_halt3_validation.py::test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3

# Phase 7.6 shortcut regression (if 7.6 is in tree):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_business_shortcut.py -q

# Phase 7.7 honest-empty-listing regression (if 7.7 is in tree):
.\.venv\Scripts\python.exe -m pytest tests/test_tier2_handler.py -q

# HALT 3 validator full run:
.\.venv\Scripts\python.exe -m app.chat.halt3_validator
```

All must PASS. If 7.5.3 / 7.7 / 8a shipped after 7.6 and the test count differs, that is fine — just record the actual baseline and the +7 delta from this lane.

---

## §7 Self-correction policy (§13 carry from 7.5.2 / 7.6 / 7.7)

If during edits you discover a substantive deviation from the wrapper's design:

- **Small in-scope deviations** (rewording a log message; adjusting a disclaimer regex to add a missing hedging-verb synonym; tightening a per-value `if r in s` check to use full-word boundaries) — proceed with judgment; note in §11.
- **Substantive deviations** (changing the consumer `_typed_fact_probes`; touching `halt3_eval_set.yaml`; modifying `_confabulation_rate` body content scoring; changing `_classify_disclosure_path`; co-locating new helpers in a different module; adding a new typed-fact regex) — STOP and report. Cowork primary will decide.

---

## §8 File scope (gotcha #18 disjointness)

**Modified files (closed set):**
- `app/chat/halt3_validator.py` — replace `_PLATFORM_URL_MARKERS` tuple + `_is_platform_url` (lines ~50, ~109-111) with tightened regex; add `_HOURS_DISCLAIMER_PATTERNS` + `_RATING_DISCLAIMER_PATTERNS` pattern tuples above `_sanitize_typed_facts`; rewrite `_sanitize_typed_facts` body (lines ~114-127) with per-sentence scrub. Verify exact line numbers via §0 check #3 at boot.

**Modified test files:**
- `tests/test_halt3_validator_hardening.py` — APPEND-ONLY: seven new unit tests per §3.2 at end of file. Do NOT modify any existing tests from Phase 7.5.2.

**Do NOT touch:**
- `app/chat/halt3_eval_set.yaml` — Phase 7.5.2 surface. The Lane G audit confirmed no YAML changes are needed for this lane (q25 expectations are already correct; the bug is in the validator, not the eval set). Watch item #1 (G4 list-promiscuity on q02 + q27 multi-tier rows) is explicitly OUT of scope.
- `app/chat/tier2_handler.py` — Phase 7.6 + 7.7 surface.
- `app/chat/tier2_business_shortcut.py` — Phase 7.6 surface.
- `app/chat/unified_router.py` — Phase 7.5.1 + 7.5.3 surface.
- `app/chat/entity_intent.py` — Phase 7.5.3 surface.
- `app/chat/tier2_parser.py` / `prompts/tier2_parser.txt` — Phase 7.6 surface.
- `app/chat/tier2_db_query.py` — Phase 7.5.x / 7.6 surface.
- `app/conditions/*` / `app/alerts/*` / `app/core/ranking.py` — Phase 8a surface.
- `tests/test_tier2_handler.py` — Phase 7.7 surface.
- `tests/test_tier2_business_shortcut.py` — Phase 7.6 surface.
- `tests/test_phase7_halt3_validation.py` — Phase 7.5.2 surface. Append-only if absolutely needed for a regression check; default is do NOT touch.
- `tests/test_phase38_gap_and_hours.py` — Phase 7.5.1 surface.
- `tests/test_gap_template_contribute_link.py` — Phase 7.5.3 surface.
- Phase 6.5 / Phase 8 / Phase 9 surfaces.
- Any other dispatch wrapper under `outputs/`.

**Parallel-eligibility:**
- Zero overlap with Phase 7.5.3 (`entity_intent.py` + `unified_router.py` + gap-template tests + `test_phase7_halt3_validation.py`).
- Zero overlap with Phase 7.6 (`tier2_business_shortcut.py`).
- Zero overlap with Phase 7.7 (`tier2_handler.py`).
- Zero overlap with Phase 8a (`app/conditions/*` + `app/alerts/*`).
- Parallel-eligible with all queued lanes. If multiple lanes ship before this one is dispatched, the only consequence is a higher pytest baseline — record actual.

---

## §9 What NOT to do

- **Do NOT git-commit.** Stop at §11. The operator commits after reviewing your diff.
- **Do NOT touch watch item #1 (G4 list-promiscuity).** The design memo §4 + Lane G audit recommended dropping it from this lane. No `tier_strict` field on `EvalQuerySpec`, no YAML changes to q02 / q27, no changes to `_tier_matches`. **This lane is watch-item-#2 only.**
- **Do NOT add new template-echo scrubs.** Phase 7.5.4 ONLY tightens the three existing scrubs (URL, hours, rating). If during testing you find another typed-fact class (phone, address, email) has an exploitable user-echo surface, surface it in §11.4 — do NOT add a new scrub.
- **Do NOT change `_typed_fact_probes`.** Only its upstream scrub feeders (`_is_platform_url` + `_sanitize_typed_facts`) change. The regex list at `:36-47` is untouched.
- **Do NOT change `_confabulation_rate` or `_classify_disclosure_path`.** Those are the consumers — they get cleaner facts after the scrub fix; their bodies don't need to change.
- **Do NOT add the `_scrub_audit` helper** from the design memo §2 (the soft-fail escalation idea). The Lane G audit determined the per-sentence tightening alone is sufficient. The `_scrub_audit` idea was a belt-and-suspenders alternative; this lane uses the belt only.
- **Do NOT broaden the URL regex** to scrub all `*.golakehavasu.com` subdomains arbitrarily — anchor it on host-or-subdomain-plus-TLD as per §2a.
- **Do NOT edit `halt3_eval_set.yaml`** even if a row's expected text fragment seems to misalign with the new scrub behavior. Surface the mismatch in §11.4 — the operator decides whether to revise the eval set in a later phase.
- **Do NOT add Anthropic calls.** The validator must remain pure-Python deterministic.
- **Do NOT add an alembic migration.** No schema change.

---

## §10 If you find a substantive deviation

Per the project's working agreement Rule 4 (deviation discipline):

- Small in-scope deviations (e.g., adding a missing hedging-verb synonym to a disclaimer pattern; tightening a regex word-boundary anchor; adjusting a log message) — proceed with judgment; note in §11.
- Substantive deviations (touching `halt3_eval_set.yaml`; adding a new typed-fact regex; changing `_typed_fact_probes`; adding the `_scrub_audit` helper; modifying `_confabulation_rate` / `_classify_disclosure_path` bodies; co-locating helpers in a different module; revisiting watch item #1) — STOP and report. Cowork primary will decide.

---

## §11 Final report (you MUST emit this; do not commit)

Emit a structured report covering:

### §11.1 Diffs
- Full unified diff of all modified files (use `git diff` output).
- Confirm no files outside §8 scope were touched.

### §11.2 Acceptance checks
For each check in §5, paste the actual output line(s). Confirm PASS for each. Record pytest collected count delta vs §0 baseline (expected +7).

### §11.3 Per-fix verification

| Scrub | Red test (pre-fix expected FAIL) | Green test (post-fix expected PASS) | Status |
|---|---|---|---|
| Rating user-echo exploit (load-bearing) | `test_rating_scrub_does_not_wipe_when_user_echo_only` | Same test post-fix | ☐ |
| Hours user-echo exploit | `test_hours_scrub_does_not_wipe_when_user_echo_only` | Same test post-fix | ☐ |
| URL adversarial substring | `test_url_scrub_does_not_match_adversarial_substring` | Same test post-fix | ☐ |
| URL legitimate template (positive regression) | `test_url_scrub_remains_for_legitimate_template_lines` | Pre+post PASS | ☐ |
| Rating legitimate disclaimer (positive regression) | `test_rating_scrub_still_fires_for_legitimate_disclaimer` | Pre+post PASS | ☐ |
| Hours legitimate disclaimer (positive regression) | `test_hours_scrub_still_fires_for_legitimate_disclaimer` | Pre+post PASS | ☐ |
| Per-sentence scope (vs whole-list wipe) | `test_rating_scrub_per_sentence_keeps_unrelated_value` | Same test post-fix | ☐ |
| Validator | `python -m app.chat.halt3_validator` 30/30 all-pass | 30/30 PASS | ☐ |
| 7.5.1 regression | `test_q22_fake_hotel_misroutes...` + `test_q07_tell_me_about_fake_entity...` | All PASS | ☐ |
| 7.5.2 regression | full `tests/test_halt3_validator_hardening.py` | All PASS | ☐ |

### §11.4 Substantive findings
- Did all 30 HALT 3 eval-set rows still PASS after the scrub tightening? If any regressed, which one, and how did you reconcile (widen the disclaimer pattern OR document the mismatch for operator review)?
- Did the new `_PLATFORM_URL_RE` regex correctly anchor `golakehavasu.com` as a hostname AND `/contribute` as a path component? Any edge cases where the regex falls short (e.g. URL with explicit port, IPv6 host)?
- Did the per-sentence sentence splitter (`re.split(r"(?<=[.!?])\s+", text)`) handle multi-sentence responses correctly? Any edge cases (e.g. abbreviations like `"Mr. Smith"` causing false splits)?
- Did the rating disclaimer patterns cover all five expected template shapes from `unified_router.py`'s gap path? Surface any gap-template phrasing not covered by the patterns.
- Any other typed-fact class (phone / address / email) where a user-echo exploit looks plausible? Surface but do NOT fix (out of scope for this lane).
- Any bugs in existing code noticed but not fixed (out of scope)?
- Anything the wrapper didn't anticipate.

### §11.5 File scope confirmation
Paste output of `git status --short` confirming only §8-listed files modified.

### §11.6 Recommended commit subject
Suggest a commit subject line. Default:

```
feat(phase7.5.4): tighten HALT 3 validator template-echo scrubs to per-sentence disclaimer anchors -- closes q25 rating-scrub exploit (user-query echo "rating for X is N.N stars" no longer wipes rating list); URL regex anchored to host/path-segment; hours scrub requires hedging-verb co-occurrence; +7 unit tests; watch item #1 (G4 list-promiscuity) deferred per Lane G recommendation
```

### §11.7 Open carries
- Watch item #1 (G4 list-promiscuity on q02 + q27 multi-tier `expected_tier` rows) — deferred per design memo §4 + Lane G recommendation. No prod failure traces to it; the proposed `tier_strict: false` flag is documentation-of-flake rather than behavioral tightening. Revisit in V1.5 only if a real regression motivates it.
- If a later phase makes one of the 8 list-bearing eval-set rows (q02, q10, q12, q14, q17, q19, q27, q30) deterministic (e.g. catalog seeding makes q02 barber consistently tier-2), tighten the list to single-tier at that phase's boundary.
- If `_scrub_audit` (the soft-fail escalation idea from design memo §2) becomes worth implementing — gate on a future scrub-suspect surface, not this lane.

### §11.8 Optional operator notes
Reserved for operator to fill in post-deploy if smoke results land before Cursor session closes.

---

End of wrapper. Now go.
