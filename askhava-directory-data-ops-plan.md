# Ask Hava — Directory Data-Ops Plan (remaining work)

**Date:** 2026-06-27
**Source audits:** `askhava-directory-audit.md` (per-category, drove batches 1–6) +
the broader re-audit with the §14 verification pass (search/intent focus, with
corrections — VR & Locksmiths leaves already exist; senior-care/hearing/derm/the
history museum are present-but-buried, not missing).
**Rule of the road (unchanged):** every batch = one PR, a dated standalone script,
**dry-run default**, `--apply --confirm`, rollback snapshot, and a **read-only probe
first** so rows already actioned in batches 1–6 are skipped. Prod gate per CLAUDE.md:
probe → show counts → Casey approves → apply. Agent never runs `--apply` on prod.

---

## Baseline — already shipped (don't re-do)

Batches 1–6 (#581–#586 + commit 93ee5f0a):
- Bulk-import junk retraction ("Go Lake Havasu Visitor Center" / 800-242-8278).
- Mailbox-suite retraction (1642 McCulloch Blvd N).
- Shadow-dupe mirror retraction tool (real listing + thin "New/Visit" mirror).
- Re-homes: Harley→powersports, Bella Faccia→med-spa, KeyMe→**locksmiths** (leaf now
  exists), bait/tackle makers + dock dealer out of Fishing/Marinas, +6 misc.
- Dedup pairs (Minute Key ×2).
- Closed/suspect retract: Stetson Winery, Driftwood Acres, Ohmalliance, Game Spot.
- Structural side effect: empty/thin leaves (Security & Alarms, Casinos) auto-hide.

## Out of scope for THIS track (code, not data — separate PRs)

These are the report's Tier-1 platform fixes and are **not** prod data ops:
1. **Count-chip aggregation** (dept chip ≠ leaf roster ≠ "N Best" title). Worth tracing
   in code — it contradicts the earlier "counts are correct" finding because the symptom
   here is *under*-count (chip "5" vs 23 rows), a different path than the "N Best"
   inflation that PR #580 fixed.
2. **Intent-aware search + relevance ranking** (§11 alias table → `app/categories/leaf_query.py`).
3. **Events stale-cache render** (reproducible "June 10" edge cache; four counts/day).

---

## Remaining data ops — gated batches (priority: boats → pools → HVAC → housing → long tail)

### Batch 7 — Priority-cluster re-homes (reversible category moves, no sourcing)
Highest-priority misfiles that only need a category change:
- **On the Water:** boat dealers out of Self-Storage (Sandbar Powersports, Horizon
  Motorsports); Wolf Watersports out of Jet Ski; scuba shops out of Jet Ski; Riverside
  Boat Dock Sales out of Marinas; Bluewater Accounting (CPA) out of Boat Tours → Professional;
  Campbell Cove out of Beaches → storage; swim team / swim lessons / Lions Dog Park out
  of Beaches.
- **Pools:** Amici Pools + Mohave Mist & Spa out of Sporting Goods → Pools & Spas; Neat
  Pool & Supply retag off "Specialty".
- **HVAC:** pull stranded All American Air, Air Control, Alpine onto the HVAC leaf; flag
  AC Pro as wholesale supply (not consumer repair).
- **Auto:** A Toe Truck out of Movers → Towing.
- **Tool:** `rehome_directory_miscategorized_*.py` pattern + `apply_taxonomy_remap.py`.

### Batch 8 — Priority-cluster dedup
Keep the reviewed/google_places row, retract the thin mirror:
- Boat Broker, Lake Havasu Marina, Paradise Wild Wave, Arizona TikiToons, WACKO kayak,
  Lake Havasu Airboat; **Ambient Edge / Fayette A/C** (real merger — keep Ambient Edge,
  alias "formerly Fayette"); **TNT / Dynamite Roofing** (shared phone — consolidate);
  Mohave Roofing ×2.
- **Tool:** `dedup_directory_pairs_*.py` + `deactivate_entities.py`.

### Batch 9 — Priority-cluster accuracy fixes (field edits, not retract)
- Amici Pools address → 420 El Camino Way Ste 104; Havasu Riviera Marina Plus Code →
  2067 Havasu Riviera Pkwy; Havasu Tropical Oasis garbage address field; Samons A/C phone
  → (928) 855-3302; Promised Land Landscaping email-in-address; Streamline Solar "Bldg B".
- **Tool:** new dated field-fix script following `fix_address_quality.py` / `set_place_website.py`.

### Batch 10 — Vacation-rental re-home + out-of-area lodging
- ~45 short-term-rental homes in Hotels & Motels → **existing** `vacation-rentals` leaf
  (§14 correction: it's a re-home, not a new leaf). Real hotel/motel count ≈ 30.
- Retract OOA lodging: Black Meadow Landing (CA), Havasu Springs Resort (Parker).
- **Tool:** `recategorize_realty_to_lodging.py` / `create_vacation_rentals_leaf.py` patterns.

### Batch 11 — Long-tail re-homes (Things to Do, Shopping, Family & Ed)
- **Parks & Playgrounds purge:** pool-service cos, HTM boat dealer, Grill Max restaurant,
  Mr Lucky's billiards, Toy Brokers golf-cart dealer, Rodeo Grounds → respective leaves;
  trails → Hiking; retract OOA (Hoover Dam, Topock, Blythe, Copper Basin).
- **Landmarks:** wedding/party/event cos → Event Planning; rentals → Rentals.
- **Shopping:** Walmart/Dillard's/JCPenney/Ross/bealls/Maurices out of Gift Shops →
  Clothing/Grocery; Cloud Slingers → Smoke & Vape; marine/pool out of Furniture/Sporting
  Goods; Loaded Gun Coffee → Eat & Drink; bakeries-vs-ice-cream retag.
- **Family/Ed:** music/dance studios out of K-12; Serrano's/Caley nurseries out of
  Preschools; Telesis → K-12; Hava Math → Tutoring; Charles-Italy → Beauty (verify not
  already moved).

### Batch 12 — Health re-homes + de-burying (no new sourcing)
- **VA "Vet Center"** out of Veterinarians → Community/Veterans (clearest word-trap).
- Out of "Doctors": Farm Fresh dispensary, nursing homes/assisted-living, audiology,
  opticians, PT, LPC/LCSW therapists.
- Pharmacy mirror merges (Walgreens/CVS); collapse Lake Havasu Family Eyecare ~7 child
  listings into the practice.
- **§14 note:** senior-care / hearing / dermatology rows already exist — this is re-home
  + de-bury; the missing piece is **browse leaves**, which is Batch 14.

### Batch 13 — Professional/Civic re-homes + dedup
- Title agencies out of Insurance → Title & Escrow; mortgage brokers out of Banks;
  paralegals/doc-preparers out of Attorneys; HBC Motors + SEO-keyword stubs out of
  Financial Advisors; D Tax → Accountants; Quick Stop + Teri Parcells out of Nonprofits.
- Retract SEO-keyword-name junk ("Hard Money Lenders Lake Havasu City AZ", "Commercial
  Lending…ZA", PhotoAiD OOA).
- Dedup: Guild ×2, Chase ×2, UniSource ×2, Chamber, library pair, Primary Residential ×2.

### Batch 14 — Taxonomy: new leaves (structural — needs a Casey design nod)
Create + wire aliases (and surface existing orphan leaves on dept hubs):
- **Marine Supply & Parts; Pool Supply (retail); Pool Builders; Swamp/Evaporative
  Coolers** (or alias → HVAC); **Urgent Care; Senior Care/Assisted Living; Hearing &
  Audiology; Dermatology; Painting; Junk Removal; Pressure Washing; Water Treatment.**
- **Already exist — do NOT recreate:** Vacation Rentals, Locksmiths.
- Gate to moving §6/§8b listings (derm/hearing/urgent-care) onto real browse pages.
- **Tool:** `seed_taxonomy.py` / `create_vacation_rentals_leaf.py` pattern.

### Batch 15 — Net-new listing adds (web-verified NAP; heaviest gate; depends on Batch 14)
- Per [[feedback_no_stale_calendar_data]]: every add web-verified before insert; hold
  `[verify]`-tagged rows until confirmed.
- Priority: Leslie's #330, Reinhard Pool & Spa, West Marine, Express Marine, Connolly
  Marine, Anderson Powersports, Dixie Belle; HVAC (Cool Dude, Semper Air, Sunrize);
  civic (AZ MVD, USPS Main, Mohave County offices/courts, Lake Havasu High School).

---

## Per-batch process (every batch)
read-only probe → show counts → **Casey approves** → `--apply --confirm` → rollback
snapshot → push PR → CI green → **Casey merges** (= prod deploy).

## Suggested order & rationale
7 → 8 → 9 clear the **priority cluster** (boats/pools/HVAC) with zero sourcing risk and
full reversibility. 10 is high tourist value and uses existing tooling. 11–13 are the
long-tail re-home/dedup sweep. **14 is the gating structural step** — several Batch-12
de-bury moves and all of Batch-15's adds want their target leaf to exist first. 15 is last
because it's the only batch that introduces new rows and carries sourcing/verification cost.
