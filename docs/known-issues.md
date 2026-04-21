Known issues tracker: one-line log for bugs deferred in favor of higher-priority work.

## Open (deferred)

### 2026-04-21 — Tier 3 recommended-entity not captured for `prior_entity` (Phase 6.4)

**Observed:** After an open-ended Tier 3 answer that **recommends** a catalog venue (e.g. Altitude), a follow-up like “What time does it open?” may **not** resolve to that venue. Explicit naming (“What time does Altitude open?”) works and can hit Tier 1 with hours.

**Expected:** Concierge-recommended primary venue should be eligible for pronoun / short-follow-up resolution within the same session window, same as user-named entities.

**Root cause:** `record_entity` depends on `IntentResult.entity` (or user-utterance resolution). Tier 3 recommendations do not populate that path, so `prior_entity` can stay `None`.

**Priority:** Deferred to **Phase 6.4.1** (design + implementation). Not catastrophic; does not reopen Phase 6.4 closure. See `docs/phase-6-4-session-memory-report.md` § “Known gap — Tier 3 recommended-entity capture”.

### 2026-04-21 — Mountain-bike retrieval miss

**Query:** "My son wants to ride mountain bikes. Any classes available?"

**Observed:** gap_template + CVB external delegation.

**Expected:** Lake Havasu Mountain Bike Association (or similar catalog entity) should have surfaced. Tier 3 response was §8-compliant — this is a retrieval problem, not a voice problem.

**Likely causes to investigate:**

- Category/tagging mismatch between "mountain bike classes" query parse and how the entity is categorized (sports / other / etc.).
- Tier 2 parser confidence floor (< 0.7) dropping the filter and falling to Tier 3, which then didn't include the entity in context.
- Entity state (draft / is_active / verified) gating retrieval.

**Priority:** Not blocking Phase 6.1. Investigate after 6.1 closes; may warrant a dedicated retrieval audit sub-phase separate from the voice audit.

### 2026-04-21 — Tier 3 date hedging on open-ended temporal queries (Phase 6.1 voice audit)

**Query:** "What's happening this weekend?" (sample `t3-01` in `scripts/voice_audit_results_2026-04-21-phase614-verify.json`)

**Observed:** Tier 3 hedges — e.g. "I don't have this weekend's date locked in, so I can't tell you what's on yet..."

**Expected:** With today's date and a resolved "this weekend" window in context, the model answers from catalog events instead of claiming the calendar anchor is missing.

**Likely causes to investigate:**

- `app/chat/context_builder.py` does not inject today's date or resolved ranges for phrases like "this weekend", "tonight", or "tomorrow" into Tier 3 context.
- Phase 6.1.4 mitigated the §8.2 voice symptom in `prompts/system_prompt.txt` (one-move rule); the underlying hedge still needs date-aware context from `context_builder`.

**Priority:** Not blocking. Investigate during Phase 6.3 or later. Suggested scope: add date-aware context injection in `context_builder`; verify `t3-01` clears on re-audit.

### 2026-04-21 — Tier 2 handling of explicit-recommendation queries (Phase 6.1 voice audit)

**Query class:** "What should I do Saturday", "pick one thing to do", "best place to take kids" (samples `t3-24`, `t3-25` in Phase 6.1.3 audit).

**Observed:** Queries route through Tier 2 retrieve-then-generate when filters extract with confidence ≥ 0.7, producing list-with-standout (Option 2) responses. Handoff §8.4 requires Option 3 (single committed pick + reason) for explicit-rec triggers.

**Expected:** Explicit-rec intents skip Tier 2 listing and land in Tier 3 synthesis where single-pick opinionated voice is natural.

**Likely causes to investigate:**

- Router does not short-circuit explicit-rec triggers before Tier 2; high parser confidence keeps the Tier 2 path hot.
- Phase 6.1.4 tightened `prompts/tier2_formatter.txt` when Tier 2 still owns the turn; the durable fix is router-level routing to Tier 3.

**Priority:** Not blocking. Investigate when Phase 7 cost optimization or a Tier 2 revisit happens. Suggested scope: explicit-rec trigger regex match in `unified_router.route` before Tier 2 attempt; on match, skip to Tier 3.

## Resolved

### Tier 3 feedback thumbs not rendering (Phase 6.2.2)

**Status:** RESOLVED.

**Resolved:** 2026-04-21 — owner confirmed Tier 3 feedback thumbs render correctly on production responses.
