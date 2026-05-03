<!--
PURPOSE: Handoff plan for two latent chat-tier issues (business-name intent
routing vs event search; lack of versioned chat eval coverage) raised at
non–River-Scene cleanup stream close. Records smoke-test context, why fixes
are deferred, recommended work order, and pointers for a fresh session.

AUDIENCE: Future maintainers and sessions building chat eval, provider
ingestion, or unified-router / hint-extractor changes. Designed as a read-first
entry point; follow Refs to retrospectives and the confabulation-eval runbook.

Unlike the post-ship retrospective files in this folder, this doc is intended
to be linked or opened at session start as bootstrap context.
-->

# Chat behavior followup plan

This doc captures two open chat-tier issues surfaced by the smoke
test at the close of the non-River-Scene cleanup stream. Neither
is fixable in the session that found them; this doc carries enough
context that a fresh Claude session, working with a fresh Cursor
session, can drive the eventual fix without rebuilding context.

Read this first. The "Refs" section at the bottom points to the
two retrospectives that bracket today's work.

## 1. Background — what closed today

Two streams closed on 2026-05-03:

- The River Scene parser-followup stream — commits `0051f17`,
  `5ec85da`, `08604ad`. See
  `docs/maintainability/river_scene_event_output_decision.md`.
- The non-River-Scene cleanup stream — chain ending in `7cba51e`.
  See `docs/maintainability/non_river_scene_cleanup.md` for the
  full retrospective, including what was deleted and why.

The cleanup removed all non-RS data from prod. The catalog is now
RS-only: 71 events, 71 contributions, every other content table
empty. Stream-close included a 3-question chat smoke test against
this RS-only catalog. Two of the three answers were correct. The
third surfaced an intent-routing issue that's the subject of this
doc.

## 2. Issue 1 — intent routing for business-name questions

**Concretely.** Smoke test question 2 was "Tell me about Anderson
Toyota." Expected behavior: provider lookup. Hava should answer
something like "I don't have provider info on Anderson Toyota"
(since the providers table is empty), or — once provider data
exists — surface the provider details. Actual behavior: Hava
returned "Havasu Balloon Festival Presented by Anderson Toyota,"
a real RS event that has Anderson Toyota in its title. The router
classified the question as event-search intent and the formatter
ran with it.

**Why this is a real issue.** "Tell me about \<business\>" is a
provider-lookup intent. Returning events sponsored by the business
as the *primary* response is wrong — the user asked about the
business, not about its events. An acceptable shape would be
provider info first, with "and they sponsor these events" as
secondary content.

**Why it's currently invisible to users.** The providers table is
empty, so every business-name question would currently route to
events anyway. The misrouting becomes user-visible the moment any
provider ingestion lane lands and starts populating the table —
at that point users will start asking about businesses we have
data on, and the router will keep falling through to event search.

So this is latent. It does not block today's catalog. It will
block the first product moment after a provider lane lands, which
is why it gets captured now rather than discovered then.

## 3. Issue 2 — chat eval coverage

**Concretely.** The smoke test was three questions, run by hand,
evaluated by owner judgment. That was sufficient for closing the
cleanup stream — it told us whether the catalog-shape change broke
chat in obvious ways — but it does not scale and it does not catch
the failure modes that matter most.

**The riskiest failure mode is confabulation.** Hava sits in front
of an LLM that has training-data knowledge of every Lake Havasu
business it ever read on the open web. When the DB has no row for
a business, "say I don't have data" is the correct behavior;
"summarize what I remember from training" is a confabulation. The
smoke test covered exactly one such case (Rotary Club, which
passed). One passing example is not coverage.

**What's missing.** A versioned query list with expected behavior
categories. Coverage across the categories that actually matter:

- *admit-absence* — DB has nothing, Hava should say so without
  filling the gap from training data.
- *surface-real-data* — DB has it, Hava should surface it
  faithfully.
- *distinguish-intent* — same noun phrase routed to different
  handlers based on the verb/framing (this is where issue 1
  lives).
- *no-confabulation* — adversarial cases where training data is
  rich and DB is empty.

And: a way to regression-test chat-tier changes without re-running
ad-hoc smoke tests by hand.

## 4. Why we can't fix issue 1 now

Three reasons, each independently sufficient:

1. **Providers table is empty.** Without provider data the happy
   path for provider lookup can't be tested end-to-end. Any fix
   would be validated only against the negative case.
