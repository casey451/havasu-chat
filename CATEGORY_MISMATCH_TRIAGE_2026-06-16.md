# Category mismatch triage — primary vs subcategory (2026-06-16)

Decision-support for `task_c054a318`. Source: read-only prod audit of active,
non-draft, classified providers where `primary_category != primary_for_subcategory(subcategory)`.
**No DB writes were made producing this.**

Current totals: **97 `review`** (subcat maps to a real primary ≠ current) + **31 `no_target`**
(subcat NULL → no canonical primary) = **128**.

## TL;DR — the blanket rule runs the wrong way

The original idea was "set `primary = primary_for_subcategory(subcategory)`." Against the
live data that is **backwards for ~85 of the 97** rows: the **primary is the trustworthy
signal and the subcategory is the noisy one** (mostly generic `specialty`/`parks-beaches`/
`hotels`/`attractions`). For those, the fix is to **correct the subcategory** (which also
resolves the mismatch, since the corrected subcat maps back to the already-correct primary)
— *not* to move the primary.

Three buckets below. Bucket 2 is the only place the original rule is correct.

---

## Bucket 1 — Keep the primary; fix the SUBCATEGORY (~85 rows)

Primary is right; subcat is generic/wrong. Suggested subcat maps to the SAME primary, so
the mismatch self-resolves. Safe to script per-cluster (dry-run → approve → apply).

### 1a. Marine businesses mislabeled `specialty`/`boutiques` (primary `on-the-water` ✓) — 11
| Provider | subcat now | → suggested |
|---|---|---|
| All Seasons Water Sports | specialty | on-the-water (rentals) |
| Nautical Watersports | boutiques | on-the-water (rentals) |
| Marina Store | specialty | marine-supply |
| Fallon Marine LLC / Germaine Marine / IMAGE MARINE / Prestige Marine / R & D Marine | specialty | marine-repair or marine-dealers (per shop) |
| Marine One Motorsports / Maxed Out Marine / Sun Country Marine Group | specialty | marine-dealers |

### 1b. Food shops mislabeled `specialty` (primary `eat-drink` ✓) — 8
| Provider | subcat now | → suggested |
|---|---|---|
| Loaded Gun Coffee | specialty | cafes-coffee |
| Berry Cherry Frozen Yogurt / Frozen Spoon / Yogurt Paradise / Sweet Treats & More / We Be Pop'n Gourmet Popcorn | specialty | quick-bites |
| Pit Stop Deli / The Local Craving | specialty | quick-bites (or restaurants) |

### 1c. RV parks / resorts mislabeled `parks-beaches` (primary `lodging-vacation-rentals` ✓) — 16
RV parks → `rv-parks`; resorts → `rv-parks` or `hotels`. Includes **Havasu Landing Resort &
Casino** (your earlier "possibly intentional" example — confirmed: keep lodging).
Campbell Cove / D-J's / Desert Hills / Havasu Falls / Havasu RV / Havasu View / Prospectors /
Sam's Beachcomber RV / Riverbound Custom Storage & RV / **Islander Rv Resort** (subcat=racquet-sports) → `rv-parks`.
Anchor Lake House / Artesa Resort / Islander Resort / Lake Havasu Resort / Havasu Landing Resort & Casino / The Gravel Pit → `rv-parks` or `hotels` (per property).

### 1d. Personal-care / tattoo / optical mislabeled `specialty`/`boutiques`/`attractions` (primary `health-wellness-care` ✓) — 18
Tattoo/piercing/lash/CBD-wellness → `beauty`. Optical/hearing → `health-medical`.
Tattoo & beauty: Bombshell Body Art, GOLD DUST TATTOO, Good Time Tattoo, Heart of Gold Fine Line,
HiveMind, Immortal Beauty, Lake Havasu London Bridge Tattoo, Lash and Mane Beauty Lounge,
Natural Gold Wellness & Beauty CBD, Saints and Sinners, Stutter Tattoo, The Guided Hand,
Tigers Eye, Wild Goose, **The Blind Pig Tattoo** (subcat=attractions) → `beauty`.
Optical/hearing: Cleartone Hearing Centers, Us Vision Inc, Walmart Vision & Glasses → `health-medical`.

