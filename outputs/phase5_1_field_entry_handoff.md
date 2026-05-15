# Phase 5.1 Eat & Drink — Scrape-Phase Close-Out + Field-Entry Handoff

> **Purpose:** the capstone for the **scrape half** of Phase 5.1 (discovery →
> enrichment → load) and the handoff into the **field-entry half** (§3 Layer-5
> manual recovery + §4 curated field entry). A fresh chat picking up Phase 5.1
> field entry should read this first — it's the index to what the scrape phase
> shipped, what state the DB is in, and what's still open.
>
> **Authored by:** Cowork primary, Phase 5 lane, the chat that ran the Phase 5.1
> scrape phase (2026-05-14). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock (this chat's scope: `app/contrib/`, `scripts/`,
> `app/db/`, `outputs/`).

---

## §1 What shipped this session

Origin advanced `0248936` → `038192d` (pushed). Three commits:

| Commit | Contents |
|---|---|
| `2d95962` | `chore(scripts)` — cleared the dead `relay/HAVA_BUSINESSES_...` doc reference from `places_enrichment.py` and `places_categories.json` (Phase 5.0 close-out drift finding 3 follow-on) |
| `7455848` | `feat(scripts)` — added a `--category` filter to `places_load.py` so per-category loads scope correctly off the shared `enrichment_enriched.jsonl` |
| `038192d` | `docs(scrape-logs)` — the eat-drink 2026-05-14 scrape log at `docs/scrape_logs/eat-drink_2026-05-14.md` |

Also updated this session (uncommitted at handoff authoring — operator commits):
`outputs/phase5_2_on_the_water_kickoff.md` — corrected the stale `places_load`
invocations to use `--category on-the-water`, and the §0 pre-flight to check
`alembic current` (DB state) rather than only `alembic heads` (migration-file head).