2. **Fix shape depends on the schema and content of the next
   provider ingestion lane.** What fields exist, what coverage
   looks like, what "provider info" means as a returned shape —
   all undetermined. Designing intent routing now is premature.
3. **No eval framework to validate the fix doesn't regress other
   chat behaviors.** Fixing one route by hand-testing one query
   is exactly how the smoke-test-doesn't-scale problem started.

So: provider ingestion lane and chat eval framework are both
prerequisites.

## 5. Recommended order of operations

1. **Build the chat eval framework first.**
   It's independent of DB state, so nothing else has to land
   before it can be useful. It captures current behavior — both
   correct and incorrect — as the regression baseline. It surfaces
   issue 1 in a structured way before the fix lands, which means
   the fix has a target to hit instead of a vibe to satisfy.

2. **Build a provider ingestion lane.**
   Open question, owner decision: which lane first? Candidates
   discussed in earlier conversation include the Aquatic Center
   scraper (lhcaz.gov), a Google Places integration, a manual
   operator-entry tool, and others. The cleanup retrospective
   covers why all previous provider lanes were removed and is the
   right starting point for thinking about which lane to build
   next. This step populates the providers table so issue 1's fix
   has a happy path to validate against.

3. **Fix intent routing.**
   Distinguish "tell me about X" (provider lookup) from "what's
   happening at X" / "events at X" (event search). Validate the
   fix against the eval framework from step 1, including the
   provider-data-present cases unlocked by step 2.

## 6. Context the fresh session needs

### Code pointers

- Chat router and intent classification entry points:
  `app/chat/unified_router.py`, `app/chat/tier2_handler.py`,
  `app/chat/tier3_handler.py`.
- Hint extraction (pulls entity hints from the user query):
  `app/chat/hint_extractor.py`.
- Tier 2 DB query shape: `app/chat/tier2_schema.py`,
  `app/chat/tier2_db_query.py`.
- Formatter prompt: `prompts/tier2_formatter.txt`.
- Tests: `tests/test_tier2_*.py`, `tests/test_unified_router.py`,
  `tests/test_classifier_hint_extraction.py`.
- **Existing eval stack in `app/eval/`** — not an empty corner.
  Worth inventorying before building anything new:
  - `confabulation_invoker.py` — defines `InProcessInvoker`
    (calls `unified.route` directly with evidence capture) and
    `HttpInvoker` (hits `POST /api/chat`, no evidence rows). The
    in-process path is the one to extend if the new framework
    needs to assert against tier/evidence shape.
  - `confabulation_query_gen.py` — defines `Probe`, the unit of
    eval input.
  - `confabulation_evidence.py` — evidence-row capture.
  - `confabulation_detector.py` — confabulation classification.
  - `confabulation_report.py` — report rendering.

  Operator-facing companion: `docs/confabulation-eval-runbook.md`
  documents how to run this stack in an operator context. Its
  existence is load-bearing for question 2 in §7 — the operator
  surface is not hypothetical, it's already here, and any
  decision about where the new framework lives should start by
  reading the runbook.

### Doc pointers

- `docs/maintainability/non_river_scene_cleanup.md` — what
  cleanup did, what was deleted, smoke-test findings, addendum
  on credential rotation.
- `docs/maintainability/river_scene_event_output_decision.md` —
  the parser-followup stream that immediately preceded cleanup.
- `docs/confabulation-eval-runbook.md` — operator-style runbook
  for the eval stack above. Read before deciding question 2.
- `docs/known-issues.md` — exists. As of stream close it's
  mostly pre–H1 voice-audit history (the file carries a banner
  to that effect) and has no open item that overlaps this plan.
  The closest neighbor is a Tier 3 `provider_id` /
  standalone-events entry — adjacent to the routing problem but
  not the same problem. If this plan eventually wants tracking
  in `known-issues.md`, a short new "Open (deferred)" block
  pointing back to this doc avoids overlap with that entry.

### Working agreements established across recent streams

The fresh session should follow these. They aren't negotiable;
they were learned from concrete near-misses upstream.

- **Halt-and-report between every commit.** Owner reviews the
  staged tree before a commit message lands. Two steps between
  stage and commit — staging is one halt, the commit message is
  another.
