# Phase 8.8.5 — Tier 2 Formatter Grounding Hardening Spec (v2)

Status: Draft for owner review  
Date: 2026-04-25  
Scope: Spec only (no implementation changes in this phase)

---

## 1) Problem statement

Post-8.8.4 validation under `USE_LLM_ROUTER=true` exposed Tier 2 formatter confabulation on sparse provider rows. Follow-up validation under flag-off showed the same pattern. This isolates the bug to Tier 2 formatter behavior, not router routing.

Why this is cross-surface:
- Router-on and router-off both execute Tier 2 formatting via `tier2_formatter.format(...)` after Tier 2 row selection (`app/chat/tier2_formatter.py`, `app/chat/tier2_db_query.py`).
- Current formatter prompt already includes grounding rules, but those rules are insufficient for sparse-description rows (`prompts/tier2_formatter.txt`).

### 1.1 Concrete failures (verbatim)

Source note: these failures are from post-deploy validation transcripts provided by owner.

1) **Aqua Beginnings**
- Verbatim row data: `"Max 3 swimmers per group. Free initial assessment. Coach Rick (Swim America® certified)."`
- Verbatim Hava response excerpt: `"private heated outdoor pool sessions, though you'd need to book directly through their site."`
- Invented details: `heated`, `outdoor`, `private sessions`, `booking-via-site requirement`.

2) **Grace Arts Live**
- Verbatim row data: `"Nonprofit. Affiliated with ACPA. established: 2006."`
- Verbatim Hava response excerpt: `"indoor option, air-conditioned, family-friendly, youth theatre production."`
- Invented details: `air-conditioned`, `family-friendly`.  
- Note: `youth theatre production` may be derivable from related Event rows in some contexts; must be verified per-query context during implementation validation.

3) **London Bridge Beach**
- Catalog state during validation: not present as a Provider row.
- Verbatim Hava response excerpt: `"shade from the bridge structure."`
- Failure type: interpolation/fabrication outside row-backed provider detail.

### 1.2 Failure mechanism

When provider `description` is sparse, and user intent implies recommendation criteria (for example kids + hot day), the model fills missing detail with plausible prose instead of acknowledging insufficient evidence. Existing prompt rule text (`"If a row does not contain a detail, do not infer it..."`) does not reliably suppress this mode.

---

## 2) Goals and non-goals

### 2.1 Goals

1. Eliminate field-level confabulation for sparse provider descriptions in Tier 2 output.
2. Preserve useful grounded descriptiveness on genuinely rich rows.
3. Keep §6.7 voice shape: one short framing line is allowed at landscape level.
4. Validation gate must pass under both `USE_LLM_ROUTER=true` and `USE_LLM_ROUTER=false`.

### 2.2 Non-goals (locked)

- No router logic changes (`app/chat/llm_router.py`, `app/chat/unified_router.py` unchanged).
- No schema changes (`app/chat/tier2_schema.py` unchanged).
- No Tier 3 prompt/handler changes (`prompts/system_prompt.txt`, `app/chat/tier3_handler.py` out of scope).
- No Event/Program model redesign in this phase.
- No catalog data quality remediation as part of 8.8.5.

---

## 3) Approach — programmatic gate + tightened prompt

## 3.1 Programmatic richness gate (primary defense)

### 3.1.1 Where it applies

Attach `description_richness` metadata at row-construction time in Tier 2 query output before formatter call:
- provider rows from `_provider_dict(...)` in `app/chat/tier2_db_query.py`
- program rows from `_program_dict(...)` in `app/chat/tier2_db_query.py`

Existing row shape references:
- `_provider_dict` currently emits `name/category/address/phone/hours/description` (`app/chat/tier2_db_query.py`).
- `_program_dict` currently emits `name/activity_category/schedule/cost/description` (`app/chat/tier2_db_query.py`).
- formatter currently receives rows as JSON blob (`app/chat/tier2_formatter.py`).

### 3.1.2 Classification rule (owner-locked starting point)

For a row text source `d`:
- Provider rows: evaluate `featured_description` first when non-null/non-empty (see 3.1.4), otherwise evaluate `description`.
- Program rows: evaluate `description`.

Compute:
- `word_count = number of whitespace-separated tokens`
- `fact_token_count = number of distinct matched concepts from implementation lexicon`

Classify as:
- `rich` if `word_count >= 18` **OR** `fact_token_count >= 4`
- `sparse` otherwise.

This threshold pair is approved as the starting point and may be adjusted only after the catalog survey HALT in Section 3.3.

### 3.1.3 Fact-token classes (conceptual lock, implementation lexicon flexible)

