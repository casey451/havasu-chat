<!--
PURPOSE: Forward-looking option space for re-introducing a provider
ingestion lane on top of the post-cleanup RS-only catalog. NOT a
commitment to any architecture. Lays out candidate sources, three
architectural patterns, and unresolved product questions so future-us
has a starting point rather than reverse-engineering the option space.

AUDIENCE: Future maintainers planning provider ingestion work and
assistants briefing on past decisions. Read alongside
docs/maintainability/non_river_scene_cleanup.md (what was removed)
and docs/maintainability/chat_behavior_followup_plan.md §5, §7
(ordering and open questions).

STATUS: Speculative. Not a current sprint deliverable. The catalog
is RS-only by deliberate decision (2026-04-30 cleanup); this doc
captures the option space for when provider ingestion is next on
deck.
-->

# Provider ingestion lane — options space

## Why this exists

Production catalog is **River Scene events only** as of the cleanup landed 2026-04-30 (`docs/maintainability/non_river_scene_cleanup.md`). The `providers` and `programs` tables are empty; all previous ingestion lanes (provider seed module, master concierge populate, Google bulk JSONL ingest/embed, REAL_SEED, instructions seed) were removed deliberately to start from a clean slate.

When provider ingestion returns, several decisions need to be made together: which source(s) to integrate, how the data flows into approval, what schema fields are required vs nullable, how chat surfaces provider data. This doc lays out the option space without committing.

Related open questions live in `docs/maintainability/chat_behavior_followup_plan.md` §7 (especially Q1: "which provider ingestion lane is the right first one to build?" and Q5: "what should 'tell me about X' return?").

## Candidate sources

Five sources have been considered in past discussions or implemented-then-removed. Each carries different coverage, effort, and reliability profiles.

### 1. Manual admin entry (existing infrastructure)

The admin UI already supports contribution review and approval. Extending it to allow direct provider creation is the lowest-effort source.

- **Coverage:** Limited to operator effort; high accuracy.
- **Effort:** Low (UI extension; existing approval pipeline).
- **Reliability:** Highest — operator-vetted.
- **Removed precedent:** None — this lane was never built; admin UI focuses on contribution approval rather than direct creation.

### 2. Public submission (form-based)

A "submit a business" form similar to the existing contribution flow but provider-typed.

- **Coverage:** Bounded by user awareness and willingness to submit.
- **Effort:** Medium (form, validation, admin review queue).
- **Reliability:** Variable — needs admin approval per submission.
- **Removed precedent:** None directly; existing contribute flow is RS-event-shaped.

### 3. Web scraping (specific sites)

Scrape a known directory or municipal site (e.g., `lhcaz.gov` for Aquatic Center, local chamber of commerce listings).

- **Coverage:** Defined by source breadth; high for in-scope categories.
- **Effort:** Medium-high per source (parser, rate limits, brittle to layout changes).
- **Reliability:** Medium — source HTML changes break ingestion silently.
- **Removed precedent:** None scraped providers specifically; River Scene parser is a precedent for the pattern.

### 4. API integration (third-party)

Google Places API, Yelp Fusion, etc. Structured data, clear rate limits.

- **Coverage:** Broad (Google Places covers most Lake Havasu businesses).
- **Effort:** Medium (auth, pagination, dedupe against existing rows, mapping to internal schema).
- **Reliability:** High — vendor-maintained data quality.
- **Cost:** Per-call API fees; tier choice affects budget.
- **Removed precedent:** Google bulk JSONL ingest/embed lane was removed (`0674467`). Reasons documented in cleanup retrospective: ingest of unvetted bulk vendor data without operator review produced low-quality catalog rows.

### 5. Bulk CSV / sheet import (one-shot)

A one-time or periodic CSV upload with admin-approval-per-row.

- **Coverage:** As broad as the source CSV.
- **Effort:** Low for the import script; medium for the approval UI to handle batch volume.
- **Reliability:** Depends on source quality; gives operator a chance to filter at upload time.
- **Removed precedent:** REAL_SEED and instructions-seed lanes (`da8734f`, `d84b9c1`) were CSV/markdown-driven; removed because seed-data was indistinguishable from real ingestion at the data layer, polluting the catalog.

## Three architectural patterns

Independent of which source is built first, the data-flow pattern matters. Three options.

### Pattern A — Mirror River Scene

