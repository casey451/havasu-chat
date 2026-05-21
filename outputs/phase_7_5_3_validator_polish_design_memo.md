# Phase 7.5.3 design memo — F-gap validator/eval polish (F1 + F4 + F5)

> **What this is:** scoping memo for Phase 7.5.3, the third (and lowest-priority) lane carved out of the Phase 7.5 production-divergence post-mortem. After 7.5.1 shipped the routing fixes for q07/q22/q03, after 7.5.2 hardens the validator's critical Goodhart gaps (G1-G5 + F3), and after 7.6 closes the residual tier-2 LLM-parser divergence on q03 — three remaining low-severity findings (F1, F4, F5) need a polish pass. This memo scopes them; it does NOT author the dispatch wrapper.
>
> **Authored by:** Cowork primary via sub-agent, 2026-05-20, post-Phase-7.5.2-dispatch.
>
> **Companion docs:**
> - `outputs/phase_7_5_prod_divergence_investigation.md` (post-mortem; F1/F4/F5 enumerated in §4 "F1, F4, F5-F7 (LOW)" and again in §9 V1.5 carries)
> - `outputs/cursor_dispatch_prompt_phase_7_5_2.md` (validator hardening — queued/dispatched; closes G1-G5 + F3; does NOT touch F1/F4/F5)
> - `outputs/phase_7_6_tier2_llm_parser_design_memo.md` (q03 residual fix scoping memo)
> - `outputs/cursor_dispatch_prompt_phase_7_6.md` (q03 dispatch wrapper; touches `tier2_business_shortcut.py` only)
>
> **Status:** design-only; no Cursor wrapper authored yet. Use this memo as input when authoring the Phase 7.5.3 dispatch wrapper.

---

## §1 Root cause hypothesis (per gap)

### F1 — `query_mentions_fake_entity_marker` is a hand-written whitelist

**Location:** `app/chat/entity_intent.py:89-93` (regex constant), `:141-143` (function).

**Code (current):**
```python
_FAKE_ENTITY_MARKER_RE = re.compile(
    r"\b(?:zzz|fake|fabricated|imaginary|nonexistent|totally\s+fake|"
    r"random\s+place|missing|404|99999|888|777|555|xyz)\b",
    re.IGNORECASE,
)
```

**What's wrong:** the regex is a literal allow-list of the markers our own eval-set queries use to flag fake entities. Real fabricated business names produced by real users (e.g. `"Joe's Lake Tavern"` when no such tavern exists, or `"Sunset Pizza Co"` when no such pizza place exists) contain none of these tokens. Any non-cataloged business name that doesn't happen to include `xyz`, a triple-digit `555`, `fake`, etc. slips past the marker probe and proceeds through the normal entity-resolution path — where it can then trigger the same near-match fail-open / tier-3 confab paths Phase 7.5.1 closed for marker-bearing queries but did NOT close for unmarked fabrications.

**Symptom in production:** an adversarial or naive user types `Tell me about Joe's Lake Tavern`. The marker probe at `unified_router.py:288` and `:655` returns False. The about-gate (`_unknown_entity_about_gate`) then runs the matcher + near-match probes; if either returns a real entity (Heat Hotel-style near-match), control proceeds and we're back in the q22-class fail-open shape — except this time the validator at 7.5.2 will catch the *citation* failure but won't have prevented the *routing* misroute that produced it. In other words: F1 is a defense-in-depth gap that only manifests on real-world inputs the eval set has never seen.

**Confidence:** medium-high that the gap exists exactly as described. Medium-low that it is currently producing user-visible failures on prod — we have no operator-reported example of a non-marker fake entity slipping through, and the §3 routing fixes in 7.5.1 are upstream of marker detection in most paths. **This is genuinely polish, not a hot fix.**

### F4 — gap-template tests assert substring presence, not full template

**Location:** `tests/test_gap_template_contribute_link.py:35,45,55` (3 sites) + `tests/test_phase38_gap_and_hours.py:90,143,246,310` (4 sites). **7 sites total** (audit-corrected from initial count of 6 — line 310 was missed in the first pass).