Spec locks conceptual classes, not literal token patterns:
1. Facility/amenity nouns
2. Operational detail markers (capacity/duration/price-like concrete numbers)
3. Credential/program markers
4. Access/physical attributes explicitly stated

Implementation policy:
- Cursor proposes an initial literal fact-token lexicon at implementation HALT 1.
- Owner reviews and approves/revises that lexicon at HALT 1 before classifier code is finalized.
- The lexicon is expected to evolve during implementation and may evolve post-deploy based on validation telemetry, without requiring a spec revision, provided the four conceptual classes remain intact.

### 3.1.4 Featured-description precedence (resolved)

Provider rule is resolved:
- If `Provider.featured_description` is non-null and non-empty, classify Provider row as `rich` immediately.
- Classifier checks `featured_description` first; only falls back to `description` when featured text is absent.

Rationale: `featured_description` is treated as the authoritative descriptive field when populated.

### 3.1.5 Required fixture outcomes

1. **Aqua Beginnings**  
   `"Max 3 swimmers per group. Free initial assessment. Coach Rick (Swim America® certified)."`  
   -> **sparse** (short and limited factual breadth in this policy).

2. **Grace Arts Live**  
   `"Nonprofit. Affiliated with ACPA. established: 2006."`  
   -> **sparse**.

3. **Lake Havasu City Aquatic Center**  
   `"Indoor facility. Olympic pool, wave pool, water slide, hot tubs, splash pad."`  
   -> **rich** via dense concrete facts despite shorter length.

4. **Program fixture: Aqua Aerobics / Water Fitness**  
   `"Schedule: Multiple class types. See monthly schedule at lhcaz.gov. Year-round adult water fitness. Classes include Aqua Aerobics, Ai-Chi, Arthritis Exercise, Cardio Challenge, and Aqua Motion."`  
   -> **rich** (multi-fact program description with concrete class taxonomy and schedule cues).

## 3.2 Tightened formatter prompt (secondary defense)

Update `prompts/tier2_formatter.txt` with explicit sparse-row contract and bad/good examples.

### 3.2.1 New hard rule

For rows tagged `description_richness=sparse`:
- Do **not** generate descriptive prose about:
  - provider/program character,
  - atmosphere,
  - audience fit,
  - accessibility,
  - amenities.
- Allow only:
  - name,
  - category/activity category,
  - and literal row-backed fields (address/phone/hours/website/cost/schedule/etc.).
- If user asks for absent detail, state briefly that row data does not provide it.

### 3.2.2 Required prompt examples

Add explicit bad/good pair:
- **Bad input row:** `"Nonprofit. Affiliated with ACPA. established: 2006."`
- **Bad output:** `"indoor option, air-conditioned, family-friendly youth theatre production"`
- **Good output:** `"Grace Arts Live (nonprofit affiliated with ACPA, founded 2006)"`

This must appear literally in prompt text.

## 3.3 Pre-implementation catalog survey HALT (new required step)

Before classifier logic is finalized in code, run a distribution survey against production catalog data using the proposed HALT 1 lexicon and threshold pair.

Required survey scope:
- all live, non-draft Provider rows
- all live, non-draft Program rows

Required report outputs:
1. Provider totals:
   - total count, sparse count, rich count, percentages.
2. Program totals:
   - total count, sparse count, rich count, percentages.
3. Spot-check examples:
   - 5 sparse + 5 rich Provider examples (description text + classification sanity note),
   - 5 sparse + 5 rich Program examples (description text + classification sanity note).

Calibration guardrail:
- If sparse percentage is above ~70% or below ~20% for either model, flag likely miscalibration and propose threshold/lexicon adjustment.

Process lock:
- This survey is a HALT checkpoint before classifier code is locked.
- Owner review/approval of survey distribution is required before finalizing classifier implementation.

---

## 4) Implementation file list

### 4.1 Files to modify

1. `app/chat/tier2_db_query.py`
   - add richness-classification helper(s)
   - apply `featured_description` precedence for Provider richness
   - attach `description_richness` to provider rows in `_provider_dict(...)`
   - attach `description_richness` to program rows in `_program_dict(...)`
2. `prompts/tier2_formatter.txt`
   - add sparse-row hard rule
   - add explicit bad/good examples
3. `tests/test_tier2_db_query.py`
   - add classifier tests for Provider + Program fixtures and edge-case behavior
4. `tests/test_tier2_formatter.py`
   - prompt-regression assertions for new rule text and examples

### 4.2 Files explicitly not to modify

- `app/chat/llm_router.py`
- `app/chat/unified_router.py`
- `app/chat/tier2_schema.py`
- `app/chat/tier3_handler.py`
- `prompts/system_prompt.txt`
- Event/Program SQLAlchemy model definitions in `app/db/models.py`

