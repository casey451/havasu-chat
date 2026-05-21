# Phase 7.6 design memo — tier-2 LLM-parser divergence fix

> **What this is:** scoping memo for Phase 7.6, the next-up lane after Phase 7.5.2 ships. Closes the residual q03 issue from Phase 7.5.1 (q03 routes to tier-3 LLM on prod with 23s latency instead of tier-2 cited list, despite catalog being populated).
>
> **Authored by:** Cowork primary via sub-agent A, 2026-05-19, post-Phase-7.5.1-ship.
>
> **Companion docs:**
> - `outputs/phase_7_5_prod_divergence_investigation.md` (post-mortem; q03 root cause documented in §3)
> - `outputs/cursor_dispatch_prompt_phase_7_5_1.md` (the routing-fix dispatch — already SHIPPED `fd695d2`)
> - `outputs/cursor_dispatch_prompt_phase_7_5_2.md` (the validator-hardening dispatch — queued)
>
> **Status:** design-only; no Cursor wrapper authored yet. Use this memo as input when authoring the Phase 7.6 dispatch wrapper.

---

## §1 Root cause hypothesis (ranked)

**H1 — Haiku non-determinism on a borderline shape (most likely).** The `tier2_parser.parse` prompt's only OPEN_NOW few-shots are softer phrasings (`"Where can I grab dinner right now?"`, `"Anywhere open for a workout this late?"`). `"what restaurants are open now"` is a category-listing question with `open_now` rather than a recommendation; the system prompt has no example of that shape. With `temperature=0.3` and Haiku's smaller model, prod runs land on one of:

