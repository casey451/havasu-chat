# Phase 7 Handoff Note — the chat + HALT 3 lane after Phase 5 + 6.3

> **SUPERSEDED-IN-PLACE 2026-05-19** — the Phase 5 restructure (5.1–5.11 SHIPPED 2026-05-17) absorbed both strands originally described in this note. Phase 7's data strand is moot (Phase 5 shipped data for all 13 categories including the 3 the original note named: Outdoors/Parks/Trails, Lodging & VR, and Pets). Phase 7's UI strand was absorbed by Phase 6.3 (commit `5ebee46`, 2026-05-19, extended the breadth pass to all 11 remaining Tier-1 slugs beyond Eat & Drink). The current Phase 7 scope is chat + HALT 3 + cross-entity queries + snowbird-return view. See `docs/maintainability/master_build_plan.md` §4 Phase 7 (refreshed 2026-05-19) for the authoritative scope. The original 2026-05-14 framing is preserved in git history.

> **Purpose:** make sure the Phase 5/6 → Phase 7 sequence isn't lost. Authored by Cowork primary at the new-chat post-`2f4676a` session (2026-05-14); refreshed 2026-05-19 post-Phase-5-restructure + Phase 6.3 breadth pass.
>
> **One-line (refreshed):** Phase 7 is the chat-integration + HALT 3 close-out lane that runs after Phase 6.3 lands the Tier 1 UI breadth pass. The original "Tier 2 UI + data" framing is historical — Phase 5 + 6.3 absorbed both strands.

---

## §1 What Phase 7 is (refreshed)

Per `docs/maintainability/master_build_plan.md` §4 Phase 7 (refreshed 2026-05-19) + §5 dependency graph:

**Phase 7 — Chat + HALT 3 + cross-entity + snowbird view (~1-2 weeks).** Single strand. The original "two strands: Tier 2 UI + Tier 2 data gathering" framing is fully absorbed:

- **Tier 2 UI absorbed by Phase 6.3** (commit `5ebee46`, 2026-05-19): the breadth pass extended category landing pages to all 11 remaining Tier-1 slugs beyond Eat & Drink, including the 3 categories the original note claimed (Outdoors/Parks/Trails, Lodging & VR, Pets). Plus district chip + time/heat-aware ranking + seasonal hours rendering.
- **Tier 2 data gathering absorbed by Phase 5 restructure**: 5.7 + 5.10 + 5.11 shipped data for those exact 3 categories (27 + 73 + 38 = 138 entries, comfortably within the original 75-175 forecast). All 13 Tier-1 categories populated at Phase 5.11 close; total active entities 1,314.

Active Phase 7 deliverables:

- **Chat tier 2 / tier 3 wired to query the ENTITY table** — replaces the pre-pivot River Scene events catalog query at `app/chat/tier2_db_query.py:33+`
- **Chat awareness of boat-access mode** — when active, queries filter by `boat_access IS NOT NULL`; tier 3 LLM prompt gets a "user is in boat mode" preamble
- **Chat awareness of conditions** — when heat advisory active, ranking shifts toward indoor venues per Opus #2; when AQI bad, similar. Uses a stub temperature constant until Phase 8 wires real AirNow + NWS + USGS data — mirrors Phase 6.3's `STUB_CURRENT_TEMPERATURE_F` pattern in `app/core/ranking.py`.
- **HALT 3 close-out** — confabulation guardrails ship; `FEATURE_FLAG_DISCLOSURE_RENDERER` flipped to `true` if validation passes
- **Cross-entity chat queries** — "where can I take my dog for breakfast?" returns dog-friendly restaurants AND dog parks interleaved
- **Snowbird-return view on homepage** — logged-in users active October-April see a "what's reopened" panel

## §2 Dependencies

- **Phase 1 (ENTITY schema)** — SHIPPED 2026-05-14
- **Phase 4 (background jobs + scrapers + reconciler)** — SHIPPED 2026-05-13
- **Phase 5 (Tier 1 data, all 13 categories populated)** — SHIPPED 2026-05-17 at Phase 5.11 close; STATE.md ledger landed at `3a2d895` 2026-05-19
- **Phase 6.1 (unified Hava card grammar)** — SHIPPED `fd16e7a` 2026-05-14
- **Phase 6.2 (category landing template + Eat & Drink proof)** — SHIPPED `3948add` 2026-05-15
- **Phase 6.3 (breadth pass — all 11 remaining slugs + district chip + ranking + seasonal hours)** — SHIPPED `5ebee46` 2026-05-19
- **Phase 8 (conditions data source)** — Phase 7 uses a stub until Phase 8 lands real AirNow + NWS + USGS data; the chat-conditions wiring is testable behind the stub