---

## 5) Test plan

## 5.1 Unit tests

1. Richness classifier fixtures:
   - Aqua Beginnings -> sparse
   - Grace Arts Live -> sparse
   - Aquatic Center example -> rich
   - Aqua Aerobics / Water Fitness Program example -> rich
2. Provider `featured_description` precedence:
   - non-empty featured description forces rich classification.
3. Prompt regression checks:
   - sparse-row hard rule string present
   - explicit bad/good example strings present

## 5.2 Validation gate (required under both router states)

Run under both:
- `USE_LLM_ROUTER=false`
- `USE_LLM_ROUTER=true`

Validation set:
- 12 canonical §8.4 queries x 3 each = 36 responses
- plus sparse-row probes:
  1. `"where should I take my kids on a hot day"`
  2. `"tell me about grace arts live"`
  3. `"what does aqua beginnings offer"`

Pass criteria:
- zero Tier 2 field-level confabulation on sparse rows.
- Gate confabulation definition: any descriptive claim about sparse-row character/atmosphere/accessibility/amenities not literally present in row fields.

Out-of-scope gate note:
- Tier 3 confabulation observations do not fail 8.8.5 gate; they are logged for future phase triage.

## 5.3 Re-enable decision logic

1. If 5.2 passes under both flag states -> re-enable router (`USE_LLM_ROUTER=true`) as part of deploy decision.
2. If 5.2 passes only under flag-off -> deploy with flag-off; router re-enable deferred.
3. If 5.2 fails under either state -> mark 8.8.5 approach failed and re-spec.

---

## 6) Risk and rollback

### 6.1 Risks

1. Threshold too aggressive -> rich rows downgraded to sparse, responses become too terse.
2. Threshold too lenient -> sparse rows still receive prose, confabulation persists.
3. Prompt hardening spillover -> reduced helpfulness even for rich rows.
4. Lexicon drift risk -> inconsistent classification if lexicon changes without review discipline.

### 6.2 Mitigations

1. Fixture-driven threshold calibration (Provider + Program fixtures).
2. Mandatory catalog survey HALT before classifier lock.
3. Owner approval of initial lexicon at HALT 1.
4. Manual validation gate across both router states.

### 6.3 Rollback

- Revert 8.8.5 commits as a unit.
- No schema migration rollback required.
- Returns system to 8.8.3 behavior with 8.8.4 router code still deployable/dormant by flag.

---

## 7) Phase ledger and docs

- Phase number: **8.8.5**
- Sequence: `8.8.4 -> 8.8.5 -> router re-enable decision -> 8.9`
- Launch impact: blocks readiness only if Tier 2 confabulation is treated as launch-blocking by owner.

Docs to update during implementation:
- `docs/START_HERE.md`
- `HAVA_CONCIERGE_HANDOFF.md` §5
- `docs/known-issues.md`
- `docs/pre-launch-checklist.md`

Known-issues tracking aligned with this phase:
1. Tier 2 sparse-row formatter confabulation (targeted by 8.8.5).
2. Tier 3 confabulation observations from 8.8.4 validation (deferred).
3. Aquatic Center selection misses for "kids on a hot day" style prompts (separate routing/selection concern).
4. Desert Storm boat race missing from catalog (data coverage gap).
5. London Bridge Beach missing as Provider entity (data modeling/content gap).

---

## 8) Resolved decisions (owner-approved in v2)

1. **Threshold baseline approved:** `word_count >= 18 OR fact_token_count >= 4` as starting point; can adjust only after Section 3.3 catalog survey review.
2. **`featured_description` resolved:** non-empty Provider featured description forces `rich`; classifier checks featured description first.
3. **Program scope resolved:** Program rows are included in 8.8.5 with same classifier and same output field `description_richness`.
4. **Lexicon governance resolved:** conceptual classes are fixed by spec; literal pattern lexicon is implementation-owned and owner-reviewed at HALT 1.

---

## 9) Code-reading references (authoritative context)

- Router and Tier 2 architecture context:
  - `docs/phase-8-8-4-llm-router-spec-v2.md`
  - `docs/phase-8-8-4-halt4-followup.md`
- Current formatter rules and invocation:
  - `prompts/tier2_formatter.txt`
  - `app/chat/tier2_formatter.py`
- Tier 2 row payload construction:
  - `app/chat/tier2_db_query.py` (`_provider_dict`, `_program_dict`, query/merge flow)
- Provider fields relevant to richness precedence:
  - `app/db/models.py` (`Provider.description`, `Provider.featured_description`, contact/location fields)

