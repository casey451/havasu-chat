# Phase 7.7 design memo — honest tier-2 empty listing on open_now zero-rows

> **What this is:** scoping memo for Phase 7.7, the next-up lane after Phase 7.6 shipped (`975e83f` + docs `19b6c8f` / `44ca1c6`). Closes the residual q03 UX issue: the Phase 7.6 shortcut now fires deterministically, but the prod catalog has restaurants populated **without** `hours_structured` / `google_hours` data, so `tier2_db_query._query_providers` returns zero rows under the `open_now=True` filter. The handler at `tier2_handler.py:184` then falls through to the LLM parser path, which still routes to tier-3 (~4s, `golakehavasu.com` redirect). Phase 7.7 closes that fallback with a deterministic tier-2 "honest empty listing" template — instant response, no LLM call, honest about the data gap.
>
> **Authored by:** Cowork primary via sub-agent, 2026-05-20, post-Phase-7.6-ship.
>
> **Companion docs:**
> - `outputs/phase_7_5_prod_divergence_investigation.md` (post-mortem; q03 root-cause chain through 7.5.1 → 7.6 → 7.7)
> - `outputs/phase_7_6_tier2_llm_parser_design_memo.md` (the 7.6 scoping memo this one extends)
> - `outputs/cursor_dispatch_prompt_phase_7_6.md` (the shipped 7.6 dispatch — `975e83f`)
> - Three-probe prod diagnostic 2026-05-20 (in-conversation; confirms restaurants present + no hours data + tier-3 cascade)
>
> **Status:** design-only; Cursor dispatch wrapper authored in parallel at `outputs/cursor_dispatch_prompt_phase_7_7.md`.

---

## §1 Root cause hypothesis

**HIGH confidence (smoke-confirmed 2026-05-20 via three-probe prod diagnostic):**

