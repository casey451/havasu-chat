# Lane D + E Post-Ship Close-Out Template

> **What this is:** the reusable Cowork-primary rhythm for closing out Phase 6.4 (Lane D) and Phase 7 (Lane E) when Cursor returns with the §12 final report. Pre-positioned 2026-05-20 so the review-commit-ledger sequence is fast when either Cursor session lands.
>
> **Author:** Cowork primary, 2026-05-20 post-`848524b` (dispatch-pre-position state).
>
> **Use either lane independently** — the template is generic to either ship. If both lanes ship around the same time, run the rhythm twice (one commit batch per lane; do NOT bundle Lane D ships + Lane E ships into a single commit batch since their work units are logically distinct).

---

## §1 Pre-flight verification (do this BEFORE declaring ship)

Run these checks against the working tree where Cursor left files:

```powershell
# 1. Confirm Cursor did NOT git-commit (constraint per wrapper: "No git add / commit / push / amend")
git status --short
# Expected: many M / ?? lines for Cursor's changes; NO commits on HEAD beyond the dispatch-pre-position SHA

# 2. Confirm alembic head matches Cursor's §12 claim
python -m alembic current
# Lane D expected: new revision SHA (post users.boat_mode_preference migration, chained from f6a7b8c9d0e1)
# Lane E expected: f6a7b8c9d0e1 IF User.last_active_at already existed at dispatch
#                  OR new revision SHA if User.last_active_at migration shipped

# 3. Confirm pytest collected count matches Cursor's §12 claim
python -m pytest --collect-only -q | tail -3
# Lane D expected: 2090-2110 (2060 baseline + 30-50 net-new)
# Lane E expected: 2110-2140 (2060 baseline + 50-80 net-new)

# 4. Confirm pytest passes
python -m pytest -q
# Both lanes: all green; pre-existing 2058 passed + 2 skipped must remain green

# 5. Confirm ruff clean
ruff check app/ tests/
# Should report 0 issues
```

