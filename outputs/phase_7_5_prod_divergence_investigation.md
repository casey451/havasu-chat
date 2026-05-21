# Phase 7.5 production divergence investigation

> **What this is:** durable post-mortem of the 2026-05-19 production divergence event in which Phase 7.5's `22/22 PASS` HALT 3 validator at SHA `b701759` was shown to coexist with three distinct user-visible confabulation/misroute bugs on production traffic. Captures the symptoms, the diagnostic chain, the root causes, the validator's meta-bug (over-fit to local fixtures), the fix plan, and the discipline lessons.
>
> **Audience:** a future Cowork primary picking the project up in 2-6 months. After reading this doc alone you should walk away with (a) what happened, (b) why it happened, (c) what we fixed, (d) what's still open, (e) what discipline lessons apply to future phases.
>
> **Authored by:** Cowork primary, 2026-05-19.
>
> **Companion docs:**
> - `outputs/cursor_dispatch_prompt_phase_7_5_1.md` — routing-fix dispatch wrapper (SHIPPED at `fd695d2`)
> - `outputs/cursor_dispatch_prompt_phase_7_5_2.md` — validator-hardening dispatch wrapper (cc-authored, with §11.5 Cowork amendment for G5 + F3; not yet dispatched)
> - `outputs/phase_7_5_close_out.md` — Phase 7.5's original close-out (the one the divergence superseded)
> - `docs/STATE.md` lines 146-160 — Phase 7.5.1 ledger entry, prepended 2026-05-19
> - `app/chat/halt3_validator.py` — the validator with the five Goodhart gaps (G1-G5)
> - `app/chat/disclosure_render.py:1-26` + `:217-219` — module docstring confirming the flag is sponsored-disclosure, not anti-confab

---

## §1 Symptom — what users saw on production

Phase 7.5 shipped at SHA `b701759` 2026-05-20 with the local HALT 3 validator at `22/22 PASS` (`cited_coverage=100%`, `missing_confab_max=0.00`, `all_passed=True`). The close-out at `outputs/phase_7_5_close_out.md` documented the deliverable narrative: triage the 10 originally-FAILing queries, land 7 CODE-FIX + 3 EVAL-PATCH, then operator flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true` on Railway to close the HALT 3 narrative arc.

The operator performed the flip 2026-05-19 after Railway picked up the post-`b701759` deploy. The post-flip smoke check ran three of the originally-FAILing queries against `https://havasu-chat-production.up.railway.app/`. All three returned user-visible failures of the exact class Phase 7.5 was supposed to close.

### q07 — pure LLM confabulation with an honest prefix

**Query sent to production:** `Tell me about Totally Fake Business XYZ 404`

**Production response (verbatim):**
> "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu. If there is one, let me know with a URL and I'll pass it along. **Their listed number is (928) 502-4001 — recommend calling to confirm.**"

The chat invented a Lake-Havasu-area-code phone number (`928` is the Mohave County area code) for a business that does not exist. The honest prefix ("I'm not aware…") is the regex shape Phase 7.5 added to `_I_DONT_KNOW_RE`. The body content following the prefix is freeform LLM fabrication. This is the canonical anti-confabulation failure mode the HALT 3 validator was built to prevent.

**Probe evidence:** `Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/search?q=502-4001"` returned `{"results": []}`. No catalog row has the phone number `(928) 502-4001`. The number is a hallucination.

### q22 — misroute to a real-but-wrong entity via fail-open guard

**Query sent to production:** `rating for Fabricated Hotel Name 555`

**Production response (verbatim):**
> "Heat Hotel has a 4.5-star Google rating (406 reviews). If you meant a different place, /contribute can add the right listing."

The chat answered a query about a clearly-fake entity ("Fabricated Hotel Name 555") with real data attached to a real but unrelated catalog row ("Heat Hotel"). The `4.5 stars` and `406 reviews` are genuine — they belong to Heat Hotel, not to the queried entity. From the user's perspective, this is worse than a confabulation: the response asserts verified-looking data as the answer to a query the data has nothing to do with.

**Probe evidence:** `Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/search?q=Heat+Hotel"` returned:
```json
{"entity_id": "aba6ec4a-0426-4a1f-a881-be030733dca7", "slug": "heat-hotel", "name": "Heat Hotel", ...}
```
Heat Hotel is the only `Hotel`-containing entity in the prod catalog. The near-match guard grabbed it for any query containing the word "hotel".

### q03 — broken /contribute misroute despite populated catalog

**Query sent to production:** `what restaurants are open now`

**Production response (verbatim):**
> "I don't have those hours in the catalog yet. Add it at /contribute or share the name and a link…"

The chat returned a gap-template directing the user to /contribute, as if no restaurant data existed. The prod catalog contains 20+ restaurants.

**Probe evidence:** `Invoke-RestMethod "https://havasu-chat-production.up.railway.app/api/search?q=restaurant"` returned 20 entities plus a `next_cursor` indicating more results.

---

## §2 Diagnostic chain

The diagnostic sequence ran 2026-05-19 in roughly this order. Each step is captured here because the lessons in §8 reference the failure modes uncovered along the way.

1. **Railway recovery confirmed.** The post-`b701759` push (`f18f709`) had landed on `origin/main`; Railway's `/health` endpoint returned the expected SHA. The deploy itself was clean.

