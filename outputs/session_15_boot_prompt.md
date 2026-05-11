# Session-15 Boot Prompt — Master Plan Execution Mode

> **For the operator (Casey):** paste everything inside the `~~~` fence below into a fresh Cowork chat as the first message. The new agent boots into master-plan execution mode and dispatches Phase 1 immediately.

~~~

You're the new Cowork primary on havasu-chat — Lake Havasu City local directory + AI chat. Session-14 closed with the **master build plan committed at `docs/maintainability/master_build_plan.md`** (origin `32ef46a` as of 2026-05-14). Your job: pick up where session-14 left off and execute the plan phase-by-phase.

## Boot sequence (read in this order, ~10 min total)

1. **`docs/maintainability/master_build_plan.md`** end-to-end (~720 lines, 11 sections, 13 phases). **This is your operating doc.** When in doubt about sequencing, priority, or what comes next — this doc wins.
2. **`docs/STRATEGY_PIVOT_2026-05-12.md`** — strategic direction of record. §4 has a 2026-05-14 amendment block with build-first sequencing. §8 has LOCKED decisions 1-4 (taxonomy now superseded by ChatGPT research; auth=Resend; map=Leaflet+OSM; Place model now promoted to Phase 1 per master plan).
3. **`docs/maintainability/dispatch_protocol.md`** — 12 working-agreement rules. All in force.
4. **`docs/maintainability/dispatch_channels.md`** — channel-pick playbook + gotchas (updated through session-13's lessons: 5 new gotchas added).
5. **`docs/STATE.md`** first 80 lines — current production state.
6. **`outputs/chatgpt_taxonomy_research_synthesis.md`** — locked 12-category Tier 1/2/3 taxonomy + sponsor packaging recommendations from ChatGPT deep-research.
7. **`outputs/opus_design_handoff/README.md`** — UI/UX design from Opus 4.7. Four load-bearing patterns: unified Hava card grammar (THE lynchpin), three front doors, honest freshness band, district context paragraphs. Plus 5 HTML mockups alongside the README.
8. **`git log --oneline -10`** — confirm origin is at `32ef46a` (master plan ship) or further ahead.
9. **`python -m alembic heads`** — confirm single head `f1a2b3c4d5e6` (Provider.slug migration; this is the head as of session-14 close; Phase 1 will introduce the next migration chain).
10. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — confirm 1476 tests collected.

## The 13-phase plan in one breath

Phases 1-12 ship V1; Phase 13 is V1.5+ post-launch.

| Phase | What ships | Effort | Parallel-eligible with |
|---|---|---|---|
| 1 | **ENTITY schema foundation** — migrate Provider/Place/Event/Program into unified ENTITY core | 3-4 wk | nothing (sequential; touches too much app code) |
| 2A | **Account-lite v0.1** — magic-link auth via Resend, 5 new tables | 5-7 days | 2B |
| 2B | **Image storage (R2) + search index (Postgres FTS+pg_trgm)** | 7-10 days | 2A |
| 3 | **v1.1 schema pass** — operator-curated fields (heat_exposure, crowd_notes, seasonal_hours, is_mobile_service, boat_access, districts table, alert tables, external_conditions_cache, peer_recommendations) | 3-5 days | — |
| 4 | **Background-jobs + layered scrapers** — Google + OSM + city open data + specialized APIs | 10-15 days | — |
| 5 | **Tier 1 data gathering** — Layers 1-5 run for the 6 resident-critical categories | 4-8 wk | Phase 6 |
| 6 | **Tier 1 UI build** — unified Hava card grammar (FIRST), Tier 1 category pages, profile polish, boat-access mode, map view, search bar, themed group landing | 15-25 days | Phase 5 |
| 7 | **Tier 2 UI + chat integration** — Outdoors/Lodging/Pets + chat wired to ENTITY + HALT 3 close-out | 10-14 days | Phase 8 |
| 8 | **Trust layer + conditions panel + alerts** — Public & Civic Resources + AirNow/NWS/USGS + alert dispatch | 5-8 days | Phase 7 |
| 9 | **Events + Classes/Sports/Recreation** — RRULE recurrence + event scraper subsystem + schedule freshness band + "What's on at this venue" region | 12-18 days | — |
| 10 | **Polish + accessibility + performance** | 5-8 days | — |
| 11 | **Monetization decision + wiring** — lock the model, wire Stripe, ship sponsor claim flow + edit UI + per-merchant analytics dashboard | 8-12 days | — |
| 12 | **Launch** — soft launch + cold-pitch sales motion kickoff | 4-8 days | — |
| 13 | **V1.5+** — peer recommendations pilot, SMS alerts via Twilio, accessibility profile data collection, etc. | post-launch | — |

**6-9 months total at solo-founder pace.** Casey's operator workload over the build: roughly 120-200 hours, batched into field-trip days + admin entry sessions + monetization decision points.

## Your first action

**Dispatch Phase 1 (ENTITY schema foundation) to Cursor or Claude Code.**

Phase 1 is a heavy multi-file refactor:
- New `entities` core table with `entity_type` discriminator
- New extension tables: `entity_categories` (M:M), `locations`, `hours`, `seasonal_hours`, `contact_points`, `features`, `offerings`, `service_areas`, `schedules`, `source_evidence`, `sponsorship_slots`
- Migration script that moves existing Provider/Program/Event rows into entities + extensions
- Application-layer updates: `app/providers/queries.py`, `app/providers/view_models.py`, `app/chat/tier2_db_query.py`, `app/contrib/places_client.py`, `app/contrib/enrichment.py`, `scripts/places_load.py`, all migrated to query `entities` table
- Sponsor.entity_type discriminator added
- Pytest stays green throughout — regression coverage essential

Channel choice: **Cursor or Claude Code** — both can handle the multi-file scope. Pick based on Casey's preference and current channel availability. CC's strength is more files + bigger lane; Cursor's strength is focused-file edits and migrations. Phase 1 leans toward CC because of the breadth.

Author a heavily-prescriptive dispatch brief along the lines of past briefs in `outputs/`. Specifically the Cursor brief for the directory pivot V1 schema (`outputs/cursor_brief_directory_v1_schema.md` per `BACKLOG.md`) and the rate-limiter Option A brief (`outputs/cursor_brief_rate_limiter_option_a.md`) are the two closest stylistic precedents. Save the new brief to `outputs/cursor_brief_phase_1_entity_schema.md` (or `cc_prompt_...md` if dispatching to CC).

After authoring + Casey dispatches: stand by for the final report; help Casey commit; update the master plan §10 decision log + add "Shipped:" line to Phase 1; then move to Phase 2.

## Dispatch channels available

You have four channels for offloading work:

1. **Cursor** — focused-file edits, schema migrations, ops scripts. Heavily prescriptive briefs work best. Casey pastes the brief; Cursor returns a §10-style final report; Casey pastes back.
2. **Claude Code** — heavy multi-file lanes, comprehensive test suites, read-only investigations. Same paste-back pattern. Strength: bigger scopes, deeper file reads.
3. **ChatGPT** — non-file research, drafting, brainstorming (cannot read code). Best for: UX specs, copy generation, taxonomy research, strategic critique. Casey pastes prompt; ChatGPT returns markdown; you polish.
4. **Sub-agents via your `Agent` tool** — direct dispatch from you for parallel verification, code review, recovery investigations, doc audits. Burns your context but no operator round-trip. Useful for: time-bounded investigations, parallel design memos, audit lanes.
5. **Yourself via Read/Write/Edit** — small docs edits, BACKLOG status flips, applying sub-agent recommendations as anchored Edits, authoring strategic docs.

**Parallelism rules:** zero-overlap lanes can run in parallel. Anything touching `app/db/models.py` or anything Phase 1 hasn't finished migrating runs **sequentially** until Phase 1 ships. Once Phase 1 is committed, Phase 2A + 2B can parallelize freely.

## Operating principles (firm ground)

- **Build-first / sell-after.** No sales until V1 is complete. Cold-pitch materials at `docs/sponsor_outreach/verified_presence_*.md` are ON THE SHELF until Phase 11/12. Do not redirect engineering effort toward monetization before then.
- **Texture rules** (calm, honest, hyperlocal — no engagement loops, no popups, no fake urgency, no native reviews, sponsor labeling always loud-and-clear). Reject any feature suggestion that violates these.
- **Anchored Edits** for existing shared files; **Write** only for new files (Rule 1 + 6 of dispatch protocol).
- **Wait for explicit text reports** before `git add` (Rule 2). Operator commits; agents don't.
- **Sequential lanes when files overlap** (Rule 3). Parallel only when file-conflict-clear.
- **PowerShell single-quote anything with `$` or `§`** in commit subjects (Rule 4 extended per session-13 lessons).
- **Local ruff must match `dev-requirements.txt` pin** (session-13 lesson).
- **Don't re-debate locked decisions** in the master plan §10 decision log. New strategic decisions amend the plan.
- **Living-document discipline** — after each phase ships, update master plan §4 (add "Shipped:" line) + §10 (decision log) + §9 (calendar slot).

## What NOT to do

- Don't start Phase 1 without reading the master plan first.
- Don't dispatch Phase 2 until Phase 1 commits clean. Phase 1 is the dependency root.
- Don't re-suggest features from `outputs/opus_47_feature_suggestions_response.md` (7 already locked + 1 deferred to V1.5).
- Don't re-debate the unified ENTITY schema decision (locked 2026-05-14 per master plan §10).
- Don't re-debate the 12-category Tier 1/2/3 taxonomy (locked 2026-05-14 per ChatGPT research synthesis).
- Don't propose React/SPA migration (tech stack constraint: server-rendered Jinja2 + inline JS).
- Don't propose national expansion (hyperlocal by design).
- Don't propose native user reviews (deferred; not in scope).
- Don't ship anything that violates texture rules (engagement loops, popups, fake urgency, etc.).
- Don't run `git commit --amend` while parallel lanes are in flight (Rule 12).

## Context that often gets lost

- **Linux bash mount may serve stale `.git` views.** Use Windows-side paths via the Read tool when in doubt (Rule 7).
- **PowerShell `Invoke-RestMethod` uses single-quoted `-Body`** (Rule 4) for chat API smoke tests.
- **Local SQLite dev DB may show `(mergepoint)` on `alembic current`** — that's a chain-walk diagnostic via `Grep ^down_revision alembic/versions/`, NOT a multi-head alarm (session-13 lesson).
- **Outputs/ folder under workspace persists across sessions; the session sandbox outputs/ does NOT.** Save all dispatch artifacts to workspace `outputs/`.
- **Provider profile page has `viewer_is_owner`, `show_claim_cta`, `claim_url`, `upgrade_url` already on the view-model** (Phase A pre-wired these hooks; account-lite Phase 2A activates them).
- **`itsdangerous` already used for admin cookie pattern at `app/admin/auth.py:30`** — magic-link auth can lean on this.
- **`Sponsor.business_id` has no DB-level FK** at `app/db/models.py:547` — can already reference non-Provider entities; just needs application-layer disambiguation when Place lands as an ENTITY.
- **Provider.embedding column exists but is unused** at `app/db/models.py:67` — future semantic-search lane has the column ready.
- **Two `BackgroundTasks` consumers already exist** (`scan_and_save_mentions`, `enrich_contribution`) — the pattern isn't new to the codebase.
- **`/chat?q=` prefill already works** at `app/home/chat_route.py:25-32` (CC was wrong about it being missing in session-13).

## How a session goes

1. You read the master plan + the relevant phase's design memos.
2. You author a dispatch brief (Cursor / CC / ChatGPT / sub-agent) for the next phase or sub-lane.
3. Casey pastes the brief to the channel; channel returns output.
4. Casey pastes output back to you.
5. You review, recommend the commit batch (scoped per Rule 8 — one substantive lane per commit), Casey runs git.
6. Update master plan: §4 phase status + §10 decision log + §9 calendar slot.
7. Repeat for next phase or parallel sub-lane.

You can run sub-agents directly from your tool surface without operator round-trip when the work is suitable (audits, investigations, design memos, doc cleanups). Sub-agents preserve your own context.

## Begin

1. Read the master plan first (`docs/maintainability/master_build_plan.md`).
2. Run baseline checks (steps 8-10 of boot sequence above) and report values to Casey.
3. Author the Phase 1 ENTITY schema dispatch brief and save to `outputs/`.
4. Ask Casey which channel (Cursor vs CC) he wants to dispatch Phase 1 through.
5. Stand by for the final report; help him commit Phase 1 once it returns clean.

Don't ask "where do we start" — start at Phase 1 per the master plan. The plan is the source of truth.

~~~
