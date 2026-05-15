# Phase 5.1 — Eat & Drink Load: Data-Quality Audit

> **What this is:** a full data-quality pass over the 287 `eat-drink` providers
> loaded into `data/events.db`. The `food_drink` discovery sweep cast a wide net —
> this audit separates the clean eateries from non-eatery leak, borderline
> judgment calls, and true duplicates, so the operator can do a cleanup pass
> **before Phase 6 renders the `/category/eat-drink` page** and before deep
> field-entry effort goes into rows that shouldn't be there.
>
> **Not a blocker.** ~240 clean eateries remain after the leak — the gate item
> "Phase 6 renders 15+ per default filter" is in no danger. This is about page
> quality, not gate-passing.
>
> **DB read method:** `/tmp` copy (mount can't open `events.db` directly — gotcha
> #4/#15). All entity_ids verified against the live DB on 2026-05-15.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`aa2622d`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock.

---

## §1 Headline

| Bucket | Count | Notes |
|---|---|---|
| Total loaded `eat-drink` providers | 287 | all have address/zip/lat/lng — 0 missing |
| **Clean eateries** | ~240 | restaurants, bars, cafes, bakeries, breweries, grocery anchors — the real category |
| **Clear non-eateries (leak)** | 31 | towing co., car dealer, golf courses, a movie theater, a laundromat, etc. — §2 |
| **Borderline / judgment calls** | 15 | convenience stores, butcher shops, a distillery, etc. — operator's call — §3 |
| **True duplicates** | 2 pairs | same name + same address — §4 |

ZIPs: 223 in 86403, 39 in 86406, 25 in 86404 — all valid LHC; the ZIP filter worked.
Missing `phone` (30) / `website` (58) is normal for small businesses — not a concern.

## §2 Clear non-eateries — 31 entities (recommend deactivate or recategorize)

These are not eat-drink venues. Several are discovery keyword false-positives
(e.g. "DELI LAUNDROMAT", "Western States **Restaurant** Consulting", "The
**Speakeasy** Beauty Lounge"). Several carry high review counts, so they'd render
prominently on the eat-drink page if left.

| entity_id | Name | Google type | Actually is |
|---|---|---|---|
| `968b4a6e-124d-4b6f-b125-cb3b58fa3145` | A Toe Truck | service | towing company (999 reviews) |
| `4d420b76-3451-4d89-a504-edd8d1cb45ba` | Hava Event Planner & Coordinator | service | event planning |
| `afa108ea-ddf1-48a1-a9d0-9b6d300e8bb5` | Lovedwell Creative | service | creative agency |
| `0da5a4ac-111b-4734-9a07-e47666840bca` | Posh Planning & Event Co. | service | event planning |
| `bae5cda8-8db2-4f4a-b541-736806b0b402` | River Rat Motorsports | store | motorsports retail |
| `61197d69-fb83-4b88-bfd8-731d261388cb` | Lake Havasu Cigars | store | cigar shop |
| `eb5d36e9-4575-4336-b30a-3722675a1a37` | Farm Fresh Medical/Recreational Marijuana Dispensary | store | dispensary |
| `c020ba06-3f36-4eac-93f4-86831292e4ee` | Close to Downtown Nightlife and Minutes from Lake Havasu | lodging | vacation rental (also a dup — §4) |
| `cdae678d-4ef1-4eea-8794-d15642f51390` | Close to Downtown Nightlife and Minutes from Lake Havasu | lodging | vacation rental (also a dup — §4) |
| `240c4f19-23c6-4f19-b8e4-5be5b8eaf7b5` | London Bridge Resort | hotel | hotel (its eateries — Martini Bay, Kokomo — load separately) |
| `2b38d5af-5bce-46aa-bd4a-2bc12574e334` | The Nautical Beachfront Resort | resort_hotel | resort (its eateries — Turtle Grille, Turtle Beach Bar — load separately) |
| `3c499705-09b0-40d6-915c-8d25b20f88c4` | Iron Wolf Golf & Country Club | association_or_organization | golf/country club |
| `1b58b28e-7ea8-4d09-8c3b-a409c77d7a7c` | Site Six Launch Ramp | (none) | public boat ramp (on-the-water — heat list §3 #19) |
| `b0acdc8a-3c14-41bc-9e89-ab67ab95531f` | Hava Style Recreation | supplier | recreation-gear supplier |
| `a68f7dd8-c196-4a45-92cc-372263087cb5` | Lake Havasu Rodeo Grounds | sports_activity_location | rodeo grounds |
| `1b82d3fe-85e0-4b14-b6e9-4b4b2c50766e` | McCulloch Center Plaza | shopping_mall | shopping plaza |
| `c0c513fb-20ab-4245-a080-24dfaa1d49d1` | Havasu 95 Speedway | race_course | speedway |
| `1920fe0f-aff9-4178-825b-ffd02a2cb7f5` | Grace Arts Live | performing_arts_theater | theater |
| `f0497e6e-d433-4df9-9a0f-278dd1fe0f1d` | London Bridge Beach | park | park / on-the-water (heat list §3 #18) |
| `b3b1c0f7-e999-48fa-ba5f-05d8c2793f9e` | Movies Havasu | movie_theater | movie theater |
| `bf3fe419-de3a-43b4-a4a4-e5452a391251` | London Bridge Swap Meet | market | swap meet |
| `5020a3b8-b3dd-40e5-b4cb-d6d82c23e1a3` | DELI LAUNDROMAT | laundry | laundromat (keyword false-positive on "deli") |
| `6737ecc9-4a4f-4e93-a7fa-b27e2fe7a005` | Sunshine Indoor Play | indoor_playground | kids' indoor playground |
| `b7731508-0993-4538-b58e-770ba3dac2fc` | The Back Nine Golf | indoor_golf_course | indoor golf |
| `dc9b2e08-7e6e-4733-947c-f0f9669488d7` | Lake Havasu Golf Club | golf_course | golf course |
| `791cf1e6-df8b-401e-9840-e4250f426d07` | W.A.V.E. Culinary and Hospitality | educational_institution | culinary school |
| `e3272eaa-28e7-4583-bf24-3e023a5a6f0d` | Western States Restaurant Consulting | consultant | consulting firm (keyword false-positive) |
| `afa6dc88-9a55-465e-af4d-776fc22e9144` | Detail Specialties & Ceramic Coating | car_wash | auto detailing |
| `b8dfe489-6b11-42d4-8966-69200427e9d3` | Martin Swanty's Paradise Auto | car_dealer | car dealership |
| `b996edfe-0c54-4941-91d3-26fb84e4895b` | Our Shabby Shack & Book Exchange | book_store | bookstore |
| `368c5360-c3bd-465d-9337-83e9cc201d24` | The Speakeasy Beauty Lounge | beauty_salon | beauty salon (keyword false-positive) |

## §3 Borderline — 15 entities (operator's call, no recommendation)

Food-adjacent retail and venues-with-dining. Defensible either way — they could
stay in `eat-drink`, move to `shopping-essentials`, or (for the rec venues) to
`classes-sports-recreation`. Listed so the call is deliberate, not accidental.

| entity_id | Name | Type | The question |
|---|---|---|---|
| `7787eae7-d430-4977-9a60-5740c14ae890` | BRB Market | convenience_store | convenience stores sell food — eat-drink or shopping-essentials? |
| `8c3e4c88-27e2-4cba-84b0-1800a307e781` | Commander Center | convenience_store | same |
| `da854966-9355-4aa2-a12f-3992901d4bb7` | Hacienda Mini Market | convenience_store | same |
| `6a5e6728-4e4c-4eb4-bc00-f9c43383e2b6` | Kiowa Drive Thru | convenience_store | same |
| `ac9f3b9f-9057-4ac7-acf5-ee6fde051d86` | Tri-M Mini Mart | convenience_store | same |
| `478dce1f-a3df-420f-befb-1110cc722f22` | Herradina American Wagyu Beef | butcher_shop | butcher = food retail — eat-drink or shopping? |
| `afc6d7fa-c29e-42fb-bb53-29fff966beed` | Just Meats | butcher_shop | same |
| `8e947013-8a49-4b8f-9d1a-b7880f8a6b5e` | Roadhouse Market & Butcher | butcher_shop | same |
| `13dd6f5c-266b-4aba-b55f-dcca7a4fea55` | Campbell Cove 1-Stop | gas_station | gas station w/ food |
| `7944cf07-c013-4b1b-83a3-2c6b87c8c7a4` | Mr Lucky's Billiards | sports_complex | billiards hall — likely has a bar |
| `20bece90-0a6a-416e-99fb-45629d7ea3fa` | Havasu Lanes & Keglers Pub | bowling_alley | bowling alley w/ a real pub |
| `45528661-beef-46f7-9884-da004858f295` | Copper Still Distillery | manufacturer | distillery — tasting room makes it eat-drink-ish |
| `b20129c1-3f7b-4d67-bd9c-1378bd94970b` | Fraternal Order of Eagles | association_or_organization | social club w/ a bar |
| `917b154c-fcd4-4292-97eb-f4b0f725e7f6` | Nutrition One | store | supplement shop |
| `3e4db7a6-d935-4b68-9c1e-7d05b432f8a6` | Grill Max Havasu | barbecue_area | BBQ spot? or a park grill area? — verify what it is |

## §4 True duplicates — 2 pairs

Same name **and** same address — one of each pair should be removed.

- **Lady Lee's** — `b4d80817-c326-4157-a3b8-e61a018f5eda` and
  `71ad6c09-f6c7-4d4f-a137-d653d697cbc1`, both at 2180 McCulloch Blvd N. Both are
  `american_restaurant` — a legit eatery, just listed twice. Keep one, drop one.
- **"Close to Downtown Nightlife..."** — `c020ba06...` and `cdae678d...`, both at
  the street-less "Lake Havasu City, AZ 86403". These are vacation rentals (also
  in §2) — both should go regardless.

**Not duplicates** (verified — distinct addresses, legitimate chain locations):
The Human Bean ×3, Carl's Jr. ×2, Domino's ×2, Subway ×3, Starbucks ×6, Dunkin'
×2, ZENSHI Handcrafted Sushi ×2 (1650 + 1980 McCulloch — grocery-store sushi
counters). Leave these alone.

## §5 What's clean — not at risk

- **All staged field-entry work targeted clean rows.** The `heat_exposure` SQL,
  the `crowd_notes` top-17, and the `boat_access` candidates all hit genuine
  eateries / grocery anchors — none of the §2 leak. No rework needed there. (One
  borderline note: the `crowd_notes` doc already flagged London Bridge Beach + the
  2 resorts as excluded; this audit confirms and extends that.)
- **No missing core fields** — address/zip/lat/lng are 100% populated.
- **The gate is safe** — ~240 clean eateries is far above the "15+ per default
  filter" bar.

## §6 Why the duplicates got through

The scrape log noted "0 ambiguous hits — DB rebuilt empty." That's the cause: the
reconciler's geo+name matching had nothing to match against in a fresh DB, so the
two Lady Lee's rows (distinct `google_place_id`s — Google itself carries two
listings) both inserted as clean rows. **Implication for Phase 5.2+:** loads into
the now-non-empty DB *will* run the reconciler with real prior rows — the drift #5
fix (reconciler counts in the load summary, committed `d34d4c3`) is exactly what
surfaces this next time.

## §7 Recommendation

Do a cleanup pass before Phase 6 renders `/category/eat-drink`. The §2 31 + §4
duplicate-extras are the actionable set. Three approaches, operator's choice:

1. **Deactivate** (`is_active = False`) — fastest, reversible, hides them from
   Phase 6. Recommended for Phase 5.1 — keeps the rows for later recategorization
   without blocking anything.
2. **Recategorize** — move each to its correct Tier-1 category. Better data, more
   work, and some targets (lodging, on-the-water) aren't scraped until 5.2+.
3. **Delete** — cleanest but destructive; the `.bak` already holds the pre-rebuild
   state, so recovery isn't via these rows anyway.

The §3 borderline 15 are a separate, lower-urgency call. **This is field-entry-lane
work (DB row edits), so it's in scope for this chat** — say which approach you want
and I'll stage the cleanup SQL the same review-and-run way as the `heat_exposure`
batch. Recategorization specifically may want a quick word with the Phase 6 agent
since it changes what renders where.

---

## §8 Files / references

- `outputs/phase5_1_heat_exposure_field_entry_staged.md` — staged work, confirmed clean
- `outputs/phase5_1_crowd_notes_top17_staged.md` — staged work, confirmed clean
- `outputs/phase5_1_boat_access_candidates.md` — staged work; §3 there first flagged the resorts/park/ramp
- `docs/scrape_logs/eat-drink_2026-05-14.md` — the load record (0-ambiguous note, §6 here)

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`aa2622d`,
2026-05-15). Lives at `outputs/phase5_1_eat_drink_data_quality_audit.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. All entity_ids verified
against a `/tmp` copy of the live `data/events.db`.*