**Code (current pattern):**
```python
assert "/contribute" in r.response
```

**What's wrong:** the assertion fires on ANY response that contains the substring `/contribute` anywhere. A future regression that emits a malformed gap template (`"sorry idk — /contribute"`, or a gap-template body fragment concatenated into a tier-3 LLM freeform response, or a contribute mention inside a confabulation like `"call (928) 555-0199 or use /contribute"`) trivially passes the assertion. The test is round-trip plumbing verification, not template-shape verification — same disease as F3 just lighter.

**Symptom in production:** none directly. The risk is regression-test rot — a future refactor that breaks the gap-template body structure won't be caught by these tests because they don't assert the structure, only one substring fragment. F4 is a test-quality issue, not a routing or validator issue.

**Confidence:** high that the over-loose pattern exists at the cited lines. Low confidence that it's currently masking any specific bug — these tests have been green through 7.5 / 7.5.1, and no production failure traces back to a malformed gap template. F4 is hygiene.

### F5 — about-gate patterns anchored at start-of-string only

**Location:** `app/chat/unified_router.py:113-119` (`_ABOUT_GATE_STRICT_PATTERNS`), `:122-125` (`_WHAT_IS_ENTITY_RE`).

**Code (current):**
```python
_ABOUT_GATE_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*tell\s+me\s+(?:more\s+)?about\b", re.I),
    re.compile(r"^\s*(?:can\s+you\s+)?describe\b", re.I),
    re.compile(r"^\s*who(?:'s|\s+is)\b", re.I),
    re.compile(r"^\s*(?:any\s+)?info(?:rmation)?\s+(?:on|about)\b", re.I),
    re.compile(r"^\s*what(?:'s|\s+is)\s+\S+\s+like\b", re.I),
)

_WHAT_IS_ENTITY_RE = re.compile(
    r"^\s*what(?:'s|\s+is)\s+(?!the\s+weather|the\s+time|the\s+date|today)",
    re.I,
)
```

**What's wrong:** every pattern has a `^\s*` start-of-string anchor. A query like `"Hey, tell me about Totally Fake Business XYZ 404"` or `"Quick question — describe Heat Hotel"` or `"OK so what is Sunset Pizza Co"` will fail every pattern despite being semantically identical to the bare `"tell me about X"` shape. The conversational lead-in clause (`"Hey, "`, `"Quick question — "`, `"OK so "`) defeats the anchor.

**Symptom in production:** users who write conversationally (rather than terse search-style queries) bypass the about-gate and fall through to tier-3 LLM. For a fake or unrecognized entity, that's the q07 prod-confab shape *exactly* — just with a lead-in clause. Phase 7.5.1 closed q07's bare shape; F5 is the same bug surface with a lead-in.

**Confidence:** high that the anchor restricts the gate to bare shapes. Medium-low that real users frequently produce conversational lead-ins on this product (Lake Havasu chat is search-style, not chatty by design) — but the post-mortem flagged it as a known gap and it's exactly the shape that would slip an adversarial probe. **Worth closing as a defense-in-depth move.**

---

## §2 Proposed fix (per gap)

### F1 — replace whitelist with generalized fake-entity heuristic

**Recommend Path A — augment, do not replace.** Keep the existing whitelist as a fast-path for known eval markers; add a structural heuristic that catches unmarked fabrications.

**Touch points:**