### 1e. Other "primary is right, subcat is wrong" singletons — ~32
| Provider | primary (keep) | subcat now | → suggested |
|---|---|---|---|
| Bogeys & Stogies / Desert Bar | eat-drink | parks-beaches | bars-breweries |
| Ghost Mine Saloon | eat-drink | on-the-water | bars-breweries |
| HEAT Bar | eat-drink | hotels | bars-breweries *(hotel_mislabels.py already targets this)* |
| Movies Havasu | events | restaurants | venues/attractions *(memory's own example)* |
| Win Win Bingo Casino | events | parks-beaches | venues |
| Iron Wolf Golf & Country Club | outdoors-parks-trails | bars-breweries | golf *(NOTE: eat_drink_mislabels.py would instead move it to eat-drink — conflict, pick one)* |
| Hooks Boat Rentals / London Bridge Beach boat rental | on-the-water | attractions | on-the-water |
| Havasu Watercraft Rental | on-the-water | professional | on-the-water |
| Sandbar Powersports | on-the-water | storage | marine-dealers |
| Advantage Boats & RV Storage | home-property-services | marine-dealers | storage |
| Essco Wholesale Electric / REDHAWK POOL SERVICE & REPAIR | home-property-services | specialty | home-services |
| Heart and Sole Fitness & Wellness / Premier Chiropractic & Functional Medicine | health-wellness-care | professional | health-medical (or beauty for fitness) |
| Jum-Pawn-It | shopping-essentials | professional | specialty |
| Trico Engineering | professional-services | home-services | professional |
| Lake Havasu Senior Center | public-civic-resources | health-medical | civic-community |
| Clothes Closet Lake Havasu / Regional Center For Border Health | public-civic-resources | venues | civic-community |
| Rotary Community Park / Thompson Bay Beach | outdoors-parks-trails | on-the-water / attractions | parks-beaches |
| Fire & Ice Recovery & Wellness | health-wellness-care | civic-community | health-medical |

---

## Bucket 2 — Apply the ORIGINAL rule (primary IS the stale one) — 3

Here the subcategory is right (or close) and the primary is wrong. `primary = f(subcategory)`
is the correct fix. These are the only safe candidates for the original approach.

| Provider | subcat | primary now → fix to | also ideally |
|---|---|---|---|
| Huukan Golf Club | parks-beaches | classes-sports-recreation → **outdoors-parks-trails** | subcat → golf |
| Los Lagos Golf Club | parks-beaches | classes-sports-recreation → **outdoors-parks-trails** | subcat → golf |
| Swivel & Sway Ballroom Dance | kids-lessons | events → **classes-sports-recreation** | — |

---

## Bucket 3 — Genuine domain calls (need your decision) — ~9

| Provider(s) | The question |
|---|---|
| Carburetion Specialties, First Class RV & Marine, WM Auto & Marine, Byrd's Mobile RV & Marine, Every Little Detail Detailing, Mobile Marine and More | **Auto/RV ↔ marine cross-trade.** Each serves both. Pick a primary per shop, or cross-list. |
| Copper Canyon Realty, Destination Havasu, First Choice Property, Havasu Realty, Integrity Arizona Real Estate | **Realtors (→ professional) vs vacation-rental managers (→ lodging)?** subcat=hotels on all 5. `realty_to_lodging.py` currently no-ops them. |
| Caley Nursery, Star Nursery Garden Center | Garden center = retail (**shopping**) or home/garden service (**home-property**)? subcat=home-services. |
| HavaZoo Tanning & Clothing Co. | Tanning (**health/beauty**) vs clothing retail (**shopping**)? |
| London Bridge Shops | Shopping center (**shopping**) vs tourist attraction (**events**)? subcat=attractions. |
| Downtown District | Civic district (**public-civic**) vs attraction (**events**)? |
| Hospice of Havasu | Healthcare (**health**) vs civic nonprofit (**public-civic**)? subcat=civic-community. |

---

## Appendix — `no_target` (31): subcategory is NULL → benign, lowest priority

These route fine today via the primary tier (e.g. Hoover Dam → outdoors, shuttles →
professional, BlueWater Resort → lodging). They only appear in the audit because
`primary_for_subcategory(NULL)` is None. The "fix" is to **add** a subcategory (so they also
surface on a `/lake-havasu/{sub}` landing) — never to change/null the primary. Examples:
tours/landmarks (Hoover Dam, Grand Canyon West, Oatman, Topock Maze, Blythe Intaglios) →
`attractions`; shuttles (A River Run, Amore, Day & Night, Havasu Party Bus, Havasu Shuttle) →
no clean leaf today (`professional` primary is fine); water rentals (Paradise Wild Wave,
Rentals on the Beach, Havasu Tropical Oasis Floating, Nautical Watersports Center) →
`on-the-water`. Defer unless landing coverage matters.

---

### Suggested execution order (each gated dry-run → counts → approve → apply)
1. **Bucket 1a–1d** — high-volume, low-judgment subcat corrections (marine, food, RV, personal-care). Biggest coverage win.
2. **Bucket 2** — 3 rows, apply original primary fix.
3. **Bucket 1e** — singletons (resolve the Iron Wolf conflict first).
4. **Bucket 3** — your domain calls.
5. **Appendix** — optional subcat backfill for landing coverage.