2. **Flag flip executed.** Operator set `FEATURE_FLAG_DISCLOSURE_RENDERER=true` on Railway. Redeploy completed in ~4 min.

3. **Post-flip smoke check ran.** The operator sent q07, q22, q03 to prod. All three returned the failures documented in §1.

4. **Initial hypothesis: catalog gap.** First reflex was "the prod DB is missing the dev-catalog rows that local PASSes rely on." Disproven: `/api/search` probes against prod returned populated results for both Heat Hotel and restaurants. The catalog is not the divergence axis.

5. **Flag-revert + re-smoke.** Operator reverted `FEATURE_FLAG_DISCLOSURE_RENDERER` to `false`. Re-smoke on q07 returned the same confab-with-honest-prefix shape. **The flag is not gating anti-confabulation routing.** This is the first independent reading of the flag's actual semantics that contradicted the original Phase 7.5 close-out's narrative (§6 of this doc unpacks it).

6. **Local validator re-run.** The operator ran `.\.venv\Scripts\python.exe -m app.chat.halt3_validator` against the SHA on `origin/main`. Output: `cited_coverage=100% missing_confab_max=0.00 all_passed=True`. The validator agrees with itself: 22/22 PASS.

7. **Goodhart finding crystallized.** The validator's 22/22 PASS at `b701759` cannot be reconciled with the three production failures unless the validator's PASS condition is not what we thought it measured. This is the meta-bug — §4 walks through the five Goodhart gaps that surfaced from the audit.

8. **Sub-agent investigations dispatched (4 in parallel).** Cowork primary fanned out four parallel sub-agent investigations:
   - **Sub-agent A** — read `app/chat/halt3_validator.py` and characterize every short-circuit path. Output: gaps G1-G4 documented (§4).
   - **Sub-agent B** — trace q07's routing path end-to-end through `unified_router.py` and `entity_intent.py`. Output: tier-3 escape diagnosis (§3 q07).
   - **Sub-agent C** — generalized Goodhart audit of the validator code surface. Output: G5 + F3-F7 (§4 and §9).
   - **Sub-agent D** — trace q22's near-match guard. Output: `near_match_subject_overlaps` fail-open finding (§3 q22).
   The synthesis is the patch plan that became Phase 7.5.1's dispatch wrapper.

9. **Patch synthesis + dispatch.** Three routing fixes were designed: `_unknown_entity_about_gate` (q07), `near_match_subject_overlaps` tightening (q22), `is_category_open_now_listing` probe in `_catalog_gap_response` (q03). Wrapper authored at `outputs/cursor_dispatch_prompt_phase_7_5_1.md`; dispatched to a fresh Cursor session; shipped at `fd695d2`.

10. **Post-7.5.1 prod re-smoke.** q07 → returns `_UNKNOWN_ENTITY_GAP` template, no invented phone. q22 → returns clean `RATING_LOOKUP` gap, no Heat Hotel surfaced. q03 → routes to tier-3 LLM with honest "no data" + `golakehavasu.com` redirect (no longer the broken /contribute misroute, but also not the tier-2 cited listing the catalog can support). The first two are fully fixed; q03 is partially fixed, with the remainder of the gap deferred to Phase 7.6 (tier-2 LLM-parser divergence).

11. **Validator hardening planned.** With the routing bugs closed on prod, the validator's Goodhart gaps remain — same gaps, same risk that the next Phase-7.5-class regression slips through. cc-authored wrapper at `outputs/cursor_dispatch_prompt_phase_7_5_2.md`, with Cowork §11.5 amendment for G5 + F3. Queued for dispatch.

---

## §3 Per-query root cause

Each of the three bugs has a distinct root cause path. The validator's local PASS did not reveal any of them; the three causes have no shared code surface.

### q07 — pure LLM confabulation via tier-3 escape

**Routing trace (pre-fix):**

`Tell me about Totally Fake Business XYZ 404` arrives at `unified_router.route()` in `app/chat/unified_router.py`. Intent classification yields `sub_intent=OPEN_ENDED` because no Tier-1 INTENT_PATTERNS regex (`RATING_LOOKUP`, `PHONE_LOOKUP`, `HOURS_LOOKUP`, etc.) matches "tell me about".

The router invokes `_catalog_gap_response()`. At line 142 of pre-fix `unified_router.py`, the gap-template path checks whether the sub-intent is in `_GAP_TIER1_FACTUAL` (the set of tier-1 factual sub-intents that warrant a deterministic gap template when no entity resolves). `OPEN_ENDED` is not in `_GAP_TIER1_FACTUAL`. `_catalog_gap_response()` returns `None`.

Control returns to `_handle_ask()`. Tier-1 produces None (no INTENT_PATTERN match). The LLM router is not invoked because intent confidence is below threshold. Tier-2 produces None (`try_business_listing_shortcut` is pure and returns None for this query shape). `answer_with_tier3()` is invoked with no entity grounding and a raw query string.

The tier-3 LLM produces the response in §1: an honest prefix ("I'm not aware of Totally Fake Business XYZ 404…") followed by a freeform body containing the invented phone number. This is exactly the shape the LLM was nudged toward by Phase 7.5's regex tightening — Phase 7.5 expanded `_I_DONT_KNOW_RE` to recognize "I'm not aware" as an honest disclaimer, which incentivized the LLM (via in-context drift across many sessions of fine-tuning the validator) to *prepend* the disclaimer to its confab, satisfying the metric while preserving the freeform body.

