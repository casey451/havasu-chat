# Operator Action Items — Entity Research Findings

**Date:** 2026-05-19
**Scope:** 4 entities flagged in `outputs/operator_action_items_walkthrough.md` §3–§6 for operator disposition decision.
**Method:** Web search (Google Maps snippets, business websites, Yelp/Tripadvisor/Birdeye review aggregators, lhcaz.gov, Polaris dealer directory).
**Note on `google_place_id`:** Not exposed in plain web search snippets. Operator should pull the real `google_place_id` from the row's existing DB value (set during Phase 5.6 scrape) — the names + addresses below are the disambiguation signal, not new place IDs.

---

### #32 Anderson AZ West

- **What it is:** Powersports dealership (Polaris / Arctic Cat / Slingshot — ATVs, UTVs, RZR, Ranger, Sportsman, Slingshot). Consumer-retail sales + service + parts + financing. NOT a B2B wholesale warehouse despite the "AZ West" name suggesting otherwise. The "Polaris Commercial" listing is just the commercial-fleet vertical of the same retail dealer (small-business / municipal sales channel), not a wholesale-only operation. Anderson runs two LHC locations; "Anderson AZ West" is the south-Havasu Sweetwater site, while "Anderson Powersports Lake Havasu" is the separate north-Havasu site on N Lake Havasu Ave.
- **Address:** 3198 Sweetwater Ave, Lake Havasu City, AZ 86406
- **Status:** Active. Hours Tue–Sat 9:00 AM – 5:00 PM, closed Sun + Mon.
- **Reviews:** ~210 reviews, 4.7-star average (Birdeye aggregate — likely mirrors Google). Yelp page also active with 12+ photos.
- **Website:** https://www.andersonazwestallsports.com/ (also https://www.andersonpowersportsaz.com/ as parent brand)
- **Recommended disposition:** **un-DRAFT** (publish). This is unambiguously consumer-retail in primary mode (walk-in showroom, sales to general public, financing). The Polaris-commercial dealer listing is a secondary B2B channel, not the core model. Walkthrough decision-tree → "Consumer-retail → un-DRAFT".
- **Confidence:** **HIGH**
- **Exact SQL:**
  ```sql
  UPDATE entities SET draft = 0 WHERE id = <ENTITY_ID>;
  ```
- **Caveats / open questions:**
  - There is a sibling location ("Anderson Powersports Lake Havasu" at 1040 N Lake Havasu Ave, ~4.2 stars, ~51 reviews on Yelp / 133 on Birdeye). If a second row exists in DB for that address, treat it the same way (un-DRAFT) — they are sister storefronts of one dealer group.
  - Category is currently cat-8 shopping-essentials from the Phase 5.6 load. Arguably "motorsport vehicle dealer" sits better in a future cat-12 sports-recreation or an auto/vehicle subcat, but no such bucket exists in V1 — keeping cat-8 is acceptable.

---

### #34 Butterfly Garden (Lake Havasu City)

