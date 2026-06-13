# Ask Hava — Phase 4 catalog re-tagging (DRY RUN)

**Date:** 2026-06-12 · **Author:** Cowork session · **Status:** Dry-run analysis — **NO database writes performed**
**Pairs with:** `ASK_HAVA_CHAT_QA_DIAGNOSTIC_2026-06-12.md`, `..._REMEDIATION_PLAN_...md`
**Source:** `subcategory_audit_20260611T201931Z.csv` (committed catalog snapshot, 2,441 entities)
**Output:** `askhava_catalog_retag_DRYRUN.csv` — 47 correction candidates, one row each.

Nothing here touches prod. This is the "dry-run → show counts → Casey approves → apply" gate from `CLAUDE.md`. I need your decisions on the 15 judgment rows before writing an apply script.

---

## Headline: the grab-bag is mostly a *retrieval* bug, not a data bug

The diagnostic's "Out on the water" grab-bag returned a detailing shop + two storage yards + two auto-repair shops. Checking the catalog, those auto/storage entities are tagged **correctly** (Britton's → auto-repair, Big Easy Storage → home-property/self-storage). They surfaced for a boat question anyway — which means the Tier-2 list path is falling back to an **unfiltered alphabetical slice** when it can't resolve the query to a clean category (928, Big Easy, BlackSheep, Britton's, High Octane = alphabetical-first).

**So re-tagging alone won't fix that grab-bag — it's a Phase 3 (code) retrieval fix.** This narrows Phase 4 to the genuine data errors below, and raises the priority of the Phase 3 retrieval fallback.

---

## What the dry-run corrects (47 candidates)

### A — `boat-and-watercraft-rentals` over-applied to non-rentals (22 rows)

This is the real data problem behind "where can I rent a kayak/pontoon → detailing shop." The rentals leaf has been stamped on businesses that don't rent watercraft:

| Proposed target | Count | Confidence | Examples |
|---|---:|---|---|
| `auto-marine-detailing` | 9 | **clear** | 928DesertDetailing, Crown Mobile Detailing, JT Kustom Detailing, RPM Detail, Superior Detailing |
| `boat-sales` | 8 | judgment | Domn8er Power Boats, Sun Country Marine Group, IMAGE MARINE, R & D Marine |
| `boat-repair-and-service` | 4 | judgment | Barrett Custom Marine, JandJ Performance & Marine Service, Chong Servicenter |
| `eat-drink` | 1 | **clear** | Ghost Mine Saloon (a saloon tagged as a boat rental) |

The 9 detailing shops and the saloon are unambiguous. The 12 "marine" businesses split between **sales** and **repair/service** — that's a judgment call (a "Custom Marine" shop could be either). Genuine rental operators were left untouched.

### B — RV parks mis-subcategorized as "parks-beaches" (22 rows, all clear)

22 RV parks / campgrounds carry `stored_subcategory = parks-beaches` while their leaf is correctly `rv-parks-and-campgrounds`. That stale subcategory is why "which beach is best for kids?" returns RV parks (Havasu View RV Space, The Gravel Pit, Windsor Campgrounds…). Fix: align the subcategory to the leaf. Low-risk, mechanical.

*(Side effect spotted: "Anchor Lake House" is one of these RV parks — which is also the source of the Tier-3 "anchor" keyword artifact from the diagnostic.)*

### C — realty / property-management vs lodging (3 rows, judgment)

Copper Canyon Realty, Destination Havasu, First Choice Property of Mohave County are stored as `professional-services`; the fresh classifier says `lodging-vacation-rentals`. Real-estate brokerages aren't lodging, but vacation-rental managers arguably are. **Your call** on each.

---

## A structural finding worth noting: beaches are under-catalogued

Only **6** entities are tagged `beaches-and-swim-areas` in the whole catalog. Lake Havasu has 400+ miles of coastline and the named public beaches (Rotary, London Bridge Beach, Body Beach, Site Six) are exactly what "which beach…" questions want. This is a **content/coverage gap (Phase 8)**, not a re-tag — flagging it because re-tagging RV parks out of "beaches" will leave that category thin until real beaches are added.

---

## Counts

- **47** correction candidates: **32 clear**, **15 judgment**.
- By type: 22 rental-overtag · 22 RV-park subcategory · 3 lodging/realty.
- Every row in `askhava_catalog_retag_DRYRUN.csv` has: id, slug, name, google category, current vs proposed (primary/subcategory/leaf), change_type, confidence, reason.

---

## What I need from you, then next steps

1. **Decide the 15 judgment rows** — mark each marine business as sales vs repair, and each realty firm as lodging vs professional-services (or "leave as-is"). Easiest: annotate the `confidence`/`proposed_leaf` columns in the CSV.
2. Once decided, I'll write a **`scripts/recategorize_water_misfiled.py`** mirroring `recategorize_health_beauty.py` exactly — pure classifier rules module + unit tests, **DRY-RUN by default**, JSON rollback snapshot, `--apply --confirm` gated. You run the dry-run, confirm counts, then **you** run `--apply --confirm` against prod. I never run the apply.

I can start on the 32 **clear** corrections' apply script now (detailing + saloon + RV-park subcategory) and hold the 15 judgment rows for your decisions — say the word.