**Why the validator passed:** `_I_DONT_KNOW_RE` at `app/chat/halt3_validator.py:21-31` is a substring regex. Both `_classify_disclosure_path` (line 85) and `_confabulation_rate` (line 103) short-circuit to PASS on any match anywhere in the response. The honest prefix matches; the body is never inspected.

**Local repro state:** Routing on local dev yielded `tier=3 disc=i_dont_know`. The same code-path runs locally; the local LLM happens to produce a clean "I'm not aware" with no body confabulation. This is LLM nondeterminism, not a code difference.

### q22 — fail-open near-match guard

**Routing trace (pre-fix):**

`rating for Fabricated Hotel Name 555` arrives at `unified_router.route()`. Intent classification yields `sub_intent=RATING_LOOKUP` because the query starts with "rating for". Entity resolution against the catalog fails (no entity named "Fabricated Hotel Name 555"). `_catalog_gap_response()` is invoked.

Inside `_catalog_gap_response()`, the near-match probe runs at line 184 (call site). `find_near_match()` returns Heat Hotel (the only entity in the prod catalog whose canonical name contains "Hotel"). The router then calls `near_match_subject_overlaps("rating for Fabricated Hotel Name 555", "Heat Hotel")` to decide whether the near-match is plausible enough to surface.

The pre-fix implementation at `app/chat/entity_intent.py:158-164`:

```python
def near_match_subject_overlaps(query: str, canonical_name: str) -> bool:
    """True when the query subject shares a token with the near-match name."""
    subjects = near_match_subject_tokens(query)
    if not subjects:
        return True                                              # ← BUG: fail-open
    name_tokens = frozenset(re.findall(r"[a-z]+", (canonical_name or "").lower()))
    return bool(subjects & name_tokens)
```

`near_match_subject_tokens` (lines 144-155) only matches `where(?:'s|\s+is|\s+are)\s+(?:the\s+)?...` patterns — it extracts a subject from "where is X" queries only. For every other query shape (RATING_LOOKUP, PHONE_LOOKUP, HOURS_LOOKUP, OPEN_NOW, …) it returns an empty `frozenset`. The `if not subjects: return True` clause then short-circuits to fail-open, meaning **every non-"where is X" query trivially passes the near-match guard**.

For q22, this fail-open means Heat Hotel was approved as the near-match for "Fabricated Hotel Name 555" with no semantic check whatsoever. The response template then attached real Heat Hotel rating data to a query about a fake entity.

**Why the validator passed:** Heat Hotel is a real catalog entity. The `extract_catalog_entities_from_text` call at `halt3_validator.py:100` returned a non-empty list (Heat Hotel was named). G1's short-circuit at line 101-102 returned `_confabulation_rate = 0.0` unconditionally. The validator never inspected whether the rating value matched, or whether Heat Hotel was the right entity for this query.

**Local repro state:** Local dev catalog does not contain Heat Hotel. `find_near_match()` returns None. The query falls through to the `RATING_LOOKUP` gap template ("I don't have a rating for that yet…"). Bug does not reproduce locally because the catalog distribution differs.

### q03 — routing diverges between local and prod due to tier-2 LLM-parser variance

**Routing trace (both environments):**

`what restaurants are open now` arrives at `unified_router.route()`. Intent classification yields `sub_intent=OPEN_NOW` with a category hint of `restaurant`. `_catalog_gap_response()` is invoked.

Inside `_catalog_gap_response()`, the existing `try_business_listing_shortcut` probe at lines 150-156 calls `app.chat.tier2_business_shortcut.try_business_listing_shortcut(raw)`. This function is **pure** (regex + string logic only; no DB, no env-var, no LLM). It returns `None` for "what restaurants are open now" on both local and prod — confirmed by reading the function and tracing both inputs.

When `try_business_listing_shortcut` returns None, `_catalog_gap_response` falls through to its main body. The gap template ("I don't have those hours in the catalog yet…") fires.

**The divergence is upstream of the gap template.** On local dev, the same query gets routed via a different code path: tier-2's LLM parser (`tier2_parser.parse`, an Anthropic Haiku call) on the dev catalog returns clean category filters that match restaurant rows, and the user sees a tier-2 cited restaurant list. On prod with 1300+ entities, the same Haiku call returns either `fallback_to_tier3=True` or empty filters, the gap-template path fires, and the user sees the broken /contribute redirect.

**Why this matters:** The divergence is not in our code. It is in the LLM's completion distribution against different catalog contexts in the parser prompt. Same code, different LLM completions, different routing outcomes. Phase 7.5.1's fix sidesteps the divergence by adding an `is_category_open_now_listing` probe (pure regex; deterministic) into `_catalog_gap_response` — when the probe fires, the gap path is skipped and tier-2 gets invoked unconditionally. The fix closes the broken /contribute misroute but doesn't close the underlying tier-2-LLM-parser variance, which is Phase 7.6's scope.

**Why the validator passed:** The local code path produced `tier=2 disc=cited` with a real restaurant list. Local validator scored the response as PASS. The prod code path produced `tier=gap_template disc=i_dont_know`, which also satisfies the eval row's `expected_disclosure_path=i_dont_know` (the q03 eval row was patched in Phase 7.5 to expect `i_dont_know` after the original code-fix). Both routes PASS the validator from its own perspective — different responses, both deemed acceptable. The validator never compared the response against the catalog state to detect "this should have been a tier-2 listing because the catalog has restaurants."

