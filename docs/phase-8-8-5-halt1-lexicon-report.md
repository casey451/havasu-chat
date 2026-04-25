# Phase 8.8.5 — HALT 1 Lexicon and Classifier Proposal

Date: 2026-04-25  
Scope: Lexicon proposal + classifier shape (no code changes yet)

---

## A) Initial fact-token lexicon by class (literal proposal)

### Class 1: Facility / amenity nouns

Proposed normalized phrases (case-insensitive):

- `pool`
- `olympic pool`
- `wave pool`
- `splash pad`
- `water slide`
- `slide`
- `hot tub`
- `hot tubs`
- `gym`
- `fitness center`
- `studio`
- `court`
- `theater`
- `theatre`
- `kitchen`
- `playground`
- `track`
- `field`
- `classroom`
- `marina`
- `dock`
- `boat ramp`
- `beach`
- `boat`
- `kayak`
- `paddleboard`
- `trail`
- `park`
- `picnic area`
- `restroom`
- `showers`

### Class 2: Operational detail markers (regex-style)

Capacity / quantity:

- `\bmax(?:imum)?\s+\d+\b`
- `\b\d+\s*(?:swimmer|swimmers|people|participants|students|kids|adults)\b`
- `\b(one[- ]on[- ]one|1:1|small[- ]group)\b`

Duration / schedule:

- `\b\d+\s*(?:min|mins|minute|minutes|hour|hours)\b`
- `\b(year[- ]round)\b`
- `\b(monthly schedule|weekly schedule|daily)\b`

Price-like:

- `\$\s*\d+(?:\.\d{2})?`
- `\bfree\b`
- `\bassessment\b`

### Class 3: Credential / program markers

- `certified`
- `accredited`
- `licensed`
- `swim america`
- `usa swimming`
- `cpr`
- `lifeguard`
- `ai-chi`
- `arthritis exercise`
- `cardio challenge`
- `aqua aerobics`
- `aqua motion`

### Class 4: Access / physical attributes

- `indoor`
- `outdoor`
- `air-conditioned`
- `air conditioned`
- `heated`
- `wheelchair accessible`
- `accessible`
- `covered`
- `shaded`
- `climate-controlled`
- `private` (physical/privacy descriptor only)

---

## B) Classifier function shape (proposed)

Proposed private helper location: `app/chat/tier2_db_query.py`

Proposed signatures:

- `_classify_description_richness(text: str | None) -> str`
- `_classify_provider_richness(description: str | None, featured_description: str | None) -> str`

Return values:

- `"rich"` or `"sparse"` only.

Canonical dedup behavior:

- The classifier counts **distinct canonical fact concepts**, not raw matches.
- Synonym/equivalent pattern groups map to one canonical concept key:
  - `theater` / `theatre` -> `theater`
  - `hot tub` / `hot tubs` -> `hot_tub`
  - `gym` / `fitness center` -> `gym`
  - `air-conditioned` / `air conditioned` / `climate-controlled` -> `climate_control`
  - `accessible` / `wheelchair accessible` -> `accessible`
- Counting logic: pattern match -> canonical concept key -> add to set -> `fact_token_count = len(set)`.

Core logic sketch:

```python
def _classify_description_richness(text: str | None) -> str:
    if text is None or not text.strip():
        return "sparse"

    normalized = normalize_text(text)  # lowercase, collapse spaces, punctuation-light
    word_count = count_words(normalized)
    fact_token_count = count_distinct_canonical_concepts(normalized)

    if word_count >= 18 or fact_token_count >= 4:
        return "rich"
    return "sparse"


def _classify_provider_richness(description: str | None, featured_description: str | None) -> str:
    # featured_description precedence per spec v2
    if featured_description is not None and featured_description.strip():
        return "rich"
    return _classify_description_richness(description)
```

---

## C) Featured-description precedence order (explicit)

For provider rows only:

1. If `Provider.featured_description` is non-null and non-empty (after `.strip()`), classify as `"rich"` immediately.
2. Else classify using `Provider.description` via standard threshold logic (`word_count >= 18 OR fact_token_count >= 4`).
3. Null/empty description falls through to `"sparse"`.

For program rows:

- Always classify from `Program.description` only.

---

## D) HALT 1.5 scope acknowledgment

Aqua Beginnings under the approved lexicon likely matches multiple concrete concepts (`max + number`, `free`, `assessment`, `swim america`, `certified`) and therefore classifies as `rich` under threshold `word_count >= 18 OR fact_token_count >= 4`.

Owner-approved interpretation:

- The classifier measures concrete content presence, not "confabulation susceptibility."
- Aqua Beginnings can be `rich` and still require stricter formatter grounding.
- Sparse-row rules primarily protect truly sparse entries (for example Grace Arts Live style rows).
- Rich-row grounding must separately forbid adding facility/atmosphere claims unless literal words exist in the row.
