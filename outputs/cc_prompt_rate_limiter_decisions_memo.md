# Claude Code Prompt — Rate-Limiter §8 Decisions Memo

> **Operator note:** paste everything inside the `~~~` fence below into a fresh Claude Code chat as the first message. CC produces a markdown memo at `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md`. No git operations; no other file edits. When CC returns, Cowork primary will frame the 7 §8 decisions for you via AskUserQuestion. Re-authored 2026-05-13 (prior-session-sandbox didn't persist).

~~~

# Task — Author the rate-limiter §8 decisions memo

You're a Claude Code agent picking up a read-only investigation lane in the **havasu-chat** repo. You will NOT edit any files except for one new memo file. You will NOT run `git add`, `git commit`, or any git-state-mutating command. You will report your findings back as a single message when done.

## §0 Baseline confirmation (do this first and report values)

Before reading anything, confirm and report:

1. `git log --oneline -3` — top of `main` should be `11b248f` on `597d9cb` on `aea87b8`.
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — collected count should be **1429** tests.
4. `python -m alembic heads` — single head **`e7f8a9b0c1d2`**.

If any baseline value doesn't match, **halt and report**. Don't proceed.

## §1 What this lane is

The Phase 2.5 third-party-source rate-limiter design doc at `docs/maintainability/phase2_5_rate_limiter_design.md` is DESIGN-COMPLETE but has **7 open questions in §8** that block implementation. The Cowork primary needs a memo that:

- States each of the 7 questions in plain language.
- Surfaces the relevant code/docs evidence Cowork primary would want to weigh (cite line refs).
- Lists the credible answer options with pros/cons.
- Recommends an answer with rationale.
- Flags any dependencies between questions (e.g. "if Q5 = single-process, then Q3 simplifies because [...]").
- Notes any risks or surprises the primary should know.

The primary will read your memo and then drive a decision round with the operator (Casey). Your output is the input to that round.

## §2 Read these first (in this order)

1. **`docs/maintainability/phase2_5_rate_limiter_design.md`** — primary source. §8 is what you're memo'ing about. §0–§7 give you the context for each question.
2. **`docs/components/places_client.md`** — the runtime Places-touching path (`app/contrib/places_client.py`) that has the rate-limit gap.
3. **`app/contrib/places_client.py`** — read end-to-end. Note the existing error envelope (`PlacesLookupResult(status="error", error_message=...)`) at the lines the design doc cites.
4. **`scripts/places_discovery.py`** — read §1.1 of the design doc first for line refs, then the file. Notice the DIY retry pattern (`INTER_REQUEST_SLEEP_S`, `MAX_RETRIES`, etc.).
5. **`scripts/places_enrichment.py`** — same DIY pattern as discovery; confirm with your eyes that it's literally copy-pasted.
6. **`app/core/rate_limit.py`** — the slowapi precedent for inbound rate-limits (not directly applicable but worth knowing).
7. **`app/api/routes/contribute.py:48–58, 228`** — the `_rate_limited` DB-backed precedent for the IP-hash pattern (the Option B design references this).
8. **`app/contrib/url_fetcher.py`** — the contributor-URL fetch path. §8 Q6 asks whether this gets folded in.
9. **`app/core/llm_messages.py::call_anthropic_messages`** — find this and skim its surface. §8 Q7 asks whether OpenAI/Anthropic eventually use the same `SourceLimiter` interface.
10. **`docs/STRATEGY_PIVOT_2026-05-12.md` §6** — the pivot's three-bucket re-prioritization. Confirm the rate-limiter is in the "load-bearing under either vision (KEEP)" bucket and that the directory-first pivot makes it MORE urgent, not less. This grounds your "how urgent is the right answer" framing in the memo.

You may also skim `docs/maintainability/llm_mock_pattern.md` for the project's mock-friendly design pattern (relevant to Q4 observability).

## §3 The 7 questions (verbatim from §8 of the design doc — restate plainly in your memo)

1. **Confirm the §0 scope correction.** Is "third-party-source rate-limiter" the right framing, or did the original brief mean something specific by "enrichment-ingest"?
2. **Per-source default QPS.** `places_discovery.py` and `places_enrichment.py` both use 4 QPS. Operator-tuned or a guess?
3. **Failure-mode policy.** Retry-exhausted 429 in the runtime path: keep current `PlacesLookupResult(status="error")` envelope, or escalate to a louder signal (retry queue, operator-visible alert)?
4. **Observability surface.** Throttle telemetry: (a) stdout only, (b) new DB table for outbound-API events, (c) structured logs to Railway? Pick one.
5. **Phase 2.5 launch concurrency.** Single-process scheduled job, or multiple concurrent workers? Determines whether P1 (Option A: in-process semaphore) is sufficient or whether P2 (Option B: DB-backed token-bucket) must ship in the same lane.
6. **`url_fetcher.py` inclusion.** Per-host rate limiting against arbitrary contributor URLs in this lane, or defer as a separate concern?
7. **OpenAI as a future source.** Same `SourceLimiter` interface eventually wrap OpenAI/Anthropic LLM calls, or do LLM calls live in a separate abstraction?

## §4 What to write

A new file at **`docs/maintainability/phase2_5_rate_limiter_decisions_memo.md`**. Suggested structure:

```
# Phase 2.5 Rate-Limiter — §8 Decisions Memo

**Status:** decision-input only; no implementation.
**Source design:** `docs/maintainability/phase2_5_rate_limiter_design.md`
**Author:** Claude Code (read-only investigation lane, <DATE>)
**Audience:** Cowork primary running a decision round with the operator.

## §1 Summary recommendations (table)

| # | Question | Recommended answer | Confidence | Blocks impl? |
|---|---|---|---|---|
| 1 | Scope framing | Yes — "third-party-source" is correct | High | No |
| 2 | Default QPS | 4 QPS / revisit ... | Med | No |
| ...

## §2 Per-question detail

### §2.1 — Q1 (scope framing)

**Question:** ...

**Evidence:**
- `phase2_5_rate_limiter_design.md:24` — ...
- `app/contrib/places_client.py:96–126` — ...

**Options:**
- (a) ... — pros: ...; cons: ...
- (b) ... — pros: ...; cons: ...

**Recommendation:** ...

**Rationale:** ...

**Dependencies:** None / "Affects Q3 because ..."

**Risks / surprises:** ...

### §2.2 — Q2 (default QPS)
...
```

Continue through Q7. Length budget: aim for ~200–400 lines total. Each question gets enough evidence + rationale that the primary doesn't have to re-read the design doc to make a call.

## §5 Constraints + standing rules

- **READ-ONLY apart from the memo file.** Do not edit any other file. Do not run `git add`, `git commit`, `git stash`. Do not modify `BACKLOG.md`, `STATE.md`, or the design doc.
- **No tests; no code; no migrations.** This is a memo lane.
- **Cite line refs.** Every claim grounded in a file should include `path:line` or `path:line-range`. If the design doc already cites a line ref and you confirm it, just re-cite it.
- **Don't recommend something you can't defend.** If a question genuinely has no clean answer, say so — "Both options are defensible; here's the trade-off; flag for operator to decide based on X."
- **Don't try to relitigate the design doc itself.** The design's choice of Option A for P1 with B-migration-path is fixed. Your scope is only the 7 open questions in §8.
- **Honor the dispatch protocol.** Anchored Edit over full-file Write if you ever need to amend the memo. (You're creating it new so Write is fine for the first pass; further passes use Edit.)
- **Halt if baseline (§0) doesn't match.** Don't proceed silently.

## §6 What to report back

When you finish, paste a single message with:

1. Baseline values from §0 (HEAD, pytest count, alembic head).
2. Memo path: `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md`.
3. Memo line count.
4. Brief summary table: each Q + your one-line recommendation.
5. Anything that surprised you during investigation (e.g. "found a third copy of the retry block I didn't expect at path X line Y").
6. Open questions YOU have for the primary (if any). These are different from the §8 questions; they're meta-questions you couldn't resolve from the doc + code alone.
7. Confirmation that you did NOT run any git-state-mutating command and did NOT edit any file other than the memo.

Begin.

~~~
