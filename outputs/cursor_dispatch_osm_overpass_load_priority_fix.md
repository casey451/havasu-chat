# Cursor Dispatch — `osm_overpass_load.py` source-priority-aware update branch

> **Operator note:** paste the fenced block below into a fresh Cursor chat. This is a
> small, bounded fix (~30 min) — the `osm_overpass_load.py` reconciler `update` branch
> currently clobbers higher-priority source data. **Dispatch this before the Phase 5.2
> "On the Water" OSM load step runs** (it's GATE 2 in `outputs/phase5_2_on_the_water_kickoff.md`).
> This is task #5 in the Cowork task list.
>
> **Why pre-staged now:** the diagnostic context (the `osm_overpass_load.py` review, the
> `places_load.py` comparison, the reconciler `SOURCE_PRIORITY` semantics) is fresh from the
> Phase 5.0 tooling review. Capturing the dispatch now means Phase 5.2 just pastes it rather
> than re-deriving the diagnosis.
>
> **Scope lock (gotcha #18):** touches `scripts/osm_overpass_load.py` +
> `tests/test_phase5_osm_overpass_load.py` ONLY. Strict-disjoint from the parallel Phase 6 lane.

---

```
You are a Cursor session fixing a source-priority bug in scripts/osm_overpass_load.py for
the havasu-chat project (a Lake Havasu City local-business directory). The script was
shipped in commit 5d429aa as part of the Phase 5.0 lead-up tooling. It works, pytest is
green, but its reconciler `update` branch has a data-quality bug that bites in Phase 5.2.

## §0 Baseline + reads

1. `git log --oneline -8` — confirm origin is on the post-5d429aa chain. If unfamiliar
   commits appear, the parallel Phase 6 chat pushed — pull origin/main first.
2. `git status` — clean.
3. `python -m alembic heads` — single head `0a1b2c3d4e5f`. No migrations in this dispatch.
4. `python -m pytest -q --collect-only 2>&1 | tail -3` — record the baseline collected count.
5. Read these before changing anything:
   - `scripts/osm_overpass_load.py` — the file you're fixing; focus on `ingest_rows()`, the
     `rec.action == "update"` branch (~lines 241-266) and `_osm_provider_kwargs()` (~lines 161-186)
   - `app/contrib/ingest_reconciler.py` — `SOURCE_PRIORITY` (operator=0, google_places=1,
     osm=2, ...), `reconcile_hit`, `_compute_merge_fields`
   - `scripts/places_load.py` — the script `osm_overpass_load.py` mirrored; note its update
     branch does the SAME blanket `setattr` — do NOT change `places_load.py`, just understand it
   - `tests/test_phase5_osm_overpass_load.py` — the existing tests you'll extend

## §1 The bug

In `ingest_rows()`, the `rec.action == "update"` branch does:

    for field, val in kwargs.items():
        setattr(prov, field, val)

where `kwargs` comes from `_osm_provider_kwargs()` and includes `verified=False`,
`google_place_id=None`, `source="osm"`, plus `phone`/`website`/`address`/`description`/
`lat`/`lng` that may be `None` (OSM tag sparsity).

OSM is `SOURCE_PRIORITY` 2 — *below* `operator` (0) and `google_places` (1). When an OSM
hit reconciles as `update` against an existing higher-priority Provider (which happens on
"geo within 50m + name match" — common in on-the-water, where Google and OSM both cover
marinas/piers/beaches), the blanket `setattr` **downgrades** the existing row:
`verified` True→False, `google_place_id` set→None, `source` "google_places"→"osm", and good
Google contact fields get overwritten with OSM's sparser/None values.

## §2 The fix

On an OSM `update`, OSM data should only **supplement**, never **override**. Change the
`update` branch so that, for an existing Provider:

- **Never touch** `verified`, `google_place_id`, `source`, `category`, `category_id`,
  `lat`, `lng`, `tier`, `is_active`, `draft`, `pending_review`, `enrichment_version` — leave
  whatever the higher-priority source set.
- **Fill-gaps only** for `phone`, `website`, `address`, `description`: set the OSM value
  ONLY if the existing Provider field is `None` or empty-string, AND the OSM value is
  non-empty. Never overwrite a populated field.
- Still call `sync_provider_entity_from_legacy(session, prov)` after, and still apply
  `rec.merge_fields` to the Entity exactly as the branch does today (that part is correct —
  `_compute_merge_fields` is already priority-gated).
- The insert branch (new Provider, no collision) is unchanged — OSM data is the only source
  there, so the full `kwargs` write is correct.

A small helper like `_fill_gaps(prov, kwargs, fields=("phone","website","address","description"))`
keeps it readable. Keep the diff minimal and focused.

## §3 Tests

Extend `tests/test_phase5_osm_overpass_load.py` with cases proving:
- An OSM `update` against an existing `verified=True` Provider leaves `verified` True.
- An OSM `update` does not null out an existing `google_place_id`.
- An OSM `update` does not overwrite a populated `phone`/`website`/`address` with OSM data.
- An OSM `update` DOES fill a `phone`/`website`/`address` that was `None`/empty.
- The insert branch (no collision) still writes OSM data normally.
Mock/stub any externals; tests stay offline and deterministic.

After the change: `python -m pytest -q` (must stay green) + `python -m ruff check scripts/ tests/`
(must stay clean).

## §4 What NOT to do

1. No schema migrations — `verified`/`source`/`google_place_id` already exist.
2. Do NOT edit `places_load.py` — the same blanket-setattr pattern there is a separate,
   lower-risk question (google_places is the top non-operator priority, so a Google re-scrape
   overwriting with fresh Google data is mostly self-consistent). Out of scope here.
3. Do NOT edit anything outside `scripts/osm_overpass_load.py` + `tests/test_phase5_osm_overpass_load.py`.
4. No `entities.sources` JSON-array migration — comma-separated string in `entity.source` per
   the Phase 4.3 lock.

## §5 Close-out (§13)

Report: §13.1 what changed, §13.2 files touched, §13.3 pytest delta + ruff status,
§13.4 deviations + rationale, §13.5 operator commit instructions (PowerShell-safe `-m` body —
no embedded double-quotes per gotcha #16). HALT after — single bounded fix, one commit.
```

---

## Operator instructions

1. Confirm the working tree is clean Windows-side before pasting.
2. Paste the fenced block into a fresh Cursor chat. It's a single bounded fix — one HALT, one commit.
3. Review the diff + tests, then commit with Cursor's suggested PowerShell-safe body.

After this lands, GATE 2 in `outputs/phase5_2_on_the_water_kickoff.md` is cleared and the
Phase 5.2 OSM load step is safe to run.

---

*Authored by Cowork primary, Phase 5 lane, new-chat post-`5d429aa` session (2026-05-14),
while Phase 5.0's heat-exposure list (B2-c) runs through ChatGPT deep research. Lives at
`outputs/cursor_dispatch_osm_overpass_load_priority_fix.md` — brand-new `outputs/` file,
safe under the parallel-chat scope lock. Pre-stages task #5 so Phase 5.2 dispatches it
directly rather than re-deriving the diagnosis.*
