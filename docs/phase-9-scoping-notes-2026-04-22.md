# Phase 9 Scoping Notes — Catalog Expansion & AI Narrative Layer

*Date: 2026-04-22*
*Status: Pre-scoping notes — not a locked plan. Captured during mid-Phase-8 conversation to preserve context for when Phase 9 is formally scoped post-launch.*

## Purpose

Capture the shared understanding reached about two related-but-separable post-launch workstreams, so they don't depend on anyone's memory when Phase 9 scoping happens.

## The Two-Arc Framing

Post-launch catalog work is two arcs, not one monolithic project. They can ship in either order, or only one can ship, depending on what real user traffic signals after launch.

**Arc 1 — Bulk Import**
Feed the 4,574-business Lake Havasu City active license roster through the existing Phase 5 contribution pipeline. Uses existing infrastructure: `app/contrib/places_client.py`, enrichment orchestrator, approval service, `/admin/contributions` admin UI.

Primary missing piece: the bulk-review tooling deferred at Phase 5 close (batch approvals, multi-select, bulk category-assign). Treat as an extension of Phase 5, not a parallel system.

Value proposition: **row coverage.** Scales the catalog from ~25 curated providers to thousands.

**Arc 2 — AI Narrative + Embedding Layer**
Generate structured Claude-written narratives per provider (quick_take, locals_say, good_for, specialties, vibe, price_range, kid_friendly, etc.), with vector embeddings for semantic retrieval. New schema additions on `providers`: `ai_overview`, `ai_overview_structured` (JSONB), `embedding` (pgvector), `google_rating`, `google_review_count`, `last_google_refresh`, `match_confidence`.

Value proposition: **query coverage.** Enables semantic retrieval for the natural-language queries Tier 3 is designed for.

## Why These Are Separable

Different capabilities, different risks, different value cases:

- Arc 1 is mostly operational scaling of existing infrastructure.
- Arc 2 is a new retrieval capability that doesn't require catalog scale to prove or deliver value.
- Either can ship without the other.
- They can ship in either order.

Conflating them made the original plan feel bigger and scarier than either deserves.

## The Four Narrative-Value Points

When evaluating Arc 2, these are the merits it should be judged on — not dismissed as "nicer catalog text":

**1. Semantic retrieval is how users actually ask questions.**
"Somewhere my 7-year-old can burn off energy," "good for date night," "cheap eats under $15" — these don't match well against business names or categories. They match against narrative text. Without narrative embeddings, Tier 3 retrieval relies on keyword/semantic search over sparse structured data, which limits how natural the chat experience can be.

**2. Structured narrative fields are queryable constraints, not just richer descriptions.**
`kid_friendly=true` as a filter is not the same as "the description mentions kids." Structured fields (good_for, price_range, vibe, kid_friendly) enable filterable queries that otherwise require Claude to read every candidate and reason about fit. Different tool than longer prose.

**3. The paid-tier pitch depends on this.**
"Your business has a good description in our app" is a thin sell. "Your business shows up when someone asks for date night spots" is a product. The narrative work is what makes the second sentence possible. This is the differentiator for $39/mo Featured listings.

**4. Voice alignment is prompt-engineering work, not a research project.**
The narrative-generation prompt gets iterated against the §8 voice spec the same way the Tier 3 system prompt was iterated in Phase 6.1. Not novel, just more of what's been done.

## Sequencing Instinct (Owner Preference, Not Locked)

**Narrative-first, then bulk import** — probably the right sequence, for these reasons:

- Bulk import adds 4,574 rows regardless of whether the retrieval model works. If narrative retrieval needs significant iteration (prompt tuning, embedding model choice, schema refinement), iterating against 4,574 rows of test data is vastly more expensive than iterating against 25.
- Narrative-first against the 25 curated providers proves semantic retrieval works with known-good data, then scales it.
- The 25 curated providers have richer hand-curated data, so narrative quality will be higher, giving a higher-quality baseline to compare against during scale-up.
- If retrieval works well at small scale, bulk import becomes a confident operation. If retrieval doesn't work, bulk import gets deferred or reshaped before spending money on 4,574 enrichment cycles.

This is the revised instinct. Original thinking was bulk-first-then-narrative because bulk is structurally simpler; narrative-first is better because it's lower-risk.

## What's NOT In Scope Here

- Correction flow UX for contested-state entities (already deferred post-launch, separate arc)
- Business-owner-facing account system (deferred)
- Featured listings / sponsored placement (deferred)
- Expansion beyond Lake Havasu City (out of scope for Phase 9 entirely)

## Trigger Conditions for Phase 9 Scoping

Don't start Phase 9 scoping until:

1. Phase 8 ships in full
2. Soft launch has 2-4 weeks of real traffic
3. There's actual signal about what users ask that the current catalog can't answer

The value of waiting: Phase 9 scope should be informed by real query patterns, not speculative. If users mostly ask about events, Arc 1 matters less and Arc 2 is the priority. If users ask for businesses the catalog doesn't have, Arc 1 is the priority. We won't know until there's traffic.

## Integration Concerns to Address in Arc 2 Scoping

Flagged during this pre-scoping conversation, to be resolved when Arc 2 is formally scoped:

**Tier 1 direct-lookup pollution risk:** Adding thousands of unverified bulk-imported providers to entity-matcher candidates risks surfacing unverified data via Tier 1's confident voice. Cleanest fix: exclude `source='bulk_import'` (and whatever narrative-ingested providers are flagged as) from Tier 1 matching entirely. Unverified providers only surface via Tier 2/3 where voice can attribute them.

**pgvector operational concern:** Installing pgvector on Railway Postgres is a one-way door. Needs owner action, not a Cursor task. Worth verifying before Arc 2 starts.

**Voice surface expansion:** Tier 3 context will include narrative content that didn't exist when the §8 voice spec was written. The 55-sample voice audit, 20-query spot-check battery, and §8 spec were tuned against current catalog shape. Arc 2 needs its own voice iteration pass — not a research project, but real work.

**Source enum:** `source='bulk_import'` already exists in the contribution schema. If narrative-enriched rows are a distinct category (e.g., AI-narrated and embedding-indexed, not just URL-contributed), consider whether a new source value is needed or whether existing `bulk_import` + a separate `enrichment_state` field is cleaner.

## Open Questions for Formal Scoping

- Is Arc 1 actually needed before Arc 2 proves itself? Could Arc 2 ship against the 25 curated providers as a complete deliverable, with bulk import as genuinely separate work?
- What's the quality bar for Arc 2's narratives? 55-sample audit like §6.1? Spot-check battery? Real-user feedback?
- How does Arc 2 interact with the Contribute flow? If a user submits a business via contribution, does it automatically get a generated narrative, or is that gated?
- Refresh cadence: quarterly? Triggered by review-count delta? Business-owner-requested?

These are scoping-time questions. Captured here so they don't have to be rediscovered.

## References

- Conversation thread: pre-scoping discussion 2026-04-22
- Related: Phase 5 close notes (deferred bulk-review tooling)
- Related: Phase 6.1 voice audit methodology (template for Arc 2 voice iteration)
- Related: Option A/B bulk-import conversation earlier in project history

## Owner Notes

This document is owner-authored, not a Cursor deliverable. It exists to preserve context, not to drive work. Update when Phase 9 scoping formally begins.