Each new source becomes a `run_pull` style script that writes pending rows into the existing `Contribution` table. Admin approval through the existing queue creates `Provider` rows from approved contributions. No new pipeline infrastructure.

- **Pros:** Leverages all existing approval infra (admin UI, approval service, contribution store). Minimum new surface area.
- **Cons:** `Contribution` schema was shaped for events; provider-specific fields would need to be smuggled into existing columns or added to the table. Approval UI may need provider-specific affordances.
- **Effort estimate:** ~2-4 weeks per source after the schema accommodation lands.

### Pattern B — Divergent provider pipeline

A separate `ProviderCandidate` table with its own approval flow. May include verification status, multi-stage approval, auto-approval for trusted sources (e.g., Google Places verified businesses).

- **Pros:** Clean separation; provider-specific fields live in provider-specific schema. Allows source-tier policies (auto-approve trusted, manual for others).
- **Cons:** Duplicates a lot of approval infrastructure. Two queues for operators to manage.
- **Effort estimate:** ~4-8 weeks for the framework, plus per-source costs.

### Pattern C — Generalized ingestion framework

One framework where River Scene becomes one instance, providers another, future sources additional instances. Source-agnostic queue, source-specific normalization adapters.

- **Pros:** Highest leverage long-term. Avoids the divergence cost of B.
- **Cons:** Significant upfront design work; risk of over-engineering before second source lands. Likely worth doing only if 3+ sources are imminent.
- **Effort estimate:** ~8-16 weeks for the framework migration; per-source costs lower thereafter.

## Open product questions (not architecture)

Independent of source and pattern, these questions need product input before any provider ingestion lands. They are reproduced here for traceability — the canonical home is `docs/maintainability/chat_behavior_followup_plan.md` §7.

1. **What does "tell me about X" return?** Provider info only? Provider info plus sponsored events as secondary content? Provider info plus programs? This is a chat-routing question that can't be answered until provider data exists, but the answer constrains schema design (e.g., do providers reference back to events they sponsor?).

2. **How does intent routing distinguish "tell me about X" (provider lookup) from "what's at X" (event search)?** Currently absorbed into event search by default (smoke test #2 in `non_river_scene_cleanup.md`). Fix unblocks once provider data exists.

3. **Verification posture: how trusted is each source?** Does Google Places need operator review? Does manual admin entry skip the queue? Per-source policy affects approval UI and audit trail design.

4. **Coverage scope: comprehensive or curated?** Is the goal "every business in Lake Havasu" or "the businesses Hava can confidently speak to"? Affects source choice (broad API vs curated scraping vs operator-only).

## Provisional first-build recommendation

If forced to pick a starting point with current information: **Pattern A (mirror RS) + Source 1 (manual admin entry)**.

- Lowest infrastructure delta from current state.
- Operator-vetted from day one (no quality risk like the removed Google bulk lane).
- Validates the routing fix path before scaling to broader sources.
- Per `chat_behavior_followup_plan.md` §5 step 2, eval framework should land first; this provider-data-present case is what unlocks the routing fix in step 3.

This is **provisional**. Reconsider when product priorities crystallize. The right answer may be Source 4 (API) for coverage, or wait until eval framework lands and pick based on whichever lane the most-needed query patterns require.

## Cross-references

- Cleanup retrospective: `docs/maintainability/non_river_scene_cleanup.md` (what was removed and why).
- Followup plan: `docs/maintainability/chat_behavior_followup_plan.md` §5 (recommended order: eval framework → provider lane → routing fix), §7 (open questions).
- Existing infrastructure: `app/contrib/approval_service.py` (provider/program approval functions exist but unused since cleanup), `app/admin/router.py` (admin UI), `app/db/contribution_store.py`.
- Current catalog state: see `chat_behavior_followup_plan.md` §6 for SQL to verify.
- River Scene as Pattern A precedent: `app/contrib/river_scene.py`, `app/contrib/river_scene_pull.py`, `app/contrib/approval_service.py`.

## Status

This is a **forward-looking option space document**. It is **not a commitment** to any source, pattern, or timeline. It exists so the next person planning provider ingestion has a starting point with explicit framing rather than reverse-engineering the option space from chat history and removed-code archaeology.

Update this doc only when (a) a source or pattern is actually chosen and built, in which case this becomes a retrospective and a forward-looking sibling doc takes its place, or (b) the option space itself shifts (new source becomes available, an option is conclusively ruled out by product direction).
