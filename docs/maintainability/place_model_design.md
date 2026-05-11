# Place Model — Design Memo

> **Status:** design only; no implementation, no migration. Output of the architecture-audit-driven design pass on 2026-05-14.
> **Source gap:** Gap #1 in `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.
> **Audience:** Cowork primary + Casey; future implementation-lane author (Cursor / CC).
> **Companion docs:** `docs/STRATEGY_PIVOT_2026-05-12.md` §8.2 (the LOCKED-as-deferred decision this memo recommends re-opening), `app/db/models.py` (current Provider + Category + Sponsor schema), `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3 Gap 1 (the gap framing).

---

## §1 Why Place exists (problem statement)

The operator's full vision is *"every useful Lake Havasu directory category for every demographic."* A substantial fraction of what users want surfaced isn't a business — it's a geographic or civic entity:

- **Recreational facilities:** dog parks, baseball fields, pickleball courts, tennis courts, soccer fields, public basketball courts, skate parks, disc golf courses, destination playgrounds.
- **Lake / outdoor infrastructure:** boat ramps, marinas (as places, distinct from marina-as-business), public beaches, fishing access points, scenic overlooks, hiking trailheads, off-road staging areas.
- **Civic / institutional:** public library, City Hall, DMV, Court, post office, schools (as places), community centers.
- **Hobbyist venues:** RC tracks, shooting/archery ranges, skating rinks (often run by clubs not businesses), model railroad meet-up spots, climbing walls (some private-but-non-commercial).
- **Landmarks:** London Bridge, lighthouses, public art / monuments, historical markers.
- **Ephemeral / seasonal locations:** farmers market site, food truck regular spots, weekly meet-up locations.

None of these fit `Provider` semantics cleanly. `Provider` carries commercial fields (phone, email, website, hours, owner-claimed verification, tier, sponsored_until) that don't apply or apply weirdly. Forcing dog parks into the `providers` table requires either nullifying half the fields permanently or carrying defensive code paths that branch on "is this actually a place or a business?" every time.

**Concrete failures the current schema produces for places:**

- `Provider.category` is required (`nullable=False`) — but a dog park doesn't have a business category; it has a place type.
- `Provider.tier` defaults to `"free"` and supports `"verified"` / `"sponsored"` — a public dog park is none of those; it's just public.
- `Provider.verification_method` enum lists `owner_confirmed`, `phone_call`, `manual`, etc. — none of which describe how you verify a dog park exists (you visit it; it's a fact, not an owner-confirmed claim).
- The Provider profile page CC just shipped renders "Verified business" / "Last verified" / "Sponsored" badges — none semantically valid for a park.
- Sponsor packaging (Verified Presence at $79/mo, Category Visibility at $349/mo) is owner-paid; no owner claims a public park.

The audit ranks Place as the single biggest schema gap because it blocks meaningful coverage of `Outdoors & Parks`, much of `Pets` (dog parks), parts of `On the Water` (ramps, beaches), parts of `Family` (playgrounds, sports fields), parts of `Community` (civic), and most of the "things any demographic finds useful" examples Casey enumerated.

---

## §2 Three design options

### Option A — Separate `places` table

A new top-level entity, parallel to `Provider`. Place rows live in their own table with their own schema. Categories like "dog parks" are first-class Place sub-types. Chat and category-page queries union across `providers` + `places` when serving cross-cutting queries.

**Pros:**
- Clean semantic separation. Place doesn't carry irrelevant business fields; Provider doesn't carry irrelevant geographic fields.
- Migration is purely additive — Provider table is untouched.
- Sponsor model's `business_id` is already FK-less (per audit finding at `app/db/models.py:547`) — a Place can be a Sponsor target without schema change.
- Query patterns stay simple per-table.

**Cons:**
- Chat and search must union across both tables for cross-cutting queries ("where can I go with my dog?" returns dog parks + dog-friendly restaurants).
- Some entities are genuinely both — a marina is a Place (the geographic ramp + slips) AND a Provider (the business renting boats). Two-row representation with a soft link.

### Option B — Flag/discriminator on `Provider`

Add `Provider.entity_type: Enum["business", "place"]` (or similar). Place entities live in the `providers` table with `entity_type="place"`, and many existing fields become nullable.

**Pros:**
- Single table for all directory entities. Chat and search query one table.
- Sponsor model already wired to `business_id` (an integer that today happens to be Provider but could be anything in this model).

**Cons:**
- `Provider` schema becomes a mess of conditional fields. Half-nullable on every column. Defensive code paths everywhere.
- Type erasure: every query has to filter by `entity_type` to be semantically clean. Easy to forget; bugs everywhere.
- The Provider model is already 100+ lines. Doubling its responsibility doubles the test surface.
- Migration touches the most-used table in the schema. Higher risk.

### Option C — Polymorphic base table

Create a `directory_entity` base table with shared fields (id, slug, name, lat/lng, district, category_id, photos, last_verified_at). `provider` and `place` become subtype tables that reference it.

**Pros:**
- Cleanly handles "entity is both Place and Provider" — one base row, two subtype rows.
- Shared fields live once.

**Cons:**
- Two table joins on every query (base + subtype). Performance cost at scale (the audit's #5 scaling concern).
- Migration is invasive — every existing Provider needs a base row created.
- ORM polymorphism in SQLAlchemy is more complex; future maintainers need to understand it.
- Over-engineered for current scale; YAGNI for V1.

---

## §3 Recommendation — Option A (separate `places` table)

Ship Place as a new top-level entity in a parallel `places` table. Keep `Provider` untouched. Build cross-entity union logic at the query layer (chat + search + category pages), not at the schema layer.

**Why Option A wins:**

1. **Schema cleanliness.** Each entity carries only the fields it needs. No half-nullable business fields on a dog park; no half-nullable geographic-amenity fields on a plumber.
2. **Migration safety.** Purely additive. Provider, Sponsor, Event, Program tables are untouched. Rollback is trivial.
3. **Sponsor model already supports it.** `Sponsor.business_id` is integer-typed with no DB FK (`app/db/models.py:547` per audit). A Sponsor row pointing at a Place works today — only application-layer validation needs to learn about Place.
4. **Cross-entity union is bounded.** Chat handlers and category-page queries need union logic, but that lives in one place (`app/chat/unified_router.py` for chat; `app/providers/queries.py` patterns extend to a new `app/places/queries.py`). Not a sprawling concern.
5. **"Entity is both" is rare and handled by a soft link.** A marina-as-Place + marina-as-Provider is two rows linked via `Place.linked_provider_id` (nullable FK). Application code joins when needed.

**The case for not picking Option B (flag-on-Provider):** the architecture audit's biggest scaling concern is N+1 query patterns and missing indexes (§5). Option B doubles the row count on the most-queried table and forces every query to filter by entity_type. Option A keeps the hot path (Provider queries) at half the row count it would otherwise be.

**The case for not picking Option C (polymorphic):** YAGNI for V1. We don't have shared-field-change requirements that would benefit from a base table. We can refactor to polymorphism later if cross-entity field churn becomes painful; we cannot easily undo a polymorphic schema if it turns out to be over-engineered.

---

## §4 Schema specification

### §4.1 `Place` model

```python
class Place(Base):
    """Geographic / civic / recreational entity that is not a commercial business.

    Distinct from Provider (commercial entities). Parks, dog parks, boat ramps,
    beaches, scenic overlooks, hiking trailheads, civic locations, hobbyist
    venues, landmarks, etc. Places have geographic facts that are verified by
    visiting/observing rather than owner-confirmed.
    """

    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Taxonomy
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    place_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "dog_park", "boat_ramp", "trail", "civic", "landmark"
    district: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Geo
    address: Mapped[str | None] = mapped_column(String, nullable=True)  # street address if applicable
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    google_place_id: Mapped[str | None] = mapped_column(String, nullable=True)  # when Google has it

    # Hours (some places have hours: parks close at sunset, civic locations have business hours)
    hours_structured: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    hours_freetext: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Photos
    photo_refs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # owner-uploaded or operator-uploaded
    google_photo_refs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # if Google has photos

    # Amenities + structured attributes — place-specific, distinct from Provider.attributes
    amenities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Example shapes by place_type:
    # dog_park: {"fenced": true, "separate_small_dog": true, "water": true, "shade": "partial", "parking": "lot", "free": true}
    # boat_ramp: {"launch_fee": "10", "trailer_parking": 30, "restrooms": true, "lighting": false}
    # trail: {"length_miles": 2.5, "difficulty": "moderate", "dog_friendly": true, "shade": "none", "water": false}
    # civic: {"hours_change_holidays": true, "appointment_required": false}

    # Verification — facts about places are observation-based, not owner-confirmed
    last_verified_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Allowed values: "operator_visit" | "google_places" | "city_records" | "user_reported" | "stale"
    # (Stricter and different from Provider.verification_method semantics.)

    # Source attribution
    source: Mapped[str] = mapped_column(String, nullable=False, default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Editorial flag (same semantics as Provider.featured — "Hava's pick")
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Soft link to a Provider when a Place IS also a business (e.g., a marina)
    linked_provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id"), nullable=True
    )

    # Bookkeeping
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    category_ref: Mapped["Category | None"] = relationship(
        "Category", foreign_keys=[category_id]
    )
    linked_provider: Mapped["Provider | None"] = relationship(
        "Provider", foreign_keys=[linked_provider_id]
    )