**If any of 1–5 diverges from Cursor's §12 claim:** STOP. Re-read Cursor's report against the wrapper acceptance gates. If divergence is benign (e.g., Cursor reported "alembic head: f6a7b8c9d0e1" but the actual head moved to the new migration SHA — session-2026-05-19 lesson #6 pattern), narrate the truth in the commit body and proceed. If divergence is substantive (e.g., test failure, ruff red, wrong file scope), don't commit — clarify with Cursor in a follow-up paste OR roll back its changes.

---

## §2 Acceptance-gate review

For each wrapper deliverable, verify Cursor's work matches the spec.

### Lane D (Phase 6.4) acceptance gates

| # | Deliverable | Verification |
|---|---|---|
| a | Leaflet+OSM map view with marker clustering | GET `/api/map_data/eat-drink` returns 200 + valid JSON shape with marker list; marker count caps at 500 with `truncated_at_n:true` flag above; `app/static/js/map.js` loads Leaflet from cdnjs; click navigates to `/provider/<slug>` |
| b | Boat-access mode toggle (URL + localStorage + User pref) | Alembic migration chains from `f6a7b8c9d0e1`; `users.boat_mode_preference` column exists with `sa.false()` default; `?boat=1` filter applied in category route; `app/static/js/boat_mode.js` reads URL > localStorage > User col; `body.boat-mode-active` CSS class toggles correctly |
| c | 4 themed group landing pages | GET `/group/eat-drink-group`, `/group/health-fitness-group`, `/group/on-the-water-group`, `/group/home-auto-group` all return 200 + render interleaved Hava cards; THEMED_GROUPS dict at `app/groups/themed_groups.py` matches the 4-group lock |
| d | Search bar separate from Ask Hava | Homepage hero contains search bar at `<!-- search-bar-include -->` anchor; category page headers contain search bar; search bar CSS class distinct from Ask Hava button; hits `/api/search` from Phase 2B.3 |
| – | Tests | 4 new test files: `test_phase6_map.py`, `test_phase6_boat_mode.py`, `test_phase6_themed_groups.py`, `test_phase6_search_ui.py`; pytest +30–50 net-new |

### Lane E (Phase 7) acceptance gates

| # | Deliverable | Verification |
|---|---|---|
| a | Chat tier 2/3 wired to ENTITY table | `app/chat/tier2_db_query.py` no longer references pre-pivot River Scene events catalog at line ~33+; queries read from entities + EntityCategory via strict join (6.2 pattern); manual smoke `where can I get coffee` returns ENTITY records, not pre-pivot River Scene events |
| b | Chat boat-mode awareness | Context builder reads `?boat=1` / header / session-state; tier 2 query filters by `Entity.boat_access IS NOT NULL` when active; tier 3 LLM prompt prepends boat-mode preamble |
| c | Chat conditions awareness | Reuses `STUB_CURRENT_TEMPERATURE_F` from `app/core/ranking.py` (NOT a new chat-local constant); tier 2 query applies `compute_card_rank` heat-bias when temp > 100°F; tier 3 prompt gets heat-bias preamble when active |
| d | HALT 3 close-out | `app/chat/halt3_eval_set.yaml` exists with 20–30 queries; `app/chat/halt3_validator.py` runs the set; validator returns per-query report; 100% disclosure-pipeline coverage on cited responses; 0 confabulation on missing-data; FEATURE_FLAG_DISCLOSURE_RENDERER NOT flipped (operator does that out-of-band) |
| e | Cross-entity queries | Multi-domain intent detection in `intent_classifier.py`; "dog-friendly breakfast" test returns interleaved cat-1 + cat-7 + cat-11 entities; single-domain queries still category-lock (regression guard) |
| f | Snowbird-return view | `app/templates/components/snowbird_panel.html` exists; `home.html` has `{% include 'components/snowbird_panel.html' %}` at `<!-- snowbird-panel-include -->` anchor; panel renders for logged-in Oct-Apr user; absent for anonymous + May-Sep + stale `last_active_at` |
| – | Tests | 6 new test files: `test_phase7_chat_entity_wiring.py`, `test_phase7_chat_boat_mode.py`, `test_phase7_chat_conditions.py`, `test_phase7_halt3_validation.py`, `test_phase7_cross_entity.py`, `test_phase7_snowbird.py`; pytest +50–80 net-new |

---

## §3 Cursor §12 report review checklist

Cursor's §12 final report (per Phase 4 §12 format) typically includes:

1. **Files touched** — cross-reference against the wrapper's "Expected files touched" list. Flag any extra files (could be deviations or scope creep) and any missing files (could be deferred work).
2. **Pytest count** — actual collected count + delta from baseline. Verify the claim against `python -m pytest --collect-only -q | tail -3` (session-2026-05-19 lesson #6).
3. **Alembic current** — actual head. Verify against `python -m alembic current`.
4. **Ruff status** — should be clean. If not, follow up with a fixup commit (session-2026-05-19 pattern at `5ebee46`).
5. **§13 deviations** — pragmatic departures Cursor made from the wrapper. Review each:
   - For each, decide: accept (most common), reverse (rare; only if it breaks acceptance gate), defer (note as V1.5 carry).
   - The wrapper enumerated 7–10 expected deviations per lane; check Cursor's reported set against that list.
6. **HALT report** — Cursor should have halted at the wrapper's specified boundary (`§3 Phase 6.4 boundary` or `§3 Phase 7 boundary`). If Cursor went further, flag and decide whether to keep the extra work or pull back.

**Red flags requiring follow-up dispatch:**
- Pytest red after Cursor's work
- Ruff red
- Cursor's `alembic current` claim disagrees with reality (session-2026-05-19 lesson #6 — common; Cursor often copies the dispatch-body-claimed value)
- File scope crossed into the parallel lane (Lane D into `app/chat/` or Lane E into `app/templates/category_landing.html` etc.)
- Acceptance gate visibly unmet

---

## §4 Commit batch recommendation (Rule 8)

**Default for either lane: single substantive commit + 0–1 fixup commits.**

### Lane D commit batch (typical)

```powershell
# Stage all of Cursor's 6.4 changes
git add app/ tests/ alembic/

# Substantive feat commit
git commit `
  -m "feat(phase6.4): Leaflet+OSM map + boat-access mode + 4 themed group landing pages + search bar" `
  -m "Per master plan sec4 Phase 6 remaining deliverables. (a) Leaflet+OSM map view via app/static/js/map.js with leaflet.markercluster from cdnjs; GET /api/map_data/<slug> returns up to 500 markers with truncated_at_n flag above. (b) Boat-access mode via URL ?boat=1 + localStorage hava.boat_mode + users.boat_mode_preference column (new alembic migration chaining from f6a7b8c9d0e1); category route filters by Entity.boat_access IS NOT NULL when active; provider profile renders top-of-fold boat-access region when active. (c) 4 themed group landing pages at /group/<slug> via app/groups/themed_groups.py + new themed_groups.py route + new themed_group_landing.html template; group-to-category mapping: eat-drink (cat-1 single), health-fitness (cat-5+cat-12), on-the-water (cat-3 single), home-auto (cat-4+cat-9). (d) Search bar in homepage hero + category page headers via app/static/js/search_bar.js + search.css; separate from Ask Hava button per master plan sec8 OQ 11." `
  -m "Pytest <PRE_COUNT> -> <POST_COUNT> (+<DELTA> net-new across 4 test files). Alembic head <PRE_HEAD> -> <NEW_HEAD>. Ruff clean. <CURSOR_DEVIATIONS_NARRATIVE>"
```

### Lane E commit batch (typical)

```powershell
git add app/ tests/

git commit `
  -m "feat(phase7): chat ENTITY wiring + boat-mode + conditions + HALT 3 close-out + cross-entity + snowbird-return view" `
  -m "Per master plan sec4 Phase 7 (refreshed 2026-05-19 at c1d9ed2). (a) Chat tier 2/3 wired to ENTITY table; replaces pre-pivot River Scene events catalog query at app/chat/tier2_db_query.py:33+. (b) Chat boat-mode awareness via context_builder.py; tier 2 filters by boat_access IS NOT NULL; tier 3 LLM gets boat-mode preamble. (c) Chat conditions awareness reuses STUB_CURRENT_TEMPERATURE_F from app/core/ranking.py; heat-bias fires at temp > 100F. (d) HALT 3 close-out: 20-30 query eval set at app/chat/halt3_eval_set.yaml + validator at app/chat/halt3_validator.py; CI-runnable; 100pct disclosure-pipeline on cited + 0 confabulation on missing-data; FEATURE_FLAG_DISCLOSURE_RENDERER NOT flipped (operator does out-of-band post-validation). (e) Cross-entity queries via intent_classifier.py multi-domain detection; interleaved compute_card_rank ordering. (f) Snowbird-return view via new app/templates/components/snowbird_panel.html + helper; logged-in users in Oct-Apr window see what-reopened panel." `
  -m "Pytest <PRE_COUNT> -> <POST_COUNT> (+<DELTA> net-new across 6 test files). Alembic head <PRE_HEAD> -> <POST_HEAD>. Ruff clean. <CURSOR_DEVIATIONS_NARRATIVE>"
```

### Fixup commit pattern (when ruff red after feat commit, per `5ebee46` precedent)

```powershell
ruff check --fix app/ tests/
git add <fixed_files>
git commit `
  -m "fix(phase<X>): ruff <RULE> in <PATH> (CI follow-up to <FEAT_SHA>)"
```

---

## §5 STATE.md + master plan ledger updates

### STATE.md prepend (top of Recently shipped section)

For Lane D:

```markdown
- **Phase 6.4 (2026-05-XX, commit `<SHA>`):** Leaflet+OSM map view + boat-access mode + 4 themed group landing pages + search bar shipped. Map view via app/static/js/map.js with marker clustering (cap N=500, truncated_at_n flag above); GET /api/map_data/<slug> endpoint. Boat-access mode via URL param + localStorage + new users.boat_mode_preference column (alembic migration `<NEW_HEAD>` chains from f6a7b8c9d0e1); category route filters + provider profile boat-access top-of-fold region. 4 themed group landing pages at /group/<slug> via new app/groups/themed_groups.py + new themed_groups.py route + new themed_group_landing.html template. Search bar in homepage hero + category page headers, separate from Ask Hava button. Pytest <PRE> → <POST> (+<DELTA> net-new). Ruff clean. <DEVIATIONS_NARRATIVE>. Phase 6.4 lane commit chain: <SHA_LIST>. Close-out index: `outputs/lane_d_e_post_ship_close_out_template.md` (this template) instantiated as `outputs/phase_6_4_close_out.md`.
```

For Lane E:

```markdown
- **Phase 7 (2026-05-XX, commit `<SHA>`):** Chat ENTITY wiring + boat-mode awareness + conditions awareness + HALT 3 close-out + cross-entity queries + snowbird-return view shipped. Chat tier 2/3 wired to ENTITY table; replaces pre-pivot River Scene query at app/chat/tier2_db_query.py:33+. Boat-mode awareness via context_builder.py + tier 3 LLM preamble. Conditions awareness reuses STUB_CURRENT_TEMPERATURE_F from app/core/ranking.py (Phase 8 swaps in live data). HALT 3 close-out: 20-30 query eval set + CI-runnable validator; 100pct disclosure-pipeline on cited + 0 confabulation on missing-data; FEATURE_FLAG_DISCLOSURE_RENDERER flip pending operator out-of-band action post-validation. Cross-entity queries via multi-domain intent + compute_card_rank interleaving. Snowbird panel at home.html (snowbird-panel-include anchor) for logged-in Oct-Apr users. Pytest <PRE> → <POST> (+<DELTA> net-new). Ruff clean. <DEVIATIONS_NARRATIVE>. Phase 7 lane commit chain: <SHA_LIST>. Close-out index: instantiated as `outputs/phase_7_close_out.md`.
```

### master_build_plan.md §4 Phase 6 / Phase 7 ship-line append

For Lane D (under `### Phase 6 — Tier 1 UI build` → `**Shipped (incremental):**` subsection, appended below the Phase 6.3 entry):

```markdown
- **Phase 6.4 — Map view + boat-access mode + 4 themed group landing pages + search bar (2026-05-XX, commit `<SHA>`):** Fourth sub-phase of Phase 6 shipped — completion of the Tier 1 UI breadth layer with cross-category browse + spatial + filter surfaces. [Then 2-3 sentences narrating the deliverables + a deviations note per Cursor's §13 report.]
```

For Lane E (under `### Phase 7 — Chat + HALT 3 + cross-entity + snowbird view` — replace the placeholder "PENDING" or add "**SHIPPED**" header):

```markdown
**SHIPPED `<SHA>` 2026-05-XX** — All Phase 7 deliverables landed. [Then 3-5 sentences narrating: chat ENTITY wiring; boat-mode + conditions awareness via shared STUB; HALT 3 eval set + validator infrastructure shipping behind the still-false flag awaiting operator validation; cross-entity queries via intent_classifier.py; snowbird-return view on home.html. Pytest <PRE> → <POST>. Phase 7 lane commit chain: <SHA_LIST>.]
```

---

## §6 Post-ship verification

```powershell
# After commits land, push
git push origin main

# Re-confirm head + alembic + log shape
git log --oneline -5
python -m alembic current
python -m pytest --collect-only -q | tail -3

# CI sanity (GitHub Actions runs automatically on push)
# Verify the next GitHub Actions run is ✓ green within ~5 minutes
```

If CI red post-push: most common cause is the ruff red pattern from Phase 6.3's `04f7aa3 → 5ebee46` recovery (single I001 import-sort). Apply the same `ruff check --fix` + fixup commit pattern.

---

## §7 Deviation triage (Cursor's §13 flags)

Cursor's report typically includes a `§13 Deviations` section. For each flagged deviation:

| Deviation type | Default disposition |
|---|---|
| Pragmatic placement (e.g., helper module location) | **Accept** unless the wrapper had a hard lock; narrate in commit body |
| Heuristic tuning (e.g., heat-bias threshold) | **Accept** if Cursor's reasoning is sound; narrate; consider noting as V1.5 revisit candidate |
| Scope creep (Cursor shipped extra deliverable) | **Discuss** — if the extra deliverable is in the parallel lane's scope, it's a gotcha #18 violation; pull back. If it's wrapper-adjacent, accept + narrate. |
| Acceptance gate not met | **Reverse** — follow-up dispatch to close the gap before commit |
| New dependency added | **Discuss** — wrapper said "no new Python dependencies"; default reverse |

Record each deviation's disposition in the commit body OR in an `outputs/phase_<X>_close_out.md` artifact for future-session reference.

---

## §8 Carries forward (queue for next session)

After Lane D ships, the natural next major lane is Phase 6.5 (homepage rebuild + 8 themed group tiles + "What's on at this venue" region hook) OR Phase 7 (if still in flight) OR Phase 8 (trust layer + conditions panel + alerts; gated on Phase 7 close-out for HALT 3 contract).

After Lane E ships, the natural next major lane is Phase 8 (conditions data swap from STUB to AirNow + NWS + USGS — also enables the HALT 3 flag flip's full validation surface) OR Phase 6.5 OR Phase 6.4 (if still in flight).

If BOTH ship: next major lane is Phase 8 OR Phase 6.5. Operator decides.

Standard carries that persist across ships:
- **Untracked-file cleanup** (from 2026-05-19 close-out §4): operator prunes when comfortable
- **Pytest count drift 2018↔2016** investigation (carry from 2026-05-19 close-out §4): if not resolved this session, persists
- **Google Places API key rotation** (deferred per operator: "all keys will be changed at the conclusion of this project")
- **V1.5 triage doc operator decisions** (triage §8 #2 re-tag #8 to Phase 9; triage §8 #4 confirm Phase 13 as V1.5 backlog home)

---

*Authored by Cowork primary at the post-`848524b` dispatch-pre-position session (2026-05-20). Lives at `outputs/lane_d_e_post_ship_close_out_template.md`. Instantiate as `outputs/phase_6_4_close_out.md` (Lane D ship) and/or `outputs/phase_7_close_out.md` (Lane E ship) when Cursor returns.*
