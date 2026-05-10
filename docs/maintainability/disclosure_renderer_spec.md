# Deterministic Sponsored-Disclosure Renderer — Phase 1 Keystone Spec

**Status:** OPEN — implementation not started  
**Source of truth for:** sponsored block rendering without LLM drift on disclosure language and tone compliance  
**Audience:** any agent (Cowork / Claude Code / Cursor) executing the renderer module and integration slices  
**Companion docs:** `ui_data_correctness_spec.md` (structural template), `persona-brief.md` (voice and blocklist), `HAVA_CONCIERGE_HANDOFF.md` (routing and tiers)

---

## 0. Why this spec exists

The chat currently routes sponsored-eligible queries to Tier 3 (Anthropic synthesis), where the LLM renders disclosure language and advertiser copy. Two failure modes emerge in production:

1. **Disclosure language drift.** Across responses, the LLM improvises disclosure phrasing: *"Featured,"* *"Partner,"* *"Recommended,"* *"Spotlight,"* instead of the canonical single word *"Sponsored."* This violates FTC requirements for consistent, clear disclosure language and makes the disclosure UI inconsistent across responses.

2. **Tone violations on paid placements.** When the LLM synthesizes copy for a sponsored block, it sometimes produces evaluative claims not grounded in verified data: *"best in town,"* *"highly rated,"* *"top-rated,"* *"locals' favorite."* These superlatives are marketing voice, not local knowledge, and contradict the persona brief (§6.7 — bulk data speaks factually, not evaluatively).

