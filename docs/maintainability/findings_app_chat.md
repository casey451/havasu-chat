# Maintainability findings — `app/chat/` pilot review

**Scope:** All 19 Python files in `app/chat/` as of bundle generated 2026-04-29T14:01:57Z.

**Method:** Single-pass code review with maintainability lens. Findings categorized by severity and disposition.

**Headline:** The code is in better shape than typical for a small-team project at this stage, but has accumulated specific structural debts that will compound badly as the codebase grows. The most consequential issue is duplicated LLM-call infrastructure across four files; the second-most is two parallel chat systems running side-by-side with unclear deprecation status. Most other findings are localized cleanups.

---

## Severity legend

- **HIGH** — fix before significant feature work; left unfixed, will compound across many files
- **MEDIUM** — fix when the affected file is touched, or in a focused cleanup pass
- **LOW** — accept and document, or fix opportunistically

## Disposition legend

- **Fix now** — schedule a ship for this before broader feature work
- **Fix when touched** — fix as part of any next ship that modifies the affected module
- **Accept and document** — leave as-is but record the rationale or limitation
- **Investigate further** — finding requires more context than this pilot can give

---

## HIGH severity findings

### H1. Two parallel chat systems running in production

**Files:** `app/chat/router.py` (905 lines, registers `POST /chat`), `app/chat/unified_router.py` (~440 lines, registers `POST /api/chat` via `app/api/routes/chat.py`).

**Problem:** Both endpoints are live and route real traffic. They use different architectures (state-machine intent dispatch vs. tiered routing), different session storage patterns, different response schemas (`ChatResponse` vs. `ConciergeChatResponse`), and different logging tags (`tier_used="track_a"` vs. numeric tiers).

**Why it matters for AI-maintainability:**

- A future Claude session asked to fix a bug in "the chat handler" cannot know which one to touch without reading both. That's 1,300+ lines of code to disambiguate before any work begins.
- Behavior fixes shipped to one path silently fail to fix the other. Voice rule changes, parser improvements, and security fixes all need to either (a) be doubled, or (b) declare which path is target.
- The mental model "Hava routes through tiered handlers" (per PROJECT.md) is incomplete — `/chat` does not route through tiers.

**Why it matters for product:**

- Users hitting `/chat` (legacy clients, perhaps older browsers, perhaps the existing frontend if it hits both paths) get different behavior than users on `/api/chat`.
- The voice-audit system (Phase 8.8.2b) presumably tested one path, not both — voice consistency across paths is an open question.
- Production verification on either endpoint does not prove the other is healthy.

**Disposition: Fix now, but as an investigation first.**

Specifically: a follow-up read-only session that answers (a) which frontend paths hit `/chat` vs `/api/chat` today, (b) whether `/chat` is used at all in the live frontend, (c) what would break if `/chat` were removed, (d) what the migration plan should be. After that investigation, decide between deletion, deprecation with redirect, or formal documentation of both paths. Do not start feature work that touches chat routing until this is resolved.

This is the single most consequential finding in this review.

---

### H2. LLM-call infrastructure duplicated across four files

**Files:** `tier2_parser.py`, `tier2_formatter.py` (`_format_via_llm`), `llm_router.py`, `tier3_handler.py`. Plus partial duplication in `hint_extractor.py` (different vendor — OpenAI).

**Problem:** Every file that calls Anthropic reproduces:

- API key check (`os.getenv("ANTHROPIC_API_KEY")`, strip, return early if empty)
- Model env-var fallback to default (`os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL`)
- Anthropic import wrapped in try/except
- Prompt-file loading from `prompts/<name>.txt` via `Path(__file__).resolve().parents[2]`
- System block construction with `cache_control: ephemeral`
- Client construction (`anthropic.Anthropic(api_key=..., timeout=...)`)
- `messages.create` wrapped in try/except returning a sentinel value
- `_extract_text_from_message` (identical implementations in all four files)
- `_usage_in_out` or `_split_usage` (slight variations, same intent)
- `_coerce_llm_text_to_json_object` (parser and llm_router; identical)

