# Claude Code task — author Phase 7.5.2 dispatch wrapper (validator hardening)

> **What this is:** a self-contained task spec for Claude Code (cc). Casey, open `cc` in the project root (`C:\Users\casey\projects\havasu-chat`) and paste the prompt below (the section between the horizontal rules) as the first message. cc authors the file at `outputs/cursor_dispatch_prompt_phase_7_5_2.md` and emits a brief summary.
>
> **Estimated cc effort:** 60-90 min.
>
> **Why this and not something else:** Phase 7.5.1 (in-flight in Cursor right now) fixes the three production routing bugs. Phase 7.5.2 fixes the *validator* that should have caught those bugs in CI. Both lanes are needed. 7.5.2 is the methodology-level improvement; without it, future Phase 7.5-style "tests pass locally but prod confabulates" regressions will continue to slip through.

---

## Prompt to paste into cc

```
You are picking up the havasu-chat project to author a Cursor dispatch wrapper for Phase 7.5.2 — the HALT 3 validator hardening lane. Your output is a single new file at `outputs/cursor_dispatch_prompt_phase_7_5_2.md`. Do NOT edit any other file. Do NOT git-commit. Stop when the wrapper is written + you've emitted a brief summary.

Working directory: `C:\Users\casey\projects\havasu-chat`. Use `.\.venv\Scripts\python.exe` for any Python invocation if you need to verify code semantics during authoring (you shouldn't — this is doc-authoring, not code-editing).

## Context

The HALT 3 validator at `app/chat/halt3_validator.py` shipped at SHA `b701759` with 22/22 PASS. Production smoke check 2026-05-19 revealed three distinct user-visible confabulation/misroute bugs on the exact queries Phase 7.5 was supposed to fix:

- q07 ("Tell me about Totally Fake Business XYZ 404") — LLM invents phone (928) 502-4001 after honest "I'm not aware" prefix
- q22 ("rating for Fabricated Hotel Name 555") — misroutes to real Heat Hotel entity via fail-open near-match guard
- q03 ("what restaurants are open now") — gap-template fires despite 20+ restaurants in catalog

The routing fixes are in flight in Phase 7.5.1 (Cursor session, separate dispatch at `outputs/cursor_dispatch_prompt_phase_7_5_1.md`). Phase 7.5.2's job is to fix the **validator** so future bugs of this class don't slip through CI.

## Substantive findings the wrapper must encode

A general-purpose sub-agent audited `app/chat/halt3_validator.py` 2026-05-19 and found **4 critical Goodhart-style gaps** plus an over-fit eval set. These are the load-bearing inputs to the Phase 7.5.2 wrapper. Encode them verbatim with line numbers.

### G1. Catalog-mention short-circuit hides body confabulation (CRITICAL)
- **Location:** `app/chat/halt3_validator.py:99-102`
- **Code:**
  ```python
  mentioned = extract_catalog_entities_from_text(response, db)
  if mentioned:
      return 0.0
  ```
- **Failure mode:** As soon as the response contains ANY catalog entity that fuzzy-matches above 75 (via `entity_matcher.extract_catalog_entities_from_text`), `_confabulation_rate` returns 0.0 unconditionally. The rest of the response is never inspected. The matcher even strips intent padding, so a single catalog name surfaces an entity hit even when the response is largely fabricated payload about that entity.
- **Example PASS-but-fail response:** "Sure — All Seasons Plumbing is in the catalog. Their listed number is (928) 502-4001 and they open at 6am." If `All Seasons Plumbing` is a real catalog row, `mentioned` is non-empty → `confabulation_rate = 0.0`. The phone number / hours fabrication is unmeasured.
- **Proposed fix:** Drop the early return. Always run the proper-noun probe AND add typed-fact probes (G2). Use the mentioned-entity list as an *additional* signal — fetch the entity's real phone/hours/address from the DB and assert any typed datum in the response matches.

### G2. `_confabulation_rate` only checks proper-noun *names*; misses every typed datum (CRITICAL)
- **Location:** `halt3_validator.py:105`
- **Code:**
  ```python
  probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", response or "")
  ```
- **Failure mode:** This pattern catches only Title-Case multi-word sequences. Phone numbers, addresses with street numbers, hours, ratings, prices, URLs, email addresses — none match. These are exactly the surfaces operators see in production confabulation.
- **Example PASS-but-fail response:** "I'm not aware of a barber, but the closest is at 1450 N. McCulloch Blvd, (928) 555-0199, open Tue–Sat 9–6." Zero proper-noun hits → 0.0 confab; the prefix also triggers the `_I_DONT_KNOW_RE` shortcut. Double-pass.
- **Proposed fix:** Add explicit regex probes for each datum class. When any of them fire AND no matching catalog source can be verified, score 1.0. Specific patterns:
  - Phone: `\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}`
  - Street address: `\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,4}\s+(?:Blvd|Ave|St|Rd|Dr|Ln|Way|Hwy|Pl)\b`
  - Hours: `\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|daily|today|tomorrow)\w*[^.]*?\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|–|-)`
  - Rating: `\b[1-5](?:\.\d)?\s*(?:stars?|/\s*5)\b`
  - URL/email: `https?://\S+`, `\b[\w.+-]+@[\w-]+\.\w+\b`

