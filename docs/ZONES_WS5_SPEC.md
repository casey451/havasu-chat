# WS-5 — Zones spec (DRAFT for Casey review, 2026-06-11)

**Status:** DRAFT — decision points marked ⚖. **Implements:** master plan
Track B2's third bullet ("WS-5 zones: In town / Nearby / Out of scope; gas
headline scoped"). Written without the original audit's WS-5 text (same
provenance caveat as the taxonomy rebuild spec — diff against it when
pasted).

## 1. Problem

A single-city directory quietly accumulates rows that aren't in the city:
Parker, Needles, Kingman, Bullhead City operators from regional feeds,
service businesses "serving Havasu" from elsewhere, and the Havasu Landing
casino (across the lake, California). Today nothing marks them, so they
count in headline numbers ("2,500+ local places", gas city average),
surface on "in Lake Havasu City" leaf pages, and erode the local-first
trust positioning. Zones make the boundary explicit and honest.

## 2. Zone model

Three values, stored not computed-per-request:

| Zone | Meaning | Surfaces |
|---|---|---|
| `in_town` | Inside Lake Havasu City proper | Everything, all headline counts |
| `nearby` | The functional lake region a local would drive to | Listed with a "Nearby — {place}" tag; excluded from "in Lake Havasu City" headline counts; included when a leaf would otherwise be thin |
| `out_of_scope` | Beyond the region | Hidden from browse/chat retrieval; soft state, not deletion (same bury-don't-remove philosophy as liveness) |

⚖ **D1 — boundary mechanism.** Options:
  a) **Zip allowlist (recommended):** `in_town` = zip ∈ {86403, 86404, 86406}
     (+86405 PO boxes). Cheap, explainable, and the WS-4 passes just
     backfilled zips. Fallback for no-zip rows: distance.
  b) Radius from city center (34.4839, -114.3225): in_town ≤ ~10 mi,
     nearby ≤ ~40 mi. Catches no-zip rows but misclassifies the airport/
     south-end edges and needs tuning.
  Recommendation: **a with b as fallback** — zip decides when present,
  distance decides for coordinate-only rows, NULL when neither exists
  (NULL renders as in_town today = no behavior change until backfilled).

⚖ **D2 — what counts as `nearby`.** Proposed: Parker, Parker Strip/
  Buckskin, Havasu Landing (CA), Topock/Golden Shores, Lake Havasu Ave
  south-end unincorporated pockets. Kingman, Bullhead/Laughlin, Needles =
  ⚖ Casey's call (locals DO drive to Laughlin; tourists asking Hava
  probably shouldn't be sent there by default).

⚖ **D3 — service-area businesses** (mobile, no storefront, Havasu in
  service area but based elsewhere): propose `nearby` + their existing
  "serves Lake Havasu City" copy, never `out_of_scope`.

## 3. Data model

`zone` String(16) nullable + CHECK ∈ {in_town, nearby, out_of_scope} on
**providers** (legacy read path) with the usual forward-compat mirror on
**entities** — same pattern as `liveness_score`/`primary_category`
(additive migration, NULL until backfill, NULL ⇒ treated as `in_town`).
Plus `zone_place` String(64) nullable ("Parker, AZ") for the Nearby tag
copy.

Backfill: `scripts/backfill_zones.py` (dry-run → counts → apply, snapshot —
the house pattern). Zip pass → distance pass → report NULL remainder for
the portal flag queue. Expected from the 2026-06-10 export: the overwhelming
majority of the 3,244 location rows are 864xx — the interesting output is
the exception list, likely a few dozen rows.

## 4. Surface changes (each one small once `zone` exists)

1. **Gas headline (the named WS-5 item):** city average + "N stations
   tracked" filter to `in_town`; nearby stations still listed below under a
   "Nearby" subhead (Topock's I-40 stations are often cheapest — locals
   want to SEE them, just not averaged into "Lake Havasu City average").
2. **Leaf pages / counts:** headline count = in_town; nearby rows render
   after in_town rows with the tag. `LEAF_PAGE_MIN_PROVIDERS` gate counts
   in_town + nearby (a thin leaf with 2 town + 1 Parker operator should
   still render) — ⚖ D4 confirm.
3. **Chat retrieval:** Tier-3 candidate filter excludes `out_of_scope`;
   nearby rows get their tag in card copy ("in Parker — about 40 min").
4. **Home "2,500+ local places" claim:** switches to the in_town count —
   honesty fix, same family as the audit's trust items.
5. **Sitemap/SEO:** out_of_scope provider pages drop from the sitemap
   (still 200 — they're real businesses, just not promoted).

## 5. Sequencing

Migration + backfill script + portal exception queue (one PR) → gas
headline + leaf/count surfaces (second PR) → chat filter (coordinates with
C-track's retrieval work — same seam as `_QUERY_TO_LEAF`). Nothing blocks
B3/B4; zones touch different columns.

## 6. Open decisions recap (⚖)

D1 boundary mechanism (rec: zip-first) · D2 the nearby place list (rec:
Parker/Buckskin/Havasu Landing/Topock yes; Laughlin/Kingman/Needles =
Casey) · D3 service-area rows = nearby (rec: yes) · D4 thin-leaf gate
counts nearby (rec: yes).

With D1–D4 answered in chat, the first PR is a one-session build.
