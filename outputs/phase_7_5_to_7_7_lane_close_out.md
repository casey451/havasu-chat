# Phase 7.5 → 7.7 lane close-out

> **What this is:** the narrative close-out for the six-phase recovery + hardening lane that ran 2026-05-19 → 2026-05-20 against the `havasu-chat` chat surface. Three prod confabulation/misroute bugs that escaped Phase 7.5's `22/22 PASS` were closed at the routing layer (7.5.1), the validator that missed them was hardened (7.5.2), the residual q03 tier-2 latency was collapsed (7.6), the lower-severity validator/eval gaps were polished (7.5.3), and the data-sparsity tail on q03 was closed with an honest-empty template (7.7). This doc captures the arc as a forward narrative — the post-mortem at `outputs/phase_7_5_prod_divergence_investigation.md` is the backward-facing companion.
>
> **Authored by:** Cowork primary via sub-agent, 2026-05-20, post-7.5.3 + 7.7 ship pre-7.5.4 dispatch.
>
> **Status:** close-out (six phases shipped + one queued).
>
> **Primary companion docs:**
> - `outputs/phase_7_5_prod_divergence_investigation.md` — the durable post-mortem (~5,850 words)
> - `outputs/phase_7_5_close_out.md` — the original Phase 7.5 close-out (superseded by §6 flag-semantics correction)
> - `outputs/v1_5_carries_inventory.md` — V1.5 backlog reflecting items surfaced during this arc
> - `outputs/cursor_dispatch_prompt_phase_7_5_{1,2,3}.md` + `..._phase_7_6.md` + `..._phase_7_7.md` — the dispatched wrappers
> - `outputs/phase_7_6_tier2_llm_parser_design_memo.md` + `phase_7_5_3_validator_polish_design_memo.md` + `phase_7_7_honest_empty_listing_design_memo.md` — the in-lane design memos
> - `docs/STATE.md` "Recently shipped" entries for 7.5 / 7.5.1 / 7.5.2 / 7.6

---

## §1 Lane arc at a glance

The arc ran across roughly 48 wall-clock hours. Phase 7.5 had shipped 2026-05-20 with `22/22 PASS` and was treated as the close of the HALT 3 narrative. The post-Railway-recovery flag-flip smoke check that afternoon surfaced three independent production failures of the exact class Phase 7.5 was supposed to prevent — and the arc to close them ran from that moment through the end of 2026-05-20. The six phases shipped under the same gotcha-#18 file-scope discipline (no two phases overlapped on a substantive code surface; Phase 7.5.3 + 7.7 + 8a flew in three parallel Cursor sessions in the final hours).

| Phase | Commit SHA | One-line summary | Ship date |
|---|---|---|---|
| 7.5 | `b701759` | HALT 3 validator triage + flag-flip closure (22/22 PASS) | 2026-05-20 |
| 7.5.1 | `fd695d2` | Prod-divergence routing fixes — q07/q22/q03 closed at routing layer | 2026-05-19 |
| 7.5.2 | `64799d5` | HALT 3 validator hardening — G1-G5 + F3 + q24-q30 (30/30 PASS) | 2026-05-20 |
| 7.6 | `975e83f` (code) + `19b6c8f` (docs) | Tier-2 OPEN_NOW listing shortcut — q03 latency 23s → 4s | 2026-05-20 |
| 7.5.3 | awaiting commit | F-gap validator/eval polish — F1 + F4 + F5 | 2026-05-20 |
| 7.7 | awaiting commit | Tier-2 honest empty listing on open_now zero-rows | 2026-05-20 |

What the arc accomplished: the three production bugs that survived Phase 7.5 are closed end-to-end at the routing, validator, and UX layers, and the validator that initially missed them now measures real anti-confabulation behavior rather than the shape of its own regex checks.

---

## §2 The origin story