- `app/chat/entity_intent.py:89-93` (`_FAKE_ENTITY_MARKER_RE`) — keep verbatim.
- `app/chat/entity_intent.py:141` (`query_mentions_fake_entity_marker`, currently a one-line body extending to :143) — extend to call a new helper `_looks_structurally_fake(query)` when the whitelist regex misses.
- **`app/chat/unified_router.py:282-302` (`_unknown_entity_about_gate`) — REORDER REQUIRED.** The marker probe at line 288 currently runs BEFORE `match_entity` (line 295) and `find_near_match` (line 297). The F1 consonant-run heuristic would flag `mdshrkbrwry` as structurally fake and short-circuit before rapidfuzz at `entity_intent.py:245-257` ever fires — regressing the Mudshark Brewery typo case. The wrapper must explicitly scope: move `query_mentions_fake_entity_marker` call to run AFTER both `match_entity` and `find_near_match` return None. Same change at the second call site (`unified_router.py:651-655`).
- New helper `_looks_structurally_fake(query) -> bool` — returns True when the proper-noun span in the query contains:
  - mixed alphanumeric tokens with high digit density (e.g. `Business 4042`, `XYZ 555`), OR
  - 3+ consecutive consonants in a non-dictionary token (e.g. `zzznonexistent`, `mdshrk` — though note `mdshrkbrwry` is a real typo for Mudshark Brewery, so the rapidfuzz escape hatch in `near_match_subject_overlaps` must still take precedence), OR
  - token sequences with no entries in a small Lake-Havasu-business-token-frequency set (gathered offline from the catalog).

  Skip the helper entirely on short queries (< 5 tokens) to avoid false-positives on legitimate short entity names like `"Heat Hotel hours"`.

**Code sketch:**
```python
_HIGH_DIGIT_DENSITY_RE = re.compile(r"\b[A-Za-z]+\s*\d{3,}\b")
_CONSONANT_RUN_RE = re.compile(r"\b[bcdfghjklmnpqrstvwxyz]{4,}", re.I)

def _looks_structurally_fake(query: str) -> bool:
    q = (query or "").strip()
    if len(q.split()) < 5:
        return False
    if _HIGH_DIGIT_DENSITY_RE.search(q):
        return True
    if _CONSONANT_RUN_RE.search(q):
        return True
    return False

def query_mentions_fake_entity_marker(query: str) -> bool:
    if _FAKE_ENTITY_MARKER_RE.search(query or ""):
        return True
    return _looks_structurally_fake(query or "")
```

**Rejected alternative:** full LLM-based fake-entity classifier. Rejected because it would re-introduce LLM-nondeterminism into the deterministic guard layer — exactly the failure mode 7.5.1 worked to remove. The heuristic above is pure regex + token logic; testable; reproducible.

**Tests:** add to `tests/test_entity_intent.py` (or wherever marker tests live — likely `tests/test_unified_router_q07.py` since the marker is consumed there):
- Positive: `query_mentions_fake_entity_marker("Tell me about Joe's 9999 Tavern")` returns True via digit-density.
- Positive: `query_mentions_fake_entity_marker("Tell me about zzznonexistent venue")` returns True via marker (existing path) AND would also fire via consonant-run.
- Negative regression: `query_mentions_fake_entity_marker("Tell me about Heat Hotel")` returns False — must not flag real entities.
- Negative regression: `query_mentions_fake_entity_marker("rating for Mudshark Brewery")` returns False — must not flag the typo-corrected real entity (or shorter-than-5-tokens skip handles this).
- Negative: `query_mentions_fake_entity_marker("hours")` returns False — short-query skip.

### F4 — tighten gap-template tests to assert full template body

**Touch points:**

- `tests/test_gap_template_contribute_link.py:35,45,55` — replace `assert "/contribute" in r.response` with full-template assertions (3 sites).
- `tests/test_phase38_gap_and_hours.py:90,143,246,310` — same treatment (4 sites).

**Code sketch:**
```python
# Before
assert "/contribute" in r.response

# After
from app.chat.unified_router import _UNKNOWN_ENTITY_GAP, _GAP_TEMPLATES_BY_SUBINTENT  # or whatever the per-sub-intent templates are named
assert r.response.strip() == _GAP_TEMPLATES_BY_SUBINTENT["DATE_LOOKUP"].strip()
# or, if exact-equality is too brittle:
expected_fragment = _GAP_TEMPLATES_BY_SUBINTENT["DATE_LOOKUP"]
assert expected_fragment in r.response
assert "/contribute" in r.response  # keep for clarity
assert r.tier_used == "gap_template"
```

