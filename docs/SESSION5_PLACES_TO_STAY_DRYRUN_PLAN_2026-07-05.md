# Session 5 — Places to Stay cleanup (GATED data op: dry-run → counts → Casey approves → apply)
**Date:** 2026-07-05 · Companion to `ASK_HAVA_FULL_SITE_AUDIT_REMEDIATION_PLAN_2026-07-04.md` (§6 Session 5).
**Status:** PLAN ONLY — no prod writes. Built from a read-only code investigation.

> **Key finding:** this is **100% a prod DATA OP — no code changes required.** The lodging surface is gate-driven (`app/categories/leaf_pages.py::LEAF_PAGE_MIN_PROVIDERS=1`), so once the vacation-rental listings are deactivated the "Vacation Rentals" tile disappears on its own, `/categories/lodging/vacation-rentals` 404s, and "Places to Stay 104" recomputes from the same `_get_index_payload` cache (refreshes on deploy/restart or its ~1h TTL). Nothing to template or route.

---

## Goal (from Casey's brief)
Remove (deactivate, reversibly) **all vacation-rental and property-management lodging**, plus **out-of-area lodging**, keeping only verified **hotels/motels + RV parks/campgrounds**. Live today: Vacation Rentals **50**, Hotels & Motels **31**, RV Parks **23** (= 104). Expected after: ~**54** (hotels+RV, minus any misfiled/OOA), VR tile gone.

## Data model (what to key on)
The live department pages key on **`EntityCategory` M:M with `is_primary=True`** (NOT the legacy `Provider.subcategory` string — different slugs; don't touch it). Deactivation convention across all prior ops = **`Entity.is_active=False` + cascade `Provider.is_active=False`** (soft, reversible). Leaf slugs: `vacation-rentals`, `hotels-and-motels`, `rv-parks-and-campgrounds`; department slug `lodging`.

Enumerate a leaf's live listings:
```sql
SELECT ec.entity_id
FROM entity_categories ec
JOIN categories c ON c.id = ec.category_id
JOIN entities   e ON e.id = ec.entity_id
WHERE c.slug = :leaf_slug AND ec.is_primary = TRUE AND e.is_active = TRUE;
```

## Removal set — three buckets (each dry-run and counted separately)
1. **Bucket A — the whole Vacation Rentals leaf (~50).** All entities whose primary leaf is `vacation-rentals`. Straight deactivate.
2. **Bucket B — VR/property-mgmt misfiled under `hotels-and-motels`.** Apply the classifier that already exists inline in `scripts/rehome_vacation_rentals_batch10_2026_06_27.py`:
   - VR if `(not real_hotel) AND (OTA_domain OR VR_name_tell OR no_street_number)`.
   - `OTA_domain` on `Provider.website`/`address`: vrbo, airbnb, expedia, bluepillow, vacasa, evolve, furnishedfinder, booking.com, agoda, avrhavasu, havasuvacationrentals (NOT bare hotels.com/choicehotels — those are real chains).
   - `VR_name_tell` on `Entity.name`: villa, retreat, oasis, getaway, casita, "sleeps N", "private pool", hot tub, "Mi to", poolside, Xanadu, "!", etc.
   - **Keep-guard (`real_hotel`):** name matches hotel/motel/inn/resort/suites/lodge/major chains **AND** has a street number. Protects real hotels whose booking domain tripped the OTA regex.
3. **Bucket C — out-of-area lodging.** In `hotels-and-motels` or `rv-parks-and-campgrounds` where `Provider.is_local IS FALSE` (or `Provider.region` ∈ parker/laughlin-bullhead), plus name backstop `\b(parker|kingman|needles|topock|black meadow|havasu springs)\b`. Named targets: **Black Meadow Landing** (Parker Dam, CA — note its address is a bogus "Go Lake Havasu Visitor Center" placeholder, so `is_local` may be NULL → rely on name match) and **Havasu Springs Resort** (Parker, AZ). These are already filtered out of serving (`is_local.isnot(False)`); this makes it permanent.

## The script (mirror the proven pattern)
Write ONE gated script combining the **classifier** from `rehome_vacation_rentals_batch10_2026_06_27.py` with the **undo-CSV + safety-guards** from `scripts/apply_bogus_deactivation.py` (the gold-standard reversible deactivator):
- **Dry-run by default**; `--apply` writes; `--undo-csv <path>` emits the manifest; `--reactivate-from <undo.csv> --apply` reverses.
- On apply: `Entity.is_active=False` + each `Provider.is_active=False`, single transaction.
- **Skip-guards (copy from apply_bogus_deactivation):** skip rows already inactive/draft; **skip any that are `verified`, claimed (`Claim.status=="verified"`), or sponsored (`tier not in ("","free")` or `sponsored_until > now`)** — never deactivate a paying/claimed listing.
- **Undo CSV schema:** `["entity_id","name","provider_ids"]` (entity-level, cascading to providers).
- Print per-bucket counts + capped samples in the dry-run, exactly like batch10 does.

## Rendering after removal — automatic, no deploy needed for correctness
- `/categories/lodging`: VR tile vanishes (gate ≥1). If somehow all leaves emptied, the dept 404s — not a risk (hotels+RV remain).
- `/categories/lodging/vacation-rentals`: 404 (`leaf_below_minimum`). Legacy `lodging-vacation-rentals` still 301s to `/categories/lodging`.
- Home "Places to Stay N" + `/categories` index: recompute from `_get_index_payload`; refresh on next deploy/restart or ~1h TTL. (A deploy or `reset_index_cache()` forces it immediately.)

## Approval checklist (per CLAUDE.md)
1. [ ] Dry-run Bucket A (`vacation-rentals` leaf) → count + sample
2. [ ] Dry-run Bucket B (misfiled-under-hotels classifier) → count + sample, **eyeball the keep-guard didn't flag a real hotel**
3. [ ] Dry-run Bucket C (out-of-area) → count + sample
4. [ ] Casey reviews the combined count (expect Places to Stay 104 → ~54) → approves
5. [ ] `--apply` with `--undo-csv`; re-verify `/categories/lodging` shows only Hotels & RV; confirm counts
6. [ ] Keep the undo CSV as the revert manifest

## Decisions for Casey
1. **Property-management companies:** the brief says remove them from lodging. Fully **deactivate** them (simplest, matches "remove for now"), or **rehome** the legit ones to the existing `property-management` leaf under Home & Property Services (keeps the business, just not as lodging)? Default = deactivate.
2. **Hotels sweep aggressiveness (Bucket B):** the live Hotels leaf is only 31 (a prior pass already moved ~50 into the VR leaf), so B may be small. Run the classifier but **manually review B's list** before apply, since that's the bucket where a real hotel could be wrongly flagged.
3. **Bookable-link quality:** keeping only hotels/motels/RV whose website is a working booking link is a **separate follow-up** (join `Provider.website` → `link_health.confirmed_broken`) — not in this op. In scope?
4. Confirm the standard dry-run → counts → approval gate and that deactivation (reversible) — not deletion — is what you want.
