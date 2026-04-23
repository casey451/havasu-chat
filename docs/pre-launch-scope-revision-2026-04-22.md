# Pre-launch scope revision — 2026-04-22

**Status:** PROVISIONAL. Decisions captured end-of-session 2026-04-22. Revisit and confirm in next session before treating as locked. If confirmed as-is, this document becomes the authoritative record of the re-sequencing. If revised, the next-session version supersedes.

**Author:** Owner (Casey), drafted with Claude 2026-04-22 session.

**Affects:** `docs/pre-launch-checklist.md`, `HAVA_CONCIERGE_HANDOFF.md` §5 build plan, `docs/persona-brief.md` §11 open items, Phase 9 scoping notes (items previously scoped as post-launch now moved pre-launch).

---

## 1. What this document is

A decision record for a set of scope changes made during the 2026-04-22 session that extend pre-launch work substantially. The changes reverse prior decisions that sequenced bulk catalog expansion as post-launch work. If confirmed, they push launch from roughly 2–4 weeks out to roughly 6–10 weeks out.

## 2. Decisions made this session (all provisional)

### 2.1 River Scene event pull — pre-launch

Pull events from River Scene (local events calendar) into the events catalog before launch. Scope: one source, structured event data ingestion, operator review pass, dedup against existing 43 seeded events. Low-risk, small-to-medium execution phase.

### 2.2 Google bulk import — pre-launch, full scope

All 4,574 businesses from the cleaned Lake Havasu business license roster get enriched via the `havasu-enrichment` pipeline and ingested into the chat app's provider catalog before launch. No stage gate — not "Batch 1 validates, then decide." The commitment is to all batches pre-launch.

Reverses:

- The original bulk-import scoping conversation's Option B (ship with 25 curated, add bulk post-launch)
- Phase 9 scoping notes' split of Arc 1 (bulk import) as post-launch work
- The enrichment framework v3's implicit staged-rollout structure

### 2.3 Voice for bulk-imported providers — deferred to 8.8.1b

With 25 hand-curated providers, Hava's firsthand voice ("The AI local of Lake Havasu") reads plausibly — she can have opinions about places she's "been to." With 4,574 bulk-imported providers she has never "been to," the firsthand voice strains. Two candidate resolutions:

- **Uniform firsthand**: voice treats curated and bulk the same; the AI identity is doing enough stylistic work that "firsthand" isn't read as literal.
- **Two-tier voice**: curated providers speak firsthand; bulk providers get a lighter texture ("I don't know this one as well — here's what I hear").

This decision is surfaced as a required 8.8.1b input. 8.8.1b does not start drafting the system prompt until it's locked.

### 2.4 No stage gate on bulk import

Batch 1 is not a validation step with a go/no-go before Batches 2–N. The commitment is to proceed through all batches regardless of Batch 1 outcomes. The enrichment framework v3's built-in safeguards (batch quality reports, match-confidence distribution tracking, manifest versioning, checkpoint/resume) remain in place, but operational gates — not strategic ones.

## 3. Revised pre-launch sequence

Before this revision:

```
8.8.1a [done] → 8.8.1b → 8.8.2 → 8.9 → dogfood → launch
```

After this revision (provisional):

```
8.8.1a [done]
  → 8.8.1b  (persona code; requires §2.3 input decision)
  → 8.8.2   (voice regression v1, curated catalog only)
  → 8.9     (event ranking — recurring vs. one-time)
  → 8.10    (River Scene event pull)
  → 8.11    (Google bulk import — havasu-enrichment full run)
       ├── 8.11.0 — Day 1 setup (owner tasks per enrichment framework)
       ├── 8.11.1 — Batch 1 execution + quality report
       ├── 8.11.2 — Batches 2–N execution
       ├── 8.11.3 — Operator review drain
       └── 8.11.4 — Ingestion into Postgres catalog
  → 8.12    (voice regression v2 — expanded catalog, revised acceptance bar)
  → 8.13    (Tier 3 retrieval tuning for expanded catalog surface area)
  → dogfood
  → launch
```

## 4. Updated pre-launch checklist

Current seven items from `docs/pre-launch-checklist.md` stay. Added items from this revision:

- Phase 8.9 event ranking complete (previously flagged missing from the checklist — persona brief §9.6)
- River Scene event pull operational, events ingested, operator-reviewed
- `havasu-enrichment` Day 1 setup complete (Google Cloud, Anthropic key, repo, venv, Drive folder)
- Batch 1 executed, quality report reviewed
- Batches 2–N executed
- Operator review queue drained to acceptable threshold (TBD — part of 8.11.3 scoping)
- All 4,574 providers ingested into chat app Postgres
- Voice regression v2 passes against expanded catalog with revised acceptance criteria
- Tier 3 retrieval verified against new narrative surface area

## 5. Operational realities this commitment carries

Not reasons to reconsider — just realities to plan around.

### 5.1 Systemic-bug detection cost

Without a stage gate, a pipeline bug found at Batch 3 means 4,574 rows to reprocess instead of 25. The enrichment framework's idempotency rules (INSERT OR REPLACE on primary keys, SQLite as source of truth) make reprocessing possible but not free.

### 5.2 Match-confidence distribution risk

If the confidence distribution lands worse than the framework assumed (heavy `name_only` or `ambiguous_match` tails), operator review load scales. At 10% review rate across 4,574 entries that's ~457 items; at 25% it's ~1,143. Review cadence planning is a real task in 8.11.3, not an afterthought.

### 5.3 Voice surface area expansion

8.8.2 voice regression verifies against the catalog *as it exists when 8.8.2 runs*. That catalog will be curated-only. 8.12 is a second voice regression against the expanded catalog with re-calibrated acceptance. This isn't redundant — it's necessary because Tier 3 synthesis quality is downstream of retrievable content, and the content is about to change.

### 5.4 Community-credit reopen interacts with bulk

The §2.1 firsthand voice decision was made with a 25-provider catalog in view. 4,574 bulk-imported providers change the plausibility envelope. This is what §2.3 captures — the decision needs to land before 8.8.1b, and it cascades into 8.12.

## 6. Open items for next session

Listed in rough priority order.

1. **Confirm or revise this document.** If confirmed, remove "PROVISIONAL" from the status and proceed. If revised, redraft.
2. **Voice for bulk-imported providers (§2.3).** Required input for 8.8.1b. Options enumerated above; decision rests with owner.
3. **Operator review cadence for 8.11.3.** How many providers per review session, what confidence tiers auto-admit vs. queue, what's the threshold for "drained enough to launch."
4. **Update `docs/pre-launch-checklist.md`.** Add the items enumerated in §4 above. Owner-authored or Cursor-executed, either works.
5. **Update `HAVA_CONCIERGE_HANDOFF.md` §5 build plan.** Phases 8.10 through 8.13 need entries. Can bundle into the existing doc-refresh rhythm.
6. **Update `docs/persona-brief.md` §11 open items.** Add the §2.3 voice decision as a required 8.8.1b input. Small amendment.
7. **Carryovers from prior sessions, still open:** §7 vs §13 test count mismatch, `prompts/voice_audit.txt` and `scripts/smoke_concurrent_chat.py` old-filename references (for 8.8.1b bundling).

## 7. What's NOT included in this document

- The River Scene event pull Cursor prompt itself. Drafted separately when 8.10 starts.
- The `havasu-enrichment` Day 1 setup walkthrough. Already exists in enrichment framework v3.
- The 8.8.1b Cursor prompt. Drafted when §2.3 decision lands.
- Any code changes. This is a decision record, not an execution artifact.

## 8. How to confirm this as non-provisional in next session

If in the next session the decisions still read right:

1. Edit this document's status from "PROVISIONAL" to "LOCKED 2026-MM-DD."
2. Execute open item #4 (pre-launch checklist update).
3. Execute open items #5 and #6 as small doc amendments.
4. Proceed with 8.8.1b.

If any decision reads differently with sleep on it:

1. Edit this document to supersede — write the revised decision, note what changed and why.
2. Walk back any work that was started on the provisional assumption (nothing has been started as of this doc's authoring).
3. Proceed with the revised plan.

Either path is clean. The provisional framing is a feature, not indecision.
