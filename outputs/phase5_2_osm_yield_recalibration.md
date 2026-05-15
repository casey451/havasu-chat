# Phase 5.2 — OSM Layer 2 yield recalibration

> **What this is:** a finding from the §0 pre-flight + smoke test of the new
> `osm_overpass_pull` JSONL writer (`fix(scripts)` commit `2ef4b3b`). The
> headline: LHC's OSM coverage on the three locked water tags is **much
> sparser than the runbook projected**, so Layer 2's contribution to Phase
> 5.2 is going to be near-zero, not 5–15 ambiguous hits per pair. Downstream
> expectations (§2 ambiguous-queue triage, §6 acceptance gate) recalibrate
> below.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.2 session
> (2026-05-15) immediately after the smoke test of `2ef4b3b`.

---

## §1 What the bbox actually has

Direct Overpass query against the locked LHC bounding box
(`(34.43, -114.41, 34.59, -114.30)`, per
`app/contrib/osm_overpass_client.py:24`), measured 2026-05-15:

| Tag pair | Elements in bbox | **Named** (passes client filter) | Names |
|---|---|---|---|
| `leisure=marina` | 6 | **2** | Lake Havasu Marina (way 227901073), Havasu Cove (way 622179700) |
| `man_made=pier` | 114 | **0** | — |
| `natural=beach` | 11 | **0** | — |

The named filter lives at `app/contrib/osm_overpass_client.py:63-64`:

```python
if not tags.get("name"):
    continue
```

It's correct as-shipped — the reconciler's match strategies (`google_place_id`,
geo+name, name-only) all require a name. Unnamed OSM elements have nowhere to
land. But for LHC specifically the implication is that **Layer 2 yields ~2
named entities total** across the three locked pairs.

## §2 Why the runbook overestimated

The kickoff runbook (`outputs/phase5_2_on_the_water_kickoff.md` §2) cited
brief §3.2 — "5–15 ambiguous hits per OSM run." That projection assumed OSM
coverage typical of more-mapped urban areas. Lake Havasu City is at the
sparser end:

- Marinas: most are tagged but only the big-name ones carry `name=` tags.
  Site Six, Crazy Horse, Windsor Beach are likely the unnamed `way`s in
  the 6-element count.
- Piers: 114 unnamed pier ways suggest OSM mappers traced the **lake-edge
  geometry** (probably individual dock segments) without naming. None are
  legible as venues without geocoding back to a named parent feature.
- Beaches: 11 unnamed beach polygons — likely shoreline segments of London
  Bridge Beach / Rotary Park / Windsor Beach traced as `natural=beach`
  without a top-level name.

**This is not a Phase 5.2 problem** — Google Places carries names for all
these venues. OSM was always the supplemental layer; it's just supplementing
less than projected.

## §3 Recalibrated downstream expectations

### §2 ambiguous-queue triage

- **Old projection:** 5–15 ambiguous hits per OSM run; tune
  `GEO_PROXIMITY_THRESHOLD_M` if >50.
- **New projection:** ~0 ambiguous hits expected. The 2 named OSM marinas
  (Lake Havasu Marina, Havasu Cove) will almost certainly match Google
  Places entries via the geo+name strategy and resolve to `action="update"`
  (fill-gaps-only per the `1560bd2` priority fix) — not `action="ambiguous"`.
- **Triage work:** likely none. The §2 step is still required by the §6
  acceptance gate ("Google ↔ OSM ambiguous reconciler hits reviewed") but
  the actual review is "0 hits, gate satisfied trivially."

### §6 acceptance gate

- **Gate item 1 (25+ entries in `on-the-water` post-load):** comes ~entirely
  from Google Places (~280 enriched `lake_recreation` rows already in
  `enrichment_enriched.jsonl` per the runbook §1) + Layer 5 manual recovery.
  OSM contributes ~2 named rows or possibly 0 if both reconcile-update
  against Google entries.
- **Gate item 2 (every marina has `boat_access` JSON):** unchanged — depends
  on operator field entry, not on layer source.
- **Gate item 6 (Phase 6 `/category/on-the-water` + boat-mode toggle render
  ≥15):** unchanged — depends on the post-load entry count, which Google
  will carry on its own.

### Phase 6.4 coordination

The Phase 6 agent's eventual 6.4 build (map water-overlay + boat-mode
toggle) consumes `boat_access` JSON. The yield-recalibration doesn't
affect them — they already render off any entries with non-NULL
`boat_access`, regardless of which layer found them.

## §4 The silent-failure side issue

Separately surfaced by the smoke test: the OSM client returns `[]` on
non-200 / `httpx.RequestError` / `ValueError` (JSON parse), with the
transport error logged at `WARNING` level (`osm_overpass_client.py:53`).
The pull script (`scripts/osm_overpass_pull.py`) doesn't configure logging
output, so warnings are invisible. The 2026-05-15 smoke test reported 0
marinas when Overpass actually had 6 — most likely the call hit a transient
non-200 (rate-limit / server hiccup) and silently returned empty.

**Fix candidates** (not blocking; queue for follow-on if it bites again):

- Add `logging.basicConfig(level=logging.INFO)` to `osm_overpass_pull.py`
  so the client's WARNING surfaces.
- Print a heuristic note: "0 results — Overpass may have throttled; retry
  in 30s before assuming the bbox is empty."
- Distinguish empty-result-from-Overpass (Overpass returned `200 OK` with
  `elements=[]`) from transport-failure-returning-empty (silent `[]` after
  non-200) by surfacing the HTTP status code.

These are ~5–10 LOC, `scripts/` + `app/contrib/` scope, no behavior change
for happy-path runs.

## §5 What to do now

1. **Retry the pull once:**
   ```powershell
   python -m scripts.osm_overpass_pull --tag leisure --value marina
   ```
   Expected output (per the 2026-05-15 sandbox sanity-check):

   ```
   Discovered 2 leisure=marina elements from OSM
     Lake Havasu Marina @ (lat, lng)
     Havasu Cove @ (lat, lng)
   Wrote 2 elements -> C:\Users\casey\projects\havasu-chat\scripts\output\osm_pull\osm_elements.jsonl
   ```

   If still 0 after a retry, the silent-failure issue (§4) is likely
   biting — schedule the visible-logging fix before §1 Layer 2.

2. **Skip the full §1 Layer 2 pull-and-load sequence until §1 Layer 1
   (Google) is done.** OSM should run *after* Google per the runbook order;
   we just need confirmation now that the pull tooling reaches Overpass
   reliably.

3. **Proceed to §1 Layer 1 Google Places scrape (Task #2).** That's where
   the bulk of the 25+ gate-item comes from anyway.

---

## §6 Reference

- `app/contrib/osm_overpass_client.py:24` — `LHC_BOUNDING_BOX`
- `app/contrib/osm_overpass_client.py:63-64` — the named-only filter
- `app/contrib/osm_overpass_client.py:43-68` — `discover()` with silent
  non-200 / transport-error handling
- `scripts/osm_overpass_pull.py` — the just-shipped JSONL writer
  (`2ef4b3b`)
- `outputs/phase5_2_on_the_water_kickoff.md` §2 — the original
  ambiguous-queue projection
- `outputs/phase5_2_on_the_water_kickoff.md` §6 — the acceptance gate

---

*Pre-staged by Cowork primary, Phase 5 lane, Phase 5.2 session
(2026-05-15) post-`2ef4b3b`. Operator-driven retry of the pull is the next
step; if successful, queue Task #2 (§1 Layer 1 Google scrape). Not a
Cursor dispatch — informational artifact + retry instructions.*
