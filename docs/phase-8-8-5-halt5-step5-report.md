# Phase 8.8.5 — HALT 5 Step 5 Report

Date: 2026-04-25  
Scope: Full-suite validation under both router flag states + commit staging readiness

---

## 1) Gate status

Blocked at Step 5 test gate: full-suite pytest did not pass under either flag state, so no staging/commits were performed.

- `USE_LLM_ROUTER=false`: `1 failed, 891 passed, 3 subtests passed` in `396.90s`
- `USE_LLM_ROUTER=true`: `1 failed, 891 passed, 3 subtests passed` in `424.86s`

Shared failing test in both runs:

- `tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results`
- Assertion expected `"Basketball Clinic"` in response, got `"Nothing on for that time. Want to peek at what's coming up later?"`

---

## 2) git log --oneline -10

- `3b2f571 docs(8.8.5): pre-implementation spec drafts (v1 and v2)`
- `fedf0a8 feat(router): LLM router module behind USE_LLM_ROUTER flag (Phase 8.8.4)`
- `9b765b3 feat(tier2): recurring-dedupe selection fix for broad windows (Phase 8.8.4)`
- `fbf5d6c feat(tier2): Tier2Filters v2 schema with structured temporal fields (Phase 8.8.4)`
- `6aad4ab docs(8.8.4): pre-implementation working artifacts (audit, spec, diagnostics)`
- `6a99f4a feat(tier2): harden formatter grounding and reorder gap-template (Phase 8.8.3)`
- `26bdc32 Revert "feat(tier3): surface unlinked future events in context"`
- `88556bb feat(tier3): surface unlinked future events in context`
- `f84ead8 docs(known-issues): cross-link Tier 3 investigation doc from Entry 1`
- `b99048a docs(known-issues): log five issues surfaced in Phase B validation session`

---

## 3) Both pytest run summaries

### 3.1 Router flag off

Command:

```powershell
$env:USE_LLM_ROUTER="false"; .venv/Scripts/python -m pytest -v
```

Summary:

- `1 failed, 891 passed, 3 subtests passed in 396.90s (0:06:36)`
- Failure:
  - `tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results`
  - Expected `"Basketball Clinic"` in response
  - Actual response: `"Nothing on for that time. Want to peek at what's coming up later?"`

### 3.2 Router flag on

Command:

```powershell
$env:USE_LLM_ROUTER="true"; .venv/Scripts/python -m pytest -v
```

Summary:

- `1 failed, 891 passed, 3 subtests passed in 424.86s (0:07:04)`
- Same single failure:
  - `tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results`

---

## 4) Final fact-token lexicon implemented (all 7 classes)

Thresholds in code:

- `word_count >= 18 OR fact_token_count >= 4`
- Set-based dedup by canonical concept key.

### Class 1 — Facility/amenity nouns

- `pool`
- `olympic_pool`
- `wave_pool`
- `splash_pad`
- `water_slide`
- `slide`
- `hot_tub` (`hot tub`, `hot tubs`)
- `gym` (`gym`, `fitness center`)
- `studio`
- `court`
- `theater` (`theater`, `theatre`)
- `kitchen`
- `playground`
- `track`
- `field`
- `classroom`
- `marina`
- `dock`
- `boat_ramp`
- `beach`
- `boat`
- `kayak`
- `paddleboard`
- `trail`
- `park`
- `picnic_area`
- `restroom`
- `showers`

### Class 2 — Operational detail markers

- `max_number`
- `capacity_number`
- `one_on_one`
- `duration`
- `year_round`
- `schedule_freq`
- `price`
- `free`
- `assessment`

### Class 3 — Credential/program markers

- `certified`
- `accredited`
- `licensed`
- `swim_america`
- `usa_swimming`
- `cpr`
- `lifeguard`
- `ai_chi`
- `arthritis_exercise`
- `cardio_challenge`
- `aqua_aerobics`
- `aqua_motion`

### Class 4 — Access/physical attributes

- `indoor`
- `outdoor`
- `climate_control` (`air-conditioned`, `air conditioned`, `climate-controlled`)
- `heated`
- `accessible` (`wheelchair accessible`, `accessible`)
- `covered`
- `shaded`
- `private`

### Class 5 — Business duration/longevity markers

- `years_in_operation`
- `since_year`
- `established_year`
- `founded_year`

### Class 6 — Organization type markers

- `nonprofit` (`non[- ]?profit`)
- `org_501c3` (`501(c)(3)`, `501c3`)
- `female_owned`
- `family_owned`
- `veteran_owned`
- `cooperative`
- `founder`

### Class 7 — Audience/enrollment markers

- `all_levels`
- `age_range`
- `broad_age_span`
- `open_enrollment`
- `esa_accepted`
- `membership_policy`
- `no_fees_membership`
- `first_free`
- `loaner_gear`

---

## 5) Classifier function code (current)

```python
def _classify_description_richness(text: str | None) -> str:
    if text is None or not str(text).strip():
        return "sparse"
    normalized = str(text).strip().lower()
    word_count = len(_WORD_RE.findall(normalized))
    fact_concepts: set[str] = set()
    for concept, pats in _RICHNESS_FACT_CONCEPT_PATTERNS.items():
        if any(p.search(normalized) for p in pats):
            fact_concepts.add(concept)
    if word_count >= _RICH_WORD_THRESHOLD or len(fact_concepts) >= _RICH_FACT_THRESHOLD:
        return "rich"
    return "sparse"


def _classify_provider_richness(
    description: str | None, featured_description: str | None
) -> str:
    if featured_description is not None and str(featured_description).strip():
        return "rich"
    return _classify_description_richness(description)
```

---

## 6) Formatter prompt block (current)

```text
**Description richness guardrails (additive):**
- For rows tagged description_richness=sparse:
  - Do not generate descriptive prose about provider/program character, atmosphere, audience fit, accessibility, or amenities.
  - Allow only: name, category/activity category, and literal row-backed fields (address, phone, hours, website, cost, schedule).
  - If the user asks for absent detail, state briefly that row data does not provide it.
- Sparse-row example (literal):
  - Bad input row: "Nonprofit. Affiliated with ACPA. established: 2006."
  - Bad output: "indoor option, air-conditioned, family-friendly youth theatre production"
  - Good output: "Grace Arts Live (nonprofit affiliated with ACPA, founded 2006)"
- Even when description_richness=rich, do not add facility, atmosphere, accessibility, or audience-fit attributes (such as indoor, outdoor, heated, private, family-friendly, air-conditioned, kid-friendly, romantic, casual, etc.) unless those exact words appear in the row text.
- Rich-row example (literal):
  - Bad input row: "Max 3 swimmers per group. Free initial assessment. Coach Rick (Swim America® certified)."
  - Bad output: "private heated outdoor pool sessions, though you'd need to book directly through their site"
  - Good output: "Aqua Beginnings runs swim instruction with max 3 swimmers per group, free initial assessment with Coach Rick (Swim America certified)"
```

---

## 7) Deferred observations

- The single failing test appears unrelated to Step 3/4 files and reproduces with router flag both off and on.
- No commits created due to failing full-suite gate.