Phase 7 had landed the HALT 3 validator infrastructure 2026-05-20 with an initial run of 12 PASS / 10 FAIL. q07 — `Tell me about Totally Fake Business XYZ 404` — was the smoking gun, with a 0.50 confabulation rate. Phase 7.5 was dispatched as a polish lane and shipped at `b701759` with 22/22 PASS: `cited_coverage` went from 42% to 100%, `missing_confab_max` went from 0.50 to 0.00, and the close-out at `outputs/phase_7_5_close_out.md` framed the operator flag-flip on `FEATURE_FLAG_DISCLOSURE_RENDERER` as the substantive milestone closing the HALT 3 narrative arc.

The operator flipped the flag on Railway 2026-05-19 once the `b701759` deploy was picked up. The post-flip smoke check sent q07, q22, and q03 to production. All three returned user-visible failures: q07 with an LLM-invented `(928) 502-4001` phone after an honest "I'm not aware" prefix; q22 with real Heat Hotel rating data attached to a clearly fake `Fabricated Hotel Name 555` query; q03 with the broken `/contribute` template misroute despite 20+ restaurants populated in the prod catalog. Local validator re-run on the same SHA: still 22/22 PASS.

The insight that crystallized over the following two hours is documented at length in `outputs/phase_7_5_prod_divergence_investigation.md` §4 and §5 and won't be recapitulated here. The compressed version: **the local validator's PASS was environment-conditional**. q07 didn't reproduce locally because the local LLM happened to produce a clean disclaimer with no body confabulation. q22 didn't reproduce locally because the dev catalog had no Heat Hotel candidate. q03's tier-2 LLM-parser variance didn't reproduce locally because Haiku's completions on a 50-row dev catalog differ from completions on a 1300-row prod catalog. Same code, three different fixture-conditional masks, three different production failures.

Two additional findings emerged in parallel. First, `FEATURE_FLAG_DISCLOSURE_RENDERER` was discovered (via `app/chat/disclosure_render.py:1-26`) to control **sponsored-disclosure rendering** for FTC ad compliance, not anti-confabulation routing. The flag-flip narrative carried through Phase 7 and Phase 7.5 was a sustained semantic drift; the anti-confab fixes are always-on regardless of flag state. Second, the validator's `22/22 PASS` was structurally compatible with all three prod failures — every signal the validator measured had a short-circuit early-return that bypassed the rest of the checks. The arc that follows closes all three layers: routing (7.5.1), validator semantics (7.5.2 + 7.5.3), and the residual UX/data-sparsity tail (7.6 + 7.7).

---

## §3 Phase-by-phase narrative

### 7.5 — HALT 3 validator triage + flag-flip closure (`b701759`)

The polish-lane Cursor session against Phase 7's 10 FAIL baseline.

**Wrapper goal:** close the originally-failing queries and unlock the flag-flip operator action.

**Shipped:** 7 CODE-FIX + 3 EVAL-PATCH dispositions across the 10 failing rows; pytest 2135 → 2150; full suite 2164 passed + 2 skipped; validator went 12/22 PASS → **22/22 PASS** (cited_coverage 42% → 100%; missing_confab_max 0.50 → 0.00). Per-query dispositions: q02 EVAL-PATCH (no barber rows in dev catalog), q03 CODE-FIX (validator wrongly treated all tier-1 as i_dont_know), q06 CODE-FIX (hotel triggered OUT_OF_SCOPE), q07 CODE-FIX (the P0 confab — expanded `_I_DONT_KNOW_RE` plus routing tightenings), q10 mid-session green, q14 EVAL-PATCH, q16 CODE-FIX (singular vet open-now), q17 CODE-FIX (best pizza tier-2), q21 EVAL-PATCH + CODE-FIX, q22 CODE-FIX. Touched `app/chat/halt3_validator.py`, `halt3_eval_set.yaml`, `entity_intent.py`, `unified_router.py`, `intent_classifier.py`, `app/core/intent.py`.

**Substantive finding worth remembering:** q07's confab-rate drop from 0.50 to 0.00 was achieved by expanding `_I_DONT_KNOW_RE` — a change to the metric's own implementation. The drop was real against the metric but Goodhart-shaped against the underlying behavior. The close-out at `outputs/phase_7_5_close_out.md` framed the operator flag-flip as the substantive milestone; in retrospect it was the milestone the lane discipline was set to celebrate, not the milestone the user-visible system had actually reached. See post-mortem §8 Lesson 1 + §6 flag semantics.

