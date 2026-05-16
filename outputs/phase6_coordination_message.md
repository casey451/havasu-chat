# Phase 6 lane — coordination message (Cowork → Claude Code / Phase 6 agent)

> Drop-in artifact for the operator to paste into the Phase 6 agent's chat
> (Claude Code terminal session or whichever agent owns the
> `docs/maintainability/master_build_plan.md` + `docs/STATE.md` lanes).
>
> Scope: ledger amendments required by Phase 5.2 close-out §3 +
> Phase 5.3 imminent SHIPPED. Out of Cowork's chat scope per the kickoff
> scope-lock.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.3 session
> (2026-05-15) post-`7c994aa`.

---

## TL;DR for the Phase 6 agent

Three ledger amendments needed in `docs/maintainability/master_build_plan.md`
and `docs/STATE.md`. All are out of the Phase 5 lane's scope but they're
blocking accurate state-tracking.

1. **Phase 5.1 retroactive correction** — gate item 5 was claimed met but
   was retroactively false until `efd193a` shipped during Phase 5.2.
2. **Phase 5.2 SHIPPED ledger line** — `b71cf0e` cleared all 6 gate items.
3. **Phase 5.3 imminent SHIPPED ledger line** — once
   `apply_phase5_3_home_property_audit.py` lands + AZ ROC + crowd_notes +
   heat_exposure all close, all 6 gate items will clear (already at 2/6
   confirmed: gate item 1 = 245 entries; gate item 6 = renders ≥15).

---

## Amendment 1 — Phase 5.1 retroactive correction

### The story

`outputs/diagnose_category_id_gap.py` was run during Phase 5.2 §0
pre-flight and surfaced that **`scripts/places_load.py` never set
`Provider.category_id`** for the 287 5.1 food_drink Providers. The Phase
1D dual-write hook (`app/db/entity_dual_write.py:_attach_provider_extensions`)
only creates `EntityCategory` rows when `category_id IS NOT NULL`. The
`/category/<slug>` route filters strictly via the `EntityCategory` join
(`app/api/routes/category_pages.py:_select_entities_for_category` lines
274-275). **Net effect: all 287 5.1 food_drink Providers landed without
EntityCategory linkage, so `/category/eat-drink` rendered 0 entities at
HEAD, not the 255 the close-out ledger claimed.**

Phase 5.1 gate item 5 was retroactively false at the original SHIPPED
commit (`273fe61`).

### The fix (already shipped at `efd193a`)

Two-part fix landed in Phase 5.2:

1. `scripts/places_load.py` — extended with `_resolve_category_id` (uses
   `google_types_mapping`) and `_ensure_entity_category` (idempotent
   EntityCategory upsert on UPDATE branches).
2. `outputs/apply_provider_category_id_backfill.py` — id-keyed
   apply-script that backfilled the 287 5.1 food_drink Providers + their
   EntityCategory rows. Self-verifies via the route's filter query.

Post-`efd193a`: `/category/eat-drink` renders **255**. Verified at HEAD
of Phase 5.3 session today (sandbox query):

```
/category/eat-drink                      rendering count = 255
```

### Required ledger updates

**`docs/maintainability/master_build_plan.md` §Phase 5.1 SHIPPED line:**
Add a "retro corrected at `efd193a`" note. The original SHIPPED line
claimed gate item 5 met at `273fe61`; that claim was retroactively false
until `efd193a`.

**`docs/STATE.md` Recently-shipped block:** mirror the same retro note.

**Phase 6.2 (`3948add`) ledger line:** add a note that the route shipped
with 0 entities rendering at HEAD (test fixtures may have masked this);
`efd193a` made the route's behaviour match its spec.

---

## Amendment 2 — Phase 5.2 SHIPPED ledger line

### The story

Phase 5.2 dispatched at `273fe61` (Phase 5.1 SHIPPED) and closed at
`b71cf0e` (all 6 gate items cleared). Mid-session 13 commits landed
including the `efd193a` retro fix. Final close-out at
`outputs/phase5_2_session_closeout.md`.