- **What it is:** A public butterfly garden feature **inside Rotary Community Park**. It is a sub-feature of a larger municipal park (the park itself has a swim beach, three playgrounds, beach volleyball, bocce, skate park, ball fields). The Butterfly Garden is its own Google Maps pin (Waze + Yelp both have separate listings, which is how Phase 5.6 picked it up). Free, public-access, city-maintained, no admission/no hours gate — it's just a planted-area trail segment.
- **Address:** Rotary Park Dr (within Rotary Community Park, parent address 1400 S Smoketree Ave, Lake Havasu City, AZ 86403)
- **Status:** Active. Open dawn-to-dusk per typical city park policy (Waze shows no formal hours — placeholder 00:00–00:00). Best viewing spring/summer per local commentary.
- **Reviews:** Standalone Butterfly Garden Yelp page exists but is low-volume (no specific count surfaced — likely <10 reviews). Most ratings flow to the parent Rotary Community Park page (which has 30+ Yelp reviews and Tripadvisor coverage with positive mentions of the garden).
- **Website:** https://www.lhcaz.gov/parks-recreation/parks-trails/rotary-community-park (parent park); no dedicated butterfly-garden page.
- **Recommended disposition:** **keep in cat-7 outdoors-parks-trails, un-DRAFT**. Walkthrough decision-tree → "Public-access garden / conservatory → keep in cat-7". Add a brief `crowd_notes` flag that this is a sub-feature of Rotary Community Park (so it doesn't read as a standalone destination on the directory). If a separate Rotary Community Park row also exists in DB, consider whether to dedupe — but two separate Google place IDs argues for keeping both.
- **Confidence:** **HIGH**
- **Exact SQL:**
  ```sql
  UPDATE entities
     SET draft = 0,
         crowd_notes = COALESCE(crowd_notes, '') ||
                       CASE WHEN crowd_notes IS NULL OR crowd_notes = '' THEN '' ELSE E'\n' END ||
                       'Sub-feature of Rotary Community Park; seasonal viewing best in spring/summer.'
   WHERE id = <ENTITY_ID>;
  ```
  (If `crowd_notes` column doesn't exist yet in V1 schema, drop that clause and just run `UPDATE entities SET draft = 0 WHERE id = <ENTITY_ID>;` — defer the note to V1.5.)
- **Caveats / open questions:**
  - Possible Rotary Community Park duplicate row — operator should run `WHERE e.name LIKE '%Rotary%'` to check before publishing both.
  - Category cat-7 is the right home; no re-cat needed.

---

### #35 ASU SWANSON FIELDS

- **What it is:** Two multi-use athletic fields on the former ASU at Lake Havasu "Daytona site" campus, just off Swanson Avenue (accessed via Cypress Drive). The fields themselves are **owned/maintained by Lake Havasu City** and open to public athletic use — they are NOT private ASU property. The ASU Lake Havasu campus itself is closing (announced closure ~June 2025 per local news), but the fields persist as a city-maintained municipal facility. Listed on the official lhcaz.gov Parks & Trails page as "ASU FIELDS". Used for soccer / general field sports.
- **Address:** Off Swanson Avenue / Cypress Drive, Lake Havasu City, AZ. (Local sports directory lists 98 Swanson Plaza as the campus address.)
- **Status:** Active (fields), even though the ASU academic campus has closed. City retains the fields for community use.
- **Reviews:** No standalone Google reviews surfaced. Listed on lhcaz.gov parks directory and at least one sports-event planning guide.
- **Website:** https://www.lhcaz.gov/parks-recreation/parks-trails/asu-fields
- **Recommended disposition:** **un-DRAFT + normalize case + verify category**. Real city-maintained facility in LHC → publish. Walkthrough decision-tree → "Real ASU athletic field in LHC area → normalize case + verify category". Recommend keeping in **cat-7 outdoors-parks-trails** since the lhcaz.gov canonical listing places it under Parks & Trails, not under classes/sports-recreation. cat-12 would be wrong: cat-12 is for instruction/league/programmed sports activities, while ASU Fields is a passive municipal field facility (a venue, not a program).
- **Confidence:** **HIGH** (existence + classification); **MEDIUM** on whether to also rename "ASU Swanson Fields" → "ASU Fields" to match the canonical city listing. Recommend keeping "ASU Swanson Fields" as the entity name because that's how Google Maps surfaces it (Swanson is the road) — both names point to the same place, and Swanson disambiguates from the ASU Tempe athletic fields.
- **Exact SQL:**
  ```sql
  UPDATE entities
     SET draft = 0,
         name = 'ASU Swanson Fields'
   WHERE id = <ENTITY_ID>;
  ```
  (Optional: if operator prefers canonical match, use `name = 'ASU Fields'` instead.)
- **Caveats / open questions:**
  - Confirm `primary_type` is something like `park` or `athletic_field` — if Google returned `university` or `school`, the cat-7 fit is still correct but the type may want manual override.
  - ASU campus closure is academic-only; fields are unaffected. No risk of stale listing.

---

### #37 Simply Savage Designs

- **What it is:** A **solo artist's brand**, not a brick-and-mortar gallery or shop. Tyler Savage creates upcycled / mixed-media art from old car parts, instruments, antiques, and Americana items. His work is **displayed and sold at "The Q Gallery & Gifts"** (a separate venue at 2102 McCulloch Blvd N) and via his **Etsy shop** ("SimplySavageDes"). He's listed as a participating artist on the Havasu Art Trail (2024). No standalone storefront for "Simply Savage Designs" — it's an artist project / sole proprietorship operating through partner venues + online + Instagram (@simplysavagedesigns).
- **Address:** No standalone street address. Studio is residential/private. Work shown at The Q Gallery, 2102 McCulloch Blvd N, Lake Havasu City, AZ 86403.
- **Status:** Active. Featured on 2024 Havasu Art Trail; RiverScene Magazine profile published; active Instagram + Etsy + Facebook group; phone 928-848-9878.
- **Reviews:** No standalone Google Business Profile / reviews discoverable. Coverage is editorial (RiverScene), social (Instagram, Facebook group), and trail-listing (havasuarttrail.com).
- **Website:** No dedicated site. Instagram: https://www.instagram.com/simplysavagedesigns/ ; Etsy: https://www.etsy.com/shop/SimplySavageDes ; Tripadvisor listing exists but is sparse.
- **Recommended disposition:** **keep DRAFT, defer to V1.5** (or soft-delete). The walkthrough's decision tree assumes a physical destination; this is an artist brand without a visit-able location. Three sub-options for operator:
  1. **Preferred — keep DRAFT, defer V1.5:** The havasu-chat V1 directory is destination-oriented (someone in town wants to *go* somewhere). An artist with no public studio doesn't fit V1's "where do I go" UX. Park it for a future "Local Makers / Art Trail" subcat in V1.5.
  2. **Acceptable — soft-delete:** If V1.5 art-trail subcat is unlikely, delete now to keep the directory clean. Tyler Savage's work is already discoverable via The Q Gallery row (if it exists).
  3. **Not recommended — un-DRAFT under cat-2 or cat-8:** Misleading to users since clicking through wouldn't lead to a visit-able address. Reject the original cat-2 (events) + art_gallery primary type — he's an artist, not a gallery; the gallery is The Q.
- **Confidence:** **HIGH** on identification (it's clearly a solo artist); **MEDIUM** on disposition (depends on whether havasu-chat will eventually have a "local makers" surface).
- **Exact SQL (preferred — keep DRAFT, annotate):**
  ```sql
  UPDATE entities
     SET draft = 1,
         crowd_notes = COALESCE(crowd_notes, '') ||
                       CASE WHEN crowd_notes IS NULL OR crowd_notes = '' THEN '' ELSE E'\n' END ||
                       'Solo upcycled-art artist (Tyler Savage); no standalone storefront. Work shown at The Q Gallery. Defer to V1.5 local-makers surface.'
   WHERE id = <ENTITY_ID>;
  ```
- **Exact SQL (alternative — soft-delete):**
  ```sql
  UPDATE entities SET deleted_at = NOW() WHERE id = <ENTITY_ID>;
  ```
  (Adjust column name to match V1 schema — could be `deleted_at`, `is_deleted`, or similar.)
- **Caveats / open questions:**
  - Verify whether The Q Gallery exists as its own row — if yes, it should be un-DRAFTed as the canonical art-gallery entry, with Simply Savage referenced only via crowd_notes or a future artist-affiliation table.
  - The original Phase 5.6 categorization (cat-2 events + `art_gallery` primary type) is wrong on both axes — drop both regardless of disposition.

---

## Summary Table

| Rank | # | Entity | Confidence | Recommended Disposition | Operator Time Estimate |
|---:|---:|---|:---:|---|---:|
| 1 | 32 | Anderson AZ West | **HIGH** | un-DRAFT (consumer-retail powersports dealer) | ~1 min |
| 2 | 34 | Butterfly Garden | **HIGH** | un-DRAFT, keep cat-7, add crowd_notes (sub-feature of Rotary Park) | ~2 min |
| 3 | 35 | ASU Swanson Fields | **HIGH** | un-DRAFT, normalize case, keep cat-7 (city-maintained fields, not classes/programs) | ~2 min |
| 4 | 37 | Simply Savage Designs | **MEDIUM** | **keep DRAFT + defer V1.5** (preferred) or soft-delete — solo artist, no storefront | ~3 min (operator judgement call) |

**Total operator time to chip through all 4:** ~8 min.

**Net publish count from this batch:** 3 un-DRAFTed (#32, #34, #35) + 1 deferred or deleted (#37).

**Cross-cutting follow-ups to add to V1.5 backlog:**
- Sister-location dedupe check for Anderson Powersports (north-Havasu Lake Havasu Ave site) if it surfaced as a separate row.
- Rotary Community Park / Butterfly Garden parent-child relationship — model in future schema or fold into crowd_notes for now.
- Local-makers / artist-trail subcat for V1.5 (covers Simply Savage Designs + any other Havasu Art Trail participants surfaced by future scrapes).
- The Q Gallery (2102 McCulloch Blvd N) — if not already in DB, add as a candidate for next scrape pass; it's the actual visit-able venue that hosts Simply Savage's work.

---

## Sources

- Anderson AZ West: [Polaris dealer listing](https://www.polaris.com/en-us/commercial/commercial-dealers/arizona/lake-havasu/2404500/), [Yelp](https://www.yelp.com/biz/anderson-az-west-lake-havasu-city-2), [Birdeye reviews](https://reviews.birdeye.com/anderson-az-west-169424286551285), [official site](https://www.andersonazwestallsports.com/)
- Butterfly Garden: [lhcaz.gov Rotary Park page](https://www.lhcaz.gov/parks-recreation/parks-trails/rotary-community-park), [Waze pin](https://www.waze.com/live-map/directions/us/az/lake-havasu-city/butterfly-garden), [Yelp](https://www.yelp.com/biz/butterfly-garden-lake-havasu-city), [Tripadvisor reviews](https://www.tripadvisor.com/Attraction_Review-g31262-d7923620-Reviews-Rotary_Community_Park-Lake_Havasu_City_Arizona.html)
- ASU Swanson Fields: [lhcaz.gov ASU Fields page](https://www.lhcaz.gov/parks-recreation/parks-trails/asu-fields), [ASU Havasu](https://havasu.asu.edu/), [ASU Havasu closure article](https://www.havasunews.com/free_access/reports-asu-havasu-could-close-by-june/article_0d67ddf4-79e4-11ef-8585-970001e1f1a3.html)
- Simply Savage Designs: [RiverScene profile](https://riverscenemagazine.com/from-old-to-new-artist-creates-art-with-unconventional-items/), [Havasu Art Trail 2024](https://www.havasuarttrail.com/tyler-savage-2024), [Instagram](https://www.instagram.com/simplysavagedesigns/), [Etsy shop](https://www.etsy.com/shop/SimplySavageDes), [The Q Gallery FB post](https://www.facebook.com/theQart/posts/the-q-gallery-gifts2102-mcculloch-blvd-nlake-havasu-city-az86403/1557440362272442/)