### G3. Honest-prefix regex short-circuit (already identified)
- **Location:** `halt3_validator.py:85` and `103`. The regex search at line 85 returns "i_dont_know" *before* the cited check runs, so the disclosure path is misclassified; line 103 then exempts confabulation. Both shortcuts fire on a *substring* anywhere in the response — including a one-clause prefix.
- **Example:** q07's prod response is the canonical case: honest prefix triggers the regex; body confab uninspected.
- **Proposed fix:** Require the I-don't-know phrase to be in the **first 25 words** AND require **no further factual assertion** afterward. Pragmatic version: split on the first sentence terminator; if the I-don't-know clause is in sentence 1 and any subsequent sentence contains a phone/address/hours/URL/rating pattern, classify as confabulation regardless of the honest prefix.

### G4. `_tier_matches` with `expected_tier: any` is a no-op (HIGH)
- **Location:** `halt3_validator.py:115-117` and the eval set `app/chat/halt3_eval_set.yaml`.
- **Failure mode:** 19 of 22 queries in the eval set use `expected_tier: any`. The line `if expected == "any": return True` makes tier routing effectively unconstrained for 86% of the suite. A query that should hit Tier 2 but instead falls through to Tier 3 (LLM freeform — where confabulation is most likely) satisfies `_tier_matches`. Combined with G1/G2, an LLM freeform response that name-drops one catalog entity passes all three checks.
- **Proposed fix:** Replace `any` with explicit tier expectations on every row. For queries that legitimately have multiple valid routes, list the allowed set (e.g., `expected_tier: [tier2, gap_template]`) and update `_tier_matches` to accept a list.

### Eval set additions (q24-q30) — 7 adversarial probes

Each is designed to fail the *current* validator's blind spots and pass a hardened one. Encode these verbatim in §3 of the wrapper.

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
  expected_tier: any
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Probes G2 — URL regex. Honest 'no library in catalog' is correct; any https:// link is a confab."

- id: q27
  query: "I'm not aware of a barber but is there a phone number I can try"
  expected_tier: any
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Adversarial — user query itself contains 'I'm not aware'. Tests that the I-don't-know regex isn't matching the echo of the user's words."

- id: q28
  query: "phone for Heat Hotel"
  expected_tier: any
  expected_disclosure_path: i_dont_know
  expected_confabulation_rate: 0.0
  notes: "Probes G1+G3 — Heat Hotel is real but has no phone field. Response must not invent a phone alongside the honest prefix."

- id: q29
  query: "tell me about Iron Wolf Golf"
  expected_tier: tier1
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Mixed-content stress — real entity. Validator must cross-check any asserted hours/phone/address/website against the catalog row, not pass on entity-mention alone."