1. Phase 7.6's `_OPEN_NOW_LISTING_RE` correctly matches `"what restaurants are open now"` and returns `Tier2Filters(category="restaurant", open_now=True, parser_confidence=0.9, fallback_to_tier3=False)` — verified by /api/chat latency drop 23s → 4s.
2. `tier2_db_query.query` is reached with those filters. The provider branch (`_query_providers_orm`) finds restaurants by category match.
3. The Python-side `open_now` filter at `tier2_db_query.py:1092-1099` then runs `effective_hours_structured(p) AND is_open_at(hs, now_local)` against each row.
4. Prod catalog restaurants are populated **without** `hours_structured` JSON (legacy migration source did not include hours; ENTITY `hours` rows haven't been backfilled). `effective_hours_structured(p)` returns None/empty → every row is filtered out → `prov_orm = []` → final `_merge_simple` returns `[]`.
5. `tier2_handler.try_tier2_with_usage` hits `if len(rows) == 0:` at line 184 and returns `(None, None, None, None)`.
6. Router cascades to tier-3 LLM, which emits the generic `golakehavasu.com` redirect.

Net UX: 4s wait for a tier-3 cascade that adds no value over an instant honest tier-2 reply.

**Independent of V1.5 hours backfill.** Even after the backfill ships, this template still serves as graceful degradation for any future category whose hours data is sparse (vets at odd hours, seasonal businesses, newly added providers).

---

## §2 Proposed fix

**Recommend Path A — honest tier-2 empty listing on shortcut-shape zero-rows.** Inside `try_tier2_with_usage`, when `_query_providers` returns zero rows AND the filters carry the q03-style shape (`open_now=True AND category is not None`), return a deterministic tier-2 response with an honest-empty template body. Zero LLM tokens, zero further routing.

### Trigger condition

```
filters.open_now is True
AND filters.category is not None
AND len(rows) == 0
```

Fires for BOTH shortcut-built filters (Phase 7.6) AND parser-built filters of the same shape. That is intentional: the user-intent signal is "I asked which open-right-now X exist" regardless of which upstream parser produced the filter object. The shortcut sets both `open_now=True` and `category=...`; the LLM parser sometimes sets `open_now=True` with `category=None` for recommendation phrasings — those will NOT trigger the template (which is correct; they should still defer to the LLM formatter / tier-3).

### Code sketch (verified against `app/chat/tier2_handler.py` lines 158-186)

The shortcut branch's existing rows-empty fall-through (lines 167-169) currently logs `"business-listing shortcut hit (zero tokens)"` only when `render_business_listing` returns a non-None string, and **separately** logs `"shortcut shape matched but no provider rows; falling through"` otherwise. Insert the honest-empty guard between those two paths:

```python
# app/chat/tier2_handler.py — inside try_tier2_with_usage, replacing the
# existing rows-empty fall-through at lines 164-169.
        text = tier2_business_shortcut.render_business_listing(
            rows, shortcut_filters.category or ""
        )
        if text is not None:
            logging.info("tier2_handler: business-listing shortcut hit (zero tokens)")
            return text, 0, 0, 0
        # Phase 7.7 — honest empty listing: shortcut matched, DB has rows of
        # the requested category, but the open_now Python-side filter dropped
        # them all (no hours_structured / google_hours data yet). Emit a
        # deterministic honest reply instead of cascading to the LLM parser.
        if shortcut_filters.open_now and shortcut_filters.category:
            logging.info("tier2_handler: open_now zero-rows; emitting honest empty listing")
            return (
                _open_now_empty_listing(shortcut_filters.category),
                0,
                0,
                0,
            )
        # Shortcut matched the shape but returned no provider rows — fall through to the
        # LLM path so the user still gets a useful answer.
        logging.info("tier2_handler: shortcut shape matched but no provider rows; falling through")
```

A second insertion point at the **LLM-parser** zero-rows branch (`tier2_handler.py:184`) covers the parser-path equivalent of the same shape:

```python
    rows = tier2_db_query.query(filters, ctx=chat_ctx)
    if len(rows) == 0:
        if filters.open_now and filters.category:
            logging.info(
                "tier2_handler: parser-path open_now zero-rows; emitting honest empty listing"
            )
            return _open_now_empty_listing(filters.category), p_in or 0, p_in or 0, 0
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None
```

(Token accounting for the parser-path return: the parser call already happened, so its `p_in` / `p_out` are non-zero. Carry them through honestly rather than hide them as zero-token.)

### Template body (chosen phrasing, see §5(c) for tradeoff)

```python
_OPEN_NOW_EMPTY_LISTING_TEMPLATE = (
    "I have {category_label} in the Lake Havasu catalog, but I don't have "
    "current hours data for them yet — so I can't tell you which are open "
    "right now. Try https://www.golakehavasu.com/ for a hours-aware listing, "
    "or share a Google Business page at /contribute and I'll fill the gap."
)
```

`{category_label}` plurals via the existing `_pluralize_for_header` helper from `tier2_business_shortcut.py` (re-importable, no new helper needed) so `"restaurant"` → `"restaurants"`, `"coffee shop"` → `"coffee shops"`. No count query — see §5(c).

### Rejected alternative — `Tier2Filters.from_shortcut` flag

Considered threading a boolean `from_shortcut: bool = False` field through `Tier2Filters` so the handler could distinguish shortcut-built filters from LLM-parser-built filters and only fire the template for the former. **Rejected** because:

(a) The `open_now=True AND category is not None` signal alone is sufficient to identify "user asked for currently-open X" intent. The filter's provenance is incidental.

(b) Threading a new flag bloats `Tier2Filters` (already 14 fields + 4 validators) without payoff. The schema is the wire format between the LLM parser and downstream consumers; adding source-tracking fields invites every future shortcut to claim its own bit.

(c) Path A's guard (`open_now AND category`) fails closed: a parser-built filter without a category cannot match, and a recommendation-shape parser output that legitimately omits category falls through to tier-3 as it does today.

---

## §3 Effort estimate

**S (~30-50 LOC + 4-6 tests, ~1-1.5h Cursor session).** One template constant + one helper function + two ~3-line conditional insertions in `tier2_handler.py` + four unit tests + one integration test in `tests/test_tier2_handler.py`. Smaller than Phase 7.6 (~80-150 LOC). No schema change, no migration, no prompt edits.

---

## §4 Sequencing

**File scope (gotcha #18):** Phase 7.7 touches:
- `app/chat/tier2_handler.py` (template constant + helper + two conditional insertions)
- `tests/test_tier2_handler.py` (new tests; file exists, verified at `tests/test_tier2_handler.py` per repo listing)

**Zero overlap with parallel-eligible lanes:**
- Phase 7.5.3 wrapper (validator polish — `app/chat/halt3_validator.py` + `halt3_eval_set.yaml`): disjoint.
- Phase 7.5.4 (G4 list-promiscuity + template-echo audit — `app/chat/halt3_validator.py`): disjoint.
- Phase 8a wrapper (`app/conditions/*` + condition-template surfaces): fully disjoint.

**Soft note on `_UNKNOWN_ENTITY_GAP` co-location:** the Phase 7.5.1 honest-empty constant `_UNKNOWN_ENTITY_GAP` lives in `app/chat/unified_router.py:105`. Phase 7.7's new template could live there for style symmetry, OR it could live in `tier2_handler.py` next to the insertion points. **Recommend keeping it in `tier2_handler.py`**: the template is conceptually a tier-2 reply (not a gap-template reply — the catalog has the category, just not its hours), and co-locating with the trigger keeps both the constant and its conditional in one diff hunk. Co-locating with `_UNKNOWN_ENTITY_GAP` would also nudge Phase 7.5.3 (Lane K) into soft conflict over `unified_router.py`. Path A keeps lanes fully disjoint.

**Parallel-eligible with all queued lanes.** Could ship before Lane K returns or after; ordering is operator preference.

---

## §5 Risks

**(a) Over-trigger.** If `open_now=True` is set by the LLM parser on a legitimately-borderline recommendation phrasing where the catalog has rows but those rows happen to lack hours data, the template would also fire and replace what could have been a tier-3 useful answer.
- **Mitigation:** require `filters.category` is set in addition to `filters.open_now=True`. The LLM parser sometimes sets `open_now=True` with `category=None` for shapes like `"anywhere open right now"`; those continue to fall through to the LLM-parser path as today. The Phase 7.6 shortcut always sets both, so all shortcut-built filters with zero rows fire the template.
- **Residual risk:** an LLM-parser output that sets BOTH `open_now=True` AND `category=...` AND lands on a legitimately-zero-rows query that would have produced useful tier-3 prose. Low likelihood; the user explicitly asked for "X open now" and there are zero X open now — the honest template is at worst neutral.

**(b) Template wording — bounce rate.** If the body is too apologetic or routes users to a competitor URL too aggressively, users may bounce instead of contributing.
- **Mitigation:** chosen phrasing leads with what we DO have ("I have restaurants in the Lake Havasu catalog") before the gap ("but I don't have current hours data"), then offers TWO paths: `golakehavasu.com` (external; preserves the existing 7.5.1 redirect convention) AND `/contribute` (internal; lets users fill the gap). Mirrors the `_UNKNOWN_ENTITY_GAP` voice — direct, honest, dual-CTA.
- **Three candidate phrasings considered:**
  1. *"I don't have current hours data for restaurants yet. Try golakehavasu.com or share a Google Business page at /contribute."* — too terse; doesn't acknowledge we have the businesses.
  2. *"Sorry, I can't tell you which restaurants are open right now — my hours data is incomplete. Check golakehavasu.com for live listings."* — too apologetic; "sorry" undermines the honest framing.
  3. **CHOSEN:** *"I have restaurants in the Lake Havasu catalog, but I don't have current hours data for them yet — so I can't tell you which are open right now. Try golakehavasu.com for a hours-aware listing, or share a Google Business page at /contribute and I'll fill the gap."* — leads with what we have, explains the gap precisely, dual CTA, ends on an inviting note.

**(c) Counting providers — latency vs. specificity.** A more specific template ("I have **18** restaurants in the catalog…") requires a count query, adding one SQL roundtrip. At current scale (<100 providers per category) the cost is sub-millisecond, but the count adds nothing the user can act on — `golakehavasu.com` is the answer either way.
- **Recommendation:** skip the count. The chosen phrasing uses an indefinite plural ("I have restaurants…") which reads naturally and avoids the SQL roundtrip + the off-by-one edge cases at the 0-or-1 boundary.
- **Alternative:** if user testing surfaces "this feels generic — does Havasu actually have restaurants?", a follow-up phase can add a count gated behind a feature flag.

---

## §6 Files referenced

- `app/chat/tier2_handler.py` lines 131-215 (`try_tier2_with_usage`); insertion points at 164-169 (shortcut zero-rows) and 183-186 (parser-path zero-rows).
- `app/chat/tier2_business_shortcut.py` lines 75-81 (`_OPEN_NOW_LISTING_RE` — read-only reference); lines 265-285 (`_pluralize_for_header` — import target); lines 299-348 (`try_business_listing_shortcut` — read-only reference).
- `app/chat/tier2_schema.py` lines 80, 83-84 (`open_now`, `parser_confidence`, `fallback_to_tier3` fields).
- `app/chat/tier2_db_query.py` lines 1015-1016 (`_query_providers`), 1067-1102 (`query` entry), 1092-1099 (Python-side `open_now` filter — the line that drops rows in prod).
- `app/chat/unified_router.py` line 105 (`_UNKNOWN_ENTITY_GAP` — style reference, not modified).
- `tests/test_tier2_handler.py` (file exists; insertion target for new tests).
- `tests/test_tier2_open_now.py` lines 58-110 (canonical `hours_structured` fixture pattern; read-only reference).

---

## §7 Recommended next step

Phase 7.7 Cursor dispatch wrapper authored in parallel at `outputs/cursor_dispatch_prompt_phase_7_7.md`. Dispatch when Phase 7.6 ledger commits have landed on `origin/main` (currently `44ca1c6` — verified) and Lane K (Phase 7.5.3 Cursor wrapper) has either returned or been deferred.

If Lane K is still pending at dispatch time, Phase 7.7 is still safe to ship — its file scope is fully disjoint. Soft preference: Lane K first if it's close, to keep validator-counter (q01-q30) clean before the new template lands.

---

*Authored by sub-agent under Cowork primary supervision, 2026-05-20 post-Phase-7.6-ship. Saved to `outputs/phase_7_7_honest_empty_listing_design_memo.md`.*
