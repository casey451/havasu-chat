# Cursor Dispatch Prompt — Phase 9b (standalone paste-ready; post-9a)

> **DISPATCH-READY 2026-05-23 v11.** Phase 9a SHIPPED at `eb406e8` (alembic head `a9b0c1d2e3f4` SINGLE on origin/main; pytest baseline ~2356 + 3 skipped; CI #414 green on `99e9b57`). Phase 9b ships the scraper subsystem + Classes/Sports/Recreation chips + Things-to-Do themed-group bundle + interleaving + chat event-intent extension. ZERO migrations in 9b (head stays at `a9b0c1d2e3f4` throughout).
>
> **Why a standalone 9b prompt:** the original combined wrapper at `outputs/cursor_dispatch_prompt_phase_9.md` covers BOTH 9a + 9b in one ~780-line body with a HALT boundary; 9a has already shipped, so a Cursor session pasting the full combined body would re-do work. This shorter prompt routes Cursor to the 9b-only portion of the combined wrapper + the design doc, with proper post-9a context.
>
> **Operator prereqs (per the combined wrapper §"Operator prereq status"):** 5 prereqs to confirm before paste:
> 1. Event source URLs RESOLVED (5 sources: Chamber GrowthZone microdata + Go Lake Havasu Simpleview JSON-LD + RiverScene WordPress RSS + LHC Library Trumba iCal + LHC City CivicPlus RSS/iCal). Per `outputs/phase_9_event_source_research.md`.
> 2. Robots.txt audit per source — confirm scrape permitted.
> 3. Schema.org microdata presence check per source.
> 4. Structured feed preference (iCal/RSS/JSON over HTML scrape where available).
> 5. Per-source scrape cadence locked (default: daily for Chamber + Go Lake Havasu + RiverScene; weekly for LHC library + LHC city).
>
> If any prereq is unresolved, HALT 9b dispatch and finish prereqs first.

---

```
Resume havasu-chat for Phase 9b dispatch.

REQUIRED READING (in order, before any action):
1. outputs/cursor_dispatch_prompt_phase_9.md from line ~259 ("PHASE 9b SCOPE") to end. The
   combined wrapper covers 9a + 9b; 9a SHIPPED at eb406e8 by Cowork primary 2026-05-23 -- skip
   the 9a steps. Phase 9b steps are (k) through (v) in the wrapper body.
2. outputs/phase_9_architecture_design.md sec5-sec13 + sec16-sec19 (scraper subsystem +
   dedup + themed-group interleaving + event-card ranking + chat extension + success criteria
   + effort estimate + sequencing).
3. outputs/phase_9_event_source_research.md (5-source recon: Chamber + Go Lake Havasu +
   RiverScene + LHC Library + LHC City; per-source format + cadence + scrape permission).
4. docs/maintainability/master_build_plan.md sec4 Phase 9 (lines 427-448) for canonical
   scope + acceptance gates; sec7 risk register #6; sec8 OQ #12.

PRE-DISPATCH CHECKS (run BEFORE any code changes):
- python -m alembic current  -> expect a9b0c1d2e3f4 (Phase 9a head)
- python -m alembic heads    -> expect SINGLE a9b0c1d2e3f4
- git rev-parse HEAD         -> expect 99e9b57 or later (Phase 9a + walkthrough docs landed)
- pytest -q --collect-only | tail -3  -> expect 2356+ tests
If alembic heads returns multiple heads, HALT and report (per gotcha #18).
If pytest count differs substantially from 2356, report observed value (per session-2026-05-19
lesson #6 -- do NOT copy dispatch-body-claimed value).

PHASE 9b SCOPE -- per outputs/cursor_dispatch_prompt_phase_9.md steps (k) through (v):
(k) app/events/scrapers/{__init__,base,chamber,go_lake_havasu,river_scene_v2,lhc_library,
    lhc_parks_rec}.py -- EventIngestClient base + 5 source adapters
(l) app/events/dedup.py -- multi-source dedup + venue resolution + merge semantics
(m) scripts/scrape_events.py -- CLI entrypoint with SOURCE_REGISTRY + --source / --all /
    --dry-run flags
(n) Extend app/contrib/approval_service.py with EVENT_AUTO_APPROVE_SOURCES allowlist
(o) Classes/Sports/Recreation category page chip filters + age-band + drop-in vs registration
(p) Things-to-Do themed-group registry entry (cat-2 + cat-7 + cat-9 bundle)
(q) Themed-group interleaving extension (events alongside entities; event-share cap 40%)
(r) compute_event_card_rank() in app/core/ranking.py
(s) _cap_event_share() helper in app/core/ranking.py
(t) Chat event-intent extension in app/chat/tier2_handler.py
(u) Phase 9b tests -- 7+ new test files per the combined wrapper's step (u) list

LOCKED DECISIONS (per design doc + combined wrapper):
- Multi-source dedup: (venue_entity_id, start_datetime, normalized_title) tuple; rapidfuzz
  token_sort_ratio threshold 85; 30-min datetime proximity window.
- Auto-approve allowlist: chamber + go_lake_havasu + river_scene; LHC city sources stay
  manual-review V1.
- Things-to-Do bundle: 3-category (cat-2 + cat-7 + cat-9).
- Themed-group event-share cap: 0.40 (env-tunable via THEMED_GROUP_EVENT_CAP_PCT).
- Per-source cadence: daily for Chamber + Go Lake Havasu + RiverScene; weekly for LHC
  library + city.

DO NOT (per master plan sec4 Phase 9 + design doc sec14):
- Don't ship a migration in 9b (head stays at a9b0c1d2e3f4).
- Don't ship Twilio SMS event reminders (V1.5).
- Don't ship Eventbrite/Meetup/Facebook Events API integration (V2).
- Don't ship event_traffic alert wiring (Phase 9.5).
- Don't ship operator booking/ticketing (V2+).
- Don't ship per-event sponsorship (Phase 11.5/V2).
- Don't ship event detail page route (V1.5).
- Don't ship calendar export (V1.5).
- Don't ship user RSVP tracking (V2+).
- Don't ship row-expansion materialization for recurrence (V1.5/Phase 13).
- Don't ship multi-day event detail expansion (V1.5).
- Don't ship auto-cancellation when source removes event (operator-only cancel in V1).
- Don't ship capacity rendering with manufactured data (master plan sec8 OQ #12 honesty rule).
- Don't add new Python dependencies BEYOND python-dateutil + feedparser (verify both in
  deps; rapidfuzz already in deps from Phase 5).
- Don't hardcode alembic head literals in test code (session-2026-05-19 lesson #4).
- Don't bash heredoc commit messages (session-2026-05-19 lesson #1).

HALT POSTURE:
- After all of (k)-(v) lands + pytest green + ruff clean + alembic head still a9b0c1d2e3f4,
  HALT and report per sec12 of the original wrapper body.
- Cowork primary will audit your sec12 + spot-check the new scrapers + commit + push the
  ship in a single feat commit. Do NOT commit or push from Cursor.
- If you encounter any of the prereqs not being met, HALT and report.
- If alembic heads returns multiple heads at any point, HALT.

Report per sec12 of the combined wrapper at end of work.
```

---

*Authored 2026-05-23 v11 close as paste-ready Phase 9b dispatch standalone. Length: ~75 lines
of prompt body inside the fenced code block. Operator copies the entire fenced block (between
the triple-backtick lines) and pastes into a fresh Cursor chat. Wrapper file at
outputs/cursor_dispatch_prompt_phase_9.md remains the authoritative scope spec for both 9a
(shipped) + 9b (this dispatch).*