Phase 7 dispatches against `5ebee46` or later. **Parallel-eligible with Phase 6.4** (map view, boat-mode toggle, themed group landing pages, search bar): Phase 6.4 touches `app/templates/`, `app/static/`, the Leaflet/map JS surface; Phase 7 touches `app/chat/`, `app/api/routes/chat.py`, the LLM prompt surfaces. File-scope disjoint per gotcha #18.

## §3 What carries forward from Phase 5 + 6.3 into Phase 7

| Predecessor artifact / capability | Phase 7 reuse |
|---|---|
| ENTITY catalog (1,314 active entities; 12 active Tier-1 slugs + cat-13 thin) | Chat tier 2/3 queries read against this; cross-entity queries operate over the full catalog |
| `app/providers/queries.py` shared helpers (`is_open_now`, `effective_hours_structured`, `effective_seasonal_hours`, district eager-load) | Chat surfaces consume these for status + freshness signals; seasonal hours feed open-now chat predicates |
| `app/core/ranking.py` (Phase 6.3 — `compute_card_rank` + heat-bias + `STUB_CURRENT_TEMPERATURE_F`) | Chat ranking surfaces reuse for "indoor bias when hot" behavior; stub temperature constant is the same one Phase 7 reads until Phase 8 swaps in live conditions |
| Operator-curated `heat_exposure` + `boat_access` + `seasonal_hours` JSON fields (Phase 5 lanes) | Chat condition-awareness + boat-mode predicates query these directly |
| `tests/test_phase6_ranking.py` + `tests/test_phase6_seasonal_hours.py` patterns | Shape templates for chat-integration tests |
| `app/api/routes/category_pages.py` chip dispatcher (12 slugs) | Reference for category-aware chat surfaces if Phase 7 ships per-category chat tweaks |

## §4 Propagation checklist (refreshed)

- [x] `master_build_plan.md` §4 Phase 7 refreshed — **DONE 2026-05-19** (this commit; deliverables pruned, dependencies updated, effort revised M-L → M, success criteria simplified to "all 13 category slugs")
- [x] `master_build_plan.md` §5 dependency graph refreshed — **DONE 2026-05-19** (this commit; `Phase 6 ──→ Phase 7 (Tier 2 + chat)` → `Phase 6.3 ──→ Phase 7 (chat + HALT 3)`)
- [x] This hand-off note refreshed — **DONE 2026-05-19** (this commit; SUPERSEDED-IN-PLACE banner + §1–§5 rewrites; original framing preserved in git history)
- [ ] `STATE.md` "Now / Next / Later" — **PENDING**: when Phase 7 dispatches, prepend a "Recently shipped" entry with the actual scope after Phase 7 ships
- [ ] Phase 7 dispatch prompt (`outputs/cursor_dispatch_prompt_phase_7.md`) — **PENDING**: author when ready to dispatch; can mirror 6.1/6.2/6.3 dispatch shape

## §5 What Phase 7 does NOT include

- **NO category landing pages.** All 12 active Tier-1 slugs have landing pages from Phase 6.2 (Eat & Drink) + 6.3 (the other 11). Phase 7 doesn't ship UI for any category.
- **NO themed group landing pages.** Those are Phase 6.4 (Outdoors, Stay, Things to Do, Eat & Drink themed groups) per master plan §4 Phase 6 deliverables list.
- **NO map view.** Phase 6.4.
- **NO new data gathering.** All Tier-1 categories shipped data in Phase 5.1–5.11. Phase 8 will land Public & Civic Resources expansion (cat-13 currently at 4 entries).
- **NO real conditions data.** That's Phase 8's AirNow + NWS + USGS wiring. Phase 7 uses a stub temperature constant for the chat-conditions-awareness path (mirroring Phase 6.3's `STUB_CURRENT_TEMPERATURE_F`).
- **NO district paragraph rendering.** V1.5 per the path-b lock — Phase 6.3 ships only the district chip, paragraph rendering is intentionally deferred.
- **NO sponsor logic.** Phase 11.

---

*Authored by Cowork primary at the new-chat post-`2f4676a` session (2026-05-14); refreshed 2026-05-19 post-Phase-5 restructure + Phase 6.3 breadth pass. Lives at `outputs/phase7_handoff_note.md`. The 2026-05-14 framing of "Tier 2 UI + Tier 2 data gathering" is preserved in git history; current scope is single-strand chat + HALT 3 close-out + cross-entity + snowbird.*
