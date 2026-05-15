# Phase 5.1 Eat & Drink — Field-Entry Close-Out + State Index

> **Purpose:** the capstone for the **field-entry half** of Phase 5.1 (the back
> half — §3/§4/§5 of the kickoff runbook). Pairs with
> `outputs/phase5_1_field_entry_handoff.md`, which closed the *scrape* half. A
> fresh chat picking up Phase 5.1 — or Phase 5.2 — should read this to know what
> the DB holds, what's committed, and what's still open.
>
> **Authored by:** Cowork primary, Phase 5 lane, the chat that ran Phase 5.1 field
> entry (2026-05-15). Brand-new `outputs/` file — safe under the parallel-chat
> scope lock (`app/contrib/`, `scripts/`, `app/db/`, `outputs/`).

---

## §1 What this session did

Booted post-`1bb2572`; origin advanced to **`ca5489a`** across 7 pushed commits,
plus 2 uncommitted `outputs/` docs at authoring (this file + the AZ ROC dispatch —
operator commits).

| Commit | Contents |
|---|---|
| `d34d4c3` | `fix(scripts)` — drift #5: `places_load` summary surfaces reconciler counts |
| `1560bd2` | `feat(scripts)` — OSM priority fix: `osm_overpass_load` update branch is now fill-gaps-only (Cursor) |
| `d76db43` | `chore(outputs)` — field-entry staging batch 1 (heat_exposure, crowd_notes top-17, AZ ROC brief, boat_access, filter_by_category dispatch) |
| `aa2622d` | `test(scripts)` — `filter_by_category` unit test (Cursor) |
| `d9f7f3a` | `chore(outputs)` — eat-drink data-quality audit + cleanup SQL |
| `250fa6b` | `chore(outputs)` — runnable apply scripts (eat-drink cleanup + heat_exposure) |
| `ca5489a` | `chore(outputs)` — short-form crowd_notes batch 2 (eatery ranks 18-48) |

Three carry-forwards from the scrape-half handoff §5 were **cleared**: drift #5,
the `filter_by_category` test, and the OSM priority fix (was GATE 2 for Phase 5.2's
OSM load — now clear).

## §2 DB state — `data/events.db` after the field-entry applies

The operator ran four applies this session (all dry-run-then-real, all
independently verified by Cowork against a `/tmp` copy):

- **287 eat-drink** providers/entities total; **255 active** — `apply_eat_drink_cleanup.py`
  set `is_active = 0` on 32 (31 non-eateries + 1 duplicate "Lady Lee's" row).
- **`heat_exposure`: 0 NULLs** — `apply_heat_exposure.py` applied 7 LOCKED off-default
  tags + swept the rest to `indoor`. Distribution: `indoor 280, water_adjacent 5,
  shaded 1, outdoor 1`.
- **`crowd_notes`: 48 populated** — `apply_crowd_notes_top17.py` (17 long-form
  `{short, long}`) + `apply_crowd_notes_batch2.py` (31 short-only `{short}`).
- DB backed up Windows-side to `data/events.db.bak-20260515` before the applies.

`boat_access` was NOT applied — it's a field-survey worksheet, not a runnable
artifact (rubric §4 "don't guess booleans").

## §3 Phase 5.1 acceptance gate — 4 of 5 met

| Gate item | Status |
|---|---|
| 60+ entries in `eat-drink` post-load | ✅ 255 active |
| All ambiguous reconciler hits reviewed | ✅ 0 ambiguous (rebuilt-empty DB) |
| Top-20 entries have long-form `crowd_notes` | ✅ 17 applied (§3.3.h "14 eateries + 3 grocery anchors" reading) |
| `heat_exposure` set on every entry (no NULL) | ✅ 0 NULLs confirmed |
| Phase 6 `/category/eat-drink` renders 15+ per default filter | ⬜ **on the parallel Phase 6 agent** |

The 5th is the only thing between Phase 5.1 and a closed sub-phase, and it's not
in this lane's control.

## §4 Carry-forward — open items