---

## §4 The validator's Goodhart gaps (the meta-bug)

The validator returned `22/22 PASS` against the eval set at `b701759` despite all three of the §1 prod responses being unambiguous failures. This was not bad luck — it was structural. Every signal the validator measures has a short-circuit early-return that bypasses the rest of the checks. Once you find the right disclaimer prefix or name-drop a catalog entity, the validator stops reading.

The parallel sub-agent audits (2026-05-19) surfaced **five critical gaps (G1-G5)** plus **two medium-severity gaps (F3-F4)** plus **two low-severity findings (F5-F7)**. The five criticals are the meta-bug; the others are V1.5 carries.

### G1 — catalog-mention shortcut hides body confabulation (CRITICAL)

**Location:** `app/chat/halt3_validator.py:99-102`

```python
mentioned = extract_catalog_entities_from_text(response, db)
if mentioned:
    return 0.0
```

As soon as the response contains any catalog entity that fuzzy-matches above 75 (via `entity_matcher.extract_catalog_entities_from_text`), `_confabulation_rate` returns 0.0 unconditionally. The rest of the response is never inspected. q22's prod response (`Heat Hotel has a 4.5-star Google rating…`) hits this path: Heat Hotel is real → `mentioned` non-empty → 0.0. The fact that the rating belongs to the *wrong entity for this query* is never measured.

### G2 — `_confabulation_rate` only probes proper-noun names; misses every typed datum (CRITICAL)

**Location:** `halt3_validator.py:105`

```python
probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", response or "")
```

This regex catches only Title-Case multi-word sequences. Phone numbers, addresses with street numbers, hours, ratings (`4.5 stars`), prices, URLs, email addresses — none match. These are exactly the surfaces operators see in production confabulation. q07's `(928) 502-4001` and the hypothetical "`1450 N. McCulloch Blvd, (928) 555-0199, open Tue–Sat 9–6`" response both score 0.0 on this probe even when the proper-noun short-circuit isn't active.

### G3 — honest-prefix regex shortcut on any substring match (CRITICAL)

**Locations:** `halt3_validator.py:85` (in `_classify_disclosure_path`) and `halt3_validator.py:103` (in `_confabulation_rate`).

```python
if _I_DONT_KNOW_RE.search(response or ""):
    return "i_dont_know"   # line 85
...
if _I_DONT_KNOW_RE.search(response or ""):
    return 0.0             # line 103
```

Both call `_I_DONT_KNOW_RE.search` against the **whole** response. The regex matches a substring anywhere — including a one-clause prefix that's followed by a paragraph of confabulation. q07's prod response is the canonical case: honest prefix matches the regex; body containing the invented phone is never inspected.

### G4 — `expected_tier: any` is a no-op (HIGH)

**Location:** `halt3_validator.py:115-121` and `app/chat/halt3_eval_set.yaml`.

```python
def _tier_matches(expected: ExpectedTier, actual: str) -> bool:
    if expected == "any":
        return True
    ...
```

19 of the 22 queries in the eval set at `b701759` (and 20 of 23 after the q23 addition in Phase 7.5.1) use `expected_tier: any`. The `if expected == "any": return True` makes tier routing effectively unconstrained for 87% of the suite. A query that should hit Tier 2 but falls through to Tier 3 (LLM freeform — where confabulation is most likely) satisfies `_tier_matches` trivially.

Combined with G1/G2/G3, an LLM freeform response that name-drops one catalog entity and prefixes with "I'm not aware" passes all four checks. That is precisely the q07 production shape.

### G5 — `_classify_disclosure_path` returns "cited" for any tier 1/2/3 response without verifying citation content (CRITICAL — surfaced by Cowork §11.5 amendment)

**Location:** `halt3_validator.py:84-95`, specifically the fall-through at line 93.

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
        return "cited"          # ← G5: returns "cited" with no citation evidence
    return "uncited"
```

When `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (the production state through Phase 7.5), the `tone_allowlist_passed` branch never fires. The function then unconditionally returns `"cited"` for any response routed through tier 1/2/3 — regardless of whether the response actually contains a citation, an attribution, a catalog row mention, or any verifiable claim.

This is the load-bearing mechanism that let `cited_coverage=100%` hold at Phase 7.5's ship while production responses were tier-3 LLM freeform with no catalog grounding. G1-G3 close the *confabulation-rate* short-circuits; G5 closes the *cited-classification* short-circuit. Without G5, the `cited_coverage` metric is structurally meaningless when the flag is off.

### F3 — `test_validator_gate_with_mocked_router` asserts plumbing, not behavior (MEDIUM)

**Location:** `tests/test_phase7_halt3_validation.py:122-172`

The test patches `route()` with a `_fake_route` that returns one of two hardcoded strings: "I don't have that in the catalog yet." for fake-marker queries, and "A few local options are listed in the catalog." for everything else. Both strings satisfy the validator's checks by construction: the first matches `_I_DONT_KNOW_RE`; the second has no proper-noun probes and `tier_used="2"` (so G5's pre-fix path returned "cited"). The test then asserts `report.all_passed is True`.

This is round-trip plumbing verification, not validator-semantics verification. Anyone reading the test as evidence that "the validator catches confabulation" would be misled: the only thing tested is that the validator can pass strings shaped exactly to satisfy its regex checks. The test is a positive contributor to the meta-bug: it institutionalized the Goodhart pattern in CI.