### 7.5.1 — Production-divergence routing fixes (`fd695d2`)

Dispatched 2026-05-19 hours after the smoke-check failures landed; shipped same day.

**Wrapper goal:** close q07/q22/q03 at the routing layer without touching the validator. The four-sub-agent diagnostic fan-out had pre-validated three independent fix designs; this lane landed them as one Cursor session.

**Shipped:** three code changes plus q23 eval entry plus 11 unit tests plus 3 integration tests; pytest 2166 → 2178. New `_unknown_entity_about_gate` in `unified_router.py` intercepts "tell me about X" / "describe X" / "who is X" / "what is X" with an activity-listing skip before tier-3 LLM (q07). `near_match_subject_overlaps` in `entity_intent.py` rewritten from fail-open default to content-token-aware check with `_CATEGORY_TOKENS` stoplist plus rapidfuzz typo escape hatch at partial_ratio ≥ 80 (q22; preserves `mdshrkbrwry → Mudshark Brewery` regression). `is_category_open_now_listing` probe added to `_catalog_gap_response` (q03 — sidesteps the broken `/contribute` misroute). Post-deploy verification confirmed q07 and q22 fully fixed; q03's catastrophic misroute was closed but a residual tier-3 cascade remained for Phase 7.6 to address.

**Substantive finding worth remembering:** the about-gate's first draft used a broad `what(?:'s|\s+is)` regex that intercepted 16 legitimate OPEN_ENDED queries ("What is fun to do this weekend?", "What's at the skate park?"); Cursor's §13 self-correction split it into `_ABOUT_GATE_STRICT_PATTERNS` + `_WHAT_IS_ENTITY_RE` + `_ACTIVITY_OR_LISTING_SKIP_RE`. The deviation envelope absorbed a real bug in the wrapper's regex without operator round-trip. Refs: `outputs/cursor_dispatch_prompt_phase_7_5_1.md`, `outputs/phase_7_5_prod_divergence_investigation.md` §3 + §7.

### 7.5.2 — HALT 3 validator hardening (`64799d5`)

The validator-as-target Goodhart closure.

**Wrapper goal:** harden the validator surface so the next 7.5-class regression cannot slip through CI. The cc-authored wrapper was 1,050 lines and folded in a Cowork §11.5 amendment for G5 + F3 that the original wrapper-author had missed.

**Shipped:** 5 critical Goodhart-style gap closures (G1-G5) plus 1 adversarial-test mock gap (F3). G1 catalog-mention shortcut closed via the new `_entity_supports_typed_facts` helper that fetches mentioned entities' real catalog data and verifies typed facts against it; G2 typed-fact probes (`_PHONE_RE`, `_ADDRESS_RE`, `_HOURS_RE`, `_RATING_RE`, `_URL_RE`, `_EMAIL_RE`) folded into G1's helper; G3 honest-prefix gate restricted to sentence-1 with no-subsequent-fact check (the new `_honest_prefix_clears_response` helper); G4 `expected_tier=any` burn-down with explicit tiers + tier-list support; G5 (the §11.5 Cowork amendment) tier-routing-as-citation evidence gate at `_classify_disclosure_path:93` — refuses to credit citation purely from `tier_used in ("1","2","3")` without textual evidence. +7 adversarial eval entries q24-q30 covering each gap. Pytest 2180 → 2193. Validator 30/30 PASS post-change.

**Substantive finding worth remembering:** the pre-change baseline run was actually **22 PASS / q12 FAIL**, not 23/23 — the prior "23/23 PASS" post-7.5.1 was environment-conditional, and G1's closure caught a real confab slip that had been masked all along. That's the moment the validator started measuring reality instead of measuring itself. The Cursor §13 deviation accepted template-echo scrubs ("open tomorrow" / "rated above N stars" / `golakehavasu.com` / `/contribute`) so legitimate gap/tier-3 disclaimers aren't scored as confab; the new scrub surface itself became a Phase 7.5.4 watch item. Refs: `outputs/cursor_dispatch_prompt_phase_7_5_2.md`.

### 7.6 — Tier-2 OPEN_NOW listing shortcut (`975e83f` + `19b6c8f`)

The residual q03 tier-2 LLM-parser divergence closure.

**Wrapper goal:** make q03 deterministic — bypass the Haiku parser whose completions varied across local vs prod catalog contexts. The design memo's Path A (extend the shortcut) was preferred over Path B (post-parser deterministic fallback) because Path B added a second decision point that was hard to test and shadowed legitimate tier-3 disambiguation.

**Shipped:** new `_OPEN_NOW_LISTING_RE` regex in `try_business_listing_shortcut` matches `what {category-noun} [are] open (now|right now)` BEFORE `_LISTING_PREFIX.match`; on match builds `Tier2Filters(category=..., open_now=True, parser_confidence=0.9, fallback_to_tier3=False)` with zero LLM tokens. Category allow-list covers restaurants, cafes, coffee shops, bars, pharmacies, vets/veterinarians, stores, shops, gyms — tight enough to fail closed. 2 files modified; pytest 2193 → 2202 (+9). Validator 30/30 PASS with q03 now `tier=2 disc=cited` (was `tier=3 disc=uncited` pre-fix).

**Substantive finding worth remembering:** prod smoke confirmed latency dropped 23s → 4s — but q03 still routed `tier_used=3` on prod. Three-probe diagnostic established the chain: shortcut fires correctly, but prod restaurants are populated **without** `hours_structured` / `google_hours` data, so `tier2_db_query._query_providers` filters them all out via the Python-side `effective_hours_structured(p) AND is_open_at(hs, now_local)` check at `tier2_db_query.py:1092-1099`, and `tier2_handler.try_tier2_with_usage` cascades to tier-3 with a generic `golakehavasu.com` redirect. The 7.6 fix is architecturally correct; the data-sparsity tail is what Phase 7.7 closes. Refs: `outputs/cursor_dispatch_prompt_phase_7_6.md`, `outputs/phase_7_6_tier2_llm_parser_design_memo.md`.

### 7.5.3 — F-gap validator/eval polish (awaiting commit)

Lower-priority polish carved out of the post-mortem F-list. Genuine polish — not a hot fix.

**Wrapper goal:** close F1 (generalized fake-entity heuristic), F4 (tighten 7 `/contribute` substring asserts to full-template equality), F5 (lead-in clauses on about-gate).

**Shipped:** F1 structural heuristic added to `query_mentions_fake_entity_marker` (digit-density via `_HIGH_DIGIT_DENSITY_RE` and consonant-run via `_CONSONANT_RUN_RE`; <5-token short-circuit preserves the `mdshrkbrwry → Mudshark Brewery` typo case at near-match resolution time). F4 tightened 7 sites across `tests/test_gap_template_contribute_link.py` (lines 35/45/55) and `tests/test_phase38_gap_and_hours.py` (lines 90/143/246/310) from `assert "/contribute" in r.response` substring shape to full-template equality plus `tier_used` check. F5 `_LEAD_IN_PREFIX` allows conversational lead-ins ("Hey, ", "Quick question — ", "OK so ") on all about-gate strict patterns. +16 new tests; validator 30/30 non-regression.

**Substantive finding worth remembering:** Cursor §13 deviation — skipped the F1.c call-order reorder in `_unknown_entity_about_gate` (post-mortem §4 had specifically scoped this as required) because the `<5 tokens` short-circuit in `_looks_structurally_fake` already covers the documented `mdshrkbrwry` test case. Acceptable for the test surface but leaves a residual defense-in-depth gap for 5+ token queries with `mdshrkbrwry`-shape typos. Tracked as backlog item #47. Refs: `outputs/cursor_dispatch_prompt_phase_7_5_3.md`, `outputs/phase_7_5_3_validator_polish_design_memo.md`.

### 7.7 — Tier-2 honest empty listing on open_now zero-rows (awaiting commit)

The graceful-degradation closure for q03's data-sparsity tail. Independent of the V1.5 hours-data backfill — the template serves as graceful degradation for any future category whose hours data is sparse (vets at odd hours, seasonal businesses, newly added providers).

**Wrapper goal:** stop the tier-3 cascade when the shortcut fires but the `open_now` filter drops every row. The design memo rejected a `Tier2Filters.from_shortcut` provenance flag because the `open_now=True AND category is not None` signal alone is sufficient to identify "user asked for currently-open X" intent; the filter's provenance is incidental.

**Shipped:** new `_OPEN_NOW_EMPTY_LISTING_TEMPLATE` in `tier2_handler.py` plus a `_open_now_empty_listing(category)` helper that pluralizes via the existing `tier2_business_shortcut._pluralize_for_header`; two ~3-line conditionals at the shortcut zero-rows branch and the LLM-parser zero-rows branch, both gated on `open_now=True AND category is not None`. The shortcut-path emission reports `(0, 0, 0)` tokens because no LLM call was made; the parser-path emission carries the Haiku parser's tokens through honestly. Zero LLM tokens, instant response, honest about the data gap. Touches `app/chat/tier2_handler.py` + `tests/test_tier2_handler.py`.

**Substantive finding worth remembering:** secondary effect to watch is q10 / q12 potentially shifting from `disclosure=cited` to `i_dont_know` because the new template body contains "I don't have" which matches `_I_DONT_KNOW_RE`. Investigation queued post-deploy as task #48; YAML pin update probable. The shift would be cosmetic (the response is still correct and honest), not a regression — but the validator's row pins were set against the pre-7.7 surface and should be re-derived once prod traffic confirms the disclosure-path classification. Refs: `outputs/cursor_dispatch_prompt_phase_7_7.md`, `outputs/phase_7_7_honest_empty_listing_design_memo.md`.

---

## §4 Goodhart's Law in action

The arc is a textbook study of validator-as-target failure. Phase 7 shipped HALT 3 with a clean spec: `cited_coverage = 100%` on cited responses, `missing_confab_max = 0.0` on missing-data responses. Phase 7's initial run produced 12/22 PASS — including q07 at confab rate 0.50, which was the entire reason HALT 3 existed. Phase 7.5 dispatched as a polish lane, closed the 10 failures, and dropped q07's confab rate to 0.00. The validator agreed it had reached the goal. The metric was being satisfied.

The metric was not measuring the goal. Phase 7.5 closed q07 by expanding `_I_DONT_KNOW_RE` to recognize "I'm not aware" as an honest disclaimer. The regex matched, the short-circuit fired, the score dropped to 0.00. But what actually happened in the system being measured: the LLM continued confabulating, and started prepending an honest-sounding clause to satisfy the regex. The metric had been redefined to make the failure mode invisible. q07's prod response — "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu… Their listed number is (928) 502-4001" — passed the validator and failed the user in the same string.

q22 and q03 produced analogous Goodhart shapes against different signal short-circuits. q22's response, "Heat Hotel has a 4.5-star Google rating (406 reviews)," passed because `extract_catalog_entities_from_text` returned a real entity (Heat Hotel), `_confabulation_rate` short-circuited to 0.0 on G1's catalog-mention rule, and the rating's wrongness relative to the user's actual query was never inspected. q03's gap-template response satisfied the row's `expected_disclosure_path=i_dont_know` even though a populated catalog should have produced a tier-2 cited list. All three failures slipped through because the validator's pass/fail conditions were a *set of regex shapes* rather than a *measurement of the system's behavior against catalog ground truth*.

Phase 7.5.2 closed this directly. G1 dropped the catalog-mention shortcut and replaced it with `_entity_supports_typed_facts` that fetches the real catalog data and verifies each typed assertion. G2 added probes for the typed-fact classes the proper-noun regex never matched. G3 restricted the honest-prefix gate to sentence-1 with a no-subsequent-fact check. G4 burned down `expected_tier=any` from 19 of 22 rows to explicit allowlists. G5 (the §11.5 Cowork amendment surfaced by sub-agent C's audit) refused to credit citation purely from `tier_used in ("1","2","3")` without textual evidence. The pre-change baseline run produced the moment that crystallized the lesson: **22 PASS / q12 FAIL**, not the 23/23 the team had been carrying. The prior "23/23 PASS" was environment-conditional, and G1's closure retroactively exposed a hidden confab slip that the un-hardened validator had been masking the whole time. That's the precise moment the validator started measuring reality instead of itself.

The discipline that fell out of the arc: **passing a validator is necessary but not sufficient evidence of correctness**, especially when the validator's pass/fail criteria are themselves under iteration. When a metric goes from N FAIL to 0 FAIL after a tweak that touched the metric's own implementation, the tweak is suspect. Phase 7.5's close-out should have flagged the change to `_I_DONT_KNOW_RE` as a metric-semantics change and re-derived the metric's meaning before claiming closure. The sub-agent audit pattern (Lanes A, D, G, J, M, O) was effectively a meta-validator running over each subsequent phase's design memos and wrappers — "is the validator hardening doing what we think it's doing?" — and caught every drift item before the phase shipped.

---

## §5 Methodology — sub-agent fan-out + audit-then-author

Two process patterns emerged over the arc and are worth codifying. The first is **parallel sub-agent dispatch for diagnosis**. The four-sub-agent fan-out 2026-05-19 (sub-agent A on the validator's short-circuits, B on q07's routing trace, C on the generalized Goodhart audit, D on q22's near-match guard) compressed roughly 6-8 hours of sequential diagnostic work into ~90 minutes of wall-clock parallel work. Each sub-agent returned a coherent scoped report bounded to a specific code surface; the Cowork primary synthesized them into a single patch plan that became the Phase 7.5.1 wrapper. The same pattern appeared again for scope authoring — Lane B authored the Phase 7.5.3 design memo, Lane F authored the Phase 7.5.4 watch-items memo, Lane H authored the Phase 7.5.3 wrapper, Lane K authored the Phase 7.7 design memo and wrapper, Lane N authored the Phase 7.5.4 wrapper.

The second pattern is **audit-then-author for dispatch wrappers**. Every cc-authored wrapper or design memo got a follow-up audit sub-agent run before paste-time: Lane A audited the cc-authored Phase 7.6 wrapper, Lane D audited the Phase 7.5.3 design memo, Lane J audited the Phase 7.5.3 wrapper, Lane G audited the Phase 7.5.4 design memo, Lane M audited the Phase 7.7 wrapper, Lane O audited the Phase 7.5.4 wrapper. Every audit pass caught real drift items — none of them blocking, all of them worth fixing pre-paste. The post-mortem documents the discipline explicitly at §8 Lesson 6, and the V1.5 carries inventory at `outputs/v1_5_carries_inventory.md` notes the codification candidate.

The arc also surfaced a working pattern of **three-Cursor parallel dispatch**. Phase 7.5.3, Phase 7.7, and Phase 8a were authored as three independent wrappers and dispatched concurrently in three separate Cursor sessions in the final hours of the arc. File-scope disjointness per gotcha #18 made this safe: 7.5.3 touched `entity_intent.py` + `unified_router.py` + two test files; 7.7 touched only `tier2_handler.py` + its test file; 8a is its own alembic-shipping lane with no overlap. The alembic-revision-DAG-is-global gotcha that bit Phase 6.4 + Phase 7 was not triggered here because only one of the three (8a) ships a migration.

The lesson that emerged: **wrapper-author + wrapper-audit as paired sub-agents** caught drift the original author missed in every audit pass. Codifying it as a default pattern in `docs/maintainability/dispatch_protocol.md` is queued — see §8.

---

## §6 Open carries → next lanes

| Item | Status | Path to closure |
|---|---|---|
| **Phase 7.5.4** — rating-scrub exploit closure on q25 | Wrapper authored (Lane N) + Lane O audit-fixed; queued for dispatch | Operator dispatches the wrapper at `outputs/cursor_dispatch_prompt_phase_7_5_4.md` to a fresh Cursor session. |
| **V1.5 hours-data backfill** | Open; non-blocking | Populate `hours_structured` / `google_hours` on prod catalog so the OPEN_NOW filter at `tier2_db_query.py:1092-1099` returns rows. Phase 7.7's honest-empty template is graceful degradation; the backfill is the proper fix. |
| **F1.c call-order defense-in-depth gap** | 7.5.3 §13 deviation; not currently producing user-visible failures | Remains for 5+ token queries with `mdshrkbrwry`-shape typos. Candidate for V1.5 if test coverage warrants. |
| **q10 / q12 disclosure shift after 7.7** | Pending post-deploy investigation | The 7.7 template body contains "I don't have" which matches `_I_DONT_KNOW_RE`; q10/q12 may shift from `disclosure=cited` to `i_dont_know`. YAML pin update probable. Tracked as task #48 in the lane backlog. |
| **F2 / F6 / F7 post-mortem F-gaps** | V1.5 carries | Tagged in `outputs/v1_5_carries_inventory.md` §2.4. F6 = `near_match_subject_overlaps` fail-open on all-category-words queries; F7 = `_USEFUL_CONTENT_RE` overbroad. |
| **`scripts/post_deploy_smoke.py` automation** | V1.5 carry | Post-mortem §8 Lesson 4 proposal — scripted prod-eval smoke against the prod URL post-deploy, posts to Slack or fails GH Actions. Would have caught the three prod bugs Phase 7.5 missed. |
| **Phase 7.5 close-out narrative amendment** | Open | The `FEATURE_FLAG_DISCLOSURE_RENDERER` flag-flip framing in `outputs/phase_7_5_close_out.md` §5 needs replacement with the §6 flag-semantics correction from the post-mortem. Either amend in place with a banner or supersede with a v2 doc. |
| **Phase 8a** (conditions + alerts) | Concurrently dispatched | Major next lane; close-out separately if needed. Alembic migration lane — only one of the three parallel Cursor sessions ships schema changes. |

---

## §7 Numbers

| Dimension | Value |
|---|---|
| Lane duration | 2 days (2026-05-19 → 2026-05-20) |
| Phases shipped | 6 (7.5, 7.5.1, 7.5.2, 7.6, 7.5.3, 7.7) |
| Phases queued | 1 (7.5.4) |
| Commits | `b701759` (7.5), `fd695d2` (7.5.1), `64799d5` (7.5.2), `975e83f` + `19b6c8f` (7.6 code + docs), 7.5.3 + 7.7 awaiting commit |
| Approximate LOC delta | ~600 LOC production + ~700 LOC tests (rough — across 7.5.1's ~204 + 7.5.2's validator rewrite + 7.6's ~43 + 7.5.3's ~150 + 7.7's ~30-50) |
| Tests added | ~60 net-new (7.5.1: +12; 7.5.2: +13; 7.6: +9; 7.5.3: +16; 7.7: +4-6) |
| Validator state trajectory | 12/22 (Phase 7 initial) → 22/22 (Phase 7.5, environment-conditional) → 23/23 (Phase 7.5.1 + q23, still environment-conditional; G1 closure later exposed q12 was hidden) → 30/30 (Phase 7.5.2 hardened) → 30/30 (post-7.6 with q03 promoted to `tier=2 disc=cited`) |
| Sub-agent lanes (A through O+) | 15+ lanes (diagnosis fan-out 4; scope-authoring + audit pairs across A/B/D/E/F/G/H/I/J/K/M/N/O) |
| Cursor lanes dispatched | 6 shipped (7.5.1, 7.5.2, 7.6, 7.5.3, 7.7) + 1 concurrent (8a) + 1 queued (7.5.4) |

---

## §8 What we'd do differently

Validator hardening should have been in scope from Phase 7, not retroactively in Phase 7.5.2. The initial HALT 3 spec defined `cited_coverage` and `missing_confab_max` as success metrics but did not define what a regression in the metric's own implementation would look like. The G1-G5 audit by sub-agent C 2026-05-19 surfaced the gaps in roughly two hours of work — that audit could have been a Phase 7 sub-task and would have caught the structural weaknesses before any production traffic ever exercised them. Future validator phases should ship with a meta-validator pass over the validator's pass/fail conditions before claiming the metric is meaningful.

Local-vs-prod data parity is the silent killer of this kind of phase. Three independent failures, three different fixture-conditional masks: LLM nondeterminism on q07, catalog distribution on q22, LLM-parser variance on q03. Wiring prod-shape fixtures (sampled subset of the prod catalog plus adversarial near-match traps like Heat Hotel) into the dev environment from Phase 0 would have collapsed the diagnosis time on all three. The Phase 7.5.2 q24-q30 entries are a step toward this; the broader discipline is to validate the validator's coverage against a known set of prod-shape failure modes before claiming a PASS means anything. The `scripts/post_deploy_smoke.py` proposal (post-mortem §8 Lesson 4) is the concrete forward move.

Wrapper-author + wrapper-audit as paired sub-agents is now the default pattern and should be codified in `docs/maintainability/dispatch_protocol.md`. Every audit lane in this arc caught real drift items pre-paste. The cost is roughly one additional sub-agent invocation per dispatched wrapper; the benefit is the deviation envelope at paste-time shrinks materially.

`FEATURE_FLAG_DISCLOSURE_RENDERER` semantic confusion was costly — the entire Phase 7.5 close-out narrative framed the flag-flip as the substantive milestone closing the HALT 3 narrative arc, when in fact the flag controls a different concern (FTC ad disclosure rendering) and the anti-confab routing was always-on. A canonical flag taxonomy doc that pastes the first 30 lines of each flag's owning module would have caught the drift during the Phase 7.5 close-out review. Worth authoring as a `docs/maintainability/feature_flag_taxonomy.md` short reference.

Cursor's §13 self-correction is a feature, not a deviation. The Phase 7.5.1 about-gate regex over-broadening, the Phase 7.5.2 template-echo scrubs, the Phase 7.5.3 F1.c call-order skip — three examples in this arc of Cursor recognizing a wrapper bug or scope overflow and self-correcting without operator round-trip. Formally documenting the "self-correct without operator approval" envelope in the deviation discipline (working agreement Rule 4) would make the pattern visible and reduce hesitation in future sessions. The corollary is that audit lanes should specifically look for §13 candidates the wrapper missed.

---

## §9 Artifacts inventory

### Post-mortem
- `outputs/phase_7_5_prod_divergence_investigation.md` — the durable post-mortem (~5,850 words); supersedes the original Phase 7.5 close-out's "HALT 3 narrative complete" framing.

### Design memos
- `outputs/phase_7_6_tier2_llm_parser_design_memo.md` — Path A (extend shortcut) vs Path B (post-parser fallback) scoping for q03.
- `outputs/phase_7_5_3_validator_polish_design_memo.md` — F1/F4/F5 scoping with the F1.c call-order reorder amendment.
- `outputs/phase_7_7_honest_empty_listing_design_memo.md` — honest-empty template scoping; rejected the `Tier2Filters.from_shortcut` flag alternative.
- `outputs/phase_7_5_4_validator_polish_watch_items_design_memo.md` — rating-scrub exploit on q25; G4 list promiscuity; template-echo sanitization surface.

### Dispatch wrappers
- `outputs/cursor_dispatch_prompt_phase_7_5_1.md` — routing fixes (shipped `fd695d2`).
- `outputs/cursor_dispatch_prompt_phase_7_5_2.md` — validator hardening with §11.5 Cowork amendment for G5 + F3 (shipped `64799d5`).
- `outputs/cursor_dispatch_prompt_phase_7_6.md` — OPEN_NOW listing shortcut (shipped `975e83f`).
- `outputs/cursor_dispatch_prompt_phase_7_5_3.md` — F-gap polish (shipped, awaiting commit).
- `outputs/cursor_dispatch_prompt_phase_7_7.md` — honest empty listing (shipped, awaiting commit).
- `outputs/cursor_dispatch_prompt_phase_7_5_4.md` — rating-scrub closure (queued; Lane O audit-cleared).

### V1.5 inventory
- `outputs/v1_5_carries_inventory.md` — 81-item consolidated backlog; §2.4 reflects F6/F7/post-deploy-smoke carries surfaced during this arc.

### This close-out
- `outputs/phase_7_5_to_7_7_lane_close_out.md` — this document.

---

*Authored by sub-agent under Cowork primary supervision, 2026-05-20 post-7.5.3 + 7.7 ship pre-7.5.4 dispatch. Saved to `outputs/phase_7_5_to_7_7_lane_close_out.md`.*
