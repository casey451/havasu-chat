# Cursor Dispatch Prompt — Phase 9 (Events as ENTITY + RRULE recurrence + 5-source event scraper + Classes/Sports/Recreation + Things-to-Do themed group + "What's on at this venue" region; recommended 9a/9b split)

> **SHA-PATCH APPLIED 2026-05-22 — DISPATCH-READY (Phase 9a paste-ready in a fresh Cursor chat).** All four SHA slots now filled with concrete values from the post-Phase-8a + post-Phase-6.5 + post-Phase-7.5 + post-lhcaz-rewrite state: Phase 8a HEAD-SHA placeholder → **`8a905c6`** (Phase 8a SHIPPED at Railway v1.3.0 — conditions + alerts subsystem); Phase 8a alembic-head placeholder → **`d8e9f0a1b2c3`** (additive migration extended `external_conditions_cache` + `alerts_dispatched` enum); Phase 6.5 HEAD-SHA placeholder → **`bdca0bd`** (homepage rebuild + 8 themed-group tiles + conditions strip placeholder + venue-events region hook on `provider_profile.html` — PHASE 6 LANE COMPLETE; anchor edit path in step (f) is now active rather than deferred); Phase 7.5 HEAD-SHA placeholder → **`b701759`** (HALT 3 validator 30/30 PASS + `FEATURE_FLAG_DISCLOSURE_RENDERER` flip executed at `d7179bc` 2026-05-22, flag is **`true`** on prod env vars). Current origin/main HEAD is `6070726` (well past all prereqs); pytest baseline at HEAD is ~2290 + 3 skipped; alembic head is `d8e9f0a1b2c3` SINGLE. The `<<<SKIP_N>>>` + `<<<SKIPLAST_N>>>` clipboard-pipeline offsets remain TBD by design — operator computes them at paste time from the actual line counts in this wrapper. Per the §9b research note in the design doc, operator should confirm scrapers cadence (3 daily + 2 weekly) and Things-to-Do bundle (cat-2 + cat-7 + cat-9) before Phase 9b paste. Historical dispatch-not-yet-ready framing preserved in the next paragraph for audit.
>
> Paste-into-Cursor prompt for Phase 9 per master plan §4 Phase 9 (lines 427-448) + `outputs/phase_9_architecture_design.md` (1620-line Plan-agent ADR-level design). Phase 9 lands the schedule-heavy expansion the master plan §4 deferred from Phase 5 — Events as a first-class ENTITY surface with RRULE-based recurrence, a 5-source event scraper subsystem reusing the Phase 4 `BaseIngestClient` envelope, multi-source dedup with operator-curated vs scraper-sourced merge semantics, integrated themed-group streams (Things-to-Do landing), Classes/Sports/Recreation category page with recurring schedule + age band + drop-in vs registration filters, and the "What's on at this venue" region filling the Phase 6.5-shipped anchor on `provider_profile.html`. Plus the event-card render through the unified Hava card grammar (status line "Tonight at 6:00pm" lake-blue per Phase 6.1).
>
> **HISTORICAL FRAMING (preserved for audit; SHA-patch has since been applied — see top header). DISPATCH-NOT-YET-READY — SHA-patch slots empty until Phase 8a ships.** Phase 8a SHIP SHA `8a905c6` + alembic head `d8e9f0a1b2c3` BOTH need filling before paste. Phase 8a is currently scheduled to dispatch post-Phase-7.5 (which itself sits behind Phase 7's HALT 3 polish lane). Phase 9 dispatches AFTER Phase 8a SHIPS — the dispatch chain is sequential per the 2026-05-20 alembic-collision gotcha (`outputs/dispatch_channels_alembic_collision_gotcha_draft.md`).
>
> **Phase 8a ship caveats Phase 9 should be aware of (verify at SHA-patch time):**
> - Phase 8a may or may not ship a new alembic migration. Per Phase 8 design doc §2, `external_conditions_cache` + `alert_subscriptions` + `alerts_dispatched` tables already exist from Phase 3.1; Phase 8a only ships a migration if additive columns are needed. **Phase 9 SHA-patch step:** observe the Phase 8a ship's actual alembic head and patch `d8e9f0a1b2c3` accordingly (may equal `c9d0e1f2a3b4` if no migration shipped, or a new revision SHA if it did).
> - Phase 8a swaps `STUB_CURRENT_TEMPERATURE_F` → `read_current_temperature_f()` at `app/core/ranking.py`. Phase 9's new `compute_event_card_rank()` helper reuses this swapped function for the heat-bias on events. Verify the swap is in place before Phase 9 dispatches; if Phase 8a's swap kept the stub as fallback, Phase 9's event-card heat-bias inherits the same fallback transparently.
> - Phase 8a also extends `app/alerts/` for heat/AQI/lake_hazard alerts. **Phase 9 does NOT touch the alerts module.** The `event_traffic` alert type (stubbed in Phase 8 §11) is wired in Phase 9.5 against the Events surface Phase 9 lands — not in Phase 9 scope.
>
> **Phase 7.5 ship caveats (if it shipped before Phase 9 dispatches):**
> - Phase 7.5 closes HALT 3 validator failures + flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true`. Phase 9's chat extensions (§13 in design doc — event-intent detection in tier-2) write through the same disclosure renderer pipeline. The chat extensions are additive — they don't change the renderer; they add a new tier-2 query branch for `events_in_window`. The flag flip is unchanged by Phase 9.
> - If Phase 7.5 has NOT shipped at Phase 9 dispatch time, that's fine — Phase 9's chat changes work with the flag either way (the disclosure renderer is invariant to whether HALT 3 polish landed).
>
> **Phase 6.5 anchor coordination (per the prompt brief):**
> - If Phase 6.5 (homepage rebuild + 8 themed group tiles + `<!-- venue-events-region-anchor -->` empty hook in `provider_profile.html`) ships BEFORE Phase 9 — Phase 9 fills the venue-events region per design doc §11.1 (replaces `<!-- venue-events-region-anchor -->` with `{% include 'components/venue_events_region.html' %}`).
> - If Phase 6.5 ships AFTER Phase 9 — Phase 9 still ships `venue_events_region.html` partial + the route query path, but the include-line in `provider_profile.html` is deferred. Phase 6.5 then includes the partial when it wires the anchor. **Recommended posture: Phase 6.5 ships before Phase 9** — the anchor is small and Phase 6.5 is a homepage-heavy wrapper that benefits from being on the build trunk before Phase 9's schedule-heavy expansion.
> - Verify Phase 6.5 ship status at Phase 9 SHA-patch time. If 6.5 has NOT shipped, swap the §11.1 anchored-edit step in the dispatch body for "ship the partial only; defer anchor wiring to Phase 6.5 lane".
>
> **Gating dependencies:** Phase 6.1 SHIPPED (`fd16e7a`) + 6.2 (`3948add`) + 6.3 (`5ebee46`) + 6.4 (`96c915d`) + Phase 5 multi-phase data-population COMPLETE at `dcf3dd4` (1,314 active entities) + Phase 7 SHIPPED at `0a305e0` + Phase 7.5 SHIPPED (assumed, post-`b701759` if applicable — Phase 9 doesn't require it) + Phase 8a SHIPPED at `8a905c6` + Phase 6.5 SHIPPED at `bdca0bd` (recommended — see anchor coordination above). **Phase 9 consumes:** Phase 4 background-jobs framework (`with_retry`, Outbox, source-isolation pattern); Phase 4 `BaseIngestClient` + `EntityPayload` at `app/contrib/ingest_base.py` (Phase 9 extends to `EventIngestClient` + `EventPayload`); Phase 4.x existing RiverScene event-scraper pattern at `app/contrib/river_scene.py` + `app/contrib/river_scene_pull.py` (Phase 9 wraps in thin adapter `app/events/scrapers/river_scene_v2.py`); Phase 5 manual-recovery + sustainability-layer pattern (`field_history` table + per-field provenance); Phase 6.1 `_event_status_line_for_card` at `app/providers/queries.py:666-696` (Phase 9 extends with occurrence-date parameter); Phase 6.3 `compute_card_rank` + heat-bias constants (Phase 9 mirrors as `compute_event_card_rank`); Phase 6.4 themed-group landing pattern at `app/groups/themed_groups.py` (Phase 9 adds `things-to-do-group` entry); Phase 6.4 themed-group routes at `app/api/routes/themed_groups.py` (Phase 9 extends the stream-builder to interleave events with entities); Phase 6.5 `<!-- venue-events-region-anchor -->` empty hook on `provider_profile.html`; Phase 7 chat tier-2/tier-3 ENTITY wiring (Phase 9 adds event-intent detection branch); Phase 8a `read_current_temperature_f()` (Phase 9's event-card heat-bias reuses).
>
> **Recommended sub-phase split — Phase 9a + Phase 9b.** Per design doc §1 + §17 effort table:
> - **Phase 9a — Event ENTITY + RRULE foundation + Events category + venue-events region** (~7-10 days dispatch). File scope = additive alembic migration + `app/events/` module (`recurrence.py` + `queries.py` + `view_model.py`) + `app/providers/queries.py` extensions + `app/api/routes/category_pages.py` events-config extension + `app/templates/components/venue_events_region.html` + admin event-edit UI + `scripts/expire_past_events.py` + tests/test_phase9_events_* + tests/test_phase9_recurrence.py + tests/test_phase9_venue_events_region.py.
> - **Phase 9b — Scraper subsystem + Classes/Sports + Things-to-Do group + interleaving** (~5-8 days dispatch). File scope = `app/events/scrapers/` (5 source modules + base.py + dedup.py) + `scripts/scrape_events.py` + `/category/classes-sports-recreation` chip extensions + `app/groups/themed_groups.py` `things-to-do-group` entry + themed-group interleaving extension + event-share cap + tests/test_phase9_scraper_*.py + tests/test_phase9_dedup.py + tests/test_phase9_things_to_do_*.py + tests/test_phase9_classes_sports_recreation.py.
>
> Combined Phase 9 = ~12-18 days dispatch per master plan §4 Phase 9 L-estimate. **This wrapper covers Phase 9a + Phase 9b in a single dispatch body with HALT between them.** Operator decides at HALT whether to commit 9a + dispatch 9b in a fresh session OR continue inline. Recommended: HALT + fresh session for 9b — RRULE storage shape is the load-bearing decision; review Phase 9a's actual recurrence-expansion query timings before authorizing 9b's bulk scraper writes.
>
> **Parallel-with caveat — Phase 8b (cat-13 expansion) is parallel-eligible with Phase 9b.** File-scope disjoint per design doc §1 + Phase 8 design doc §10.4 split. Phase 8b touches cat-13 Public & Civic Resources data layer; Phase 9b touches `app/events/` + themed-group registry. **Phase 8b is NOT a Phase 9 prereq** — they're independent. If operator dispatches them in parallel, both will chain off the same alembic head (Phase 8a's) — verify SINGLE head per the 2026-05-20 collision gotcha; sequence if alembic-collision risk surfaces.
>
> **Operator prereq status (per `outputs/phase_9_operator_prereq_checklist.md` — referenced in design doc §5 + §18 but separate doc not yet shipped at this wrapper's authoring time; should exist before Phase 9b dispatch):** 5 prereqs to RESOLVE before Phase 9b paste (Phase 9a has no operator prereqs):
> 1. **5 event-source URLs + scrape-formats RESOLVED 2026-05-20 via sub-agent research at `outputs/phase_9_event_source_research.md`.** All 5 sources GREEN (usable public feeds; no auth). Canonical surfaces: **Chamber** (`business.havasuchamber.com/community-event-calendar/Search` GrowthZone schema.org microdata, 70 events). **Go Lake Havasu** (`golakehavasu.com/events/<slug>/` Simpleview JSON-LD `@type:Event`). **RiverScene** (`riverscenemagazine.com/events/feed/` WordPress RSS — existing `app/contrib/river_scene.py` already does sitemap+detail HTML parsing; just needs a thin `EventIngestClient` adapter, ~2h). **LHC Library** (NOT a city resource — it's Mohave County Library District via Trumba: `https://www.trumba.com/calendars/havasu.ics` — cleanest data shape of all 5; iCal/JSON/RSS/XML). **LHC City** (CivicPlus NOT Sitefinity: `https://www.lhcaz.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml` RSS + `https://www.lhcaz.gov/common/modules/iCalendar/iCalendar.aspx?catID=23&feed=calendar` iCal — **NOTE: meeting-focused (P&Z, City Council, Parks-Rec Advisory Board) NOT rec-activity content**; rec activities already in ENTITY via Phase 5.7 WebTrac + aquatic schedule scrapers; reframe source #5 from "parks-rec calendar" to "public meetings calendar"). **Cross-cutting finding:** all 5 sources expand recurring events into individual instances; NONE publish raw RRULEs at scrape-time — `app/core/event_recurrence.py` from design doc §6 is needed for OPERATOR-CURATED recurring events but NOT for scrape-ingest. **Recommended dispatch order:** RiverScene (2h adapter) → LHC Library (2-3h iCal) → LHC City (2-3h iCal) → Chamber (3-4h microdata HTML) → Go Lake Havasu (3-4h JSON-LD HTML). Total 12-16h scraper effort within design doc §11 budget.
> 2. **Robots.txt audit per source** — confirm scrape permitted; identify any nofollow/noindex on event pages.
> 3. **Schema.org microdata presence check** — prefer microdata-extraction over CSS-selector when present (most modern WordPress event plugins emit it).
> 4. **Structured feed preference** — if any source publishes iCal / RSS / JSON feed, prefer over HTML scrape.
> 5. **Per-source scrape cadence locked** — design doc §5.1 default: daily for Chamber + Go Lake Havasu + RiverScene; weekly for LHC library + parks-rec. Operator confirms or tunes.
>
> If any prereq is unresolved at Phase 9b dispatch time, **HALT 9b and finish prereqs first**. Phase 9a has no operator prereqs and can ship without them.
>
> **Operator decision-lock status:** the 6 Phase 9-relevant decisions are LOCKED per the architectural design (`outputs/phase_9_architecture_design.md`):
>
> 1. **RRULE expansion strategy — at-query-time, NOT row-expansion.** Per design doc §3.1. 1 row per logical event; `rrule` + `exdate` + `rdate` columns hold the rule; expansion via `dateutil.rrule` at query time. Forward-compatible with materialization optimization in Phase 13 if profiling proves need. **Hybrid** = the design-doc term for "rule storage + finite-horizon expansion at query time"; lock this.
> 2. **Event lifecycle states — 4-state CHECK constraint `('draft', 'live', 'cancelled', 'expired')`.** Per design doc §2.3. Additive CHECK on `events.status` column (currently shipped without CHECK from Phase 1A). Plus new `cancellation_reason TEXT NULL` column for operator-supplied cancel reason (rendered on detail page; terse "Cancelled" on card). Plus background job `scripts/expire_past_events.py` daily sweep transitioning live → expired 7 days past event date.
> 3. **Multi-source dedup key — `(venue_entity_id, start_datetime, normalized_title)` fuzzy tuple.** Per design doc §6.2. Refinement: 30-min datetime proximity window + token_sort_ratio threshold 85 (rapidfuzz library). Same-venue same-day same-hour with ≥85 title similarity = merge.
> 4. **Capacity-null default — render nothing when `capacity IS NULL`.** Per master plan §8 OQ #12 + design doc §4. Schema columns ship (`capacity` + `capacity_source`) but render branch returns None when NULL — honest pattern. V1 ships with zero capacity rendering; V2 lights it up when Eventbrite-class data lands.
> 5. **Events category-page sort default — chronological (next occurrence date ascending).** Per design doc §12.3. Alternatives `closest_now` + `featured` available via sort dropdown; chronological is the default.
> 6. **Things-to-Do themed group cuts — cat-2 (Events) + cat-7 (Outdoors-parks-trails) + cat-9 (Classes/Sports/Recreation).** Per design doc §8.2 recommended bundle. **3-category cut.** Alternative 2-category cut (drop cat-9) would create lopsided "events + parks only" feel — recommend 3-category. Operator confirms at dispatch time; the wrapper defaults to 3 per design doc.
>
> Plus 2 supplementary locks:
>
> 7. **Per-source scrape cadence — daily for Chamber + Go Lake Havasu + RiverScene; weekly for LHC library + parks-rec.** Per design doc §5.1. Operator-tunable post-ship via Railway service env config.
> 8. **Migration shape — additive 8-column migration + status CHECK + 4 new indexes.** Per design doc §2.2. Columns: `rrule String(255) NULL` + `rdate JSON NULL` + `exdate JSON NULL` + `scraped_at TZAwareDateTime NULL` + `cancellation_reason Text NULL` + `operator_override Boolean DEFAULT false NOT NULL` + `capacity Integer NULL` + `capacity_source String(64) NULL`. Indexes: `ix_events_status_date` + `ix_events_is_recurring_date` + `ix_events_provider_id_date` + `ix_events_scraped_at`. CHECK: `status IN ('draft', 'live', 'cancelled', 'expired')`. Plus `EVENT_AUTO_APPROVE_SOURCES = {'chamber', 'go_lake_havasu', 'river_scene'}` env-tunable allowlist (default in code; override via env var for ops flexibility).
>
> **Author note:** authored at the post-Phase-7-close-out Cowork primary session (2026-05-20) against the design-pre-positioned `outputs/phase_9_architecture_design.md`. Two SHA-patch slots — `8a905c6` + `d8e9f0a1b2c3` — fill at post-Phase-8a-ship time. Plus optional `bdca0bd` if Phase 6.5 shipped first + `b701759` for Phase 7.5 reference. The 1620-line `outputs/phase_9_architecture_design.md` is the authoritative scope spec. Per the master plan §4 Phase 9 — "Events as ENTITY type fully wired (already in schema from Phase 1; this phase wires the UX)."
>
> **Clipboard pipeline** (PowerShell 5.1 truncates large payloads; uses Notepad as synchronous router per session-2026-05-19 lesson #3; offsets TBD until authored — recompute post-SHA-patch since authoring may shift line counts):
> ```powershell
> # Verify offsets after SHA-patch by counting fence positions:
> # python3 -c "import sys; lines = open('outputs/cursor_dispatch_prompt_phase_9.md').readlines(); fences = [i+1 for i, ln in enumerate(lines) if ln.strip() in ('```', '````')]; print('Fences at lines:', fences, 'Total:', len(lines))"
> Get-Content outputs\cursor_dispatch_prompt_phase_9.md | Select-Object -Skip <<<SKIP_N>>> | Select-Object -SkipLast <<<SKIPLAST_N>>> | Out-File -FilePath $env:TEMP\phase_9_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_9_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```
>
> Verify clipboard size via temp-file Length (per session-2026-05-19 lesson #2):
> ```powershell
> Get-Clipboard | Out-File -FilePath $env:TEMP\clip_check.tmp -Encoding utf8; (Get-Item $env:TEMP\clip_check.tmp).Length; Remove-Item $env:TEMP\clip_check.tmp
> ```
> Expected size: ~26000–32000 bytes. <1000 bytes = truncation; redo Notepad.

---

````
Read outputs/phase_9_architecture_design.md end-to-end (1620 lines, Plan-
agent ADR-level design; sec1 scope split + 9a/9b recommendation, sec2
schema additions + status CHECK + indexes, sec3 RRULE expansion strategy
+ at-query-time vs row-expansion decision + recurrence helper module,
sec4 capacity-null default + honesty rule, sec5 5-source scraper sub-
system + per-source cadence + file layout + EventIngestClient base,
sec6 multi-source dedup + venue resolution + merge semantics, sec7
operator-curated vs scraper-sourced + operator_override flag + edit UI,
sec8 Things-to-Do themed group + category bundle, sec9 integrated
stream interleaving + event-share cap, sec10 event-specific freshness
band + card grammar, sec11 venue-events region + caching, sec12
category page chip filters + sort dropdowns + pagination, sec13 chat
integration + tier-2 event intent + tier-3 LLM preamble, sec14 NOT in
Phase 9 explicit non-scope, sec15 risk register top-5, sec16 success
criteria across 6 surfaces, sec17 effort estimate 17 days dispatch,
sec18 sequencing + dispatch chain + commit batching, sec19 summary).

Also read docs/maintainability/master_build_plan.md sec4 Phase 9 (lines
427-448) for canonical scope + acceptance gates. Read sec7 risk register
entry #6 (schedule-heavy expansion refresh burden — Phase 9 IS the
refresh burden phase). Read sec8 OQ #12 (capacity display — honest-or-
omit rule that locks capacity=null V1 default).

Phase 6.1 SHIPPED on origin at fd16e7a (unified Hava card grammar).
Phase 6.2 SHIPPED at 3948add (category landing template). Phase 6.3
SHIPPED at 5ebee46 (breadth pass + district chip + ranking + seasonal
hours). Phase 6.4 SHIPPED at 96c915d (Leaflet+OSM map + boat-access via
preferred_mode reuse + 4 themed group landing pages + search bar). Phase 5
multi-phase data-population COMPLETE at 5.11 (1,314 active entities).
Phase 7 SHIPPED at 0a305e0 (chat ENTITY wiring + boat-mode + conditions-
awareness via STUB + HALT 3 + cross-entity + snowbird-return view).
Phase 8a SHIPPED at 8a905c6 (conditions panel + alerts +
chat live-conditions wiring; alembic head d8e9f0a1b2c3).
Phase 6.5 ship status: bdca0bd if shipped first (fills
homepage rebuild + 8 themed group tiles + venue-events-region-anchor on
provider_profile.html). Phase 7.5 ship status: b701759
if shipped (HALT 3 polish lane + FEATURE_FLAG_DISCLOSURE_RENDERER=true
flip).

Pytest baseline going in is post-Phase-8a. Verify per python -m pytest
--collect-only -q | tail -3 BEFORE starting work. Likely range 2220-
2330 (Phase 7 baseline 2135 + Phase 8a ~+80-130 net-new + any Phase 7.5
+ 6.5 deltas). Alembic head is d8e9f0a1b2c3. Verify per
python -m alembic current BEFORE starting work and REPORT THE OBSERVED
VALUE (do NOT copy dispatch-body-claimed value — session-2026-05-19
lesson #6).

CRITICAL — RUN BOTH:
- python -m alembic current   (returns SINGLE head)
- python -m alembic heads     (returns ALL heads; should be EXACTLY ONE)
If python -m alembic heads returns MULTIPLE heads, you have a multi-head
state. HALT immediately and report. This is the alembic-collision
pattern from the 2026-05-20 Phase 6.4/Phase 7 parallel-session collision
— see outputs/dispatch_channels_alembic_collision_gotcha_draft.md for
context. Do NOT proceed with Phase 9 against a multi-head DB. Phase 9a
ships an additive 8-column migration; Phase 9b ships NO migration. If
Phase 8b (cat-13 expansion) is dispatching in parallel against the same
Phase 8a head, alembic-collision risk applies — verify SINGLE head at
Phase 9a start AND at Phase 9a end.

Ship Phase 9 in two sub-lanes per outputs/phase_9_architecture_design.md
sec1 split. Phase 9a + Phase 9b in this dispatch body; HALT at the
sec18.4 9a/9b boundary for operator commit + fresh-session decision on
9b.

PHASE 9a SCOPE (Event ENTITY + RRULE foundation + Events category +
venue-events region; ~7-10 days dispatch):

(a) Additive alembic migration chaining off d8e9f0a1b2c3.
    Per design doc sec2.2: 8 columns added to events table (rrule + rdate
    + exdate + scraped_at + cancellation_reason + operator_override +
    capacity + capacity_source) + 4 new indexes (ix_events_status_date +
    ix_events_is_recurring_date + ix_events_provider_id_date + ix_events_
    scraped_at) + status CHECK constraint (status IN ('draft', 'live',
    'cancelled', 'expired')). Upgrade + downgrade tested in
    tests/test_phase9_events_schema.py with DYNAMIC head capture
    (script.get_current_head() + script.get_revision(head_rev).down_
    revision) per session-2026-05-19 lesson #4. NEVER hardcode head
    literals.

(b) New app/events/ module with:
    - app/events/__init__.py
    - app/events/recurrence.py — dateutil.rrule wrapper; expand_event()
      helper takes Event + window_start + window_end + cap=100 safety
      ceiling; returns list[date] of occurrences; handles EXDATE + RDATE;
      raises ValueError on cap-exceeded. occurrences_in_window() multi-
      event variant returning [(event, occurrence_date)] sorted by (date,
      start_time, normalized_title). Per design doc sec3.2.
    - app/events/queries.py — events_in_window(db, window_start, window_
      end, category_slug=None, limit=50) two-pass strategy: SQL pre-
      filter narrows to candidate events (is_recurring=False + date IN
      window OR is_recurring=True); Python expansion produces flat
      (event, date) tuples. Per design doc sec3.4.
    - app/events/view_model.py — event-specific view-model extensions
      hooking into build_card_view_model.

(c) Anchored edit on app/providers/queries.py:
    - Add derive_event_freshness_band(event, now) — tighter decay curve
      (EVENT_FRESHNESS_GREEN_DAYS=7 + EVENT_FRESHNESS_AMBER_DAYS=21)
      reading from event.scraped_at; falls back to entity.updated_at
      when NULL. Per design doc sec10.1.
    - Add build_card_view_model_for_event_occurrence(db, event_id,
      occurrence_date, now=None) — parameterized variant supporting
      recurring events surfacing different occurrences in different
      views. Per design doc sec10.4.
    - Extend _event_status_line_for_card to render "Cancelled" red when
      event.status == 'cancelled'. Per design doc sec10.3.
    - Extend the build_card_view_model freshness branch with the
      event-typed override per design doc sec10.2.

(d) Events category page chip filters + sort dropdown extensions —
    anchored edit on app/api/routes/category_pages.py per design doc
    sec12.1. Add CategoryPageConfig entry for 'events' slug with
    operational_chips for today/this-weekend/this-week/next-month +
    sort_default='chronological'. Query-string handling for
    ?when=today / ?when=this-weekend / etc. Window math per design doc
    sec3.4 chip-filter window presets.

(e) "What's on at this venue" region partial + query path. New
    app/templates/components/venue_events_region.html (Jinja partial;
    iterates venue_events context var, renders Hava cards; collapses
    gracefully when empty). Anchored edit on app/providers/router.py
    (or wherever the provider profile route lives) adding _venue_events_
    for_profile(db, provider, limit=5) returning up to 5 upcoming event
    cards tied to this venue via entity_id OR provider_id link with
    RRULE expansion. Per design doc sec11.

(f) Anchored edit on app/templates/provider_profile.html replacing
    `<!-- venue-events-region-anchor -->` with `{% include 'components/
    venue_events_region.html' %}`. **IF Phase 6.5 has not shipped at
    Phase 9 dispatch time**, defer this anchor-edit step — ship the
    partial only; Phase 6.5 wires the anchor when it lands.

(g) Admin event-edit UI surface — new admin route /admin/events/<id>/edit
    per design doc sec7.3. New template app/templates/admin_event_edit.
    html with structured RRULE-form (FREQ + BYDAY + UNTIL pickers), EXDATE
    add UI, status toggle (Live / Cancelled with reason textarea),
    "Lock my edits" operator_override checkbox. Hooks into existing
    contribution-approval flow at app/contrib/approval_service.py.

(h) Background job script scripts/expire_past_events.py — daily Railway
    cron 0 3 * * * Lake Havasu local. UPDATE events SET status='expired'
    WHERE status='live' AND date < CURRENT_DATE - INTERVAL '7 days' AND
    (rrule IS NULL OR parsed_until_from_rrule(rrule) < CURRENT_DATE -
    INTERVAL '7 days'). Pattern from scripts/outbox_redrive.py. Per
    design doc sec2.5.

(i) Smoke script scripts/recurrence_smoke.py — one-off "expand all live
    events; surface any cap-exceeded warnings; log parse-error events
    for operator review". Per design doc sec15 Risk 2 mitigation.

(j) Phase 9a tests — 5+ new test files:
    - tests/test_phase9_events_schema.py (~8-12 tests; migration upgrade
      + downgrade roundtrip; CHECK constraint enforced; indexes created)
    - tests/test_phase9_recurrence.py (~15-20 tests; DST-aware Phoenix vs
      Pacific; Feb 29 leap-year; EXDATE removal; RDATE addition; open-
      ended rule + window-cap; cap-exceeded raises; BYDAY combinations)
    - tests/test_phase9_events_queries.py (~10-15 tests; events_in_window
      with chip-filter windows; category_slug filter; recurring + non-
      recurring mix; limit pagination)
    - tests/test_phase9_event_card_rendering.py (~10-14 tests;
      derive_event_freshness_band tighter thresholds; build_card_view_
      model_for_event_occurrence; cancelled status red; recurring event
      shows next occurrence not master date)
    - tests/test_phase9_venue_events_region.py (~8-12 tests; query path
      returns up to limit events; collapses on zero events; entity_id
      vs provider_id link both work; recurring events surface once)
    - tests/test_phase9_events_category_page.py (~8-12 tests; chip filter
      'today' / 'this-weekend' / 'next-month' window math; chronological
      sort default; sort dropdown switches)
    - tests/test_phase9_expire_past_events.py (~6-10 tests; sweep
      transitions live → expired; UNTIL=-bounded recurrence expires;
      open-ended recurrence does NOT auto-expire)
    - tests/test_phase9_chat_event_intent.py (~6-10 tests; detect_event_
      intent("what's happening tonight") returns {'when': 'tonight'};
      tier-2 routes to events_in_window when detected)

HALT BOUNDARY between Phase 9a and Phase 9b. After step (j) completes +
pytest green + alembic head verified + commits drafted, HALT for
operator decision. Operator commits + pushes 9a; 9b dispatches in a fresh
session against 9a HEAD SHA. The HALT mirrors Phase 8a-A vs 8a-B and
Phase 6.4-Lane-D vs Lane-E.

PHASE 9b SCOPE (Scraper subsystem + Classes/Sports + Things-to-Do group +
interleaving; ~5-8 days dispatch):

(k) New app/events/scrapers/ module with:
    - app/events/scrapers/__init__.py
    - app/events/scrapers/base.py — EventIngestClient base class extending
      app/contrib/ingest_base.BaseIngestClient; EventPayload dataclass
      specializing EntityPayload for entity_type='event' with start_date
      + end_date + start_time + end_time + venue_name + venue_entity_id +
      rrule + tags + event_url + description fields. Per design doc
      sec5.3.
    - app/events/scrapers/chamber.py — Chamber community calendar HTML
      scraper; schema.org Event microdata preferred + CSS selector
      fallback; reuses with_retry envelope from Phase 4.
    - app/events/scrapers/go_lake_havasu.py — Go Lake Havasu events
      scraper; same shape.
    - app/events/scrapers/river_scene_v2.py — thin adapter wrapping
      existing app/contrib/river_scene_pull.py into EventIngestClient
      interface; preserves Phase 4.x contributions-queue write path.
      Per design doc sec5.8.
    - app/events/scrapers/lhc_library.py — City library HTML scraper
      (weekly cadence).
    - app/events/scrapers/lhc_parks_rec.py — City parks-and-rec HTML
      scraper (weekly cadence).

(l) New app/events/dedup.py — multi-source dedup helpers per design doc
    sec6.2. find_duplicate(db, venue_entity_id, start_date, start_time_
    obj, normalized_title) uses rapidfuzz token_sort_ratio threshold 85 +
    30-min datetime proximity window. resolve_venue_entity_id(db,
    venue_name, venue_address) reuses Phase 4.x ingest_reconciler pattern.
    On match — merge semantics per sec6.4: scraper updates NULL fields
    + skips operator-locked fields + bumps scraped_at + writes field_
    history rows.

(m) New scripts/scrape_events.py CLI entrypoint with SOURCE_REGISTRY dict
    + --source flag + --all + --dry-run flags. Pattern follows Phase 8's
    scripts/fetch_external_conditions.py --source X structure. Per design
    doc sec5.4.

(n) Extend app/contrib/approval_service.py with AUTO_APPROVE_EVENT_
    SOURCES = {'chamber', 'go_lake_havasu', 'river_scene'} env-tunable
    allowlist + should_auto_approve(contribution) check. Per design doc
    sec5.6. City library + parks-rec stay manual-review V1.

(o) Classes/Sports/Recreation category page chip filter extensions —
    anchored edit on app/api/routes/category_pages.py per design doc
    sec12.2. Add CategoryPageConfig entry for 'classes-sports-recreation'
    slug with operational_chips for drop-in / registration / kids / teens
    / adults / 55-plus. Age-band filter logic via Program.age_min /
    Program.age_max columns (Phase 1A). Drop-in vs registration via
    Entity.crowd_notes JSON {'drop_in_friendly': bool} operator-typed
    field — Phase 9 extends crowd_notes shape; no schema migration since
    crowd_notes is already JSON.

(p) Things-to-Do themed group — anchored edit on app/groups/themed_
    groups.py adding 'things-to-do-group' entry to THEMED_GROUPS dict
    with category bundle ['events', 'outdoors-parks-trails', 'classes-
    sports-recreation']. Plus _GROUP_LABELS / _GROUP_ONE_LINERS /
    _GROUP_ACCENTS entries. Route /group/things-to-do-group auto-picks-up
    via Phase 6.4 themed-group routes module — no new route code. Per
    design doc sec8.3.

(q) Themed-group interleaving — anchored edit on app/api/routes/themed_
    groups.py extending get_themed_group_card_stream(db, group_slug,
    limit) to include events alongside entities. Calls events_in_window
    for upcoming-30-days window; filters by group's category bundle;
    combines entity_ids + upcoming_event_entity_ids; ranks via
    compute_card_rank + new compute_event_card_rank. Per design doc sec9.2.

(r) compute_event_card_rank() in app/core/ranking.py — anchored edit
    adding event-card ranking shape. Bias factors per design doc sec9.3:
    imminence (today +30% / tomorrow +15% / this weekend +10% / this week
    +5%) + distance + heat-aware (events at indoor venues +20% when temp
    >= 100°F — reuses Phase 8a's read_current_temperature_f()) + boat-
    mode (+10% when boat-mode active + venue boat-accessible) +
    editorial featured +25%.

(s) Card variety cap — _cap_event_share() helper per design doc sec9.4.
    Caps event cards at 40% of visible themed-group stream; operator-
    tunable via env var THEMED_GROUP_EVENT_CAP_PCT (default 0.40).

(t) Chat event-intent extension — anchored edit on app/chat/tier2_
    handler.py adding detect_event_intent(query) helper returning
    {'when': 'today' | 'tonight' | 'this_weekend' | None} per design doc
    sec13.1. When detected, tier-2 routes to events_in_window. Tier-3
    LLM prompt gets event-intent preamble (1-line addition).

(u) Phase 9b tests — 7+ new test files:
    - tests/test_phase9_scraper_base.py (~8-12 tests; EventIngestClient
      + EventPayload roundtrip; with_retry envelope; source-isolation)
    - tests/test_phase9_scraper_chamber.py (~8-12 tests; mocks Chamber
      HTML; microdata-preferred parsing; fixture-based event extraction)
    - tests/test_phase9_scraper_go_lake_havasu.py (~8-12 tests; same shape)
    - tests/test_phase9_scraper_river_scene_v2.py (~6-10 tests; adapter
      delegates to existing river_scene_pull module without behavior
      change)
    - tests/test_phase9_scraper_lhc.py (~8-12 tests; covers both library
      + parks-rec sources)
    - tests/test_phase9_dedup.py (~12-15 tests; same event same day same
      time = match; 30-min window edge cases; token_sort 88 above
      threshold = match; 80 below threshold = no-match; venue resolution;
      operator_override preserves operator-locked fields)
    - tests/test_phase9_classes_sports_recreation.py (~10-14 tests; age-
      band chip filters; drop-in / registration filters; recurring class
      status line "Tuesdays at 6:00pm")
    - tests/test_phase9_things_to_do_group.py (~8-12 tests; route
      /group/things-to-do-group renders; category bundle resolved
      correctly; cards mix entity_type values)
    - tests/test_phase9_themed_group_interleaving.py (~10-14 tests;
      events + places mixed in stream; rank-ordered; event-share cap
      40% honored; cap-exceeded events filtered)
    - tests/test_phase9_event_card_rank.py (~8-12 tests; imminence bias
      today vs tomorrow vs next week; heat-bias reuses read_current_
      temperature_f; boat-mode boost; editorial featured boost)
    - tests/test_phase9_chat_events.py (~10-14 tests; "what's happening
      tonight" routes to events_in_window; "this weekend" applies window
      correctly; cross-entity "what to do with kids" mixes events + parks)

(v) After all of the above: confirm full pytest stays green (post-Phase-
    8a baseline + 150-250 net-new = ~2370-2580), ruff clean, alembic
    head matches Phase 9a's new revision SHA. Manual smoke deferred-to-
    operator:
    - python -m scripts.scrape_events --source chamber --dry-run + verify
      EventPayload count (~10-30 events expected on first dry-run)
    - python -m scripts.scrape_events --all --dry-run + verify per-source
      success counts + Sentry breadcrumbs visible
    - Browse /category/events + verify date chip filters work + card
      grammar matches Phase 6.1
    - Browse /category/classes-sports-recreation + verify age band +
      drop-in chips work
    - Browse /group/things-to-do-group + verify interleaved stream
      shows both events + places
    - Browse /provider/<slug> for a venue with events + verify "What's
      on at <venue>" region renders
    - Ask chat "what's happening tonight in Havasu" + verify event-
      typed entities returned with correct status lines

LOCKED OPERATOR DECISIONS (per design doc sec1-19):
- RRULE expansion: at-query-time hybrid (rule storage + finite-horizon
  expansion via dateutil.rrule); reject row-expansion at V1 scale per
  sec3.1
- Event lifecycle: 4-state CHECK ('draft', 'live', 'cancelled',
  'expired') + cancellation_reason TEXT NULL + daily expirer cron sweep
- Multi-source dedup: (venue_entity_id, start_datetime, normalized_
  title) tuple; rapidfuzz token_sort_ratio threshold 85; 30-min datetime
  proximity window
- Capacity-null default: schema columns exist; render branch returns
  None when NULL; honest per master plan sec8 OQ #12
- Events category-page sort default: chronological (next occurrence
  ascending); alternatives closest_now + featured available via dropdown
- Things-to-Do themed group cuts: 3-category bundle = cat-2 + cat-7 +
  cat-9; cat-3 + cat-1 + cat-10 explicitly excluded (own themed groups
  or wrong domain)
- Per-source scrape cadence: daily for Chamber + Go Lake Havasu +
  RiverScene; weekly for LHC library + parks-rec; operator-tunable post-
  ship
- Migration shape: additive 8-column + status CHECK + 4 indexes;
  Phase 9a ships ONE migration chaining from d8e9f0a1b2c3;
  Phase 9b ships ZERO migrations
- Auto-approval allowlist: chamber + go_lake_havasu + river_scene; city
  sources stay manual-review V1 (operator audits 2 weeks then can flip
  via EVENT_AUTO_APPROVE_SOURCES env var)
- EVENT_FRESHNESS_GREEN_DAYS=7; EVENT_FRESHNESS_AMBER_DAYS=21 (operator-
  tunable constants)
- EVENT_DEDUP_TITLE_THRESHOLD=85; EVENT_DEDUP_DATETIME_WINDOW_MINUTES=30
  (operator-tunable env vars)
- THEMED_GROUP_EVENT_CAP_PCT=0.40 (operator-tunable env var)
- Operator-override default: TRUE when operator edits any field via
  admin UI; operator can uncheck "Lock my edits" to allow scrapes to
  re-take

ORDER MATTERS WITHIN PHASE 9:

1. First: read the design doc end-to-end + master plan sec4 Phase 9 +
   master plan sec7 risk #6 + master plan sec8 OQ #12. Critical reads in
   the codebase:
   - app/db/models.py (Event table at lines 166-246; verify schema
     matches design doc sec2.1 baseline; flag any drift)
   - app/providers/queries.py (Phase 6.1 _event_status_line_for_card at
     lines 666-696; derive_freshness_band_from_updated_at at line 536;
     build_card_view_model at lines 723-805; Phase 9 extends)
   - app/contrib/ingest_base.py (BaseIngestClient + EntityPayload; Phase
     9 extends to EventIngestClient + EventPayload)
   - app/contrib/river_scene.py + app/contrib/river_scene_pull.py
     (Phase 4.x existing RiverScene scraper; Phase 9 layers EventIngest
     Client interface via thin adapter — does NOT rewrite)
   - app/contrib/approval_service.py (contributions-queue approval flow;
     Phase 9 extends with AUTO_APPROVE_EVENT_SOURCES allowlist)
   - app/contrib/ingest_reconciler.py (venue resolution pattern; Phase 9
     dedup reuses)
   - app/core/ranking.py (Phase 6.3 compute_card_rank + heat-bias; Phase
     8a read_current_temperature_f swap; Phase 9 adds compute_event_card_
     rank mirroring shape)
   - app/groups/themed_groups.py (Phase 6.4 themed-group registry;
     Phase 9 adds things-to-do-group entry)
   - app/api/routes/themed_groups.py (Phase 6.4 themed-group routes +
     stream builder; Phase 9 extends to interleave events)
   - app/api/routes/category_pages.py (Phase 5.8+ CategoryPageConfig +
     Chip dataclass; Phase 9 adds events + classes-sports-recreation
     configs)
   - app/chat/tier2_handler.py + tier2_db_query.py (Phase 7 ENTITY
     wiring; Phase 9 adds event-intent detection branch)
   - app/chat/tier3_handler.py (Phase 7 LLM tier; Phase 9 adds 1-line
     event-intent preamble)
   - app/templates/provider_profile.html (Phase 6.5 venue-events-region-
     anchor location)
   - app/templates/components/ (Phase 6.1 hava_card.html pattern; new
     venue_events_region.html follows same shape)
   - docs/maintainability/master_build_plan.md sec4 Phase 9 + sec7 #6 +
     sec8 OQ #12

2. Then: schema migration. Verify d8e9f0a1b2c3 is current
   single head. Author additive migration adding 8 columns + status
   CHECK + 4 indexes per design doc sec2.2. CRITICAL: use python -m
   alembic heads to verify SINGLE head before authoring. Migration
   upgrade + downgrade cycle tested in tests/test_phase9_events_schema.py
   with DYNAMIC head capture per session-2026-05-19 lesson #4. NEVER
   hardcode head literals.

3. Then: app/events/ module — recurrence.py + queries.py + view_model.py.
   Pure-function helpers; test-first since the recurrence math has many
   edge cases (DST, leap, EXDATE, RDATE, cap-exceeded).

4. Then: app/providers/queries.py extensions — derive_event_freshness_
   band + build_card_view_model_for_event_occurrence + cancelled-status
   red. Anchored edits.

5. Then: events category page chip filters + sort dropdown. Anchored
   edits on app/api/routes/category_pages.py.

6. Then: venue-events region partial + query path + (conditional)
   provider_profile.html anchor edit. If Phase 6.5 has not shipped, ship
   partial only.

7. Then: admin event-edit UI + expirer script + recurrence smoke script.

8. Then: Phase 9a tests — 5-8 new test files.

[HALT BOUNDARY — operator commits + pushes 9a; 9b dispatches fresh]

9. Then (9b start): app/events/scrapers/ — base.py + 5 source modules.
   Reuse Phase 4 with_retry envelope. Source-isolation pattern.

10. Then: app/events/dedup.py — multi-source dedup + venue resolution +
    merge semantics.

11. Then: scripts/scrape_events.py CLI + AUTO_APPROVE_EVENT_SOURCES
    allowlist extension to approval_service.py.

12. Then: classes-sports-recreation category page chip filters.

13. Then: things-to-do-group themed group registry extension + interleaving
    extension + event-share cap + compute_event_card_rank.

14. Then: chat event-intent detection extension.

15. Then: Phase 9b tests — 7-10 new test files.

16. After all of the above: confirm pytest green, ruff clean, alembic
    head matches Phase 9a's revision SHA (Phase 9b ships no migration).
    Manual smoke deferred-to-operator per step (v) above.

POSTGRES COMPATIBILITY (carry-forward from brief sec0 + Phase 1A lesson +
Phase 8 carry-forward):
- Phase 9a ships ONE additive migration adding 8 columns + status CHECK
  + 4 indexes. All columns nullable or DEFAULT-constrained. Use sa.true()
  / sa.false() for Boolean defaults; sa.func.now() for timestamps. Never
  use sa.text("1")/sa.text("0") for Boolean defaults (Phase 1A Postgres
  lesson).
- The status CHECK constraint syntax: `CREATE CHECK ck_events_status
  CHECK (status IN ('draft', 'live', 'cancelled', 'expired'))` — works
  on both Postgres + SQLite (Phase 1A precedent: contributions.status
  has similar CHECK).
- JSON columns (rdate + exdate) use SQLAlchemy JSON type — auto-maps to
  jsonb on Postgres + JSON1 on SQLite.
- TZAwareDateTime alias from app/db/types.py reused for scraped_at —
  matches existing Phase 1A conventions.
- python -m alembic heads MUST return SINGLE head at start AND at end of
  Phase 9a dispatch. Phase 9b ships ZERO migrations so head stays at
  Phase 9a's revision SHA throughout 9b.
- NEVER hardcode alembic head literals in test code (session-2026-05-19
  lesson #4); use script.get_current_head() + script.get_revision()
  helpers.

DEVIATION INVITATIONS (per design doc sec1-19 + master plan sec4 Phase
9; expect 8-12 deviations):

- Event source URL discovery — design doc sec5.1 marks Chamber + Go
  Lake Havasu + library + parks-rec URLs as TBD; operator confirms in
  prereq. If operator's discovered URL has different shape than
  design-doc anticipated, flag the per-source parser at step (k) for
  adjustment.
- Source HTML stability — if any of the 5 sources lacks schema.org
  microdata AND has unstable CSS structure, scraping that source is
  high-risk; flag for V1.5 deferral if reliability < 50% on first dry-
  run.
- Per-source cadence tuning — design doc sec5.1 locks daily Chamber/
  GoLakeHavasu/RiverScene + weekly LHC library/parks-rec. Operator
  may want different cadences after observing source change-velocity;
  flag operator-tunable env var pattern.
- Auto-approval allowlist — design locks Chamber + Go Lake Havasu +
  RiverScene auto-approve. If first 2 weeks show too many low-quality
  scraped events, operator can shrink allowlist via env var; flag this
  knob.
- RRULE expansion cap — design locks cap=100 occurrences per window.
  If real recurring events legitimately exceed (e.g. daily yoga over
  1 year = 365 occurrences within a 1-year query window), flag cap-
  tuning + window-cap negotiation.
- Dedup threshold tuning — design locks token_sort_ratio 85 + 30-min
  window. If first 2 weeks show false-positive merges, flag for
  threshold-tightening; if false-negative duplicates surface, flag for
  loosening.
- Things-to-Do bundle cut — design locks 3-category bundle (cat-2 +
  cat-7 + cat-9). If operator decides cat-9 belongs only in health-
  fitness-group (avoid overlap), flag for 2-category bundle alternative.
- Themed-group event-share cap — design locks 40%. If cap feels too
  restrictive (events dominate themed-group landing on busy weekends
  legitimately) OR too permissive (events crowd places), flag for
  THEMED_GROUP_EVENT_CAP_PCT tuning.
- Phase 6.5 anchor coordination — if Phase 6.5 hasn't shipped at Phase
  9 dispatch time AND the provider_profile.html anchor doesn't exist,
  ship venue_events_region.html partial standalone + defer anchor wiring
  to Phase 6.5 lane. Flag this in close-out for Phase 6.5 lane to
  re-coordinate on.
- Operator-edit UI scope — design doc sec7.3 ships full RRULE-form +
  EXDATE add UI + cancellation reason. If admin UI scope grows
  uncomfortable (≥1 day of design polish), flag scope-reduction option:
  ship JSON-textarea RRULE editing in V1 + structured form in V1.5.
- Chat event-intent detection regex — design doc sec13.1 ships
  keyword-based "tonight / happening / events / what's on" + "this
  weekend / saturday / sunday". If false-positives surface (non-event
  queries routing to events_in_window), flag for tighter intent gate.
- Capacity rendering enablement — design locks capacity-null V1 default.
  If operator wants a single test event with operator_typed capacity to
  validate render branch, flag the path.

WHAT NOT TO DO (per master plan sec4 Phase 9 + design doc sec14):

- Don't ship Twilio SMS event reminders ("Yoga starts in 30 min").
  Master plan + Phase 8 sec11 + design doc sec14 defer to V1.5.
- Don't ship Eventbrite / Meetup / Facebook Events API integrations.
  V2 scope; ticketing-API integration requires app review + cost.
- Don't ship event_traffic alert wiring. Phase 8 stubbed this; Phase
  9.5 wires against the Events surface Phase 9 lands.
- Don't ship operator booking / ticketing flow. Hava is a directory,
  not a marketplace. V2+ separate strategic decision.
- Don't ship per-event sponsorship (sponsored event cards). Phase 11
  lands sponsor mechanism on commercial entities first; event-typed
  sponsorship deferred to Phase 11.5 / V2.
- Don't ship event detail page route (separate URL /events/<id>). Card
  links to event_url (the source URL) by default; dedicated detail
  page is V1.5.
- Don't ship calendar export (.ics file per event). V1.5.
- Don't ship user RSVP / "I'm going" tracking. Marketplace feature; V2+.
- Don't ship row-expansion materialization for recurrence. At-query-time
  expansion is fast enough at V1 scale per design doc sec3.5; Phase 13 /
  V1.5 if profiling shows need.
- Don't ship multi-day event detail expansion ("see all dates"). Card
  shows next occurrence; multi-occurrence drill-in is V1.5.
- Don't ship auto-cancellation when source removes event. False-positive
  risk too high; operator-only cancel in V1 per design doc sec7.4.
- Don't ship capacity rendering with manufactured data ("Limited spots"
  without real number). Master plan sec8 OQ #12 honesty rule.
- Don't ship Phase 8b cat-13 expansion (parallel-eligible but separate
  lane).
- Don't ship Phase 9.5 (event_traffic alert wiring).
- Don't ship Phase 10 polish / accessibility audit. Separate later phase.
- Don't ship Phase 11 monetization / sponsorship.
- Don't ship district paragraph rendering. V1.5.
- Don't add new Python dependencies BEYOND `python-dateutil` (likely
  already in deps; verify) for RRULE + `feedparser` OR `feedfinder` if
  needed for any source emitting RSS/Atom (verify at step k; HTML
  scraping uses existing httpx + BeautifulSoup). `rapidfuzz` for dedup
  is likely already in deps from Phase 5 reconciler work; verify.
- Don't bash heredoc commit messages. PowerShell-safe multi-line `-m`
  flags or here-string per session-2026-05-19 lesson #1.
- Don't hardcode alembic head literals in test code (session-2026-05-19
  lesson #4).
- Don't proceed if `python -m alembic heads` returns multiple heads.
  HALT.
- Don't proceed past the 9a/9b HALT boundary inline. Operator commits +
  pushes 9a; 9b dispatches in a fresh session against 9a HEAD SHA.

HALT at the sec18.4 9a/9b boundary. After Phase 9a ships + commits +
pushes, halt for operator re-dispatch in a fresh session for Phase 9b
(scrapers + Classes/Sports + Things-to-Do group + interleaving). Same
constraints as Phase 6.4 + 7 + 8 split-lane pattern.

Same constraints as Phase 6.1 + 6.2 + 6.3 + 6.4 + Phase 7 + Phase 8:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 sec12 final report format adapted for Phase 9
- Re-verify python -m alembic current AND python -m alembic heads at
  start of 9a + end of 9a + start of 9b + end of 9b; report observed
  values
- If alembic heads returns multiple heads, HALT and report
- PowerShell-safe commit message preparation per session-2026-05-19
  lesson #1 (operator runs git; Cursor does NOT)
- Notepad clipboard router pattern per session-2026-05-19 lesson #3
  (operator-facing; Cursor doesn't need it)

Pre-dispatch checklist (verify before paste):

- Phase 6.1 SHIPPED on origin (fd16e7a)
- Phase 6.2 SHIPPED on origin (3948add)
- Phase 6.3 SHIPPED on origin (5ebee46)
- Phase 6.4 SHIPPED on origin (96c915d)
- Phase 7 SHIPPED on origin (0a305e0)
- Phase 8a SHIPPED on origin (8a905c6) — fill at SHA-patch
- Phase 8a alembic head d8e9f0a1b2c3 is the current SINGLE
  alembic head on origin (verify via `python -m alembic current` AND
  `python -m alembic heads`)
- Phase 5 ledger SHIPPED on origin (3a2d895)
- Sidecar migration SHIPPED on origin (532d48b)
- Phase 6.5 ship status verified (bdca0bd if shipped
  first; otherwise note "Phase 6.5 deferred; venue-events anchor wiring
  conditional in step (f)")
- Phase 7.5 ship status verified (b701759 if shipped;
  Phase 9 doesn't require it but worth noting for chat surface state)
- Pytest baseline going in matches reality per `python -m pytest
  --collect-only -q | tail -3` (likely 2220-2330 post-Phase-8a)
- The 5 operator prereqs for Phase 9b are RESOLVED (or HALT 9b until
  resolved; Phase 9a can ship without 9b prereqs): 5 event-source URLs
  + robots.txt audit + microdata presence check + structured-feed
  preference + per-source cadence locked
- The 6 operator decisions are LOCKED at design-doc-defaults: RRULE
  expansion at-query-time, 4-state lifecycle CHECK, multi-source dedup
  tuple + thresholds, capacity-null default, events sort = chronological,
  Things-to-Do 3-category bundle
- The 2 supplementary locks are confirmed: per-source cadence + migration
  shape (8 columns + CHECK + 4 indexes)
- Master plan sec4 Phase 9 reviewed + acceptance gates noted (per design
  doc sec16.1-16.7)
- Phase 8b (cat-13 expansion) NOT in scope (separate lane; parallel-
  eligible with 9b but disjoint file scope)
- Phase 9.5 (event_traffic alert wiring) NOT in scope (deferred; lands
  after Phase 9 ships)
- Phase 10 / 11 NOT in scope (deferred)
````

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phase ships: paste back to Cowork primary chat, primary reviews against design doc §16 success criteria + master plan §4 Phase 9 acceptance gates, recommends commit batch (Rule 8), operator commits + pushes. Phase 9 splits into 2 close-out rhythms — one for 9a, one for 9b. See `outputs/phase_9_close_out_template.md` (TBD — pre-position alongside this wrapper).

Expected files touched:

**Phase 9a (~15-20 files):**
- 1 new alembic migration (additive — 8 columns + status CHECK + 4 indexes)
- 1 new module dir `app/events/` (~4 files: `__init__.py`, `recurrence.py`, `queries.py`, `view_model.py`)
- 1 new `app/templates/components/venue_events_region.html` (~40-80 lines)
- 1 new `app/templates/admin_event_edit.html` (~120-200 lines)
- 2 new scripts: `scripts/expire_past_events.py` + `scripts/recurrence_smoke.py`
- 1 modified `app/db/models.py` (anchored edit; +~8 SQLAlchemy column definitions on Event)
- 1 modified `app/providers/queries.py` (anchored edits; `derive_event_freshness_band` + `build_card_view_model_for_event_occurrence` + status line extension)
- 1 modified `app/providers/router.py` (anchored edit; `_venue_events_for_profile` + render context wiring)
- 1 modified `app/api/routes/category_pages.py` (anchored edit; events CategoryPageConfig + date-window query parsing)
- 1 modified `app/templates/provider_profile.html` (anchored edit; venue-events region include — conditional on Phase 6.5)
- 1 modified `app/api/routes/admin.py` (or wherever admin routes mount; anchored edit; /admin/events/<id>/edit route)
- 5-8 new test files at `tests/test_phase9_*.py`

**Phase 9b (~15-20 files):**
- 0 new alembic migrations (no schema change)
- 1 new module dir `app/events/scrapers/` (~7 files: `__init__.py`, `base.py`, `chamber.py`, `go_lake_havasu.py`, `river_scene_v2.py`, `lhc_library.py`, `lhc_parks_rec.py`)
- 1 new `app/events/dedup.py`
- 1 new `scripts/scrape_events.py`
- 1 modified `app/contrib/approval_service.py` (anchored edit; `AUTO_APPROVE_EVENT_SOURCES` + `should_auto_approve` extension)
- 1 modified `app/api/routes/category_pages.py` (anchored edit; classes-sports-recreation CategoryPageConfig)
- 1 modified `app/groups/themed_groups.py` (anchored edit; things-to-do-group entry + label dict + accents)
- 1 modified `app/api/routes/themed_groups.py` (anchored edit; interleaving extension + event-share cap)
- 1 modified `app/core/ranking.py` (anchored edit; `compute_event_card_rank` + event-share cap helper)
- 1 modified `app/chat/tier2_handler.py` (anchored edit; `detect_event_intent` + tier-2 routing branch)
- 1 modified `app/chat/tier3_handler.py` (anchored edit; LLM preamble line for event-intent queries)
- 7-10 new test files at `tests/test_phase9_*.py`

Expected pytest delta: **+150-250 net-new tests across 9a + 9b combined.** Phase 9a contributes ~70-100 (recurrence + queries + card rendering + venue region + category page + expirer); Phase 9b contributes ~80-150 (5 scrapers + dedup + classes-sports + things-to-do + interleaving + ranking + chat). Pre-existing tests must remain green.

Expected effort: **L (12-18 days dispatch) per master plan §4 Phase 9.** Per design doc §17 refined estimate: 17 days combined (9a=8 days + 9b=9 days). CURSOR SPLITS INTO TWO SUB-SESSIONS at the HALT boundary:
- **Phase 9a:** Event ENTITY + RRULE foundation + Events category + venue-events region (~7-10 days; file scope per above; HALT at end for operator commit + fresh-session 9b dispatch)
- **Phase 9b:** Scraper subsystem + Classes/Sports/Recreation + Things-to-Do themed group + interleaving + event-share cap + chat event-intent (~5-8 days; file scope per above)

HALT between 9a and 9b at the natural §18.4 work-unit boundary; operator commits + pushes 9a; 9b dispatches fresh against 9a HEAD SHA. The HALT is REQUIRED — RRULE storage shape is the load-bearing decision; review Phase 9a's actual recurrence-expansion query timings + admin event-edit UI ergonomics before authorizing 9b's bulk scraper writes that depend on the same shape.

Expected pragmatic deviations:

1. Event-source URL discovery (operator prereq finds URLs differ from design-doc anticipation)
2. Source HTML stability — if 1-2 sources lack microdata + have unstable CSS, V1.5 deferral
3. Per-source cadence tuning (operator rate-limit anxiety or change-velocity observation)
4. Auto-approval allowlist tightening (first-2-weeks observation)
5. RRULE expansion cap tuning (legitimate daily-over-year recurrence exceeds default cap=100)
6. Dedup threshold tuning (false-positive merges or false-negative duplicates)
7. Things-to-Do bundle cut (3-category vs 2-category; cat-9 overlap concern)
8. Themed-group event-share cap (40% vs alternative on busy weekends)
9. Phase 6.5 anchor coordination (Phase 6.5 hasn't shipped at Phase 9 dispatch time)
10. Operator-edit UI scope (full RRULE-form vs simplified V1.5 polish)
11. Chat event-intent detection regex (false-positive routing)
12. Capacity rendering enablement (single operator-typed test event)

## After Phase 9 ships

Update master plan §4 Phase 9 — append SHIPPED line per the close-out template. Update STATE.md "Recently shipped" prepend with Phase 9a close-out narrative; then again with 9b close-out narrative after 9b ships. Update alembic head reference to Phase 9a's revision SHA.

After Phase 9 is durable:

- **Phase 9.5 (event_traffic alert wiring)** dispatch wrapper to be authored — likely a smaller micro-dispatch (~2-3 days) wiring Phase 8a's alert subsystem against the Events surface Phase 9 landed. Threshold definitions for `event_traffic` (e.g. events with attendance >500 within 24h triggering traffic-pattern alerts) lock at that dispatch's authoring time.
- **Phase 8b (cat-13 Public & Civic Resources expansion)** continues independently — parallel-eligible with Phase 9b if not yet dispatched; landing dispatch wrapper at `outputs/cursor_dispatch_prompt_phase_8b.md` (TBD).
- **Phase 10 (polish + accessibility + pre-launch hardening)** dispatch wrapper authored after Phase 9 + 9.5 + 8b all ship — final pass before launch.

Expected V1.5 carry-forward items from Phase 9:
- Event detail page route (`/events/<id>` standalone)
- Multi-day event detail expansion ("see all dates")
- Calendar export (.ics per event)
- Twilio SMS event reminders
- Operator scrape-monitoring dashboard (Phase 9b stretch may ship V1; otherwise V1.5)
- Row-expansion materialization for recurrence (Phase 13 if profiling shows need)

Pre-position the Phase 9 close-out template at `outputs/phase_9_close_out_template.md` (TBD — author after this wrapper SHA-patches + before Phase 9a dispatch). Mirror the Phase 7 + 8 close-out shape: §1 ship narrative; §2 commit chain; §3 acceptance criteria check against design doc §16; §4 deviations encountered; §5 V1.5 carry-forward; §6 next-lane unblock.

---

*Authored by Cowork primary at the post-Phase-7-close-out session (2026-05-20). Lives at `outputs/cursor_dispatch_prompt_phase_9.md`. SHA-patch slots `8a905c6` + `d8e9f0a1b2c3` + `bdca0bd` (optional) + `b701759` (optional) need filling post-Phase-8a-ship. Per the 2026-05-20 alembic-collision gotcha (`outputs/dispatch_channels_alembic_collision_gotcha_draft.md`), Phase 9 is sequential after Phase 8a — they do NOT run in parallel. Phase 9b is parallel-eligible with Phase 8b (cat-13 expansion) per file-scope disjointness; verify SINGLE alembic head if both dispatch in parallel sessions. Architectural design at `outputs/phase_9_architecture_design.md` (1620 lines) is the upstream artifact; operator prereq checklist at `outputs/phase_9_operator_prereq_checklist.md` (TBD — author before Phase 9b dispatch) gates the 5 event-source URLs + robots.txt audit. The recommended Phase 9a + Phase 9b split (sequential, with HALT at §18.4 boundary) mirrors Phase 6.4-Lane-D vs Lane-E + Phase 8a-A vs 8a-B + Phase 7-vs-7.5 split-lane discipline.*
