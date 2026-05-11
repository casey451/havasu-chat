# Lake Havasu Directory Taxonomy — Research Synthesis

> **Origin:** ChatGPT deep-research output 2026-05-14 in response to `outputs/chatgpt_prompt_directory_taxonomy_research.md`. Source doc was uploaded to session sandbox (`uploads/deep-research-report.md`); this synthesis captures the load-bearing decisions and feeds directly into the master build plan.
>
> **Status:** taxonomy LOCKED; schema decision LOCKED (unified ENTITY); 7 strategic questions from §Open strategic questions remain for the master plan.

---

## §1 The 12 categories (LOCKED 2026-05-14)

ChatGPT did not expand the count — it materially restructured what's in each bucket. Same 12, structurally re-drawn.

### Tier 1 — Resident-critical, highest monetization, launch first (~390-740 entries)

| Category | Slug | Est. inventory | Change vs original |
|---|---|---|---|
| Home & Property Services | `home-property-services` | 120-220 | Renames + expands Home Services |
| Health, Wellness & Care | `health-wellness-care` | 30-70 | Renames + broadens Health |
| Eat & Drink | `eat-drink` | 90-140 | Keep, tighter boundaries |
| On the Water | `on-the-water` | 40-90 | Keep, broaden to full boating stack |
| Auto, RV & Fuel | `auto-rv-fuel` | 50-100 | Renames Auto & Gas |
| Shopping, Grocery & Essentials | `shopping-essentials` | 60-120 | Renames Shopping, prioritize essentials |

### Tier 2 — High utility, manageable upkeep (~75-175 entries)

| Category | Slug | Est. inventory | Change vs original |
|---|---|---|---|
| Outdoors, Parks & Trails | `outdoors-parks-trails` | 20-50 | Renames Outdoors & Parks |
| Lodging & Vacation Rentals | `lodging-vacation-rentals` | 40-90 | Renames Lodging; absorbs vacation rentals |
| Pets | `pets` | 15-35 | Keep, broader scope |

### Tier 3 — Schedule-heavy, ship after refresh tooling (~90-250+ entries)

| Category | Slug | Est. inventory | Change vs original |
|---|---|---|---|
| Events | `events` | 50-150 annual | Keep, lower build priority |
| Classes, Sports & Recreation | `classes-sports-recreation` | 25-60 | **NEW** — replaces Family as structured inventory |
| Public & Civic Resources | `public-civic-resources` | 15-40 | **NEW** — splits from Community (trust/retention) |

### Structural changes summary

**DELETED:**
- `Family` (too broad/fuzzy; reborn as cross-cutting filter)
- `Community` (catch-all bucket with no clean schema; split into Public & Civic + Events + Classes/Sports)

**NEW:**
- `Classes, Sports & Recreation` (replaces Family as schedulable activity inventory)
- `Public & Civic Resources` (splits from Community; trust/retention category)

**RENAMED/BROADENED:**
- Home Services → Home & Property Services (expanded scope)
- Health → Health, Wellness & Care (broader)
- Auto & Gas → Auto, RV & Fuel (includes RV)
- Shopping → Shopping, Grocery & Essentials (essentials-first)
- Outdoors & Parks → Outdoors, Parks & Trails (broadened)
- Lodging → Lodging & Vacation Rentals (absorbs vacation rentals)
- On the Water (kept, broadened to full boating stack)
- Eat & Drink (kept, tighter boundaries)
- Pets (kept, broader scope)
- Events (kept, ship-later priority)

Total estimated inventory: **555-1,265 entries** across all 12.

---

## §2 Cross-cutting concepts — NOT top-level categories

Per ChatGPT research §"Cross-cutting concepts that should not become categories" — these are filter-axes / landing pages / ranking signals / chat-layer interpretations, NOT buckets:

- Date night
- Family-friendly
- Dog-friendly
- Open now
- After-hours / emergency
- Lake view / waterfront
- Boat-accessible (already locked as a directory-wide mode per Opus #4)
- **Near the bridge** (first-class geographic-intent axis — not just a landmark)
- Remote-work-friendly
- Snowbird-friendly
- Late-night
- Kid-friendly
- Accessible / ADA
- Local-owned
- Low-crowd / uncrowded
- Vacation-rental-owner-friendly

Implementation pattern: each is some combination of filter chip + landing page + ranking signal + chat interpretation. None become top-level categories.

---

## §3 Schema decision — Unified ENTITY (LOCKED 2026-05-14)

ChatGPT recommended a normalized schema with a single ENTITY core + category-specific extensions via many-to-many through ENTITY_CATEGORY. Casey accepted this recommendation 2026-05-14.

### Entity-relationship shape

```
CATEGORY ||--o{ ENTITY_CATEGORY : classifies
ENTITY ||--o{ ENTITY_CATEGORY : belongs_to
ENTITY ||--|| LOCATION : has
ENTITY ||--o{ HOURS : has
ENTITY ||--o{ CONTACT_POINT : has
ENTITY ||--o{ FEATURE : tagged_with
ENTITY ||--o{ OFFERING : provides
ENTITY ||--o{ SERVICE_AREA : covers
ENTITY ||--o{ SCHEDULE : runs
ENTITY ||--o{ SOURCE_EVIDENCE : verified_by
ENTITY ||--o{ SPONSORSHIP_SLOT : monetized_by
```

### Impact on existing schema

- **Provider model** (current) → migrated into ENTITY rows with `entity_type="commercial"` (or similar). Provider-specific fields move to a Provider-extension table OR to FEATURE/OFFERING/CONTACT_POINT records depending on shape.
- **Place model** (per `place_model_design.md`) → no longer a separate top-level table. Place becomes ENTITY rows with `entity_type="place"` + Place-specific fields in extension table or amenities JSON.
- **Event model** → migrated into ENTITY rows with `entity_type="event"` + SCHEDULE records for dates.
- **Program model** → migrated into ENTITY rows with `entity_type="program"` + SCHEDULE records.
- **Sponsor model** → unchanged in shape (no DB FK on `business_id`; can already reference any ENTITY).
- **Category model** → unchanged in shape; gains the ENTITY_CATEGORY many-to-many.

### Impact on existing design memos

- `place_model_design.md` Option A (separate `places` table) → superseded by ENTITY approach. The Place-specific content (place_type discriminator, amenities JSON shapes, operator workflow, boat-access fields, heat_exposure tagging) carries forward; what changes is the table shape (ENTITY + extension vs separate table). Brief amendment memo to follow.
- `image_storage_design.md` — the polymorphic `(entity_type, entity_id)` pattern in the Photo schema gets cleaner: just `entity_id` referencing ENTITY.
- `account_lite_v01_design.md` — UserFavorite + Claim already polymorphic; same simplification.
- `search_index_decision.md` — Postgres FTS gets simpler: one tsvector on ENTITY rather than per-table indexes.
- `conditions_panel_and_alerts_design.md` — favorites query is simpler (one ENTITY table to join).
- `boat_access_mode_design.md` — boat_access JSON lives on ENTITY where `entity_type in (commercial, place)`. Same content.

### Implementation cost

ChatGPT did not estimate. My read: **~2-3 weeks additional architecture work** beyond what was previously scoped — the ENTITY migration touches Provider/Place/Event/Program in app code (queries, view-models, templates), but the existing Sponsor + Category + sub-models stay mostly stable.

Saves future migration pain: if we'd shipped V1 on Provider+Place separate then refactored to ENTITY later, that's much bigger surgery against production data.

---

## §4 Sponsor packaging — ChatGPT pushes back on the default plan

ChatGPT recommended substantial changes to the Verified Presence / Category Visibility / Seasonal Takeover defaults. Casey's monetization is kept flexible, so these are inputs to the eventual locking decision rather than locked changes:

### Verified Presence ($79/mo)

Directionally sensible. Recommended additions: annual discount, tighter feature set (ownership claim, photos, key attributes, messaging/call CTA, emergency badge eligibility, source-verification priority). Most attractive in Home & Property, Pets, Auto/RV/Fuel, Health.

### Category Visibility ($349/mo flat) — TOO BLUNT

Replace with **intent-cluster sponsorships**:

| Cluster | Recommended pricing |
|---|---|
| Emergency / high-intent service clusters | $499-$1,250+/mo (depending exclusivity) |
| Water/boating clusters | $500-$1,500+/mo (peak season) |
| Dining / lodging / district placement | $249-$749/mo |
| Long-tail local categories | $99-$299/mo |
| Public & Civic | Generally non-sponsored or lightly underwritten only |

### Seasonal Takeover ($1,500-$5,000)

**Too LOW for marquee boating windows** (Boat Show alone draws $50M+ in inventory per official sources). **Too HIGH for weak categories**. Replace with **season + district + intent bundling**:

- Spring boating package — Desert Storm / Boat Show / launch-ramp corridor / marinas / towing / lodging
- Winter-snowbird package — healthcare / grocery / golf / pickleball / senior services / long-stay lodging
- Bridge district package — channel-area dining / lodging / tours / shuttles / nightlife-adjacent operators

### Critical sponsorship rule

**Do NOT allow sponsorship to overpower trust-sensitive ranking in Health, Pets, or Public & Civic Resources.** Sponsorship increases exposure within clearly disclosed bounds only; it does not override organic ranking on emergency or care-critical queries.

---

## §5 Geographic + seasonal patterns

### "Near the bridge" as first-class geographic-intent axis

Not just a landmark — a real geographic axis that changes dining, lodging, launch, walking, and nightlife recommendations. London Bridge connects mainland to an island containing shops, restaurants, hotels, resorts, housing.

### Mainland corridors vs lake/island

- Resident-essential surface concentrates along **McCulloch, Acoma, Kiowa, Mesquite, Highway 95**
- Visitor-essential surface concentrates around **English Village, channel, state-park access**
- Ranking principle: **trip purpose first, then district**

### Seasonal ranking flex

Same taxonomy year-round; ranking weights flex by season:

- **Spring/summer (May-September):** On the Water + Lodging + Auto/RV/Fuel + waterfront dining surface higher; heat-aware ranking kicks in
- **Winter/shoulder (October-April):** Health + Shopping + golf + pickleball + senior services + homeowner-support surface higher; snowbird-return view active
- **Event windows:** Boat Show (April), Balloon Festival (January), IJSBA World Finals (October), Desert Storm — premium periods, premium sponsorship pricing

Extends the time-aware ranking heuristic from Opus #2 with a seasonal dimension. Same architectural shape; different ranking weights per season.

---

## §6 Sequencing — Tier-based build

ChatGPT's recommended build order (matches Casey's "build-first / sell-after" framing):