```

### §4.2 Key differences vs `Provider`

| Field | Provider | Place | Why different |
|---|---|---|---|
| `category` (legacy string) | yes (required) | absent | Place doesn't need legacy column; designed post-pivot |
| `category_id` (FK) | yes | yes | Both reference `categories` table; same taxonomy applies where it overlaps |
| `place_type` | absent | yes (required) | Place sub-type discriminator (dog_park, boat_ramp, etc.) — finer-grained than category |
| `phone` / `email` / `website` | yes | absent | Places usually have none of these |
| `facebook` | yes | absent | Same |
| `attributes` | yes (JSON) | absent | Replaced by `amenities` JSON with place-type-specific shape |
| `amenities` | absent | yes (JSON) | Place-specific structured fields |
| `tier` / `sponsored_until` / `featured_description` | yes | absent | Places don't have sponsorship semantics directly — see §6 for how sponsor slots work on Place pages |
| `verified` (bool) | yes | absent | Replaced by `verification_method` enum that includes "observation" semantics |
| `verification_method` enum | `manual`, `scraper`, `owner_confirmed`, `npi_registry`, `none`, `phone_call`, `in_person`, `web_form_submission`, `email_confirmation` | `operator_visit`, `google_places`, `city_records`, `user_reported`, `stale` | Place verification is observation-based, not owner-confirmed |
| `raw_enrichment_json` / `embedding` / `enrichment_version` | yes | absent (V1) | Defer enrichment infrastructure for Place until needed |
| `linked_provider_id` | absent | yes (nullable FK) | Cross-entity link for marina-as-Place + marina-as-Provider |

### §4.3 `Category` table — extension

The current `Category` table (`app/db/models.py:580`) needs no schema change. Existing categories serve both Provider AND Place:

- **Outdoors & Parks** → mostly Places (parks, trails, scenic spots) + some Providers (guide services)
- **On the Water** → mix (boat rentals are Providers; ramps are Places; marinas are both)
- **Pets** → mix (vets are Providers; dog parks are Places)
- **Community** → mix (community centers are Places; community organizations may be Providers)
- **Family** → mix (kid-friendly restaurants are Providers; playgrounds/parks are Places)

The chat and category page queries union across `providers WHERE category_id = X` UNION `places WHERE category_id = X`. Place-only categories like "dog parks" or "ramps" become **sub-types within a category** (Pets/dog_park, On the Water/boat_ramp) rather than separate top-level categories.

**Open question:** the taxonomy research from ChatGPT may surface a need for one or more Place-heavy categories that don't fit the current 12 (e.g., a dedicated "Outdoor Recreation" category split from "Outdoors & Parks"). Defer this question to the taxonomy lock pass after the research returns.

---

## §5 Relationship to Provider / Sponsor / Event / Program

**Place ↔ Provider:** soft-linked via `Place.linked_provider_id` when one entity is both. Example: a marina has a Place row (the geographic ramp + slips + parking) AND a Provider row (the business renting boats). The Place row's `linked_provider_id` points at the Provider; the chat and category page can render either or both depending on user intent.

**Place ↔ Sponsor:** the existing `Sponsor.business_id` field is integer-typed with no DB-level FK (verified by audit at `app/db/models.py:547`). Application-layer validation needs to learn that `business_id` can reference either a `providers.id` (string UUID) OR a `places.id` (string UUID). **Important:** since both tables use String UUID PKs, type collision isn't possible — IDs are unique across both tables. Suggest adding a `Sponsor.entity_type: Enum["provider", "place"]` field to disambiguate which table the FK refers to. Single small migration.

**Place ↔ Event:** Events can reference a Place via `Event.place_id` (new nullable FK) in addition to the existing `Event.provider_id`. Either OR both can be set. Example: a kayak race event might link to both the marina (Provider) and the launch ramp (Place). Migration adds the FK.

**Place ↔ Program:** Programs (classes / recreation activities) can also reference a Place via `Program.place_id` (new nullable FK). Example: a yoga-in-the-park program references the park (Place) and optionally the yoga studio operating it (Provider).

**Net schema change:** new `places` table + `Sponsor.entity_type` field + nullable `Event.place_id` FK + nullable `Program.place_id` FK. Single migration.

---

## §6 Chat query integration

The chat's tier 1 / tier 2 / tier 3 routing (per `app/chat/unified_router.py`) needs to learn about Place. Implementation pattern:

- **Tier 1 (deterministic):** entity matcher should find Place names just like Provider names. Add Place names to the matcher's lookup index. The matcher already returns `(entity_id, score)` tuples; the only change is the type — caller now needs to know whether the matched ID is a Provider or a Place. Suggest a Tier 1 return shape extension to include `entity_type`.
- **Tier 2 (structured retrieval):** category-filtered queries currently hit `providers` only. Extend to union with `places`. Example: "dog parks in Lake Havasu" should match Place rows with `place_type="dog_park"`.
- **Tier 3 (LLM synthesis):** the synthesis prompt includes a list of matched entities. The format needs to distinguish "businesses" from "places" so the LLM doesn't write "Call the dog park to verify hours."

**Confabulation guardrails:** Place entities have fewer attributes than Providers (no phone, no website, often no hours). The LLM should not hallucinate phone numbers for parks. The HALT 3 close-out work (Gap #2 in audit) becomes more important here — Place data is patchier and the LLM has more room to invent.

**Cross-entity queries:** "dog-friendly" pulls from BOTH Provider (restaurants with `attributes.dog_friendly`) AND Place (dog parks + dog-friendly trails). Chat handler unions results. Each row is tagged with its entity type so the LLM can differentiate ("Try Mudshark patio for breakfast — dog-friendly. Then walk over to North Park dog park.").

---

## §7 Sponsor slot integration on Place pages

Place pages need their own URL pattern: `/place/<slug>` (parallel to `/provider/<slug>`). The template structure largely mirrors the Provider profile page CC just shipped:

- Identity header (name, place_type label, district, "Hava's pick" badge if featured)
- Action row (Directions, Save for later, Ask Hava — no Call/Website since Places don't have them)
- Amenities section (rendered from the `amenities` JSON per place_type schema)
- Photos
- Hours (if applicable)
- Map embed (more important than Provider since Place is geographic-first)
- Sponsor slot at bottom (optional)

**Sponsor slot on Place pages:** the Sponsor.business_id field already supports non-Provider entities. Example: a marina (Provider) sponsors the boat ramp (Place) — Sponsor row has `entity_type="place"`, `business_id=<place_id>`. The Place page's sponsor slot renders the marina's sponsor card.

**Open question for the operator:** does Category Visibility ($349/mo if that pricing model is what wins) apply to a Place page? Or only to a Provider category page? My read: Category Visibility is per-category, not per-page. A sponsor of "On the Water" gets visibility on both the category list page AND on individual Place pages within that category. This is monetization-specific; defer until model is locked.

---

## §8 Migration strategy

Single migration. Phased upgrade:

1. **Create `places` table** with all fields per §4.1.
2. **Add `Sponsor.entity_type: String(16)`** with default `"provider"` for existing rows; NOT NULL after default applies.
3. **Add `Event.place_id`** nullable FK to `places.id`. No backfill — existing events keep `provider_id` only.
4. **Add `Program.place_id`** nullable FK to `places.id`. Same.
5. **No data backfill needed.** Existing rows aren't Places; new Places get inserted via the operator workflow (admin form + scraper + manual recovery checklist).

Idempotent. Reversible. No production data risk.

---

## §9 Open questions for Casey

1. **Re-open pivot §8.2 LOCKED status?** §8.2 says Place is deferred to Phase 2 because "Home Services + Eat & Drink ship business-only first; districts handled via string field." Under the full vision (everything Lake Havasu + all demographics + dog parks/parks/civic) Place is critical for V1. Recommendation: re-open §8.2 and lock Place in as a Phase 1 ship.

2. **Place slug format and uniqueness across tables.** Place uses the same slug shape (`make_unique_slug` from `app/utils/slug.py`). Should slug uniqueness be enforced across `providers` AND `places` combined (so `/provider/acme` and `/place/acme` can't both exist), or per-table only? My recommendation: per-table only, with the URL path (`/provider/` vs `/place/`) being the disambiguator. Avoids cross-table slug-allocation logic and lets a Place and a Provider share a slug if they're semantically the same entity (e.g., the marina is at both `/provider/jet-ski-rentals-lhc` and `/place/site-six-marina` — different slugs, no collision).

3. **Reviews / ratings for Places.** Some Places have Google ratings (parks, museums). Some have none (a quiet trail, a community ball field). Should Place pages render Google ratings when available? My recommendation: yes, via `attributes.google_rating` mirroring Provider. Most Places will have nothing; that's fine.

4. **Place verification cadence.** Provider has `last_verified_at` and operator workflow for re-verification. Places change less often (a park doesn't go out of business), so the cadence is different. Suggest annual re-verification for most Places; quarterly for those with hours (civic locations); ad-hoc for landmarks (verify once, leave alone). Worth setting as an operator policy in the manual-recovery checklist.

5. **Naming the entity in chat.** When the chat surfaces a dog park, does it say "Aquatic Park" or "Aquatic Park dog park" or "the dog park at Aquatic Park"? Tier 3 LLM context shape needs to handle Place naming gracefully. Worth a small Tier 3 prompt update once Place data starts landing.

6. **`place_type` vocabulary.** §4.1 examples: `dog_park`, `boat_ramp`, `trail`, `civic`, `landmark`. The full vocabulary is what the taxonomy research will inform. Suggest waiting on the ChatGPT research output to lock the canonical `place_type` enum.

7. **Operator-visit verification workflow.** The admin form for Place will be different from the Provider admin form (no phone/website/business fields; new amenity fields per place_type). Operator workflow for "I just visited the dog park; let me enter the data" needs UI support. Defer admin-form-for-Place to the launch-prep pass; for V1 data-gathering, CSV ingest or direct DB insert is acceptable.

---

## §10 Effort estimate

**Migration + ORM model:** S (hours).

**Sponsor + Event + Program FK additions:** S (hours).

**Place admin form + ingest tooling:** M (2-3 days). New form fields per `place_type`; validation logic.

**Chat integration (Tier 1 + Tier 2 unioning + Tier 3 prompt updates):** M (2-3 days). Bounded but touches `app/chat/` which is sensitive.

**Place profile page template (`/place/<slug>`):** S-M (1-2 days). Mostly mirrors the Provider profile page; place_type-specific amenity rendering is the only novel bit.

**Cross-entity union in category-page queries:** S (hours). One-time pattern; future category pages copy.

**Tests:** M (1-2 days). Schema tests, ORM relationship tests, chat-integration tests, template tests.

**Total: roughly 7-10 days of focused engineering work**, dispatchable as 2-3 Cursor or CC lanes. Maps to the audit's "L effort (1-2 weeks)" classification, on the low end.

---

## §11 Sequencing implications

If Place ships in Phase 1 of the build sequence (not Phase 2 as currently locked), the order is:

1. **Lock taxonomy + place_type vocabulary** (after ChatGPT research returns)
2. **Place schema migration + ORM model** (S)
3. **Place admin form** (M) — unblocks operator data entry
4. **Scheduled scraper extension** to discover Place candidates from Google Places (the Places API actually returns parks and ramps with `types: ["park"]`, `types: ["marina"]` etc.) — fold into existing `scripts/places_discovery.py`
5. **Manual-recovery campaign** for Places that Google doesn't have (running in parallel with scraper)
6. **Place profile page template** (S-M)
7. **Chat integration for Place** (M) — gated on the HALT 3 close-out polish for confabulation guardrails on patchy data
8. **Category-page cross-entity union** (S) — done alongside the Home Services / Eat & Drink category landing pages

Place ships **before** the first category landing pages (Home Services / Eat & Drink) — the category pages need to handle cross-entity union from day one, which means Place schema must exist when those pages are built.

---

## §12 Summary

Place is the single biggest schema gap in the current architecture relative to the full vision. The audit's recommendation to re-open the §8.2 deferral is correct. Option A (separate `places` table) is the cleanest design — additive migration, no Provider table touch, sponsor model already supports cross-entity references. Total effort 7-10 engineering days; sequenced into Phase 1 of the build before any further category landing pages ship. Seven open questions for operator decision; most are minor / defer-until-taxonomy.

**Next step after this memo is reviewed:** lock the open questions, then file a Cursor or CC dispatch brief for the Place migration + ORM model + admin-form scaffolding (Step 2 + 3 of §11 sequencing).