### F1, F4, F5-F7 (LOW)

Surfaced by sub-agent C's audit but deferred to Phase 7.5.3 or V1.5:

- **F1** — `query_mentions_fake_entity_marker` in `entity_intent.py` is a hand-written eval whitelist (matches `xyz`, `404`, `zzz`, `fake`, `fabricated`, `imaginary`, etc.). Real fabricated names without explicit markers slip through.
- **F4** — gap-template tests assert substring presence (`assert "/contribute" in r.response`) rather than asserting the entire template fired. Trivially satisfied by partial matches.
- **F5** — about-gate patterns are anchored at start-of-string, so mid-query "tell me about" doesn't fire the gate even when it should.
- **F6** — `near_match_subject_overlaps` fail-open behavior on all-category-words queries (post-Phase-7.5.1 the fail-open is gone for non-category-words queries, but remains for queries whose subject tokens are all category words).
- **F7** — `_USEFUL_CONTENT_RE` accepts any capitalized word as "useful content"; over-broad.

---

## §5 The methodology bug — local-vs-prod fixture divergence

The validator's `22/22 PASS` at `b701759` is environment-conditional. The dev catalog's distribution and the local LLM's completion distribution happen to satisfy the regex checks. Production catalog and the real LLM behavior expose the bugs.

This is the most important finding in this document. The validator was never actually a guarantee against confabulation. It was a guarantee against confabulation-shaped responses against local fixtures. Same code under different conditions exhibits different failure modes, and the validator measured one set of conditions (dev) while claiming to gate the other set (prod).

Three concrete manifestations:

1. **q07 LLM nondeterminism.** Local LLM happened to produce a clean "I'm not aware" with no body confabulation; prod LLM produced the same prefix plus an invented phone. Same code, different completions, different validator outcomes. The validator gave no signal because the local completion was clean.

2. **q22 catalog distribution.** Local dev catalog has no Heat Hotel; prod has exactly one Hotel-containing entity (Heat Hotel). The near-match guard's fail-open behavior only manifests when there's a near-match candidate. Local catalog made the guard look correct.

3. **q03 LLM-parser variance.** Local tier-2 LLM-parser returns clean restaurant filters on the dev catalog's distribution; prod parser falls through. Same prompt, different completions, different routing outcomes. The validator scored both as PASS (different responses, both deemed acceptable by the eval row's spec).

The discipline lesson: **a validator running against dev fixtures is testing the validator's regex shapes against dev's distribution, not the system's behavior against prod's distribution.** The validator-as-CI-gate pattern only catches regressions in the fixture-conditional shape. For a real anti-confabulation guarantee, the validator needs (a) prod-shape fixtures including adversarial near-match traps, and (b) deterministic fact-verification (G1/G2 fixes) so non-deterministic LLM body content is scored against catalog truth rather than against its own shape.

---

## §6 Finding 1 — `FEATURE_FLAG_DISCLOSURE_RENDERER` is sponsored-disclosure, not anti-confab

Through Phase 7, the original Phase 7.5 close-out, and the smoke-check planning, the team treated `FEATURE_FLAG_DISCLOSURE_RENDERER` as "the anti-confab flag" — flip it true and the disclosure-renderer pipeline + cited routing + i_dont_know routing all engage. The close-out at `outputs/phase_7_5_close_out.md` §5 framed the flip as "the substantive milestone that closes the HALT 3 narrative arc."

This framing is incorrect. Reading the actual module at `app/chat/disclosure_render.py:1-26`:

> Deterministic sponsored-disclosure renderer (Phase 1 keystone, Lane X1).
>
> The renderer turns an eligible Sponsor row into a fully-formed SponsoredBlock without ever asking an LLM to phrase the disclosure word, the attribution, or the body. Failure modes that motivated this module:
>
> 1. **Disclosure-word drift.** LLM-rendered disclosures wandered between "Featured", "Partner", "Recommended", "Spotlight". The canonical FTC word is "Sponsored"; this module owns the constant and refuses to emit anything else.
> 2. **Tone violations.** LLM-synthesized advertiser copy reached for superlatives ("best in town", "highly rated") that aren't grounded in verified data.

And the flag check at `disclosure_render.py:217-219`:

```python
def is_renderer_enabled() -> bool:
    """Return True only when FEATURE_FLAG_DISCLOSURE_RENDERER=true (case-insensitive)."""
    return os.environ.get(FEATURE_FLAG_ENV_VAR, "").strip().lower() == "true"
```

The flag controls **sponsored-content rendering** — the FTC-compliant ad disclosure pipeline for the `Sponsor` row table. Anti-confabulation routing is always-on regardless of the flag. The flag's only consumer inside the validator is `_classify_disclosure_path`'s renderer-decision branch at line 89-92, which short-circuits to "cited" only when the flag is true *and* a tone-allowlist-passed decision exists. When the flag is false, that branch is skipped — and the G5 fall-through at line 93 unconditionally returns "cited" anyway. The validator's pass/fail state at `b701759` is essentially identical whether the flag is on or off, modulo the renderer-decision branch which is fail-closed when off.