The key shift: assert the response equals (or starts with) the actual template body, plus assert `tier_used == "gap_template"`. The `tier_used` check is the cheapest catch — any response that contains `/contribute` but is NOT actually the gap-template tier (e.g. a tier-3 LLM confab that mentions /contribute) fails.

**Rejected alternative:** snapshot tests against canonical template files. Rejected because the templates live as Python string literals inside `unified_router.py`; introducing a snapshot mechanism is heavier than just importing the constant and equality-checking.

**Tests:** these ARE the tests. The change is to existing assertions, not new test files. Confirm with a red-then-green: temporarily corrupt the template (e.g. drop the `/contribute` link from the constant) and verify the test fails; restore.

### F5 — allow lead-in clauses before about-gate patterns

**Touch points:**

- `app/chat/unified_router.py:113-119` (`_ABOUT_GATE_STRICT_PATTERNS`) — relax the anchor from `^\s*` to a lead-in-tolerant prefix.
- `app/chat/unified_router.py:122-125` (`_WHAT_IS_ENTITY_RE`) — same relaxation, preserving the activity/listing skip at `:127-133`.

**Recommend Path A — add an optional lead-in clause prefix.** Replace `^\s*` with `^\s*(?:[^,]{0,30}[,—-]\s*)?` (matches up to 30 chars of any non-comma followed by a comma/em-dash/dash, optionally — captures `"Hey, "`, `"Quick question — "`, `"OK so "` when "so" is followed by a comma/dash — though `"OK so what is X"` would need a different shape, see below).

**Code sketch:**
```python
# Before
re.compile(r"^\s*tell\s+me\s+(?:more\s+)?about\b", re.I),

# After
_LEAD_IN_PREFIX = r"^\s*(?:[a-z][a-z\s,'-]{0,40}[,—\-]\s+)?"
re.compile(_LEAD_IN_PREFIX + r"tell\s+me\s+(?:more\s+)?about\b", re.I),
```

Apply the same prefix to all five `_ABOUT_GATE_STRICT_PATTERNS` members and to `_WHAT_IS_ENTITY_RE`. The lead-in alternation should be cautious — the `[,—\-]\s+` punctuation anchor prevents over-matching mid-sentence drifts like `"the bar tell me about that place"` which would be a different (and weirder) shape.

**Rejected alternative:** drop the start-of-string anchor entirely and let `tell me about` fire anywhere in the query. Rejected because it pulls in false-positives: `"the description says 'tell me about your services' — is that legitimate?"` would wrongly enter the about-gate. The lead-in clause approach narrows the relaxation to a documented shape.