- **Commit messages: UTF-8 no-BOM, written via temp file.** Apply
  with
  `git -c core.hooksPath=.git/hooks-disabled-empty commit -F <msgfile>`.
  Don't use `--no-verify` — that bypasses the prepare-commit-msg
  trailer hook. Don't use PowerShell `>>` for any text-file write;
  it's the wrong encoding by default. See
  `.cursor/rules/windows-utf8-text-appends.mdc`.
- **Production data verification uses a real Postgres client**
  (DBeaver, TablePlus, the Railway UI). Cursor's tool shell does
  not inherit the env var reliably and silently falls back; don't
  trust query results from inside Cursor for prod.
- **Don't paste the prod connection string into chat.** Set it in
  PowerShell, verify by length only.
- **No rebasing for cosmetic fixes.** Working rule: "amend if it
  misleads about behavior; otherwise leave."

### Current catalog state (as of stream close, 2026-05-03)

- `events`: 71 rows, all `source='river_scene_import'`.
- `contributions`: 71 rows, all `source='river_scene_import'`.
- `providers`: 0 rows.
- `programs`: 0 rows.
- `field_history`: 0 rows.
- `llm_mentioned_entities`: 0 rows.

Verify before relying on these — anything could have shifted
between this doc being written and being read. Verify with:

```sql
SELECT 'events' AS t, COUNT(*) FROM events WHERE source = 'river_scene_import'
UNION ALL
SELECT 'contributions', COUNT(*) FROM contributions WHERE source = 'river_scene_import'
UNION ALL
SELECT 'providers', COUNT(*) FROM providers
UNION ALL
SELECT 'programs', COUNT(*) FROM programs
UNION ALL
SELECT 'field_history', COUNT(*) FROM field_history
UNION ALL
SELECT 'llm_mentioned_entities', COUNT(*) FROM llm_mentioned_entities;
```

Run against prod via a real Postgres client (see working
agreements above), not the Cursor tool shell.

## 7. Open questions for the fresh session

Each is a real decision, not rhetorical.

1. **Which provider ingestion lane is the right first one to
   build?** Aquatic Center scraper (lhcaz.gov)? Google Places
   integration? Manual operator-entry tool? Something else? The
   trade-off is roughly coverage vs. effort vs. alignment with
   eventual launch needs. The cleanup retrospective is the right
   starting point — it explains why each previously-built lane
   was removed.
2. **Where should the chat eval framework live?** The strong
   default is to extend `app/eval/` — the confabulation stack
   listed in section 6 already covers invoker, probe generation,
   evidence capture, detection, and reporting, and
   `docs/confabulation-eval-runbook.md` already documents the
   operator-facing run path. The new versioned query list with
   behavior-category tags (`admit-absence`, `surface-real-data`,
   `distinguish-intent`, `no-confabulation`) maps cleanly onto
   `Probe`, and the runbook is the natural place to extend with
   the new categories. Standing up a parallel top-level `evals/`
   directory is only worth it if the new query set needs a
   fundamentally different invocation shape than what the runbook
   documents — read the runbook before assuming so.
3. **Should the eval run in CI or only manually?** Cost matters
   here — the eval almost certainly calls real LLM APIs, so
   "every PR" is a different proposition from "nightly" or
   "on-demand." Worth a single dry run to measure token cost
   per query before deciding.
4. **Where does the intent-routing fix actually live?** In the
   hint extractor (classify intent before routing)? In the router
   itself (route based on classified intent)? Both? Investigate
   the existing code path before designing the fix.
5. **What should "tell me about X" return?** Provider info only?
   Provider info plus sponsored events as secondary content? This
   is a product call, not a code call.
6. **Verify current status of the Postgres credential rotation.**
   The cleanup addendum noted it as pending at stream close. By
   the time this doc is read, it may or may not have happened.
   Confirm before any prod chat-tier work that exercises real DB
   calls from the deployed app's environment; rotate first if not
   yet done.

## 8. Refs

- Cleanup retrospective:
  `docs/maintainability/non_river_scene_cleanup.md`
- Parser-followup retrospective:
  `docs/maintainability/river_scene_event_output_decision.md`
- Confabulation eval runbook:
  `docs/confabulation-eval-runbook.md`
- Smoke test occurred 2026-05-03; chat history at
  `havasu-chat-production.up.railway.app` if Hava's chat log is
  accessible to the fresh session.
- This planning doc is the entry point. Read it first.