1. **Foundation** — Core ENTITY schema, dedupe, source evidence, address normalization, hours model, category assignments, filter framework, geography-aware ranking. Everything else depends on this.
2. **Launch core (Tier 1)** — Home & Property, Health, Eat & Drink, On the Water, Auto/RV/Fuel, Shopping. Highest practical demand and monetization. Site is immediately useful for residents.
3. **Stable discovery layer (Tier 2)** — Outdoors, Lodging & VR, Pets. High utility, manageable upkeep.
4. **Trust layer** — Public & Civic Resources. Improves retention; low monetization.
5. **Schedule-heavy: Events** — Only after refresh / expiry / cancellation tooling exists.
6. **Schedule-heavy: Classes, Sports & Recreation** — Only after recurring schedule / age bands / registration tooling exists.

Practical implication: instead of "all 12 categories launch in parallel," ship Tier 1 first (resident-critical spine), then Tier 2, then Tier 3 once schedule-tooling matures. This naturally aligns with the build-first sequencing — Tier 1 makes the site useful, Tier 2-3 deepen it.

---

## §7 Open strategic questions (from research §)

These need operator decision but most can be folded into the master plan:

1. **City-bounded vs cross-border surfaces.** Should certain intents surface Parker, Havasu Landing, or Topock assets when materially useful? Affects scrape scope.
2. **Google Maps Place IDs + Yelp IDs for dedupe.** Will ingestion join official records to these external IDs for entity resolution? Affects ingestion architecture.
3. **Dynamic / semi-dynamic data later.** Fuel prices, room availability, launch conditions, event cancellations — V1, V2, or never?
4. **Vacation-rental permits joined to lodging records.** Public data exists; operator decision on whether to integrate.
5. **Professional services as separate expansion later.** Lawyers, accountants, insurance — not currently in the 12. V2 question.
6. **Sponsorship strictness rules in Health, Pets, Public & Civic.** Per research recommendation: NEVER override ranking in these. Confirm.
7. **First-party neighborhood / district model.** Districts as named entities (English Village, North End, etc.) vs raw string field. Affects ENTITY schema.

Q2, Q6, Q7 are architecturally relevant for the master plan; Q1, Q3, Q4, Q5 can be deferred.

---

## §8 Master plan integration notes

When I write the master plan (after Opus UI/revenue returns), this synthesis drives:

1. **Phase 1 architecture** includes ENTITY schema design + migration of Provider/Place/Event/Program into ENTITY core. ~2-3 weeks added work.
2. **Tier-1/2/3 sequencing** structures the build phases. Tier 1 ships before Tier 2 ships before Tier 3.
3. **Cross-cutting concepts** as filters + landing pages + ranking signals + chat interpretations — confirmed pattern.
4. **Sponsor packaging recommendations** feed into the monetization phase as "default plan now includes intent-cluster pricing + season+district+intent bundles, not flat tiers."
5. **Geographic axis** + **seasonal flex** are first-class ranking concepts in the ranking heuristic, not afterthoughts.
6. **Open strategic questions** become decision points in the master plan; Casey resolves as we work through phases.

---

## §9 What's NOT changed

- All 8 design memos (audit, Place, account-lite, background-jobs, layered scrape, conditions/alerts, image storage, search index, boat-access) remain valid in concept. Schema-shape details adjust to ENTITY. Operator workflows, sponsorship logic, scrape strategy, UI patterns all carry forward.
- Opus 4.7 7 V1 feature additions (conditions panel, heat-aware ranking, seasonal hours, boat-access mode, crowd context, mobile-services, alerts) — all carry forward; #7 peer recommendations still held for V1.5 pilot.
- The pivot doc amendment (build-first, sell-after, full vision) — still authoritative direction.
- The 6-9 month timeline at solo-founder pace — ENTITY refactor adds ~2-3 weeks but is within the timeline.
