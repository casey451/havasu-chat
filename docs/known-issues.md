Known issues tracker: one-line log for bugs deferred in favor of higher-priority work.

## Open (deferred)

### 2026-04-21 — Tier 3 date hedging on open-ended temporal queries (Phase 6.1 voice audit)

**Query:** "What's happening this weekend?" (sample `t3-01` in `scripts/voice_audit_results_2026-04-21-phase614-verify.json`)

**Observed:** Tier 3 hedges — e.g. "I don't have this weekend's date locked in, so I can't tell you what's on yet..."

**Expected:** With today's date and a resolved "this weekend" window in context, the model answers from catalog events instead of claiming the calendar anchor is missing.

**Likely causes to investigate:**

- `app/chat/context_builder.py` does not inject today's date or resolved ranges for phrases like "this weekend", "tonight", or "tomorrow" into Tier 3 context.
- Phase 6.1.4 mitigated the §8.2 voice symptom in `prompts/system_prompt.txt` (one-move rule); the underlying hedge still needs date-aware context from `context_builder`.

**Priority:** Not blocking. Investigate during Phase 6.3 or later. Suggested scope: add date-aware context injection in `context_builder`; verify `t3-01` clears on re-audit.

## Resolved

### 2026-04-21 — Tier 2 handling of explicit-recommendation queries (Phase 6.1 voice audit)

**Status:** RESOLVED by **Phase 8.0.2** (router-level explicit-rec bypass to Tier 3; Tier 2 formatter explicit-rec block removed).

**What changed:** §8.4 trigger phrases skip Tier 2 and use Tier 3 with `prompts/system_prompt.txt` Option 3 rules.

### 2026-04-21 — Mountain-bike retrieval miss

**Status:** RESOLVED by **Phase 8.0.3** (entity matcher aliases for `Lake Havasu Mountain Bike Club`).

**What changed:** Generic mountain-bike phrasing (`mountain bikes`, `mountain biking`, `mtb`, trails language, etc.) now fuzzy-matches the catalog provider above the enrichment threshold so Tier 3 context includes club programs instead of falling through to CVB-only answers.

### 2026-04-21 — Tier 3 recommended-entity not captured for `prior_entity` (Phase 6.4)

**Status:** RESOLVED by **Phase 6.4.1** (implementation on `main` pending owner commit — see `docs/phase-6-4-1-recommended-entity-capture-report.md`).

**What changed:** After Tier 2 or Tier 3 returns assistant text, the unified router scans that text for catalog **provider** names (same fuzzy threshold as `match_entity`). When **exactly one** provider matches above threshold, `record_entity` runs so `prior_entity` is set for pronoun follow-ups. User-named capture still runs first on the same turn; recommended capture runs last and **overwrites** when it fires (per locked precedence).

### Tier 3 feedback thumbs not rendering (Phase 6.2.2)

**Status:** RESOLVED.

**Resolved:** 2026-04-21 — owner confirmed Tier 3 feedback thumbs render correctly on production responses.