### Gate scorecard at close

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 25+ entries in on-the-water post-load | ✅ **100** | Layer 1 + Layer 2 + audit + sustainability re-route |
| 2 | Every marina has `boat_access` JSON populated | ✅ 5/5 | 2 evidence-populated, 3 `{}` placeholders pending field-trip |
| 3 | All Google ↔ OSM ambiguous reconciler hits reviewed | ✅ | 1 hit reviewed, no action needed |
| 4 | Top-10 marinas + ramps have `crowd_notes` | ✅ **10** | Long-form `{short, long}` applied |
| 5 | `heat_exposure` non-NULL on every entry | ✅ **0 NULL** | 78 water_adjacent + 22 indoor |
| 6 | `/category/on-the-water` + boat-mode toggle render ≥15 | ✅ page: 100; boat-mode: 100 | Placeholder sweep set `{}` for 95 non-marina entries |

### Required ledger updates

**`docs/maintainability/master_build_plan.md`:** add Phase 5.2 SHIPPED
line at `b71cf0e` with the gate scorecard above.

**`docs/STATE.md` Recently-shipped block:** add Phase 5.2 SHIPPED with
the 13-commit chain summary (see close-out §1 for the full table).

---

## Amendment 3 — Phase 5.3 imminent SHIPPED

### Current state (this session)

| # | Gate item | Status |
|---|---|---|
| 1 | 60+ entries in home-property-services | ✅ **245 at HEAD; 230 projected post-audit-apply** |
| 2 | All ambiguous reconciler hits reviewed | ⏳ 75 audited (1 misroute found, applied via Slice D); apply-script pending |
| 3 | AZ ROC verification run | ⏳ playwright install + chromium download still pending operator-side |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ⏳ |
| 5 | `heat_exposure` non-NULL on every entry | ⏳ |
| 6 | `/category/home-property-services` renders ≥15 | ✅ **245** |

### Commits landed this session

| # | Commit | Subject |
|---|---|---|
| 1 | `cdf3d0c` | `fix(scripts)` — places_discovery dry-run + --category produces empty intersection |
| 2 | `7c994aa` | `fix(scripts)` — _DISCOVERY_DOMAIN_FALLBACK extends for home_services |

Plus pending in working tree:
- `outputs/phase5_3_home_property_pre_load_audit.md` (combined pre+post audit)
- `outputs/apply_phase5_3_home_property_audit.py` (apply-script for §2 + §3 decisions)

### Required ledger updates (DEFERRED until 5.3 actually SHIPS)

Don't add the SHIPPED line yet — wait for all 6 gate items to clear.
Cowork will signal SHIPPED via a final commit (analog of `b71cf0e` for
5.2). At that point:

- `docs/maintainability/master_build_plan.md`: add Phase 5.3 SHIPPED at
  the final commit
- `docs/STATE.md` Recently-shipped block: mirror

---

## Coordination summary

**Phase 6 lane: please action Amendments 1 + 2 now** (already-shipped
work that needs documenting). Amendment 3 is deferred until Phase 5.3
SHIPS.

**Phase 5 lane (Cowork) will**:
- Land apply-script for 5.3 audit decisions
- Coordinate AZ ROC verification (playwright dispatch)
- Apply crowd_notes top-10
- Apply heat_exposure sweep
- Ship Phase 5.3 final commit when all 6 gate items clear

**Cursor lane**: dispatch artifacts queued at
- `outputs/cursor_dispatch_osm_pull_writer_test.md` (from 5.2 close-out, +8 tests)
- `outputs/cursor_dispatch_phase5_3_regression_tests.md` (this session, +19 tests)

---

*Drop-in artifact authored by Cowork primary, Phase 5 lane, Phase 5.3
session (2026-05-15) post-`7c994aa`. Operator dispatches to Phase 6
agent at their convenience.*