I count at least 60 lines of near-verbatim duplication per file, totaling 200+ lines that drift independently.

**Why it matters for AI-maintainability:**

- Future Claude sessions adding a fifth LLM-using module will copy this pattern again, driving total duplication higher.
- Bug fixes (e.g. adjusting timeout handling, adding retry logic, fixing token-usage attribution) need to be applied four to five times. Inevitably one site gets missed.
- Vendor-side changes (Anthropic SDK updates, new usage fields, deprecated parameter names) require coordinated edits across all four files.
- The `_split_usage` function in `tier3_handler.py` is the most complete; `_usage_in_out` in three other files is a slightly different shape. Comparing them takes effort to confirm whether the difference is intentional or drift.

**Why it matters for the product:**

- Token-counting drift means cost reporting may be inaccurate (some sites count cache reads, others don't, with subtle variations).
- Timeout handling that's right in three places and wrong in one place produces hard-to-diagnose latency bugs.
- Voice audit may pass on Tier 3 paths but fail on parser paths because they report different metadata.

**Disposition: Fix now.**

Recommended structure: an `app/chat/_llm_client.py` (or `app/core/llm_client.py`) module exposing:

- `call_anthropic_messages(system_prompt: str, user_text: str, *, max_tokens: int, temperature: float, model: str | None = None) -> AnthropicResult | None` — returns a structured result or `None` on any failure
- `extract_text(msg) -> str`
- `extract_usage(msg) -> Usage` — dataclass with input/output/cache fields

Each calling site shrinks from ~40 lines to ~5 lines. Voice-style differences (system prompt, temperature, max_tokens) stay at the call site; mechanical infrastructure goes to the helper.

The `hint_extractor.py` (OpenAI) shouldn't be merged with this — different vendor, different API surface — but should be moved to its own helper for consistency.

---

### H3. Hardcoded entity list will not survive bulk catalog import

**Files:** `entity_matcher.py` (`CANONICAL_EXTRAS`), `intent_classifier.py` (`_ENTITY_NAMES`).

**Problem:** Per START_HERE.md and BACKLOG history, Phase 8.11 will bulk-import 4,574 businesses from Google. The current entity-matching architecture has 14 hand-coded canonical names with hand-coded synonym lists. `intent_classifier.classify()` matches against this hardcoded list (`_ENTITY_NAMES`), separate from `entity_matcher.match_entity()` which matches against the live DB.

**Why it matters:**

- After bulk import, the hardcoded list will be 0.3% of the catalog. Entity matching during classification will miss 99.7% of providers.
- The two entity-match paths (hardcoded list in classifier, live DB in `unified_router._enrich_entity_from_db`) can disagree. A query that matches DB-side but not classifier-side will get a different `IntentResult.entity` than one matched in the router. This creates confusing dispatch behavior.
- The synonym-extras pattern (`"trampoline park" → "Altitude Trampoline Park"`) works well for hand-curated entries but doesn't scale. After bulk import, deciding which businesses get synonym entries is unclear.

**Disposition: Investigate further, then fix before Phase 8.11.**

The right fix isn't obvious — load CANONICAL_EXTRAS from a database table? Make it part of the Provider model? Use an embedding-based match instead of regex/fuzzy? — and depends on what the bulk import actually produces. The investigation belongs to the Phase 8.11 work, but should happen before the import lands so the architecture can absorb the data correctly.

For now: document the limitation in the entity_matcher docstring so future Claude knows the pattern doesn't scale.

---

## MEDIUM severity findings

### M1. `tier1_handler.try_tier1` is a 150-line if/elif chain

**File:** `tier1_handler.py`

**Problem:** Nine sub-intent branches (`OPEN_NOW`, `DATE_LOOKUP`, `PHONE_LOOKUP`, etc.) each follow the same shape: validate input → fetch data → call `render()` → append voice → return. Variations are real but small. A dispatch table would make new sub-intents obvious to add and reduce visual scanning.

**Why it matters:** When adding a new Tier 1 sub-intent, the right pattern isn't immediately obvious — there's `_open_now_from_hours`-style helpers, `_phone_for_query`-style helpers, and inline logic. Future Claude has to reverse-engineer the convention from existing branches.

**Disposition: Fix when touched.** Or alternatively, leave as-is and document the pattern in `docs/components/tier1_handler.md` when that's written. The if/elif is readable; refactoring is opportunistic, not urgent.

---

### M2. Magic confidence numbers throughout `intent_classifier.py`

**File:** `intent_classifier.py`

**Problem:** ~18 distinct float literals in 0.4–1.0 range used as confidence scores. No comments explain why specific values were chosen. The downstream consumer (`_merge_confidence`) treats them as inputs to a tunable formula but with no calibration trail.

**Why it matters:** When future Claude tweaks classifier behavior (e.g., adding a new sub-intent), choosing the right confidence value is guesswork. The values have implicit relationships (e.g., `0.85` for one-correct-marker is purposefully higher than `0.78` for next-occurrence) but those relationships aren't documented.

**Disposition: Fix when touched.** Lift to module-level named constants with comments explaining the relative ordering. Or accept and document if the values are known to be empirically tuned.

---

### M3. Definitions of "summer" disagree between two modules

**Files:** `local_voice_matcher.py` (May–September), `tier2_db_query.py` (June–August).

**Problem:** Two semantic definitions of `summer` for different purposes (voice matching vs. catalog query). May or may not be intentional — voice matching is fuzzy/aesthetic, query window is calendar-precise. But:

- The discrepancy isn't documented anywhere
- `winter` differs too: voice-match uses Dec–Feb (months 12, 1, 2), DB query uses Dec 1 – end of Feb of next year (the wraparound)
- A future change to one's definition won't propagate to the other

**Why it matters:** Inconsistent semantic models are a class of bug that's hard to find by testing. A user query "What's good in summer?" is voice-matched against May 1–Sep 30, but if it triggers a Tier 2 path filtered by `season=summer`, the date range narrows to Jun 1–Aug 31. The two sides disagree about what "summer" means.

**Disposition: Fix when touched.** Either centralize the season-to-date-range mapping in one module (`app/core/seasons.py`?) or document the difference explicitly in both files. The hardcoded month sets in multiple places (`_MONTH_TO_INT` in `tier2_db_query`, `_MONTHS` in `tier2_schema`) is a related concern.

---

### M4. Bare `except` and over-broad exception handling

**Files:** Multiple. Specific examples:

- `entity_matcher._provider_id_for_name`: bare `except Exception: pass`, swallows anything
- `tier2_formatter._format_via_llm`: catches everything, logs `unexpected error in format` but doesn't include error details
- `tier1_templates.render`: `except (KeyError, IndexError): pass` inside a hot path
- `tier3_handler.answer_with_tier3`: bare `except` around `import anthropic` (probably fine)

**Why it matters:** Over-broad exception handling makes failure modes invisible. When something stops working, log searches reveal "tier2_formatter: unexpected error" with no detail, and the next debugging step requires re-running with stack traces enabled. AI agents debugging issues will face the same wall.

**Disposition: Fix when touched.** Each occurrence individually is a small fix; doing them all in one ship is also reasonable. Replace bare exceptions with specific types when known, log exception info (`logging.exception`) instead of `logging.warning` for unexpected errors, and avoid `pass` in except blocks where a real failure mode exists.

---

### M5. Module-global mutable state in `entity_matcher`

**File:** `entity_matcher.py`

**Problem:** `_rows: list[_EntityRow] | None = None` is module-level mutable state, populated lazily on first call. Tests have to use `reset_entity_matcher()` to clear it; concurrent first-calls would race; cache invalidation is manual.

**Why it matters:**

- The `assert _rows is not None` (used twice) is defensive against the lazy-init pattern but vulnerable to `python -O` runs which strip asserts.
- The cache is process-global. Multi-worker uvicorn deployments (mentioned as a concern in the unified_router doc) have separate caches per worker, leading to inconsistent matching after bulk imports.
- Future Claude adding a similar pattern elsewhere copies the antipattern.

**Disposition: Fix when touched.** Either move the cache to an explicit class (`class EntityMatcherIndex` with methods) or wrap in a function-level cache (`functools.lru_cache` on a "get index" function). Replace `assert` with explicit `if`. Document that the cache is process-local.

---

### M6. `tier2_db_query.query()` opens its own DB session

**File:** `tier2_db_query.py`

**Problem:** Public entry point uses `with SessionLocal() as db:` to open a fresh session, separate from the request-scoped session passed through everywhere else (`unified_router.route(query, session_id, db)`). Implications:

- Two database connections per request when Tier 2 fires (the route's session, and Tier 2's session)
- Transaction semantics are independent — if route-side commits or rollbacks, Tier 2 doesn't see them
- Connection pool pressure under load is doubled for Tier 2 paths

**Why it matters:** As traffic scales, this doubles connection usage. Railway's Postgres connection limits become a binding constraint sooner. Beyond the load issue, the inconsistency between route-side and Tier 2-side session handling is a maintainability problem — future Claude needs to know which functions take a session vs. open their own.

**Disposition: Fix when touched.** Refactor `query()` to accept a session parameter, plumbed through `tier2_handler.try_tier2_with_usage` from `unified_router._handle_ask`. This is a small refactor with clear gain.

---

### M7. `intent_classifier._CORRECT_MARKERS` has a duplicate alternation

**File:** `intent_classifier.py` line 537

**Problem:** `re.compile(r"\b(actually it is|actually it's|actually it is)\b")` — the first and third alternations are identical. Almost certainly copy-paste leftover from when one was meant to be different (perhaps `actually that is`?).

**Why it matters:** Bug, not just a maintainability issue. The intended pattern probably wasn't captured.

**Disposition: Fix when touched.** Single-line fix.

---

### M8. `tier2_db_query` and `tier2_schema` independently define month and day name sets

**Files:** `tier2_db_query.py` (`_MONTH_TO_INT`, `_WEEKDAY_NAMES`), `tier2_schema.py` (`_MONTHS`, `_DAYS`), also `tier1_templates.py` (`_WEEKDAY_NAMES`).

**Problem:** Three modules independently maintain weekday/month string sets. They agree today, but nothing enforces that they continue to agree.

**Disposition: Fix when touched.** Centralize to one module (`app/core/calendar_strings.py`?) or to `tier2_schema.py` and import from there.

---

## LOW severity findings

### L1. Bundle export had encoding issues — actual files probably OK

**Observation:** The bundle file shows mojibake for em-dashes, en-dashes, arrows, and similar Unicode characters (`â€"` for `—`, `â€"` for `–`). The actual source files should be fine; this is a bundle-export bug. Worth confirming on a few files before assuming the source is clean.

**Disposition:** Cursor verifies on the next bundle production. If the source is mojibake, that's a different (real) finding.

### L2. Stale references in module docstrings

**Files:** `tier1_templates.py` references "HAVASU_CHAT_MASTER.md" (almost certainly renamed to `HAVA_CONCIERGE_HANDOFF.md`). `entity_matcher.py` references "docs/HAVASU_CHAT_SEED_INSTRUCTIONS.md".

**Disposition: Fix when touched.** Or do a focused docstring-currency pass. Not blocking.

### L3. `compact_onboarding_user_context_line` is a deprecation alias

**File:** `tier3_handler.py`

The docstring says "backward-compatible alias for tests / callers using the Phase 6.3 name." Either confirm callers have moved off and remove, or document deprecation timeline.

**Disposition: Fix when touched.**

### L4. `variant = 0` is dead code in `tier1_handler.try_tier1`

**File:** `tier1_handler.py`

Set unconditionally, never varied. Could be removed entirely or tied to actual variant selection.

**Disposition: Fix when touched.**

### L5. Hardcoded threshold magic numbers

**Files:** Various. `entity_matcher`'s `> 75.0` (3 occurrences), `tier2_handler`'s `TIER2_CONFIDENCE_THRESHOLD = 0.7` (good — this one is named).

**Disposition: Fix when touched.** Lift to named constants.

### L6. `intent_classifier._LIST_BY_CATEGORY` is a 9-alternation regex

**File:** `intent_classifier.py`

The regex is readable but won't scale as more categories are added. At some point, this transitions from regex to a different matching approach (keyword extraction + category dictionary, embedding similarity, LLM). Not urgent — flag for the future.

**Disposition: Accept and document.**

### L7. `unified_router.ChatResponse.tier_used` field has a comment listing values

**File:** `unified_router.py`

The field-level comment lists 9 string values but isn't a typed enum. Future Claude has to grep for the values to confirm they're current. The component doc captures this, but the source is the docstring/comment.

**Disposition: Accept and document.** A `Literal` type would be tighter but requires a coordinated update across all callers, not worth doing for this alone.

---

## Cross-cutting observations

**Test infrastructure isn't in this bundle.** I can't speak to test quality, coverage, or maintainability of the test layer. That should be its own bundle if a test review is part of the broader maintainability workstream.

**The `__init__.py` is intentionally minimal.** Single docstring line, no re-exports. That's good — keeps imports explicit.

**Voice rules are not visibly enforced in code.** The voice-audit waivers file (`scripts/voice_audit_waivers_2026-04-23.md`, mentioned in START_HERE history) implies external/test-time enforcement. No in-code voice validation. That's a design choice, not a finding — but worth flagging if the eval harness (Phase 8.8.6) is intended to enforce this systematically.

**Deterministic vs. LLM rendering split is well-shaped.** The `tier2_formatter.format` dispatch (empty → fixed string, all-event → deterministic, mixed → LLM) is a clean pattern. New row types should follow the same shape. Worth highlighting in a future component doc.

**The codebase is small enough for these findings to be tractable.** ~4,800 lines across 19 files is well within a single Claude session's context window. Larger codebases (10K+ lines, hundreds of files) would need different tooling.

---

## Recommendations

### Immediate ships (in priority order)

1. **H1 investigation ship** — read-only session that maps which paths use `/chat` vs. `/api/chat`, decides deprecation strategy. Output: a decision doc and a backlog item.
2. **H2 refactor ship** — extract `app/chat/_llm_client.py` (or similar), migrate four call sites to use it. Significant ship, but a clear win.
3. **M3 ship** — centralize season/month/day definitions, document any intentional differences.

These three address the highest-leverage maintainability issues. Together they probably take 4-6 sessions.

### Hold for later

- All MEDIUM and LOW findings can wait. Schedule them when the affected modules are touched, or do a focused "cleanup ship" later.
- H3 (entity matching scale) waits for Phase 8.11 prep.

### Don't fix

- L6 (`_LIST_BY_CATEGORY` regex) — current scale doesn't warrant a different approach.
- L7 (`tier_used` taxonomy as comment vs. enum) — current shape is fine.

---

## What this pilot tells us about scaling the review

The pilot covered 19 files / ~4,800 lines / ~165 KB. Findings are concrete, severity-rated, and actionable. The same approach scales to the rest of the codebase, with these adjustments:

- **`app/core/`** — likely smaller per-file but more files; group into bundles by sub-area (intent, slots, search, session, etc.)
- **`app/db/`** — needs the schema (`models.py`) plus migration history; smaller bundle but more careful reading
- **`app/api/`** — endpoint registration and request schemas; likely small
- **Frontend** — different language (JS), different review questions; deserves its own session
- **Tests** — quality-of-test review is a different lens; can run after core code review

If the pilot's findings are useful, scaling to the full codebase is probably 4-6 more sessions for the AI-maintainability workstream alone.