Alembic head unchanged (`0a1b2c3d4e5f`); no migrations shipped. Pytest baseline
unchanged (1825) — no test files added (`tests/` is outside this chat's scope).

---

## §2 Phase 5.1 status — scrape phase DONE, field entry remaining

The §1 scrape sequence from `outputs/phase5_1_eat_drink_kickoff.md` is **complete
and verified**:

- Discovery: 302 unique Place IDs across 36 `food_drink` labels
- Enrichment: all 302 enriched (the shared `enrichment_enriched.jsonl` carries
  2,540 rows total — see §4 finding 4)
- Load: **287 eat-drink providers + 287 entities** in `data/events.db`

**§6 acceptance gate — 2 of 5 met:**

| Gate item | Status |
|---|---|
| 60+ entries in `eat-drink` post-load | ✅ **287** |
| All ambiguous reconciler hits reviewed | ✅ 0 ambiguous — DB rebuilt empty, nothing to reconcile against |
| Top-20 entries have long-form `crowd_notes` | ⬜ field entry |
| `heat_exposure` set on every entry | ⬜ field entry |
| Phase 6 `/category/eat-drink` renders 15+ per default filter | ⬜ needs Phase 6 + the data |

The remaining three are the **field-entry phase** — operator-driven, self-paced
(~2h/day cap, ~7–22h over 1–2 weeks per the §5 rhythm).

---

## §3 DB state — important for the field-entry chat

- **`data/events.db` was rebuilt clean this session.** It is now at alembic head
  `0a1b2c3d4e5f` with a correct schema, holding exactly the 287 eat-drink
  providers + 287 entities and nothing else.
- **The old DB is backed up at `data/events.db.bak-20260514`** — it held 2,291
  providers, 875 `field_history` rows, 5,578 `chat_logs`, 200 `contributions`.
  The operator chose "rebuild clean" knowing that data is parked in the `.bak`
  (recoverable if ever needed; not in the live DB).
- **All 287 entities land with `heat_exposure` unset.** Field entry sets it per
  the `outputs/heat_exposure_priority_30_list.md` decision tree — default
  `indoor`, only priority-list venues tagged off-default.
- No `DATABASE_URL` in `.env` → the app + scripts use local SQLite
  (`data/events.db`). Phase 5.1's load target is local SQLite by operator
  decision; prod sync happens later, separately.

---

## §4 The 5 drift findings (matches the scrape log)

1. **`places_load.py` was not category-scoped — FIXED (`7455848`).** It read the
   entire shared `enrichment_enriched.jsonl` and would have loaded ~2,266
   providers across all 14 domains. Added a `--category` filter mirroring
   `places_discovery`'s `DISCOVERY_CATEGORY_TO_DOMAINS` resolution.
2. **Dead `relay/` doc reference — FIXED (`2d95962`).** Cleared from
   `places_enrichment.py` + `places_categories.json`.
3. **§0 pre-flight gap — `alembic heads` vs DB state.** The pre-flight checked
   the migration files' head, not whether the local DB was actually migrated to
   it. The 5.2 runbook has been corrected; future runbooks should check
   `alembic current` / run `alembic upgrade head`.
4. **`enrichment_enriched.jsonl` pre-populated + local DB inconsistent.** The
   enrichment file already held 2,525 (now 2,540) rows from a prior comprehensive
   all-domain scrape — **this is a head start, not pollution** (~280 enriched
   `lake_recreation` rows are Phase 5.2's Google layer, already done). The local
   `data/events.db` had an unmigratable inconsistent schema (a `create_all()`-built
   DB — which only creates *missing* tables — later stamped rather than migrated;
   `init_db()` in `app/db/database.py` has a `has_events → command.stamp(head)`
   branch that produces exactly this). Resolved by the §3 rebuild.
5. **`places_load` load summary omits reconciler counts — OPEN.** The
   `--- load summary ---` prints input/skipped/inserted/updated but not
   `reconcile_skipped_ambiguous` / `reconcile_merged_geo`, even though it tracks
   them and runbook §2 expects them surfaced. Cosmetic; ~2-line fix to the
   summary print in `scripts/places_load.py`. Mattered little for 5.1 (0
   ambiguous into an empty DB) — **matters for 5.2+**, which loads into a
   non-empty DB. See §5.

**Operational note:** the bash sandbox mount was unreliable three times this
session (truncated `places_categories.json`, phantom null-bytes in
`discovery_unique.jsonl`, couldn't open the rebuilt `events.db`). Consistent with
gotchas #4/#15 — treat Windows-side reads as authoritative; have the operator run
DB/file verification rather than the sandbox.

---

## §5 Carry-forward — open items

| Item | Where / what | When it's needed |
|---|---|---|
| **Drift #5 — `places_load` summary reconcile counts** | ~2-line fix to the summary print in `scripts/places_load.py` (in scope for the Phase 5 chat) | Before Phase 5.2's `places_load` run (5.2 loads into a non-empty DB, so ambiguous hits will actually occur) |
| **`filter_by_category` unit test** | `tests/` is outside the Phase 5 chat's file scope — needs a Cursor dispatch or a coordinated batch | Low priority; before Phase 5.2 ideally |
| **Task #5 — `osm_overpass_load.py` priority fix** | Cursor dispatch staged at `outputs/cursor_dispatch_osm_overpass_load_priority_fix.md` | Before the Phase 5.2 OSM load step |
| **Task #6 — real `az_roc_client.lookup_contractor`** | Stub today; needs an operator build-or-fallback decision | Before Phase 5.3 |
| **`master_build_plan.md` §4 ledger** | Needs a "Phase 5.0 SHIPPED" line *and* a Phase 5.1 scrape-phase progress note. **Shared doc (`docs/maintainability/`) — out of scope; coordinate with the Phase 6 agent or apply at a checkpoint** | At a checkpoint |
| **`STATE.md` refresh** | `outputs/state_md_refresh_supplement.md` (Phase 5.0) is still pending; this session adds the `init_db` stamp-branch footgun + the recurring bash-mount unreliability. **Shared doc — out of scope; coordinate** | At a checkpoint |
| **2 PROVISIONAL heat-list rows** | El Paraiso, College Street Brewhouse — `heat_exposure_priority_30_list.md` §2 | 30-second patio-shade confirm during field entry |
| **`boat_access_rubric.md` §3.4 Pier 19 defunct example** | Flagged in heat list §7/§9 — `docs/operations/` owner patches it | Outside Phase 5 chat scope |

---

## §6 What's next — Phase 5.1 field entry

The field-entry phase works from the **same runbook**,
`outputs/phase5_1_eat_drink_kickoff.md` — §0/§1 (pre-flight + scrape) are done;
**§3, §4, §5 are the live sections now**:

- **§3 Layer-5 manual recovery** — food trucks + meet-ups, River Scene magazine
  features, seasonal vendors, dock-and-dine spots Google misses. The English
  Village + Channel sweep is the highest-value field trip.
- **§4 curated field entry** — `heat_exposure` (decision tree:
  `heat_exposure_priority_30_list.md`), `crowd_notes` (short-form typical /
  long-form top-20), `boat_access` (shoreline restaurants only),
  `seasonal_hours` (snowbird venues). Enter via direct DB SQL or the existing
  `admin/*` HTML surfaces — no Phase 5 admin form.
- **§5 rhythm** — cap sessions ~2h/day; ~7–22h over 1–2 weeks.

When the §6 gate is fully met, Phase 5.1 gets its SHIPPED ledger line on
`master_build_plan.md` §4, and **Phase 5.2 On the Water** dispatches off
`outputs/phase5_2_on_the_water_kickoff.md` (updated this session — and that's
where task #5 fires).

---

## §7 Reference / read order for the field-entry chat

1. **This file** — the scrape-phase close-out + field-entry handoff.
2. `outputs/phase5_1_eat_drink_kickoff.md` §3/§4/§5 — the live field-entry runbook.
3. `outputs/heat_exposure_priority_30_list.md` — the LOCKED `heat_exposure` decision tree.
4. `docs/scrape_logs/eat-drink_2026-05-14.md` — the run record (counts, cost, drift).
5. `docs/STATE.md` — production state + gotchas (esp. #4/#15 bash-mount, #16 PowerShell `-m` quoting).
6. `outputs/phase5_0_close_out.md` — the prior sub-phase capstone (still the index for Phase 5.0 artifacts + the original carry-forwards).

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 scrape-phase chat
(2026-05-14). Lives at `outputs/phase5_1_field_entry_handoff.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. The Phase 5.1 scrape
phase is closed; field entry dispatches off `outputs/phase5_1_eat_drink_kickoff.md`
§3/§4/§5 with this file as the state index.*