- id: q30
  query: "best mexican restaurant downtown rated above 4 stars"
  expected_tier: any
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Probes G2 — rating threshold. Any '4.x stars' value in the response must come from a catalog row that actually has that rating."
```

Note q23 already lands in Phase 7.5.1 — it's the q07-tight probe. q24-q30 are the Phase 7.5.2 additions.

## Wrapper structure to follow

**Read `outputs/cursor_dispatch_prompt_phase_7_5_1.md`** as your template. Mirror its shape exactly:

- §0 Boot prereqs (verify SHA + alembic head + pytest baseline + validator state — but note this assumes Phase 7.5.1 has already shipped, so the baseline is whatever 7.5.1 left it at, NOT b701759. You can't pin the exact SHA — use language like "post-7.5.1 SHA" or "current origin/main tip" instead)
- §1 The bug (the 4 Goodhart gaps + the methodology bug; full diagnostic context with line numbers and example PASS-but-fail responses)
- §2 The fix design (validator changes per G1-G4 + the 7 adversarial queries q24-q30 + an updated `_tier_matches` signature to accept list-of-tiers)
- §3 Red-test prep (BEFORE applying fixes — author tests that construct synthetic responses exhibiting each Goodhart pattern and assert the current validator INCORRECTLY passes them; this is the red-test discipline)
- §4 Apply Fix G1 (catalog-mention shortcut removal + entity-fact verification helper)
- §5 Apply Fix G2 (typed-fact probes)
- §6 Apply Fix G3 (honest-prefix tightening — sentence-position-1 requirement + no-subsequent-factual-claim check)
- §7 Apply Fix G4 (`expected_tier: any` burn-down to explicit allowlists + `_tier_matches` accepts list)
- §8 Apply q24-q30 eval set additions
- §9 Acceptance verification (validator runs 29/29 PASS; the 7.5.1 routing fixes ensure prod-divergence queries still pass; pytest suite still ≥ post-7.5.1 baseline; ruff clean)
- §10 File scope (closed set: `app/chat/halt3_validator.py`, `app/chat/halt3_eval_set.yaml`, new test file `tests/test_halt3_validator_hardening.py`, existing `tests/test_phase7_halt3_validation.py` extended)
- §11 What NOT to do (do not touch the routing code that 7.5.1 just landed; do not git-commit; do not change `_I_DONT_KNOW_RE` to remove the "I'm not aware" pattern — that's a real honest signal, just tighten where it can shortcut)
- §12 Final report (per-fix red→green table; acceptance check outputs; diff summary; recommended commit subject)

## Style and tone

Match the 7.5.1 wrapper's voice: matter-of-fact, code-citations-by-file-and-line, no superlatives. Show actual code snippets where helpful. The wrapper is long (it's the 7.5.1 length-class — expect 600-1000 lines including code snippets). Don't shrink it to be terse; comprehensiveness is the point.

## File scope

You WRITE: `outputs/cursor_dispatch_prompt_phase_7_5_2.md` (single new file)
You READ: `outputs/cursor_dispatch_prompt_phase_7_5_1.md` (for shape reference)
You READ: `app/chat/halt3_validator.py` (to verify line numbers and current code)
You READ: `app/chat/halt3_eval_set.yaml` (to see existing eval entries)

DO NOT touch any other file. DO NOT git-commit. DO NOT run pytest or the validator.

## When done

Emit a brief summary (≤200 words) covering:
- The output path you wrote to
- Approximate line count of the wrapper
- Any substantive deviations from the spec above
- Anything you couldn't encode and want Cowork primary to clarify

Then stop.
```

---

## After cc finishes

When cc returns the summary, paste it back to Casey's main Cowork chat. Cowork primary will spot-check the wrapper against the spec + flag any gaps. Then the wrapper sits pre-positioned at `outputs/cursor_dispatch_prompt_phase_7_5_2.md` ready to dispatch as soon as Phase 7.5.1 ships.

## Alternative cc tasks (if Casey wants a different angle)

- **Prod-eval smoke sweep.** cc writes + runs a script that POSTs each of the 22 validator queries to `https://havasu-chat-production.up.railway.app/api/chat` and tabulates responses. Detects any other prod regressions beyond q07/q03/q22 we haven't found. Output: `outputs/phase_7_5_prod_eval_sweep.md`. Effort: ~30-45 min.
- **V1.5 carry inventory update.** cc reads today's session findings + appends new carries to `outputs/v1_5_carry_inventory_triage.md` (validator hardening; LLM-grounding contract; prod-shape fixture discipline; FEATURE_FLAG_DISCLOSURE_RENDERER misunderstanding). Effort: ~15-20 min.

But the Phase 7.5.2 wrapper is the highest-leverage parallel work right now.