The **architectural precedent** is `app/chat/tier2_catalog_render.py` (Phase 4.2), which solved the analogous count-drift problem on event listings (Backlog #6). When all rows are events, Tier 2 bypasses the LLM entirely and uses a deterministic renderer. This spec generalizes that pattern to sponsored surfaces: when a query is eligible for sponsored placement in one of three regimes (§1), a deterministic renderer produces the block instead of the LLM, eliminating both drift and tone violations by construction.

---

## 1. Three placement regimes

The intent classifier (`app/chat/intent_classifier.py`) produces `mode` and `sub_intent` signals. The router determines whether sponsored eligibility applies based on this tuple and query context.

### 1.1 Regime A: Specific-quality (zero sponsored)

**Triggering conditions:**

- Mode: `ask`
- Sub-intent: **one of** `PHONE_LOOKUP`, `WEBSITE_LOOKUP`, `HOURS_LOOKUP`, `LOCATION_LOOKUP`, `RATING_LOOKUP`, `REVIEW_COUNT_LOOKUP`, `TIME_LOOKUP`, `OPEN_NOW`
- Intent: entity resolved (named provider in the query)

**Whether sponsored is eligible:** NO — zero sponsored blocks allowed.

**Reliability bar:** N/A.

**Whether organic alternatives must accompany:** N/A.

**Rationale:** User has a specific business in mind and wants a factual property (hours, phone, address). Injecting a sponsored alternative here misleads intent. The Tier 1 path already handles this — renderer not involved.

**Worked example:**

```
Query: "What are Barley Brothers' hours?"
Intent: mode=ask, sub_intent=HOURS_LOOKUP, entity=Barley Brothers
Router decision: → Tier 1 deterministic (no sponsored path)
Output: "Barley Brothers is open 11 AM–10 PM daily." (Tier 1)
```

### 1.2 Regime B: Generic-category (sponsored eligible, organic required)

**Triggering conditions:**

- Mode: `ask`
- Sub-intent: **one of** `GENERAL_QUESTION`, `RECOMMENDATION`, `DISCOVERY`
- Intent: **no entity resolved** (category mentioned, not a specific business); category is searchable (e.g., "restaurants," "coffee," "nightlife," "fitness," "tours")

**Whether sponsored is eligible:** YES — if eligible sponsors exist in this category.

**Reliability bar:** Standard. Sponsored block must have verified fields from `Sponsor` record (name, attribution text). Renderer must pass tone allowlist (§3).

**Whether organic alternatives must accompany:** YES — organic catalog rows must be returned alongside the sponsored block. Query for 3–5 organic results in the category; renderer wraps the sponsored block; Tier 3 or formatter lists both.

**Rationale:** User asks a category-level question without a specific business in mind. A relevant sponsored option is informative if clearly disclosed and grounded in verified data. Showing both sponsored and organic respects user choice.

**Worked example:**

```
Query: "Where can I grab coffee?"
Intent: mode=ask, sub_intent=GENERAL_QUESTION, entity=None, inferred_category=coffee
Router decision: → Tier 2 / Tier 3 eligible for sponsored
Sponsored candidate: Sponsor { name="Brew Haven", attribution_text="local coffee roaster", status=live }
Organic candidates: [Provider {provider_name="Hava Café"}, Provider {provider_name="The Daily Grind"}, …]
Renderer output:
  Sponsored block: "Sponsored: Brew Haven — local coffee roaster. [Visit](url)"
  Organic: Hava Café and The Daily Grind are solid standbys…
Tier 3 combines: framing + sponsored + organic in one response
```

### 1.3 Regime C: Emergency-urgent (sponsored eligible, organic required, high reliability bar)

**Triggering conditions:**

- Mode: `ask`
- Sub-intent: **one of** `DATE_LOOKUP`, `NEXT_OCCURRENCE`, `AGE_LOOKUP`, `COST_LOOKUP` on program/event rows
- Intent: user seeks immediate time-sensitive information (when is X, is X family-friendly, is X free/cheap)
- Catalog has: verified event or program rows + eligible sponsor(s) in the same domain (e.g., "looking for free kids activities" + free program sponsor)

**Whether sponsored is eligible:** YES — but only if organic alternatives exist and reliability gates pass.

**Reliability bar:** STRICT. Sponsor record must have:
- Non-null `verified_fields_present` status (see Sponsor model, §2)
- No tone-allowlist violations (§3)
- Temporal alignment: for date/time lookups, sponsor booking window (`starts_at`, `ends_at`) must overlap with query context (don't show "summer camp" sponsor for a winter event)

**Whether organic alternatives must accompany:** YES — mandatory. If organic rows exist, they are returned alongside sponsored. If no organic rows exist, sponsored block is suppressed (falls back to organic-only).

**Rationale:** Emergency-urgent queries (when is the next kids program, how much does the workshop cost) are high-stakes — users may be making immediate decisions. Sponsored blocks are allowed only when verified alternatives exist in parallel, and the sponsor's temporal scope matches the query window.

**Worked example:**

```
Query: "Are there any free kids activities this weekend?"
Intent: mode=ask, sub_intent=COST_LOOKUP, inferred_category=programs, age_hint=kids
Router decision: → Tier 3 eligible for Regime C
Organic candidates: [Program {title="Aquatic Center open swim", cost=free}, Program {title="Museum Saturday", cost=free}]
Sponsored candidate: Sponsor {name="Youth Center", attribution="community programs", status=live, starts_at=2026-05-09, ends_at=2026-05-31}
Reliability check: cost field present, temporal overlap confirmed ✓
Renderer output:
  Organic: Two free kids activities this weekend…
  Sponsored: "Sponsored: Youth Center — community programs. [Visit](url)"
Tier 3 combines both
```

**If no organic rows exist:**

```
Query: "Free events next week?"
Organic candidates: [] (empty — no free events in the catalog)
Sponsored candidate: exists but reliability check fails (no organic to pair with)
Renderer decision: → suppress sponsored block, return organic-only (which is empty)
Output: "Don't have free events scheduled next week — /contribute to add one."
```

---

## 2. Module: `app/chat/disclosure_render.py`

This module contains deterministic, pure functions for rendering sponsored blocks. No LLM calls; all formatting is database-driven and rules-based.

### 2.1 Public function signatures

```python
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.db.models import Sponsor

class PlacementRegime(str, Enum):
    """Placement eligibility based on query intent."""
    SPECIFIC_QUALITY = "specific_quality"      # No sponsored allowed
    GENERIC_CATEGORY = "generic_category"      # Sponsored eligible, organic required
    EMERGENCY_URGENT = "emergency_urgent"      # Sponsored eligible, strict bar

@dataclass
class SponsoredBlock:
    """Rendered sponsored content for injection into response."""
    disclosure_word: str          # Always "Sponsored"
    body: str                      # Verified factual descriptors (50–100 words)
    cta: Optional[str]            # CTA label and URL, or None if CTA suppressed
    attribution: str              # Sponsor name and attribution text (5–20 words)
    sponsor_id: str               # For impression/click logging
    regime: PlacementRegime       # Which regime gates this block

def select_placement_regime(
    intent_result: IntentResult,
) -> PlacementRegime:
    """Classify the query into a placement regime.

    Args:
        intent_result: output from intent_classifier.classify()

    Returns:
        PlacementRegime enum value.

    Logic (per §1):
    - If sub_intent is specific-quality (HOURS_LOOKUP, PHONE_LOOKUP, etc.)
      and entity is resolved → SPECIFIC_QUALITY
    - If sub_intent is generic (GENERAL_QUESTION, RECOMMENDATION, DISCOVERY)
      and no entity, and category searchable → GENERIC_CATEGORY
    - If sub_intent is emergency-urgent (DATE_LOOKUP, COST_LOOKUP, AGE_LOOKUP, NEXT_OCCURRENCE)
      and catalog has event/program rows → EMERGENCY_URGENT
    - Else → SPECIFIC_QUALITY (default safe, zero sponsored)
    """

def render_sponsored_block(
    regime: PlacementRegime,
    candidate_sponsors: list[Sponsor],
    *,
    query_context: Optional[dict] = None,
    db: Optional[Session] = None,
) -> Optional[SponsoredBlock]:
    """Render a sponsored block for a given regime.

    Args:
        regime: PlacementRegime from select_placement_regime()
        candidate_sponsors: list of eligible Sponsor rows (pre-filtered by caller
                           for status=live, active=True, booking window overlap)
        query_context: optional dict with keys:
                      - 'organic_rows': list of Provider/Event/Program dicts
                      - 'category': inferred category (e.g., 'coffee', 'fitness')
                      - 'date_context': date/time scope if emergency-urgent
        db: Session for read-only lookups if needed (mostly unused; for consistency)

    Returns:
        SponsoredBlock if rendering succeeded and tone/reliability checks pass.
        None if regime forbids sponsored, candidate list is empty, or tone
        allowlist violations detected.

    Behavior (per regime):
    - SPECIFIC_QUALITY: always return None (zero sponsored allowed)
    - GENERIC_CATEGORY: pick one sponsor (highest weight if multiple live),
                       render factual body from sponsor fields, check allowlist
    - EMERGENCY_URGENT: pick one sponsor, apply temporal check (starts_at/ends_at
                       overlap with query context), apply strict tone bar, return
                       None if organic_rows is empty (no pairing possible)

    Deterministic: given the same inputs (regime, sponsors, context), always
    returns the same struct. Internal randomness is forbidden.
    """

def _check_tone_allowlist(
    disclosure_word: str,
    body: str,
    attribution: str,
) -> bool:
    """Validate tone against allowlist.

    Args:
        disclosure_word: the word to be disclosed (always "Sponsored")
        body: rendered body text
        attribution: sponsor attribution line

    Returns:
        True if text passes (no disallowed phrases detected).
        False if any disallowed superlatives, comparative claims, or evaluative
        language found (§3).

    Implementation: regex/token matching against DISALLOWED_PHRASES (defined
    in module). Checks body and attribution together; disclosure_word is
    always "Sponsored" so always passes.
    """

def _pick_sponsor(candidates: list[Sponsor]) -> Optional[Sponsor]:
    """Pick one sponsor from a list for rendering.

    Deterministic selection: highest weight first; ties broken by created_at
    (oldest first, stable sort).

    Args:
        candidates: non-empty list of Sponsor rows

    Returns:
        One Sponsor or None if list is empty or all candidates fail pre-checks.
    """
```

### 2.2 SponsoredBlock dataclass

```python
@dataclass
class SponsoredBlock:
    disclosure_word: str          # Always literal "Sponsored" (see §4)
    body: str                      # Factual body: 50–100 words, no superlatives
    cta: Optional[str]            # Formatted as "Label [URL](url)" or None to suppress
    attribution: str              # "Sponsor name — role/descriptor" (5–20 words)
    sponsor_id: str               # For impression/click logging via the API layer
    regime: PlacementRegime       # Which regime gates this block
```

**Body field constraints:**

- Drawn from verified `Sponsor` record fields: `name`, `headline`, `pitch`, `attribution_text`, and linked `Provider` fields (if `business_id` is set): `years_in_business`, `hours`, `service_area`, `certifications`.
- Factual descriptors only (see §3 allowlist). No evaluative language.
- Length: 50–100 words. Rendered as a single paragraph; no markdown or formatting inside body.
- If verified data produces empty or non-compliant body, return `None` (fallback to organic-only).

**CTA field:**

- Format: `"Label [URL](url)"` where Label is `Sponsor.cta_label` and URL is `Sponsor.cta_url`.
- If `cta_label` or `cta_url` is missing, return `None` (CTA not shown).
- URL must be non-empty and valid (`http://` or `https://` scheme).

**Attribution field:**

- Format: `"Sponsor name — descriptor"` where descriptor is from `Sponsor.attribution_text` or inferred category/role.
- Example: `"Brew Haven — local coffee roaster"` or `"Youth Center — community programs"`.
- Length: 5–20 words.
- Must include the sponsor name and at least one verified descriptor.

---

## 3. Tone allowlist (deterministic)

The tone allowlist is a set of allowed patterns and a corresponding disallowed list. The renderer applies regex and token matching to the body and attribution before outputting a `SponsoredBlock`.

### 3.1 Allowed factual descriptors

**From verified `Sponsor` fields:**
- Sponsor name (always allowed in attribution)
- `attribution_text` (advertiser-supplied descriptor, verbatim if on allowlist)
- `headline`, `pitch` (advertiser-supplied, but scanned for tone violations)

**From linked `Provider` (if `business_id` set):**
- `years_in_business` (e.g., "in business since 2015," "15+ years")
- `hours` (e.g., "open 9–5 weekdays," "by appointment")
- `service_area` (e.g., "serves Lake Havasu and surrounding area")
- `certifications` (e.g., "licensed, insured," "certified yoga instructor")
- `category` (e.g., "coffee roastery," "fitness studio") — use `_category_label()` from `app/home/queries.py`

**Allowed templates (examples):**
- `"{name} is a {category} in {city}."`
- `"{name} has been {years_in_business}."`
- `"{name} offers {service_area}."`
- `"{name} is {certification_status}."`
- `"{name} is open {hours}."`
- `"{name} — {role}."`

### 3.2 Disallowed language

**Superlatives and comparative claims — strictly forbidden:**
- `best`, `top`, `leading`, `premier`, `finest`, `outstanding`
- `highest-rated`, `best-reviewed`, `most-popular`
- `only`, `unique`, `exclusive`
- `award-winning`, `award winner`
- `#1`, `rank 1`, `number one`
- Any phrase implying ranking or hierarchy

**Evaluative/marketing language — strictly forbidden:**
- `highly rated`, `highly recommended`, `customer favorite`
- `perfect`, `excellent`, `amazing`, `fantastic`, `incredible`
- `don't miss`, `must try`, `must-have`
- `locals' secret`, `locals' favorite`, `locals love`
- `worth it`, `absolutely worth your time`
- `life-changing`, `transformative`

**False scarcity / urgency — strictly forbidden:**
- `limited time`, `while supplies last`, `ends soon`
- `exclusive offer`, `special deal`

**Comparative language — strictly forbidden:**
- `better than`, `superior to`, `beats all other`

### 3.3 Implementation: DISALLOWED_PHRASES

```python
# In app/chat/disclosure_render.py

DISALLOWED_PHRASES = [
    # Superlatives
    r'\b(best|top|leading|premier|finest|outstanding)\b',
    r'\b(highest-rated|best-reviewed|most-popular)\b',
    r'\bonly\b', r'\bunique\b', r'\bexclusive\b',
    r'\baward[-\s]?winning\b', r'\baward winner\b',
    r'#1|rank 1|number one',
    # Evaluative marketing
    r'\bhighly\s+(rated|recommended)\b',
    r'\b(customer|local|visitor)\s+favorite\b',
    r'\b(perfect|excellent|amazing|fantastic|incredible)\b',
    r'\bdon\'?t miss\b', r'\bmust\s+(try|have)\b',
    r'\blocals?\s+love\b', r'\blocals?\s+secret\b',
    r'\bworth\s+it\b', r'\babsolutely\b',
    r'\blife-changing\b', r'\btransformative\b',
    # False scarcity
    r'\blimited\s+time\b', r'\bwhile\s+supplies\b',
    r'\bspecial\s+deal\b',
    # Comparative
    r'\bbetter\s+than\b', r'\bsuperior\s+to\b', r'\bbeats\b',
]

def _check_tone_allowlist(
    disclosure_word: str,
    body: str,
    attribution: str,
) -> bool:
    """Return False if any disallowed phrase found in body or attribution."""
    combined = f"{body} {attribution}".lower()
    for pattern in DISALLOWED_PHRASES:
        if re.search(pattern, combined, re.IGNORECASE):
            return False
    return True
```

### 3.4 Failure mode: renderer returns None

If verified `Sponsor` record contains no allowable factual descriptors (e.g., all copy is marketing hyperbole), the renderer **returns `None`**. The call-site falls back to organic-only response (per Regime B or C rules).

**Example:**

```python
# Sponsor with no compliant body
Sponsor { 
    name="Amazing Coffee Co",
    headline="Best coffee in Lake Havasu!",  # violates allowlist
    attribution_text="award-winning cafe",    # violates allowlist
    pitch=None
}

# Renderer tries to build body from allowlist-compliant fields
# → no fields available → returns None
# → Tier 3 falls back to organic-only listing
```

---

## 4. Disclosure consistency

**Canonical disclosure word:** `"Sponsored"` (always this, never "Featured," "Partner," "Recommended," etc.).

**Module constant:**

```python
# In app/chat/disclosure_render.py
DISCLOSURE_WORD = "Sponsored"
```

**Output template (for chat):**

The disclosure word appears once per sponsored block, prominently at the start:

```
Sponsored: [attribution]. [body] [CTA link if present].
```

**Example renderings:**

```
Regime B (generic-category):
  Sponsored: Brew Haven — local coffee roaster. Hand-roasted beans, open 7 AM–6 PM daily. Visit.

Regime C (emergency-urgent):
  Sponsored: Youth Center — community programs. Free Saturday open gym for ages 5–12, 9 AM–12 PM. Register.
```

**Where the constant lives:** `app/chat/disclosure_render.py::DISCLOSURE_WORD = "Sponsored"`

---

## 5. Integration points

The renderer is invoked at two sites in the existing call chain. Both are dispatch decision points where the codebase currently routes to the LLM; the renderer adds a deterministic alternative.

### 5.1 Tier 2 formatter dispatch (optional integration)

**Location:** `app/chat/tier2_formatter.py::format()`

**Current behavior:** Tier 2 already bypasses the LLM for all-event rows (lines 144–153) using `tier2_catalog_render.render_tier2_events()`. This is the precedent.

**Proposed integration:**

Extend the dispatch to cover sponsored-eligible category queries:

```python
# Tier 2 formatter, new dispatch branch (after line 143)

if all(r.get("type") == "event" for r in rows):
    # Existing path: all-event deterministic render
    text = tier2_catalog_render.render_tier2_events(query, rows)
    return text.strip(), 0, 0

# NEW: Sponsored-eligible category query (generic-category regime)
regime = tier2_catalog_render.select_placement_regime(intent_result)
if regime == PlacementRegime.GENERIC_CATEGORY and rows:
    sponsored_block = tier2_catalog_render.render_sponsored_block(
        regime=regime,
        candidate_sponsors=candidate_sponsors,  # passed from tier2 caller
        query_context={"organic_rows": rows, "category": intent_result.category},
        db=db
    )
    if sponsored_block:
        # Inject sponsored block into formatter output
        text = tier2_formatter._format_via_llm(query, rows)
        # Post-process to inject sponsored block (see integration notes below)
        return text, in_tok, out_tok
    # If renderer returns None, fall through to LLM-only path below

# Existing LLM path (mixed or non-event rows)
text, in_tok, out_tok = _format_via_llm(query, rows)
```

**Tier 2 integration note:** This is a **Phase 2 optional** slice. Phase 1 focuses on Tier 3 integration (§5.2). The Tier 2 slice adds complexity around injection and reordering; defer unless throughput data justifies the token savings.

### 5.2 Tier 3 handler post-processing (primary Phase 1 integration point)

**Location:** `app/chat/tier3_handler.py::answer_with_tier3()`

**Current behavior:** Tier 3 receives an `IntentResult` and optional onboarding hints; it calls the LLM with a context block and returns synthesis text.

**Proposed integration:**

Insert a pre-LLM renderer check:

```python
# In tier3_handler.py, at start of answer_with_tier3()

from app.chat.disclosure_render import (
    select_placement_regime,
    render_sponsored_block,
    PlacementRegime,
    SponsoredBlock,
)

def answer_with_tier3(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: Mapping[str, Any] | None = None,
    now_line: str | None = None,
    organic_context: Optional[list[dict]] = None,  # NEW: organic catalog rows from Tier 2
) -> tuple[str, int, int]:
    """Tier 3 synthesis with optional sponsored block pre-rendering."""

    # NEW: check if sponsored block should be rendered deterministically
    regime = select_placement_regime(intent_result)
    
    sponsored_block: Optional[SponsoredBlock] = None
    if regime != PlacementRegime.SPECIFIC_QUALITY:
        # Regime B or C: fetch eligible sponsors and attempt render
        candidate_sponsors = db.query(Sponsor).filter(
            Sponsor.status == SponsorStatus.LIVE.value,
            Sponsor.active == True,
            Sponsor.starts_at <= now_lake_havasu(),
            or_(Sponsor.ends_at == None, Sponsor.ends_at > now_lake_havasu()),
        ).all()
        
        if candidate_sponsors:
            sponsored_block = render_sponsored_block(
                regime=regime,
                candidate_sponsors=candidate_sponsors,
                query_context={
                    "organic_rows": organic_context or [],
                    "category": intent_result.inferred_category,
                    "date_context": now_lake_havasu(),
                },
                db=db,
            )

    # Existing Tier 3 path: build context and call LLM
    context = build_context_for_tier3(intent_result, db, organic_context)
    
    # LLM call (unchanged)
    system_prompt = _load_tier3_system_prompt()
    result = call_anthropic_messages(
        system_prompt=system_prompt,
        user_text=f"Query: {query}\n\nContext:\n{context}",
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_TEMPERATURE,
        model=_TIER3_MODEL,
    )
    
    # NEW: inject sponsored block if renderer produced one
    text = result.text if result else None
    if text and sponsored_block and regime == PlacementRegime.GENERIC_CATEGORY:
        # Inject sponsored block after first sentence of organic response
        text = _inject_sponsored_block(text, sponsored_block)
    elif text and sponsored_block and regime == PlacementRegime.EMERGENCY_URGENT:
        # For emergency-urgent, prepend sponsored block (time-sensitive info)
        text = f"{_format_sponsored_block(sponsored_block)}\n\n{text}"
    
    # Log and return
    in_tok = result.usage.billable_input if result else None
    out_tok = result.usage.output_tokens if result else None
    return text, in_tok, out_tok
```

**Helper: format and inject**

```python
def _format_sponsored_block(block: SponsoredBlock) -> str:
    """Format a SponsoredBlock for text injection."""
    line = f"{block.disclosure_word}: {block.attribution}. {block.body}"
    if block.cta:
        line += f" {block.cta}"
    return line + "."

def _inject_sponsored_block(organic_text: str, block: SponsoredBlock) -> str:
    """Insert sponsored block after first sentence of organic response.
    
    Deterministic: find the first period, insert block after it.
    """
    first_period = organic_text.find(".")
    if first_period == -1:
        return organic_text  # No period; append at end
    insert_at = first_period + 1
    sponsored_line = _format_sponsored_block(block)
    return organic_text[:insert_at] + f" {sponsored_line}" + organic_text[insert_at:]
```

### 5.3 Spotlight homepage (already deterministic — consistency only)

**Location:** `app/home/queries.py::spotlight()` (or equiv builder)

**Current behavior:** Spotlight rows are already deterministic (curated list, no LLM). They may render a disclosure label in the template.

**Proposed integration:**

Ensure spotlight-rendered sponsors use the same `DISCLOSURE_WORD` constant. Import from `disclosure_render.py`:

```python
from app.chat.disclosure_render import DISCLOSURE_WORD

# In spotlight builder:
if row.get("is_sponsored"):
    row["disclosure"] = DISCLOSURE_WORD  # Always "Sponsored"
```

This is a **consistency-only** pass; no new logic needed. Prevents template drift toward custom disclosure labels.

---

## 6. Eval harness extension

Test categories are added to `tests/test_disclosure_render.py`. The harness covers the four principal failure modes: disclosure compliance, tone violations, regime gating, and regression.

### 6.1 Test file: `tests/test_disclosure_render.py`

**Structure:**

```python
import pytest
from sqlalchemy.orm import Session
from app.chat.disclosure_render import (
    select_placement_regime,
    render_sponsored_block,
    _check_tone_allowlist,
    PlacementRegime,
    SponsoredBlock,
    DISCLOSURE_WORD,
)
from app.db.models import Sponsor, SponsorStatus
from app.chat.intent_classifier import IntentResult
```

### 6.2 Test categories and assertions

#### 6.2.1 Disclosure compliance (zero drift)

**Test: every sponsored mention carries the canonical word**

```python
def test_disclosure_word_always_canonical(db: Session):
    """Every rendered sponsored block uses the literal word 'Sponsored'."""
    sponsor = Sponsor(
        name="Test Coffee",
        status=SponsorStatus.LIVE.value,
        active=True,
        attribution_text="local roaster",
        cta_label="Visit",
        cta_url="https://example.com",
    )
    db.add(sponsor)
    db.commit()
    
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    
    assert block is not None
    assert block.disclosure_word == DISCLOSURE_WORD
    assert block.disclosure_word == "Sponsored"
```

#### 6.2.2 Tone violations (allowlist enforcement)

**Test: zero allowlist breaches**

```python
def test_tone_allowlist_rejects_superlatives(db: Session):
    """Sponsor with 'best in town' fails allowlist check."""
    sponsor = Sponsor(
        name="Best Coffee Ever",
        status=SponsorStatus.LIVE.value,
        active=True,
        headline="Best coffee in Lake Havasu!",
        attribution_text="award-winning cafe",
        cta_label="Visit",
        cta_url="https://example.com",
    )
    db.add(sponsor)
    db.commit()
    
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    
    # Renderer rejects due to tone violations
    assert block is None

def test_tone_allowlist_allows_factual(db: Session):
    """Sponsor with verified factual descriptors passes."""
    sponsor = Sponsor(
        name="Brew Haven",
        status=SponsorStatus.LIVE.value,
        active=True,
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso and pastries.",
        pitch="Open weekdays 7 AM–6 PM.",
        cta_label="Visit",
        cta_url="https://example.com",
    )
    db.add(sponsor)
    db.commit()
    
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    
    assert block is not None
    assert "best" not in block.body.lower()
    assert "award" not in block.body.lower()
```

#### 6.2.3 Regime gating (specific-quality zero)

**Test: specific-quality regime zero sponsored**

```python
def test_regime_specific_quality_zero_sponsored():
    """Specific-quality regime always returns None."""
    intent_result = IntentResult(
        mode="ask",
        sub_intent="HOURS_LOOKUP",
        entity_resolved="Barley Brothers",
    )
    regime = select_placement_regime(intent_result)
    
    assert regime == PlacementRegime.SPECIFIC_QUALITY
    
    # Any sponsored candidates are ignored
    sponsor = Sponsor(name="Test", status="live", active=True)
    block = render_sponsored_block(
        regime=regime,
        candidate_sponsors=[sponsor],
        query_context={},
        db=None,
    )
    
    assert block is None
```

#### 6.2.4 Emergency regime temporal check

**Test: emergency-urgent temporal overlap enforced**

```python
def test_regime_emergency_urgent_temporal_check(db: Session):
    """Emergency-urgent: sponsor.starts_at must overlap with query date."""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    past_date = now - timedelta(days=10)
    
    sponsor = Sponsor(
        name="Old Summer Camp",
        status=SponsorStatus.LIVE.value,
        active=True,
        starts_at=past_date,
        ends_at=past_date + timedelta(days=5),  # Ended 5 days ago
        attribution_text="community programs",
        cta_label="Visit",
        cta_url="https://example.com",
    )
    db.add(sponsor)
    db.commit()
    
    intent_result = IntentResult(
        mode="ask",
        sub_intent="DATE_LOOKUP",
        inferred_category="programs",
    )
    regime = select_placement_regime(intent_result)
    assert regime == PlacementRegime.EMERGENCY_URGENT
    
    # Sponsor is outside its booking window; renderer returns None
    block = render_sponsored_block(
        regime=regime,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [{"title": "Summer Swim", "date": "2026-05-09"}],
            "date_context": now,
        },
        db=db,
    )
    
    assert block is None  # Out of temporal window
```

#### 6.2.5 Emergency regime organic pairing required

**Test: emergency-urgent with no organic rows suppresses sponsored**

```python
def test_regime_emergency_urgent_requires_organic_pair(db: Session):
    """Emergency-urgent: if no organic_rows, sponsored is suppressed."""
    sponsor = Sponsor(
        name="Youth Center",
        status=SponsorStatus.LIVE.value,
        active=True,
        starts_at=datetime.now(),
        ends_at=datetime.now() + timedelta(days=30),
        attribution_text="community programs",
        cta_label="Visit",
        cta_url="https://example.com",
    )
    db.add(sponsor)
    db.commit()
    
    intent_result = IntentResult(
        mode="ask",
        sub_intent="DATE_LOOKUP",
        inferred_category="programs",
    )
    regime = select_placement_regime(intent_result)
    
    # No organic rows provided
    block = render_sponsored_block(
        regime=regime,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [],  # Empty — no organic alternative
            "date_context": datetime.now(),
        },
        db=db,
    )
    
    assert block is None  # Sponsored suppressed (no organic pairing)
```

#### 6.2.6 Regression: canned queries with golden files

**Test: known sponsor inventory, known intent, expected output struct**

```python
def test_regression_generic_category_coffee_query(db: Session):
    """Golden-file regression: 'Where can I grab coffee?' query."""
    # Seed: one live sponsor, two organic providers
    sponsor = Sponsor(
        name="Brew Haven",
        status=SponsorStatus.LIVE.value,
        active=True,
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso, open 7 AM–6 PM.",
        pitch="Sourced from regional roasters.",
        cta_label="Visit",
        cta_url="https://brewhaven.example.com",
    )
    db.add(sponsor)
    db.commit()
    
    # Intent result from normalized query "where can i grab coffee"
    intent_result = IntentResult(
        mode="ask",
        sub_intent="GENERAL_QUESTION",
        entity_resolved=None,
        inferred_category="coffee",
    )
    
    regime = select_placement_regime(intent_result)
    assert regime == PlacementRegime.GENERIC_CATEGORY
    
    block = render_sponsored_block(
        regime=regime,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [
                {"provider_name": "Hava Café", "category": "coffee"},
                {"provider_name": "The Daily Grind", "category": "coffee"},
            ],
            "category": "coffee",
        },
        db=db,
    )
    
    assert block is not None
    assert block.disclosure_word == "Sponsored"
    assert "Brew Haven" in block.attribution
    assert "local coffee roaster" in block.attribution
    assert block.body  # Non-empty, factual body
    assert block.cta == "Visit [https://brewhaven.example.com](https://brewhaven.example.com)"
    assert block.sponsor_id == sponsor.id
    assert block.regime == PlacementRegime.GENERIC_CATEGORY
```

**Golden file:** `tests/fixtures/disclosure_regression_golden.json`

```json
{
  "query": "where can i grab coffee",
  "expected_regime": "generic_category",
  "expected_disclosure_word": "Sponsored",
  "expected_body_contains": ["Brew Haven", "hand-roasted", "7 AM", "6 PM"],
  "expected_body_excludes": ["best", "award", "favorite", "amazing"]
}
```

### 6.3 Close criteria (all tests in one batch)

```bash
pytest tests/test_disclosure_render.py -v --tb=short
```

**All tests must pass.** No skips or xfails permitted.

---

## 7. Migration path

The renderer ships behind a feature flag. This de-risks rollout and allows gradual validation in production.

### 7.1 Phase 1: ship module + tests

**Deliverable:** `app/chat/disclosure_render.py` + `tests/test_disclosure_render.py`

**Default:** `FEATURE_FLAG_DISCLOSURE_RENDERER` env var (default unset → renderer not invoked)

**Behavior:** Existing LLM-formatted paths unchanged. Renderer is available but not invoked.

**Close criterion:** All tests pass; code review; no integration points activated yet.

### 7.2 Phase 2: enable for generic-category (low risk)

**Lever:** Set `FEATURE_FLAG_DISCLOSURE_RENDERER=true` in the production environment (Railway env var)

**Scope:** Tier 3 integrates the renderer for `PlacementRegime.GENERIC_CATEGORY` only (Regime B).

**Rationale:** Generic-category queries have low specificity; sponsored blocks are informative. No temporal constraints. Easiest to validate.

**Observability (P2.OBS.1 — shipped):** Persist disclosure telemetry as **typed scalar columns** on `chat_logs`, not JSON blobs:

| Column | Purpose |
| --- | --- |
| `disclosure_regime` | `VARCHAR(32)` — nullable; CHECK allows `specific_quality` \| `generic_category` \| `emergency_urgent` (PlacementRegime values). Partial index `ix_chat_logs_disclosure_regime` where non-NULL. |
| `disclosure_sponsor_id` | `VARCHAR(64)` — nullable sponsor UUID string when a candidate was evaluated or rendered. |
| `disclosure_tone_allowlist_passed` | `BOOLEAN` — nullable; `TRUE` only when a sponsored block was emitted. |
| `disclosure_eligible` | `BOOLEAN` — nullable; whether at least one sponsor passed regime eligibility gates for placement (may be `FALSE` when no inventory qualifies). |

All four are **NULL** when the deterministic renderer did not run (feature flag off, non–Tier-3 path, or Tier 3 exit before `render_with_decision`). Phase 2 audit queries expect `GROUP BY disclosure_regime`, aggregates on booleans, and index-backed filters — typed columns support this; a single JSON column does not.

**Transport:** `RenderDecision` (`regime`, `eligible`, `sponsor_id`, `tone_allowlist_passed`) is recorded from `disclosure_render.render_with_decision()` via a **`contextvars.ContextVar`**. `record_decision()` runs inside the renderer; `consume_decision()` runs once inside `log_unified_route` at chat-log insert time (one-shot read+clear). `reset_decision_context()` runs at **unified-router request entry** so decisions never bleed across requests.

**Rejected:** stuffing observability into **`chat_logs.llm_tokens_used`** or any other typed numeric token counter — that column counts completion tokens; overloading it with JSON was a spec typo/misuse and is explicitly **out of scope**.

**Rollback:** Feature flag flip to False; existing Tier 3 path restored.

### 7.3 Phase 3: extend to emergency-urgent (after reliability validation)

**Scope:** Tier 3 integrates the renderer for `PlacementRegime.EMERGENCY_URGENT` (Regime C).

**Prerequisite:** Phase 2 observability data shows <0.1% tone-allowlist violations and no user complaints.

**Rationale:** Emergency-urgent queries are time-sensitive; the strict reliability bar and organic-pairing requirement justify the risk.

**Rollback:** Feature flag disables both B and C, falls back to LLM-only.

---

## 8. Out of scope (do not expand)

- **LLM-generated sponsor copy.** The renderer reads advertiser-supplied `Sponsor` fields; it does not LLM-synthesize copy. Copy curation is a separate admin/advertiser workflow.
- **Pricing tier logic (Featured / Spotlight / Premier gating).** The `Sponsor.slot` column already encodes this; renderer reads it, does not decide it.
- **Sponsor inventory rotation.** Caller pre-filters sponsors by `status`, `active`, booking window, etc. Renderer does not manage inventory.
- **Visitor mode UI (Phase 2/4).** Rendering is the same; UI presentation is separate.
- **Homepage Spotlight rendering (already deterministic).** Consistency pass only; no new logic.
- **Email / SMS / push notifications.** Disclosure renderer is chat-only.

---

## 9. Lane map (parallelism guide)

The renderer is cohesive enough for a single agent but has clear sub-slices if multiple agents coordinate.

| Lane | Slice | Primary files | Dependencies |
|---|---|---|---|
| **X1** | Module + tests | `app/chat/disclosure_render.py`, `tests/test_disclosure_render.py` | None — self-contained |
| **X2** | Tier 3 integration | `app/chat/tier3_handler.py`, `docs/maintainability/disclosure_renderer_spec.md` (update with integration notes) | X1 (must ship first) |
| **X3** | Tier 2 integration (optional Phase 2) | `app/chat/tier2_formatter.py` | X1, X2 |
| **X4** | Feature flag + observability | `app/config.py`, `app/db/chat_logging.py` | X1, X2 |

**Conflict surface:** All lanes touch common files (config, chat_logging, models if schema changes needed). Mitigations:

- Lanes X1 and X2 are serialized (X1 first, X2 second). X2 depends on X1 landing.
- Lane X3 (Tier 2) is optional and deferred to Phase 2; don't start it until X1 + X2 are live and validated.
- Lane X4 (config/observability) is a thin slice; treat as part of X2.

**Critical convention:** agents executing parallel lanes **must use anchored `Edit` operations, never full `Write`** on shared files like `models.py`, `config.py`, or chat_logging.py. This is the lesson from the UI-data-correctness chaos where three `Write`-based agents truncated each other's work. Document this prominently in commit messages and on PR descriptions.

---

## 10. Doc/PR hygiene (per WORKING_AGREEMENT)

For the disclosure renderer ship:

- **Commit message:** `disclosure-renderer: deterministic sponsored block rendering (Phase 1 keystone)` — reference the spec section number (e.g., §2 module, §6 tests).
- **BACKLOG.md ship-log entry:** One entry per lane (X1 module+tests, X2 tier3 integration); include close criteria and testing scope.
- **STATE.md narrative update:** Record that the renderer is live (Phase 1) and feature-flagged off by default; note observability instrumentation added.
- **This spec:** Mark status `RESOLVED` once all tests pass and the module lands in main.

---

## 11. Out of scope for subagent (do NOT touch)

- `app/home/queries.py` — concurrent work on homepage.
- `app/home/router.py` — concurrent work.
- `tests/test_home_queries*.py` — concurrent test files.
- `app/db/models.py` — concurrent slot-migration repair (Cursor) may touch Sponsor model; coordinate schema changes in writing.
- `alembic/versions/` — concurrent migrations.
- `docs/BACKLOG.md` — do NOT append ship-log entries there; return as text in final report only.

---

**Spec complete.** Ready for Phase 1 implementation. All sections are aligned with `ui_data_correctness_spec.md` template, `tier2_catalog_render.py` architectural pattern, and persona-brief tone requirements.
