Known issues tracker: one-line log for bugs deferred in favor of higher-priority work.

## Open (deferred)

### 2026-04-21 — Mountain-bike retrieval miss

**Query:** "My son wants to ride mountain bikes. Any classes available?"

**Observed:** gap_template + CVB external delegation.

**Expected:** Lake Havasu Mountain Bike Association (or similar catalog entity) should have surfaced. Tier 3 response was §8-compliant — this is a retrieval problem, not a voice problem.

**Likely causes to investigate:**

- Category/tagging mismatch between "mountain bike classes" query parse and how the entity is categorized (sports / other / etc.).
- Tier 2 parser confidence floor (< 0.7) dropping the filter and falling to Tier 3, which then didn't include the entity in context.
- Entity state (draft / is_active / verified) gating retrieval.

**Priority:** Not blocking Phase 6.1. Investigate after 6.1 closes; may warrant a dedicated retrieval audit sub-phase separate from the voice audit.

## Resolved

### Tier 3 feedback thumbs not rendering (Phase 6.2.2)

**Status:** RESOLVED.

**Resolved:** 2026-04-21 — owner confirmed Tier 3 feedback thumbs render correctly on production responses.