**Tests:** add to `tests/test_phase7_halt3_validation.py` or `tests/test_unified_router_q07.py`:
- Positive: `"Hey, tell me about Totally Fake Business XYZ 404"` enters the about-gate → returns `_UNKNOWN_ENTITY_GAP` template.
- Positive: `"Quick question — describe Heat Hotel"` enters the about-gate (then resolves to Heat Hotel and proceeds normally, NOT to the gap template — that's a different path).
- Negative regression: existing bare-shape tests still fire (no regression in `^\s*tell me about` paths).
- Negative: `"the description says 'tell me about your services'"` does NOT fire (mid-sentence drift; quotation marks defeat the lead-in prefix).

---

## §3 Effort estimate

- **F1:** S, ~50-90 LOC + ~6 unit tests. Heuristic itself is small; includes the call-order reorder in `_unknown_entity_about_gate` (`unified_router.py:282-302`) to preserve the Mudshark Brewery typo case + careful negative-regression tests against real catalog entity names. **~1-1.5 hour Cursor session.**
- **F4:** S, ~25-35 LOC of test diff (no production code changes). Mechanical — replace 7 assertion sites with a 2-3-line block each (3 in `test_gap_template_contribute_link.py` + 4 in `test_phase38_gap_and_hours.py`). **~30-40 min Cursor session.**
- **F5:** S, ~15 LOC of prod code + ~4 unit tests. Single regex prefix added to 5 patterns. **~45 min Cursor session.**

**Aggregate: M (~150 LOC + ~15 tests, ~2-3 hour Cursor session).** Genuinely a polish phase; not effort-comparable to 7.5.1 (~200 LOC + 12 tests, 4-6h session) or 7.5.2 (~300 LOC + 8 tests, 2-4h session).

---

## §4 Sequencing

**File-scope check (gotcha #18):**

- **Phase 7.5.2 touches:** `app/chat/halt3_validator.py`, `app/chat/halt3_eval_set.yaml`, validator-adjacent tests (`tests/test_phase7_halt3_validation.py`, new `tests/test_halt3_validator_hardening.py`).
- **Phase 7.6 touches:** `app/chat/tier2_business_shortcut.py`, `tests/test_tier2_business_shortcut.py`, optionally `tests/test_tier2_handler.py`.
- **Phase 7.5.3 touches:** `app/chat/entity_intent.py` (F1), `app/chat/unified_router.py` (F5), `tests/test_gap_template_contribute_link.py` + `tests/test_phase38_gap_and_hours.py` (F4), plus new positive-case tests in `tests/test_phase7_halt3_validation.py` (F5) which is also touched by 7.5.2.

**Overlap finding:** Phase 7.5.3 and Phase 7.5.2 both touch `tests/test_phase7_halt3_validation.py`. Phase 7.5.2 *extends* it with the new mocked-router adversarial test. Phase 7.5.3 would add F5 about-gate lead-in positive tests to the same file. **This is a soft conflict** — both phases would add new test functions to the same file, which is a routine merge case (no overlapping line ranges if 7.5.2 appends and 7.5.3 also appends) but not strictly disjoint.

**Phase 7.5.3 vs Phase 7.6:** zero overlap. 7.6 is `tier2_business_shortcut.py` only; 7.5.3 is `entity_intent.py` + `unified_router.py` + gap-template tests. Parallel-eligible.

**Recommendation:** **serialize 7.5.3 after 7.5.2 ships.** Two reasons:
1. The soft test-file overlap above is trivially resolved by ordering, and we lose nothing by waiting.
2. F5's "lead-in clause" addition to the about-gate is exactly the shape 7.5.2's q24-q30 adversarial probes are designed to catch. If we land 7.5.3 first, we risk regressing one of the 7.5.2 probe rows; landing 7.5.2 first means 7.5.3's regex changes get validated against the hardened validator immediately.

Phase 7.5.3 CAN run in parallel with Phase 7.6 (zero file overlap), so the practical recipe is: ship 7.5.2 → dispatch 7.5.3 and 7.6 concurrently → ship in either order.

---

## §5 Risks

### F1 risks

- **False-positive on a real entity with a numeric model in the name.** A future Lake Havasu business named e.g. `"Studio 7 Coffee"` or `"Route 95 Diner"` could fire `_HIGH_DIGIT_DENSITY_RE` and be wrongly classified as fake. Mitigation: the regex requires 3+ digits (`\d{3,}`) so single/double-digit business names are safe. Add a negative-regression test for the actual prod catalog's numeric-in-name rows (need to enumerate from prod catalog first).
- **Mudshark Brewery typo regression.** The `mdshrkbrwry` typo case must continue to route to Mudshark Brewery via rapidfuzz at `entity_intent.py:245-257` (post-7.5.1; line range corrected from initial `:158-164` cite). The F1 heuristic runs upstream and would mark `mdshrkbrwry` as structurally fake via consonant-run. **Mitigation requires an explicit call-order reorder in `_unknown_entity_about_gate` (`unified_router.py:282-302`)** — currently the marker probe at line 288 runs BEFORE `match_entity` (line 295) and `find_near_match` (line 297). Phase 7.5.3 wrapper must scope this reorder, not just verify the existing order.

### F4 risks

- **Brittle equality assertions.** If the gap-template body gets a copy edit (e.g. operator changes the contribute pitch wording), the equality assertion breaks for a non-bug. Mitigation: use `in` against the template constant rather than strict equality, plus assert `tier_used == "gap_template"`. The combination is robust to copy edits but rigid about structure.

### F5 risks

- **Lead-in regex over-matches and incorrectly enters the about-gate.** Mitigation: cap the lead-in span at 40 chars and require punctuation (`[,—\-]\s+`). The about-gate body then runs the matcher + near-match probes, so even an over-matched query gets sanity-checked against the catalog before the gap template fires. Worst case: a borderline query gets routed to the gap template instead of tier-3 — that's a *softer* failure mode than the q07 confab, not harder.
- **Regression on existing q07-shape tests.** Mitigation: red-then-green by running the full Phase 7.5.1 q07 test suite (`test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3` and friends) before and after.

**Aggregate worst case:** an over-corrected F1 wrongly flags a real entity in the prod catalog → user gets the `_UNKNOWN_ENTITY_GAP` template instead of the rating/hours/etc. for the real entity. That's a degraded-but-honest response, not a confabulation. Strict downgrade from the q22-class failure that motivated 7.5.1.

---

## §6 Files referenced

- `app/chat/entity_intent.py` lines 89-93 (`_FAKE_ENTITY_MARKER_RE`), 141 (`query_mentions_fake_entity_marker`, one-liner body extends to 143), 245-257 (rapidfuzz escape hatch in `near_match_subject_overlaps` — must not regress under F1; line range corrected from initial `:158-164` cite).
- `app/chat/unified_router.py` lines 113-119 (`_ABOUT_GATE_STRICT_PATTERNS`), 122-125 (`_WHAT_IS_ENTITY_RE`), 127-133 (`_ACTIVITY_OR_LISTING_SKIP_RE`), 136-142 (`_about_gate_query_eligible`), 265-301 (`_unknown_entity_about_gate` — F1 call-order reorder required at 282-302; marker check at line 288 must move below `match_entity` at 295 and `find_near_match` at 297), 651-655 (second `query_mentions_fake_entity_marker` call site, same reorder applies).
- `app/chat/halt3_validator.py` lines 21-31 (`_I_DONT_KNOW_RE` — context only; not touched by 7.5.3).
- `tests/test_gap_template_contribute_link.py` lines 28-55 (3 gap-template tests with substring assertion at 35/45/55).
- `tests/test_phase38_gap_and_hours.py` lines 90, 143, 246, 310 (4 `/contribute` substring assertions; line 283 has a `not in` negative assertion that should stay as-is).
- `tests/test_phase7_halt3_validation.py` line 42 (`"don't have that one in the catalog"` substring assertion — F4-adjacent; tightening optional, would bump F4 effort by ~5 LOC if folded into the lane).
- `outputs/phase_7_5_prod_divergence_investigation.md` §4 "F1, F4, F5-F7 (LOW)" (lines ~252-259) — original F-gap enumeration.
- `outputs/phase_7_5_prod_divergence_investigation.md` §9 V1.5 carries (lines ~398-401) — restated F-gap deferral.

---

## §7 Recommended next step

Hand this memo to a Cowork session OR to `cc` to author the actual Phase 7.5.3 dispatch wrapper. The wrapper should mirror Phase 7.5.1's structure (§0-§12), pin to a post-7.5.2 SHA, and explicitly disclaim the `halt3_validator.py` + `halt3_eval_set.yaml` surfaces (those belong to 7.5.2) and the `tier2_business_shortcut.py` surface (those belong to 7.6). The wrapper should also enumerate the F1 negative-regression test cases against the actual prod catalog's numeric-in-name rows (operator may need to enumerate those before dispatch).

When authored, the wrapper lives at `outputs/cursor_dispatch_prompt_phase_7_5_3.md`.

---

*Authored by sub-agent under Cowork primary supervision, 2026-05-20 post-Phase-7.5.2-dispatch. Saved to `outputs/phase_7_5_3_validator_polish_design_memo.md`.*
