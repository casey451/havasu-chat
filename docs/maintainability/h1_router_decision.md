# H1 Investigation: `/chat` vs `/api/chat` — Decision Recommendation

**Status:** Read-only investigation complete. Decision recommendation below; awaits owner approval before any deletion or deprecation ship.

**Bundle reviewed:** `h1_router_investigation_bundle.txt` (139,951 bytes, 2,919 lines, 8 sections)

---

## Findings (the actual picture)

### What's running

**Two FastAPI routers are mounted in `app/main.py` (lines 1483–1484), both serve real HTTP traffic:**

1. **`POST /chat`** — registered by `app/chat/router.py` (905 lines). Uses `ChatRequest` / `ChatResponse` with `message` field. State-machine intent dispatch via long if/elif chains. Logs to `chat_logs.tier_used = 'track_a'`.

2. **`POST /api/chat`** — registered by `app/api/routes/chat.py`, which calls `app.chat.unified_router.route()` (~440 lines). Uses `ConciergeChatRequest` / `ConciergeChatResponse` with `query` field. Tiered routing (Tier 1/2/3). Logs with numeric `tier_used`.

### The deprecation intent is documented

The smoking gun is in `app/api/routes/chat.py` lines 25–29:

> Path (Option B, approved): POST /api/chat — Track A's static UI still uses POST /chat with message + session_id; mounting the concierge here avoids collisions. Intent: keep /api/chat until Phase 3 is production-ready and the frontend can migrate safely; then swap to unified POST /chat in a coordinated cutover (handoff §5 Phase 2.3).

That comment is from before Phase 3. Phase 3 has shipped (`unified_router.py` git history shows Phase 3.1, 3.2, 3.8). The cutover the comment described never happened in the form it described — instead, the frontend migrated to `/api/chat`, and `/chat` remained as a parallel legacy endpoint.

### The frontend migrated

`app/static/index.html` line 842:
```javascript
fetch("/api/chat", {
  method: "POST",
  ...
  body: JSON.stringify({ session_id: sessionId, query: text }),
})
```

The live frontend hits **only** `/api/chat`. There are zero `/chat` POST calls in `app/static/`. The migration the routes/chat.py comment described as future work has already happened; the comment is stale.

### Documentation acknowledges the split

**`docs/runbook.md` lines 159–161:**
> User-facing chat UIs use POST /api/chat (unified router)... Legacy POST /chat (Track A) remains for older scripts; logs with `tier_used = 'track_a'` to separate from unified analytics. **Live site uses /api/chat (see app/static/index.html).**

**`docs/known-issues.md` line 219:**
> A small historical share of rows... where `tier_used` is SQL NULL (primarily Track A POST /chat / log_chat_turn writes that predate unified-router analytics columns)... **Not a runtime defect in current /api/chat logging.**

The runbook describes `/chat` as "for older scripts." Nothing in the bundle identifies what those older scripts are or who runs them.

### Test coverage trail

Uncapped test counts:

- `app.chat.router` test imports: **0**
- `app.chat.unified_router` test imports: **116**

Phase-numbered test files (`test_phase2.py` through `test_phase8.py`) do still hit `/chat` — but no test files mock the `app.chat.router` module directly. The phase-numbered tests look like behavior fixtures from earlier phases, not current development against `/chat`.

The current test cohort (`test_api_chat_e2e_ask_mode.py`, `test_ask_mode.py`, `test_phase2_integration.py`, `test_classifier_hint_extraction.py`, `test_gap_template_contribute_link.py`) targets `/api/chat` and patches `unified_router` internals.

### Git history per file

**`app/chat/router.py`** — 15 commits in last 30, mostly older sessions. Most recent commit: `f55146e` ("feat(8.9): event recurrence field, migration, backfill script, ranking"). Other commits cluster in earlier "Session" series (Session L, N, P, T, Z-2, AC-2). The Phase 8.9 commit looks like a coordinated update across both routers for a schema-compatible change rather than active feature development on the legacy path.

**`app/chat/unified_router.py`** — 16 commits in last 30, most named by phase: 8.8.4, 8.8.3, 8.8.1b, 8.3, 8.0.5, 8.0.2, 6.4.1, 6.4, 6.3, 5.5, 5.4, 4.3, 3.8, 3.2, 3.1, 2.2. Active feature development trail.

### Cross-references in app/

- `app.chat.router`: 1 import (only `app/main.py`, registers the route)
- `app.chat.unified_router`: 2 imports (`app/api/routes/chat.py` for the route, `app/eval/confabulation_invoker.py` for the eval harness)

The legacy router is wired into nothing else — no shared helpers, no cross-imports.

### Sentry/error reporting

`app/main.py` line 1208 has a path allowlist that includes both:

```python
return path.endswith("/api/chat") or path.endswith("/chat")
```

This scrubs chat bodies from Sentry events on either path. So both endpoints' user content is being filtered correctly — that's not a security finding, but it's evidence that both paths are still expected to receive traffic.

---

## Conclusion

`POST /chat` is **legacy code, kept alive for backward compatibility with unspecified external clients ("older scripts" per runbook)**. It is:

- Mounted in production
- Receiving some traffic (otherwise removing the Sentry scrubber would be safe to consider)
- Not the path the live frontend uses
- Not actively developed (zero test imports, sparse git activity, no cross-references)
- Not part of the architecture documented in canonical state docs (PROJECT.md, the unified_router component doc)

