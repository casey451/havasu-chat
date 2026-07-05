# Hours ingestion — finding + fix plan
**Date:** 2026-07-05 · Read-only investigation. No code/data changed.

## Headline: the "hours gap" is mostly a measurement artifact
The earlier completeness scorecard reported hours ~100% missing. That measured the **structured `Hours` 1:N table** (`app/db/models.py:1187`), which holds only ~8 rows. But **Google opening hours ARE stored** on every enriched listing in `Provider.google_hours` (`models.py:130`), and the render resolver `app/providers/queries.py::effective_hours_structured` (L432) reads them as a fallback (`Hours` rows → `hours_structured` → `google_hours`, converting on the fly via `hours_helper.places_hours_to_structured`).

**Confirmed live:** the Restaurants leaf shows a live "Open now" pill on every card, and the Azul Agave profile reads **"Open now · Closes at 9 PM."** So hours already render for the ~2,000+ Google-enriched listings. The near-empty `Hours` table is a **propagation bug, not a data-acquisition failure.**

## Root cause (propagation)
- The bulk loader `scripts/places_load.py:214` maps Google hours into `google_hours` only — it never sets `Provider.hours_structured` and never creates `Hours` rows.
- `app/db/entity_dual_write.py:154` builds Entity `Hours` rows **only from `provider.hours_structured`** — which the Google pull left NULL. So 0 `Hours` rows for all Google listings → the "~8."

## Why fix it at all (since hours mostly render)
Everything that uses `effective_hours_structured` already works (profiles, open-now pills, chat tiers). The value of fixing is: **consistency** (the structured columns/table match what renders, so any feature keying on `hours_structured` or the `Hours` table behaves), filling the **genuine empties** (rows where Google returned no hours — map audit suggested ~26%, ~600 rows), and fixing a known **midnight-clamp artifact** (overnight closes render as `23:59` / "Closes 11:59 PM"; source at `hours_helper.py:135-136`).

**Priority: this is a cheap cleanup, not the urgent systemic gap it appeared to be.** Do it when convenient.

## The fix
**(a) Code PR (small, gated).**
- `scripts/places_load.py::row_to_provider_kwargs` (L180-231): also set `hours_structured = places_hours_to_structured(row["regular_opening_hours"])` so future loads populate the structured column.
- `app/db/entity_dual_write.py:154`: change `hs = provider.hours_structured` → `hs = provider.hours_structured or places_hours_to_structured(provider.google_hours or {})` so dual-write materializes `Hours` rows from `google_hours`. Add/adjust tests. Consider fixing the overnight midnight-clamp while here.

**(b) Backfill — $0, DB-only (gated data op).** For every Provider with non-empty `google_hours`: compute `hours_structured` via the existing converter and (re)generate Entity `Hours` rows. **No Google API calls needed** for these (~2,000+ rows). Mirror `scripts/backfill_*.py` (dry-run → counts → Casey approval → apply); write an undo snapshot.

**(c) Optional top-up — the genuine empties (~600 rows).** Only rows with NULL/empty `google_hours` need a fresh Google Place Details call (reusing the stored `place_id`; no re-discovery). Cost ≈ 600 × ~$0.040 ≈ **~$24**. **First check** whether the original raw responses are still on disk (`scripts/output/places_pull/enrichment_raw.jsonl`) — if so, re-parse for **$0**; only pay for what's truly missing.

## Code vs data-op + cost
- Code PR (a): small, no prod risk on its own.
- Backfill (b): prod data op, **$0** (pure DB UPDATEs/INSERTs), gated.
- Top-up (c): optional, ~$24 max (or $0 if the JSONL exists), gated.

## Recommendation
Ship (a) + (b) together as a cheap consistency win whenever you want the structured `Hours` table to match reality; treat (c) as an optional follow-up. Given hours already render for most listings, this is **not** blocking anything — lower priority than it first appeared.