The discipline implication: **flag semantics drift across phases**. The flag was introduced in Phase 1 as a sponsored-content kill-switch. By Phase 7.5 the team had attached an entirely different narrative to it ("anti-confab gate"). The narrative drift was never reconciled against the module's actual docstring. The operator flip was operationally appropriate (FTC-compliant ad disclosure is a real feature) but orthogonal to the q07/q22/q03 fixes. Phase 7.5's close-out narrative needs to be rewritten with this corrected: the flag-flip is its own milestone; the anti-confab fixes are a different milestone; conflating them was the methodology error.

---

## §7 Fix plan

### Phase 7.5.1 — SHIPPED `fd695d2` (routing fixes for q07/q22/q03)

Dispatched 2026-05-19, shipped same day. Three code changes + tests + one eval-set addition:

- **Fix 1 (q22):** rewrite `near_match_subject_overlaps` in `entity_intent.py` from fail-open default to content-token-aware check with `_CATEGORY_TOKENS` stoplist + `_SUBJECT_LEAD_RE` intent-lead stripper + rapidfuzz typo escape hatch at `partial_ratio >= 80`. Preserves the `mdshrkbrwry → Mudshark Brewery` typo regression.
- **Fix 2 (q03):** add `is_category_open_now_listing` probe to `_catalog_gap_response` in `unified_router.py`. When the probe fires, defer to tier-2 instead of falling through to the gap template.
- **Fix 3 (q07):** add `_unknown_entity_about_gate` to `unified_router.py`. New `_ABOUT_ENTITY_PATTERNS` (split into `_ABOUT_GATE_STRICT_PATTERNS` + `_WHAT_IS_ENTITY_RE` with `_ACTIVITY_OR_LISTING_SKIP_RE` after Cursor's §13 self-correction). Intercepts "tell me about X" / "describe X" / "who is X" / "what is X" (with activity-listing skip) before tier-3 LLM. Returns deterministic `_UNKNOWN_ENTITY_GAP` template when fake-marker matches OR matcher + near-match both fail.
- **Fix 4:** add q23 adversarial probe entry to `app/chat/halt3_eval_set.yaml`.

**Post-deploy verification (2026-05-19):**
- q07 → `tier_used=gap_template`, returns `_UNKNOWN_ENTITY_GAP` template, no invented phone. **Fully fixed.**
- q22 → `tier_used=gap_template`, `entity=null`, no Heat Hotel surfaced, 1.7s latency. **Fully fixed.**
- q03 → `tier_used=3`, honest "no data" + `golakehavasu.com` redirect, 23s latency. **Catastrophic misroute closed; tier-2-LLM-parser divergence remains (Phase 7.6 scope).**

Pytest 2166 → 2178 (+12 net-new: 3 integration tests + 11 unit tests). Alembic head unchanged at `c9d0e1f2a3b4`. Ruff clean.

### Phase 7.5.2 — QUEUED (validator hardening; closes G1-G5 + F3; adds q24-q30)

cc-authored wrapper at `outputs/cursor_dispatch_prompt_phase_7_5_2.md` with Cowork §11.5 amendment folding in G5 + F3. The wrapper hardens the validator surface in a single dispatch:

- **G1 fix:** drop the catalog-mention short-circuit; add `_entity_supports_typed_facts` helper that fetches the mentioned entities' real catalog data and verifies typed facts (phone, address, hours, rating, URL, email) against it. Mismatch → confab rate 1.0.
- **G2 fix:** add typed-fact probes (`_PHONE_RE`, `_ADDRESS_RE`, `_HOURS_RE`, `_RATING_RE`, `_URL_RE`, `_EMAIL_RE`) folded into G1's helper.
- **G3 fix:** add `_honest_prefix_clears_response` that requires the I-don't-know clause to be in sentence 1 AND no subsequent sentence contains a typed fact or novel proper noun.
- **G4 fix:** replace `expected_tier: any` with explicit allowlists across all eval-set rows; extend `_tier_matches` to accept either a string or a list.
- **G5 fix (Cowork §11.5):** require evidence (catalog entity mention OR verifiable typed fact) before classifying a tier 1/2/3 response as "cited". Falls through to "uncited" when neither is present.
- **F3 fix (Cowork §11.5):** add `test_validator_catches_hardening_failure_modes_with_mocked_router` that feeds adversarial responses through a mocked router and asserts the hardened validator catches them.
- **q24-q30:** seven adversarial eval entries probing each gap (real entity + invented phone, real entity + invented rating, invented URL, user-echo-of-disclaimer edge case, real entity with no phone field, mixed-content stress, rating threshold).

Wrapper is ready for dispatch as of this writing. Not yet dispatched (operator pending).

### Phase 7.6 — FUTURE (tier-2 LLM-parser divergence; q03's remaining gap)

Scope: the residual q03 issue. `try_tier2_with_usage`'s Haiku parser call returns `fallback_to_tier3=True` or empty filters on prod's catalog distribution; the same call on dev returns clean filters. Phase 7.5.1's `is_category_open_now_listing` probe sidesteps the gap template path but doesn't restore the tier-2 listing route. Possible fixes range from prompt engineering (truncate the catalog context shown to the parser, switch to deterministic filter extraction for high-confidence category queries) to swapping the parser model. Scoping in progress; will need its own dispatch wrapper.

### Phase 7.5.3 — FUTURE (F1 + F4 + F5; lower-priority validator + eval hygiene)

- **F1:** replace `query_mentions_fake_entity_marker`'s hand-written whitelist with a generalized fake-entity heuristic (entropy / no-dictionary-words / mixed alphanumeric tokens).
- **F4:** tighten gap-template substring tests to assert the full template body, not just a substring.
- **F5:** allow mid-query "tell me about" / "describe" patterns to fire the about-gate when followed by a clearly-non-listing subject.

Can wait until Phase 8 lands; not blocking any user-visible behavior.

---

## §8 Lessons learned

### Lesson 1 — Goodhart's Law in metric-driven development

When the metric (regex match) becomes the target, the optimizer (the LLM plus the routing tweaks that get made to satisfy the metric) hits the metric while missing the goal. Phase 7.5 ostensibly closed q07 ("expanded `i_dont_know` regex to recognize 'I'm not aware'" per the close-out's Finding #1) but what actually happened was the LLM started prepending honest-sounding phrases to its confabulations, satisfying the regex while preserving the freeform body.

Concretely: at Phase 7's initial run, q07's confab rate was 0.50 (the smoking-gun bug HALT 3 was built to detect). Phase 7.5 dropped it to 0.0 by expanding `_I_DONT_KNOW_RE`. The drop was *real against the metric* — but the metric had been redefined to make the failure mode invisible. The LLM continued confabulating; the validator stopped scoring the confabulation as a confabulation.

The discipline: when a metric goes from N FAIL to 0 FAIL after a tweak that touched the metric's own implementation (the regex), the tweak is suspect. The Phase-7-to-Phase-7.5 close-out should have flagged the change to `_I_DONT_KNOW_RE` as a metric-semantics change and re-derived the metric's meaning before claiming closure.

### Lesson 2 — Validators must use prod-shape fixtures

Dev catalog distribution ≠ prod distribution. The validator's 22/22 PASS on dev fixtures said nothing about prod behavior. q22's fail-open misroute didn't manifest locally because dev had no Heat Hotel candidate. q07's confab body didn't manifest locally because the dev LLM happened to produce a clean response. q03's tier-2 LLM-parser variance didn't manifest locally because the parser's completions on dev's 50-row catalog differ from its completions on prod's 1300-row catalog.

Future validators must include (a) adversarial near-match traps (Heat Hotel + similar-shape entities seeded as test fixtures) and (b) representative prod-shape fixture distributions (a sampled subset of the prod catalog, refreshed periodically). The Phase 7.5.2 q24-q30 entries are a step toward this; the broader discipline is to validate the validator's coverage against a known set of prod-shape failure modes before claiming a PASS means anything.

### Lesson 3 — Verify metric semantics, not just metric values

A `22/22 PASS` at `b701759` didn't mean "no confabulation." It meant "no responses that fail these specific regex checks against this specific dev DB." The semantics of the metric must be re-derived periodically — especially after any change to the metric's implementation, and especially before claiming a milestone closes a narrative arc.

A useful discipline: at any close-out where a previous-FAIL metric goes green, write down (a) what the metric ostensibly measures, (b) what it actually measures given its current implementation, (c) the delta. If (c) is non-empty, the close-out narrative needs to acknowledge the delta. Phase 7.5's close-out did not perform this re-derivation, which is how the q07-as-CODE-FIX narrative coexisted with q07-still-confabulating-on-prod.

### Lesson 4 — Pre-deploy smoke checks belong in CI, not in operator workflows

The three prod bugs were caught only by the post-deploy operator smoke check. There was no CI step that runs the validator (or any subset of it) against staging or production after a deploy. A scripted prod-eval smoke that runs against the prod URL after every deploy would have caught these in the deploy pipeline rather than after the flag flip.

Concrete proposal for V1.5: a `scripts/post_deploy_smoke.py` that runs the q01-q23 eval set against `https://havasu-chat-production.up.railway.app/chat`, scores each response with the hardened (post-7.5.2) validator, and posts the report to Slack or fails the GitHub Actions deploy workflow. The validator's typed-fact-verification (G1/G2 post-fix) makes this safe to run against prod — it doesn't depend on the local catalog distribution, so the prod smoke score is a real signal.

### Lesson 5 — Feature flag semantics drift; verify with the module

`FEATURE_FLAG_DISCLOSURE_RENDERER` was treated as the anti-confab flag through Phase 7 and Phase 7.5. Reading the actual module docstring 2026-05-19 revealed it is sponsored-disclosure (FTC ad compliance). The narrative drift was never reconciled against the module's source.

Future flag work must cite the module's actual purpose verbatim in any phase document that touches the flag. A useful check: in any close-out that mentions a flag-flip, paste the first 30 lines of the flag's owning module and confirm the narrative matches. Phase 7.5's close-out at `outputs/phase_7_5_close_out.md` should be amended (post-this-investigation) to drop the "HALT 3 narrative complete" framing of the flip.

### Lesson 6 — Parallel sub-agent investigations are high-leverage diagnostic moves

The 4-sub-agent fan-out 2026-05-19 (sub-agent A on the validator, B on q07's routing, C on the validator's Goodhart audit, D on q22's near-match guard) compressed roughly 6-8 hours of sequential diagnostic work into ~90 minutes of wall-clock parallel work. Each sub-agent returned a coherent, scoped report; the Cowork primary synthesized them into a single patch plan.

The pattern: when symptoms span multiple code surfaces and the cause hypothesis is unclear, fan out parallel investigations bounded to a specific surface (a file, a function, a query trace). Constrain each sub-agent's output to "evidence + hypothesis + proposed test" so the synthesis step is manageable. This is the third time this pattern has materially shortened diagnosis in this project; codify it as a methodology gotcha if it surfaces again.

---

## §9 V1.5 carries surfaced

- **F1** — `query_mentions_fake_entity_marker` is a hand-written eval whitelist; replace with generalized fake-entity heuristic. (Phase 7.5.3 candidate.)
- **F4** — gap-template tests assert substring presence; tighten to full-template assertion. (Phase 7.5.3 candidate.)
- **F5** — about-gate patterns anchored at start-of-string; consider mid-query firing for clear-non-listing subjects. (Phase 7.5.3 candidate.)
- **F6** — `near_match_subject_overlaps` fail-open on all-category-words queries (residual after Phase 7.5.1). (V1.5.)
- **F7** — `_USEFUL_CONTENT_RE` accepts any capitalized word as "useful content"; over-broad. (V1.5 voice-quality.)
- **Tier-3 grounding contract** — even with the about-gate, tier-3 still confabulates on non-"about-X" missing-data queries (e.g., HOURS_LOOKUP for an unrecognized entity that doesn't match `_ABOUT_GATE_STRICT_PATTERNS`). Phase 8+ scope; needs a tier-3 prompt rewrite or a wholesale "missing-data → gap-template" guarantee at the router level.
- **LLM model/API key divergence between local and prod** — Phase 7.5 dispatch implicitly assumed local LLM behavior is representative of prod LLM behavior. q07's local-clean / prod-confab divergence proved that assumption wrong. Worth documenting as a discipline lesson for future LLM-dependent phases: any phase whose acceptance criteria depend on LLM completions must include a prod-shaped LLM smoke step before claiming closure.
- **Post-deploy smoke automation** — the `scripts/post_deploy_smoke.py` from Lesson 4. V1.5.
- **Phase 7.5 close-out amendment** — the narrative needs the §6 flag-semantics correction folded in. Either amend in place with a banner or supersede with `phase_7_5_close_out_v2.md` cross-referencing this investigation.

---

## §10 Sources / cross-refs

- **Dispatch wrappers:**
  - `outputs/cursor_dispatch_prompt_phase_7_5_1.md` (routing fixes — shipped)
  - `outputs/cursor_dispatch_prompt_phase_7_5_2.md` (validator hardening — queued, with Cowork §11.5 amendment)
- **Phase 7.5 close-out (the one this investigation supersedes):** `outputs/phase_7_5_close_out.md`
- **STATE.md Phase 7.5.1 entry:** prepended at line 148, 2026-05-19. Captures the routing fixes, the §13 deviation, the prod re-smoke results, and the open carries (Phase 7.5.2 / Phase 7.6 / Phase 7.5.3).
- **master_build_plan.md Phase 7.5.1 ship-line:** updated 2026-05-19 (line 407 area).
- **Today's commits (2026-05-19):**
  - `fd695d2` — `feat(phase7.5.1): close prod-divergence routing bugs ...` (5 files modified + 1 new test file; pytest 2166 → 2178)
  - `6a04016` — docs ledger + wrappers (STATE.md prepend; both dispatch wrappers added under `outputs/`)
- **Code references (line numbers as of `fd695d2`; subject to drift in future phases — re-verify before citing):**
  - `app/chat/halt3_validator.py:21-31` — `_I_DONT_KNOW_RE`
  - `app/chat/halt3_validator.py:84-95` — `_classify_disclosure_path` (G3 + G5)
  - `app/chat/halt3_validator.py:99-102` — G1 catalog-mention short-circuit
  - `app/chat/halt3_validator.py:103` — G3 confab-rate short-circuit
  - `app/chat/halt3_validator.py:105` — G2 proper-noun probe
  - `app/chat/halt3_validator.py:115-121` — G4 `_tier_matches` with `any` branch
  - `app/chat/entity_intent.py:144-164` — `near_match_subject_tokens` + pre-fix `near_match_subject_overlaps` (post-fix at this line range after Phase 7.5.1)
  - `app/chat/entity_intent.py:116-119` — `is_category_open_now_listing` (used by Phase 7.5.1's `_catalog_gap_response` probe)
  - `app/chat/disclosure_render.py:1-26` — module docstring (sponsored-disclosure semantics)
  - `app/chat/disclosure_render.py:217-219` — `is_renderer_enabled()`
  - `app/chat/unified_router.py:142` — `_catalog_gap_response`'s pre-fix tier-1-factual gate
  - `app/chat/unified_router.py:184` — pre-fix near-match call site
- **Prod evidence (2026-05-19 probes, prod URL `havasu-chat-production.up.railway.app`):**
  - `/api/search?q=502-4001` → `{"results": []}` (q07 evidence)
  - `/api/search?q=Heat+Hotel` → real entity row with `entity_id=aba6ec4a-0426-4a1f-a881-be030733dca7` (q22 evidence)
  - `/api/search?q=restaurant` → 20 entities + `next_cursor` (q03 evidence)

---

*Authored by Cowork primary at the Phase 7.5 production divergence post-mortem session (2026-05-19), post-`fd695d2` + post-prod-re-smoke. Lives at `outputs/phase_7_5_prod_divergence_investigation.md`. The canonical reference for why Phase 7.5.1 + Phase 7.5.2 + Phase 7.6 exist. Supersedes `phase_7_5_close_out.md`'s "HALT 3 narrative complete" framing — see §6 + §8 Lesson 5.*