The previous Claude session that briefed me used PROJECT.md's phrasing — "A query enters via POST /api/chat..." — which describes only the modern path. That description is accurate for the live frontend but incomplete for the full deployment.

This is not "two parallel chat systems" in the active-development sense. It's "modern path + legacy carryover." The real question is whether the legacy carryover should remain, be deprecated cleanly, or be deleted.

---

## Three options

### Option A: Leave it as-is, document explicitly

**Action:** Add a `## Legacy /chat endpoint (Track A)` section to PROJECT.md and unified_router.md's "Related components" section. State that `/chat` is a legacy endpoint kept for unspecified backward compatibility, owned by `app/chat/router.py`, that the live frontend doesn't use, and that future development happens on `/api/chat` only.

**Pros:**
- Zero risk to existing clients (whoever they are)
- Future Claude sessions stop being confused — the doc explains the split
- No code changes
- Cheapest to ship

**Cons:**
- Maintainability debt persists — `router.py` (905 lines) keeps existing
- Phase 8.9-style "update both routers for schema compatibility" remains a hidden cost on every schema-touching ship
- Two routers' worth of analytics columns in `chat_logs`
- Doesn't actually solve the H1 finding from the maintainability review — it just describes it

### Option B: Deprecate with structured rollout

**Action:**

1. Investigate "older scripts" — figure out what's actually hitting `/chat` in production. Look at `chat_logs.tier_used = 'track_a'` row counts over the last 30 days. If non-zero, identify clients via IP/user-agent if logged.
2. Add a deprecation header (e.g. `Deprecation: true`, `Sunset: <date>`) to all `/chat` responses.
3. Wait a defined period (30/60/90 days).
4. Either delete (if no traffic) or formalize (if traffic confirmed and worth keeping).

**Pros:**
- Data-driven decision — real production usage, not guesswork
- Standard HTTP deprecation pattern
- Reversible until the deletion step

**Cons:**
- Multi-step ship across multiple weeks
- Requires production query access (non-trivial in this collaboration model)
- Sets a deletion deadline that the team has to honor

### Option C: Delete `/chat` immediately

**Action:**

1. Check `chat_logs.tier_used = 'track_a'` row count over recent period (last 7-30 days).
2. If essentially zero, delete `app/chat/router.py`, the `chat_router` import in `app/main.py`, the `/chat` path from the Sentry scrubber, the phase-numbered tests that hit it, and any related analytics views/queries.
3. Watch for breakage in production via Sentry / Railway logs over 24-48 hours.
4. Revert if anything breaks; finalize if quiet.

**Pros:**
- Solves the maintainability finding cleanly
- Removes 905 lines of code, ~30 phase-numbered test references, and the "two parallel routers" mental burden
- Future Claude sessions never have to disambiguate which router
- Frees the `/chat` path for future use if ever needed

**Cons:**
- Risk of breaking unspecified clients ("older scripts")
- Aggressive — no migration period
- Production traffic check is the gate; if traffic exists, this option doesn't apply

---

## Recommendation

**Option B is correct.** Reasoning:

- Option A (leave as-is) doesn't actually fix anything; it just describes the problem. The maintainability cost continues.
- Option C (delete now) is the right destination but the wrong process — without a traffic check, it's a guess. With a traffic check, it converges with Option B's first step.
- Option B is Option C done responsibly. The investigation step (look at `track_a` row counts in production) determines whether the rollout is "deprecate with header, wait, delete" or "delete immediately because there's no traffic."

The first step of Option B is itself one session of work — read-only production query against `chat_logs`. After that, the path is clear:

- Zero or near-zero `track_a` traffic → straight to deletion (effectively Option C, but with confidence)
- Meaningful traffic → identify clients, communicate with them, structured deprecation

Either way, the legacy router's deletion is the goal, but the path depends on whether real users would be affected.

---

## Proposed next session

A read-only Track A traffic investigation:

**Scope:** Query production `chat_logs` for rows where `tier_used = 'track_a'` over the last 30 days. Report:

- Total row count
- Distribution by day (any sign of regular usage)
- Distribution by `session_id` prefix (single test client vs. many distinct sessions)
- Distribution by user-agent or IP if logged

**Output:** A decision artifact saying either:

- "No meaningful traffic, recommend immediate deletion ship per Option C"
- "Meaningful traffic identified, structured deprecation per Option B with timeline X"

That session is small. From there, the deletion or deprecation ship is its own session, following the standard halt-and-report discipline.

---

## What this changes about the maintainability findings

The H1 finding from the maintainability review (`maintainability_findings_app_chat.md`) said "two parallel chat systems running in production." That framing was correct but incomplete — it's better characterized as "modern path with active legacy carryover."

This investigation **does not change** the disposition recommendation for H1 (resolve before broader feature work). It does change the urgency signal: the legacy router isn't being actively maintained against the modern path's standards, which means voice-rule changes, security fixes, and so on are going to drift from one path to the other if the parallel state continues.

The H2 finding (LLM-call infrastructure duplicated across four files) remains independent of the H1 outcome. The four files duplicating LLM-call boilerplate are all on the modern path — refactoring them doesn't depend on what happens to `/chat`.

The H3 finding (hardcoded entity list won't survive bulk import) is also independent.

So the original three-priority order from the maintainability review still holds:

1. H1 (this investigation; deletion or deprecation ship next)
2. H2 (LLM infra refactor)
3. H3 (entity matching scale)