| Item | Where / what | When |
|---|---|---|
| **Phase 6 render check** | gate item 5 — parallel Phase 6 agent verifies `/category/eat-drink` renders 15+ | closes Phase 5.1 |
| **AZ ROC client (task #6)** | Cursor dispatch staged: `outputs/cursor_dispatch_az_roc_client_playwright.md` (Option A — Playwright). Operator decides whether to take the `playwright` dependency, then dispatches. Option D (manual stopgap) is the fallback. | before Phase 5.3 |
| **2 PROVISIONAL heat-list confirms** | El Paraiso, College Street Brewhouse — patio-shade confirm on the field trip. `apply_heat_exposure.py` has them commented-out, ready to enable. | field trip |
| **`boat_access` survey** | `outputs/phase5_1_boat_access_candidates.md` — 12 shoreline venues, survey worksheet for the English Village + Channel field trip | field trip (5.2-rhythm) |
| **15 borderline rows** | data-quality audit §3 — convenience stores / butcher shops / etc.; keep-in-eat-drink vs recategorize. Currently left active. | operator decision |
| **`crowd_notes` long tail** | 48/255 done. ~99 more ≥100-review eateries available for follow-on batches; the sub-100 long tail is better as the operator's own pass (review signal too thin). Not a gate item. | optional completeness |
| **`master_build_plan.md` §4 + `STATE.md`** | Phase 5.1 SHIPPED line + STATE refresh — shared docs, out of this chat's scope. Draft when the gate fully closes; coordinate with the Phase 6 agent. | at gate closure |

## §5 Artifacts produced this session (all in `outputs/`)

**Runnable apply scripts** (all run + verified except where noted):
- `apply_eat_drink_cleanup.py` — ran, 32 deactivated ✅
- `apply_heat_exposure.py` — ran, 0 NULLs ✅
- `apply_crowd_notes_top17.py` — ran, 17 long-form ✅
- `apply_crowd_notes_batch2.py` — ran, 31 short-form ✅

**Staging / decision docs:**
- `phase5_1_heat_exposure_field_entry_staged.md` — heat_exposure SQL + reasoning
- `phase5_1_crowd_notes_top17_staged.md` / `phase5_1_crowd_notes_batch2_staged.md`
- `phase5_1_boat_access_candidates.md` — shoreline survey worksheet
- `phase5_1_eat_drink_data_quality_audit.md` — the 31 non-eateries + 15 borderline + dupes
- `phase5_1_eat_drink_cleanup_staged.md` — cleanup SQL + reasoning
- `az_roc_client_build_or_fallback_brief.md` — task #6 research, 4 options
- `cursor_dispatch_az_roc_client_playwright.md` — task #6 Option A dispatch
- `cursor_dispatch_filter_by_category_unit_test.md` — dispatched + done (`aa2622d`)

## §6 Read order for the next chat

1. **This file** — field-entry close-out + state index.
2. `outputs/phase5_1_field_entry_handoff.md` — the scrape-half close-out (still the index for the scrape phase + DB rebuild history).
3. `outputs/phase5_1_eat_drink_data_quality_audit.md` — what's in the load, what got deactivated, what's borderline.
4. `outputs/phase5_2_on_the_water_kickoff.md` — the next sub-phase runbook (task #5 OSM fix is already cleared; GATE 2 is green).
5. `docs/STATE.md` — production state + gotchas (#4/#15 bash-mount: read a `/tmp` copy of `events.db`, the mount can't open it directly; #16 PowerShell `-m` quoting).

## §7 Notes / lessons

- **The `/tmp`-copy DB read pattern works.** Gotcha #4/#15 confirmed again — the
  bash sandbox can't open `data/events.db` on the mount, but `cp` to `/tmp` then
  query the copy is reliable. Used for every DB read + verification this session.
- **The rebuilt-empty DB hid two true duplicates** (Lady Lee's, a vacation rental)
  — the reconciler had nothing to match against. Phase 5.2+ loads into a non-empty
  DB, so the reconciler runs for real; the drift #5 fix surfaces those counts.
- **`crowd_notes` JSON shape locked this session:** `{"short": str}` for typical
  venues, `{"short": str, "long": str}` for the top-20. Phase 6 reads the presence
  of `long` to distinguish list-blurb from profile-section. This shape reached the
  Phase 6 agent via the `d76db43` / `ca5489a` pushes.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (2026-05-15).
Lives at `outputs/phase5_1_field_entry_close_out.md` — brand-new `outputs/` file,
safe under the parallel-chat scope lock. The Phase 5.1 field-entry phase is
substantively done; the sub-phase closes when the Phase 6 `/category/eat-drink`
render check (gate item 5) passes.*
