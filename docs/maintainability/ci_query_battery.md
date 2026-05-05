<!--
PURPOSE: How-to-run reference for the 120-query battery in
scripts/run_query_battery.py. Tier-drift regression detection: each
query has an expected tier_used label captured from production; the
battery flags drift.

AUDIENCE: Developers and assistants running the battery for verification
or extending it.
-->

# CI Query Battery

## What it is

`scripts/run_query_battery.py` runs 120 fixed queries against the production
`/api/chat` endpoint and compares each response's `tier_used` field against
a captured baseline. Mismatches surface tier-routing regressions
(e.g., a query that previously routed Tier 2 now hitting Tier 3).

The battery is **diagnostic-only**: it does not import from `app.` and runs
out-of-process via HTTP. This is intentional — it verifies routing as the
deployed service actually behaves, not as the test suite imagines.

## Why it exists

Pytest covers code-level correctness but cannot verify that real user queries
hit the intended tier in production. The battery fills that gap by exercising
the live routing decisions across a broad fixed input set. Drift between
expected and actual tier_used is the signal.

History:

- **Slice 16 (#12 RESOLVED):** Battery retargeted from legacy `/chat` to the
  unified `/api/chat` endpoint with `ConciergeChatResponse` payload shape.
- **Slice 23 (#25 RESOLVED):** `SINGLE_SHOT` expected labels rebuilt from a
  captured production baseline. `matches()` helper restored.
  `run_all()` reports matched/mismatched counts. The battery now functions
  as a tier-drift regression detector rather than a behavioral oracle.

## How to run (manual)

From the repo root:

    python scripts/run_query_battery.py

The script POSTs each query to `https://havasu-chat-production.up.railway.app/api/chat`
with a fresh `session_id` and 15-second timeout, classifies the response by
`tier_used`, and prints a per-query line plus a summary at the end.

Output is JSON dumped to stdout (`print(json.dumps(out, indent=2))`):

    {
      "total": 120,
      "matched": 119,
      "mismatched": 1,
      "results": [
        {
          "num": 1,
          "section": "Section 1",
          "query": "boat race",
          "actual": "TIER3",
          "expected": ["TIER3"],
          "match": true,
          "mode": "ask",
          "sub_intent": "...",
          "entity": null,
          "tier_used": "3",
          "latency_ms": 1234,
          "llm_tokens_used": 567,
          "chat_log_id": "...",
          "elapsed_seconds": 1.23,
          "note": "Section 1",
          "response_snippet": "...",
          "status": 200
        },
        ...
      ]
    }

The `total`/`matched`/`mismatched` summary is the headline; per-query
records preserve full context for investigation. Each record holds the
`actual` tier classification, `expected` set, `match` boolean, and
the unified router's response payload fields (`mode`, `sub_intent`,
`entity`, `tier_used`, latency, tokens, chat_log_id) for traceability.

Pipe through `jq` for ad-hoc inspection:

    python scripts/run_query_battery.py | jq '.matched, .mismatched'
    python scripts/run_query_battery.py | jq '.results[] | select(.match == false)'

A clean run is `matched: 120, mismatched: 0`. The known LLM-non-determinism
flake budget (per Slice 23 verification) is 1/120 on borderline date phrases;
re-runs should converge.

## Success criteria

- **Pass:** `matched == 120` (or `mismatched <= 1` on borderline date phrases
  with re-run convergence).
- **Investigate:** `mismatched > 1`, or a sustained mismatch on a previously
  stable query.
- **Block deploy:** any tier downgrade on a Tier 1 query (deterministic
  template path), or any tier change on a query previously stable for 5+ runs.

## Where the labels live

`scripts/run_query_battery.py:SINGLE_SHOT` is the source of truth. Each tuple
is `(num, query, expected_set, note)`. The `expected_set` holds the
`tier_used` value(s) the query was last seen producing in production.

## How to update labels

When intentional routing changes ship (e.g., a Tier 2 parser broadens its
match surface, pulling a query down from Tier 3), update the corresponding
`expected_set` in the same commit as the routing change. Don't update labels
in a separate commit — the test of the routing change IS the new label.

For wholesale rebuilds (every label refreshed from a captured baseline),
follow the Slice 23 pattern: capture, diff, rebuild, verify against the
production baseline run. Document the rebuild in the BACKLOG entry.

## Future invocation patterns

Currently the battery runs manually. Three plausible CI integration paths
(none currently implemented):

1. **GitHub Actions on push-to-main.** A workflow file
   `.github/workflows/query-battery.yml` that runs the script after each
   merge to main. Surfaces drift within minutes of a deploy.
   - Cost: 120 queries × ~1-3s each = 2-6 min wall time per run.
   - Complexity: low (single Python invocation).
   - Caveat: requires production to be healthy at run time; transient
     Railway outages would produce false positives.

2. **Railway scheduled task.** Daily or post-deploy hook invocation from
   within the deploy environment. Simpler env handling (production URL
   already wired), but mixes monitoring with deploy infra.

3. **Pre-deploy verification hook.** Block deploy until battery passes
   against the previous version. Rejects bad routing changes before they
   reach users. Highest friction; would need a parallel "previous version"
   environment to query.

Until one is wired, treat manual runs as the canonical signal: run the
battery before any merge that touches `app/chat/` routing or Tier 1/2/3
handlers, and after deploy if a routing-relevant change shipped.

## Cross-references

- Battery script: `scripts/run_query_battery.py`
- Source query list with expected categories: `docs/query-test-battery.md`
  (the human-readable spec; `SINGLE_SHOT` is the executable form)
- Phase C epic: `docs/BACKLOG.md` Backlog #18, sub-bullet "§5 gap: CI
  query-battery story"
- Resolution that unblocked this doc: `scripts/run_query_battery.py`
  retarget (Slice 16, #12) and label rebuild (Slice 23, #25)