- `fallback_to_tier3=True` (parser thinks it's vague)
- `parser_confidence<0.7` (sub-threshold for tier-2 to commit)
- `category=null` with only `open_now=true` (which fails the post-fetch category match)
- `category="restaurant"` that matches locally but is filtered out post-fetch on prod by `_category_match_provider` (prod catalog's `google_primary_category` strings may not include "restaurant" in the synonym group for all eat-drink rows)

Evidence: local dev returns cited rows; prod hits tier-3. Exact same input, exact same code path → divergence vector is the LLM call output, not the DB layer.

**H2 — 23s latency = Haiku timeout/retry then tier-3 cascade (likely).** `tier2_parser.parse` calls `call_anthropic_messages` with `max_tokens=300, temperature=0.3` and the date-context prepend doubles prompt length. If Anthropic throttled or the call retries, you get a several-second tier-2 attempt, then a tier-3 Sonnet/Opus call on top. The `llm_tokens_used=0` in the prod metric is misleading — `try_tier2_with_usage` returns `(None, None, None, None)` on every fallback path (parser error, refused, low confidence, no matches) and the router records 0 from tier-2 even though Haiku was actually billed. So the metric understates tier-2 work; the 23s contains real Haiku latency.

**H3 — Category-slug normalization difference (less likely).** `_category_match_provider` runs against `Provider.category` + `Provider.google_primary_category` with `_normalize_for_match` (lowercase + underscore→space). The match is identical on SQLite and Postgres. Ruled out for this query as the dominant cause, but worth a spot-check: prod's eat-drink providers may have `google_primary_category` strings that don't include "restaurant" in the synonym group.

**Most likely chain:** H1 (parser returns `fallback_to_tier3=True` or `parser_confidence<0.7`) → `try_tier2_with_usage` returns `None` → router cascades to tier-3 → 23s latency from both LLM calls → tier-3 emits Phase 7.5.1 honest-no-data response.

---

## §2 Proposed fix

**Recommend Path A — extend the shortcut to cover OPEN_NOW + category listings.** Bypasses the divergence vector entirely (zero LLM tokens, deterministic).

### Touch points

- **`app/chat/tier2_business_shortcut.py`** — add a second regex `_OPEN_NOW_LISTING_RE` matching shapes like:

  ```python
  _OPEN_NOW_LISTING_RE = re.compile(
      r"^what\s+(?:restaurants?|cafes?|coffee\s+shops?|bars?|"
      r"pharmacies|vets?|veterinarians?|stores?|shops?|gyms?)\s+"
      r"(?:are\s+)?open\s+(?:now|right\s+now)$",
      re.IGNORECASE,
  )
  ```

  On match, build `Tier2Filters(category=<extracted>, open_now=True, parser_confidence=0.9, fallback_to_tier3=False)`. Call this **before** `_LISTING_PREFIX.match` in `try_business_listing_shortcut`. Reuse the existing `_EVENT_SHAPE_TOKENS` guard and 3-word cap on the extracted category.

- **`app/chat/tier2_handler.py`** — no change; existing shortcut wiring already passes filters through `_query_providers` which honors `open_now`.

- **Tests** — `tests/chat/test_tier2_business_shortcut.py` add:
  - `test_open_now_listing_shortcut_matches_q03`
  - `test_open_now_listing_shortcut_returns_filters_with_open_now_true`
  - Negative case: `test_open_now_listing_skips_when_event_shape_present` (e.g. "what restaurants are open tonight" should defer — `tonight` is in `_EVENT_SHAPE_TOKENS`)
  - Integration test: `try_tier2_with_usage("what restaurants are open now")` returns non-None text with zero tokens.

### Path B rejected

A deterministic category-keyword fallback **after** the LLM-parser returns None was considered but rejected: it adds a second decision point that's hard to test deterministically and shadows legitimate tier-3 disambiguation. Path A's regex is narrow enough to fail closed.

### Regression risk

Low. The new regex requires both a category noun AND `open now`/`right now` phrasing — much tighter than `_LISTING_PREFIX`. Existing shortcut tests should be unaffected. Worst case: a query like "what stores are open now" that has no matching rows falls through to LLM path via existing rows-empty fallback in `try_tier2_with_usage` (line 184).

---

## §3 Effort estimate

**S (~80-150 LOC + tests).** Smaller than Phase 7.5.1 (~200 LOC). One regex constant, one extraction helper, ~5 test cases. **~1-2 hour Cursor session.**

---

## §4 Sequencing

**Phase 7.6 is parallel-eligible with Phase 7.5.2.** File-scope check (gotcha #18):

- **Phase 7.5.2 touches:** `app/chat/halt3_validator.py`, `app/chat/halt3_eval_set.yaml`, validator-adjacent tests.
- **Phase 7.6 touches:** `app/chat/tier2_business_shortcut.py`, `tests/chat/test_tier2_business_shortcut.py`, possibly `tests/chat/test_tier2_handler.py`.

Zero overlap. They can run concurrently in separate Cursor sessions.

**Recommendation:** ship 7.5.2 first (validator hardening is more urgent — it gates how 7.6's improvement gets measured by allowing the hardened validator to detect q03's tier-2-vs-tier-3 routing in CI), then 7.6.

If parallel velocity matters more than measurement, they CAN run concurrently — but post-ship, the q03 hardening test in 7.5.2's eval set should be re-pinned from `expected_tier: tier2` (proposed) to actually-tier-2 once 7.6 lands.

---

## §5 Risks

- **Shortcut over-trigger** — mitigated by requiring `open now`/`right now` phrasing AND a category noun from an explicit allow-list. A query like "what bars are open later" won't match (no "now"/"right now").
- **Empty-result fallback** — if extracted category has no matching providers in prod catalog, the existing `rows == 0` fall-through (`tier2_handler.py:184`) catches it and Haiku still runs. Net: no worse than today.
- **Shadow tier-3 disambiguation** — non-issue. These shapes are unambiguous category listings; the LLM was adding latency, not value.
- **Category synonym coverage** — the regex's noun allow-list must align with `_category_needle_set` so "vets" resolves to veterinarian providers. Add `vets?|veterinarians?` to the regex AND verify `_category_synonyms` maps them correctly; tests should cover at least restaurants, vets, pharmacies.

---

## §6 Files referenced

- `app/chat/tier2_handler.py` lines 131-215 (fallback paths)
- `app/chat/tier2_parser.py` lines 23-75 (LLM call)
- `app/chat/tier2_business_shortcut.py` lines 37-70 (prefix), 256-290 (entry)
- `app/chat/tier2_db_query.py` lines 1067-1102 (query entry), 1092-1099 (open_now python filter)
- `app/chat/entity_intent.py` lines 151-154 (`is_category_open_now_listing`)
- `prompts/tier2_parser.txt` lines 69-73 (only OPEN_NOW few-shots in current prompt)
- `app/chat/tier2_schema.py` (`Tier2Filters` shape)

---

## §7 Recommended next step

Hand this memo to a Cowork session OR to `cc` to author the actual Phase 7.6 dispatch wrapper. The wrapper should mirror Phase 7.5.1's structure (§0-§12) and pin to a post-7.5.2 SHA.

When authored, the wrapper lives at `outputs/cursor_dispatch_prompt_phase_7_6.md`.

---

*Authored by sub-agent A under Cowork primary supervision, 2026-05-19 post-Phase-7.5.1-ship. Saved to `outputs/phase_7_6_tier2_llm_parser_design_memo.md`.*
