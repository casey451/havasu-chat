# `app/core/intent.py` module disposition — decision

**Date:** 2026-05-06 (Slice 68).  
**Author:** Doc slice (Cursor); Casey approval pending §7.  
**Status:** Draft — awaiting Casey's §7 sign-off. Implementation campaign **OPEN** until then.  
**Companion:** `docs/components/intent.md` (Slice 67b component inventory).

## §1 Observation

`app/core/intent.py` is **654 lines** (line count as of this slice).

**Step 0 audit (reproducible):**

```powershell
Select-String -Path 'app\**\*.py','tests\**\*.py','scripts\**\*.py' `
  -Pattern '^from app\.core\.intent import|^from app\.core import intent|^import app\.core\.intent'
```

Across **`app/`** (excluding `app/core/intent.py` itself), **exactly two** modules import from `app.core.intent`:

| Symbol | Importer | Role |
| ------ | -------- | ---- |
| `detect_out_of_scope_category` | `app/chat/intent_classifier.py` — import at **line 17**, call at **line 147** | Tier 1 early gate before LLM-heavy routing; returns chat `"OUT_OF_SCOPE"` when a category matches. |
| `open_ended_search_message` | `app/core/search.py` — import at **line 32**, call at **line 379** | Search-strategy dispatch: open-ended prompts without slots → `"CLARIFY_DATE"` vs `"RUN_WITH_NUDGE"`. |

No `scripts/**/*.py` imports surfaced.

**Tests** still import the dormant cascade and helpers:

- `tests/test_phase3.py` — `detect_intent`, `detect_out_of_scope_category`, labels.
- `tests/test_phase8.py` — `detect_intent`, `is_cancel_or_restart`.
- `tests/test_phase8_5.py` — broad cascade coverage + `detect_out_of_scope_category`.
- `tests/test_calendar_intent.py` — `detect_intent`, `is_calendar_open_phrase`, `CALENDAR_VIEW`.

**In-module surface not reachable from any `app/` importer today:**

- **Cascade:** `detect_intent` (15-step ordering documented in `docs/components/intent.md`).
- **Helpers:** includes `_explicit_add_event_route`, `_commercial_services_query`, `_word_boundary`, `is_hard_reset`, `is_soft_cancel`, `is_cancel_or_restart`, `_has_time_or_date_reference`, `_add_creation_language`, `_add_meta_intent_question`, `_active_non_search_flow`, `_listing_hit`, `_refinement_looks_like_filter`, `_query_looks_like_program` (defined **lines 523–538**; **no non-test callers** in-repo), `is_confirmation`, `is_rejection`, `is_skip_optional_contact`, `is_greeting`, `escape_to_search`, plus non-cascade helpers such as `is_calendar_open_phrase`.
- **Twelve label constants:** `HARD_RESET`, `SOFT_CANCEL`, `GREETING`, `LISTING_INTENT`, `ADD_EVENT`, `SERVICE_REQUEST`, `DEAL_SEARCH`, `REFINEMENT`, `SEARCH_EVENTS`, `OUT_OF_SCOPE`, `UNCLEAR`, `CALENDAR_VIEW` (plus exported phrase/frozenset constants tied to the cascade).

That dormant block is **roughly 570 lines** of cognitive surface (everything beyond the two production-facing entry points and their shared lower layers — exact boundary depends how shared helpers are attributed).

**Stale contributor guidance:** `.cursorrules` **line 14** still says intent every turn runs `detect_intent(message, session)` with router handling hard/soft cancel. That matched the **legacy** `/chat` router; Tier 1 today uses `app/chat/intent_classifier.py`. New sessions reading `.cursorrules` alone get the wrong mental model.

## §2 Why it matters

- **Maintainability:** Future readers must parse ~650 lines to learn that production only uses **two** symbols; the rest reads like active routing law but is test-only.
- **CI cost:** Four test modules exercise `detect_intent` on every run; failures there do **not** reflect production regressions until/unless the cascade is rewired.
- **Documentation drift:** `.cursorrules` contradicts the unified-router architecture (`intent_classifier` + slot/search pipeline).
- **Architectural clarity:** The distinction between deterministic `intent.py` and LLM `intent_classifier.py` is already called load-bearing in `docs/components/intent.md`; leaving the cascade in-repo without a disposition decision perpetuates the confusion.

## §3 Options

### Option A — Delete the dead surface

Remove `detect_intent`, helpers used only by it/tests, and label constants not needed by the two live symbols or their tests. Delete or radically slim the four test files that exist solely for the cascade. Update `.cursorrules` to remove the stale `detect_intent` line (implementation slice — not Slice 68).

Target shape: `app/core/intent.py` shrinks on the order of **654 → ~80 lines** (the two live functions plus minimal shared helpers and constants).

**Pros:** Clearest end state if Tier 1 LLM routing stays canonical; eliminates phantom production semantics.  
**Cons:** Loses instant revive of deterministic cascade; revival becomes a git-history exercise.

### Option B — Wire `detect_intent` as deterministic fallback

On Tier 1 LLM failure / unparsable output, invoke `detect_intent` and map labels into the Tier 1 taxonomy.

**Pros:** Defense-in-depth without LLM.  
**Cons:** Highest blast radius; vocabularies differ (12 deterministic labels vs concierge sub-intents); needs explicit mapping design — warrants its own small decision doc before coding.

### Option C — Document dormant; keep code

Add a prominent **DORMANT** header in `intent.py`, tighten `docs/components/intent.md`, fix `.cursorrules` to describe `intent_classifier.py` as canonical.

**Pros:** Lowest immediate risk; no behavioral change.  
**Cons:** Dead weight persists; "dormant" often becomes permanent.

### Option D — Hybrid: delete zero-caller helpers; keep cascade labeled dormant

Example candidates for deletion after audit: `_query_looks_like_program` (**zero importers** outside `intent.py`), helpers/tests only touched by obsolete branches — retain `detect_intent` + covered helpers, mark dormant, trim tests.

**Pros:** Partial maintenance win; preserves fallback optionality.  
**Cons:** Riskiest ambiguity — half-present cascades read as partially wired; demands loud comments.

## §4 Recommendation

Cowork-side leaning for Casey to overturn if desired:

1. **Option A** if the project commits to **LLM Tier 1** as the sole intent authority for the unified router — matches “delete residue after architecture shift.”
2. **Option C** only if product/engineering wants **zero delete risk** while scheduling a later cleanup.
3. **Option B** is strategically interesting but **outsize scope** for a quick win; treat mapping + fallback policy as a **separate decision** before implementation.
4. **Option D** is the weakest default — it saves lines but keeps the hardest-to-explain surface (**half** deterministic intent).

## §5 Implementation sketch (after §7)

Per-option work ships **only after** Casey signs §7. Slice numbers are placeholders.

| Option | Sketch |
| ------ | ------ |
| **A** | Single slice: delete dead module body + dead tests + `.cursorrules` fix; expect **fewer** pytest tests; smoke Tier 1 + search strategy. |
| **B** | Slice 1 — fallback design doc (LLM-down behavior + label mapping). Slice 2 — implementation + tests. |
| **C** | Single slice: comments + `docs/components/intent.md` + `.cursorrules`; pytest count unchanged. |
| **D** | Single slice: delete confirmed zero-caller helpers + orphaned tests; annotate dormant cascade; pytest delta per audit. |

## §6 Alternatives considered and rejected

- **`intent_legacy.py` split** — Second file without resolving product direction; rejected.
- **Demote `intent_classifier`; promote `detect_intent`** — Reverses deliberate post-H1 architecture; rejected.
- **Delete `intent.py` entirely** — Impossible while `detect_out_of_scope_category` and `open_ended_search_message` remain production imports.

## §7 Decision

**Decision: Option A approved on 2026-05-06 by Casey.**

**Scope extension:** This disposition applies to both
`app/core/intent.py` AND `app/core/search.py`. Slice 70's peer review
of `search.md` surfaced that the search-pipeline surface
(`search_events`, `format_search_results`, `search_events_keyword_only`,
and supporting scoring/filtering helpers) has the same dormancy shape
as the `intent.py` cascade — bypassed by the LLM-driven Tier 1/2/3
architecture, kept alive only by tests. Same architectural origin,
same disposition.

**Rationale:** The deterministic-template-era surface in `app/core/`
has been bypassed by the LLM-driven Tier 1/2/3 chat architecture
(`intent_classifier.py`, Tier 2 SQL retrieval in `tier2_db_query.py`,
Tier 3 Anthropic Haiku in `tier3_handler.py`). Keeping the dormant
code as fallback (Option B) carries ongoing maintenance and
architectural-confusion cost without a clear operational trigger;
documenting it dormant (Option C) defers the question without
resolving it. The clean end state — delete the dormant surface,
the test files exercising only-dead helpers, the stale `.cursorrules`
reference — fits the project's recent shipping pattern (schema
cleanup in #30, static-html extraction in #31).

**What stays:** Live functions `detect_out_of_scope_category` (used by
`app/chat/intent_classifier.py`) and `open_ended_search_message` (used
by `search.py`). Live function `_deterministic_embedding_1536` (used
by `app/admin/router.py`). Plus any helpers these three functions
genuinely depend on. Implementation slice's Step 0 audit confirms
the keep-set before any deletion.

**Implementation:** Slice 71 drafts the deletion campaign (single
slice; pre-flight verifies pytest count delta matches the deleted
test count; ruff stays clean; component docs `intent.md` and
`search.md` get updated to reflect the post-deletion state).


> Decision: Option ___ approved on YYYY-MM-DD by Casey.  
> Rationale: …

## §8 Verification posture

- **Option A / D:** Full pytest run; count drops must match deleted tests only; production smoke on chat + search clarify path; `.cursorrules` spot-check.
- **Option B:** Happy-path Tier 1 unchanged; injected LLM failure triggers deterministic labels per spec; mapping tests required.
- **Option C:** Doc/commit review; CI unchanged (965 passed / 5 deselected baseline at Slice 68 ship).

Per `docs/WORKING_AGREEMENT.md`, production verification applies when **user-visible behavior** changes (**A**, **B**, **D**); **C** is documentation-only if truly comment/doc touching.
