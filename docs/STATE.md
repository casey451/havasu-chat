> **Fresh Claude or Cursor session?** Read this file first, then `docs/WORKING_AGREEMENT.md`, then `docs/BACKLOG.md`. Architecture context lives in `docs/PROJECT.md` if you need it.

# Current state

This document is updated at the end of each session that ships work. It is the canonical answer to "where is the project right now."

## Production

- **Deployed commit:** `d279165` — Tier2 formatter: deterministic Python rendering for event listings
- **Production URL:** https://havasu-chat-production.up.railway.app
- **Health:** `/health` returns 200, db_connected, event_count 114

## Tests

- **Pytest baseline:** 997 passing
- **Test command:** `python -m pytest -q`

## Recent commits (newest first)

```
d279165  Tier2 formatter: deterministic Python rendering for event listings
cdc4ac7  Chat UI: render markdown link syntax in assistant bubbles
7d89a03  Tier2 query: include event_url in event row payload
1c262ad  Tier2 formatter: completeness, count fidelity, date_exact ordering
6934d1d  Past-date retrieval: honor explicit date bounds without clamping to today
d763775  Multi-day events: schema, retrieval, parser fields, and backfill
63a4535  Parser: document date_exact, ranges, month, season in tier2 prompt
8203a7f  Fix 2: Backfill pending RiverScene contributions
6e2b558  Fix 1: Auto-approve RiverScene contributions on creation
```

## Recently shipped (last work cycle)

- **Past-date retrieval fix** (`6934d1d`) — `_query_events` no longer clamps explicit past date bounds to today. Production verification deferred until catalog has past-dated events.
- **Tier 2 ranking improvement** (`1c262ad`, SQL ordering portion only) — events whose start_date matches the query date rank above overlap-only events for `date_exact` queries. The prompt-rule portion of this commit was deployed but had no observable effect on the LLM and was superseded by `d279165`.
- **Clickable URLs** (`7d89a03` + `cdc4ac7` + emergent in `d279165`) — `event_url` flows through the row payload, frontend renders markdown link syntax as clickable anchors, deterministic renderer emits `[title](url)` for events with non-empty URLs.
- **Formatter completeness fix** (`d279165`) — Tier 2 event responses now render via deterministic Python instead of LLM. Row count, order, and verbatim titles structurally guaranteed. Programs and providers still use the LLM path with the existing prompt.

## Queued / open work

See `docs/BACKLOG.md` for the canonical list. Items not yet addressed:

- Programs and providers: scope-limited out of the deterministic renderer. Whether they have the same dropping/count-fabrication bug as events did is unverified.
- Phase 8.8.6 eval harness: automated LLM-behavior testing wiring is incomplete. Several deferred-verification notes in `BACKLOG.md` would close once this lands.

## Working tree

Clean except for the canonical-docs introduction work. No stale modifications, no in-flight changes outside that.

## How to update this document

At the end of each session that ships work, update:

- **Deployed commit** — new top commit hash and subject
- **Recent commits** — prepend the new commit(s); keep the list at roughly 10 entries
- **Recently shipped** — describe what changed in user-facing or architectural terms; reference the commit hash
- **Queued / open work** — adjust based on what's now closed vs. still pending

Do not update this file mid-session. Update it as part of close-out, after verification has confirmed ship.
