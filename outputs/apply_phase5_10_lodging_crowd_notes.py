"""Apply long-form crowd_notes to the top-10 lodging-vacation-rentals
(cat-10) entities.

Closes Phase 5.10 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` -- Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Drafts sourced from each entity's ``Provider.google_review_snippets``
(own column on Provider, NOT inside ``attributes`` -- per the 5.4
close-out 4 source-path correction). Top-10 surfaced via
``outputs/phase5_10_top10_discovery.py`` against
``Provider.google_review_count`` desc, taken post-2-apply (so the 6
Slice E NEW creates are eligible -- Travelodge by Wyndham at #4 made
the top-10).

Mirrors ``apply_phase5_9_classes_crowd_notes.py`` shape exactly:
id-prefix-keyed dict, ``--dry-run`` first, idempotent (overwrites
existing crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized in
5.4/5.5/5.6/5.7/5.8/5.9):** ``Entity.crowd_notes`` is mapped as JSON;
SQLAlchemy serializes dicts on write. Pass the dict directly --
do NOT ``json.dumps()`` first.

Snippet coverage in the post-2-apply top-10 was **100% (5 snippets
each)** -- abundant signal for hand-curating. The notes focus on
cat-10-specific themes per kickoff 4 rubric: cleanliness consistency,
staff helpfulness (named-staff callouts), room condition (beds,
showers, bathrooms), location relative to attractions (London Bridge,
restaurants, lake), amenities (pool / spa / breakfast / parking),
noise level, value for price, family-friendliness, accessibility for
mobility needs. Per the 5.10 ambig dump, ~25 ambig cat-1 hits were
geo-noise (strip-mall adjacency) so the notes don't try to surface
restaurant cross-links unless review text mentions them.

Usage:
    python outputs/apply_phase5_10_lodging_crowd_notes.py --dry-run
    python outputs/apply_phase5_10_lodging_crowd_notes.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# entity_id 8-char prefix -> {"short": str, "long": str}
# Drafted from Provider.google_review_snippets per entity. Operator
# edits inline before live apply if any text needs adjustment.
# Ordering matches the post-2-apply top-10 by review_count desc.
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "29d04918": {  # Quality Inn & Suites Lake Havasu City -- 1474r, 3.8*, hotel
        "short": (
            "Largest hotel by review volume in LHC (1474+ reviews, 3.8 stars). "
            "Reviewers describe a large multi-building property with a heated "
            "pool but dated rooms, breakfast-buffet supply shortages, traffic "
            "noise from McCulloch Blvd, and mixed front-desk service."
        ),
        "long": (
            "A high-volume property where consistency suffers from sheer scale. "
            "Reviewers consistently mention the heated pool (no hot tub), "
            "variable room cleanliness (some report blood/dirt on linens; "
            "others find rooms clean), and a breakfast buffet that runs short "
            "on plates, coffee, utensils, and condiments. Front-desk service "
            "ranges from professional to confrontational. Echo from group "
            "travelers in the open-air breeze-ways carries into rooms. Best "
            "for budget-conscious travelers prioritizing the McCulloch Blvd N "
            "location over polished hospitality; request a quiet room away "
            "from the road and breeze-way traffic."
        ),
    },
    "d5f9b4bb": {  # Hampton Inn Lake Havasu City -- 1292r, 4.0*, hotel
        "short": (
            "Reliable chain hotel near the lake (1292+ reviews, 4.0 stars). "
            "Reviewers highlight clean spacious rooms, comfortable beds, hot "
            "breakfast, helpful front-desk staff who rescue guests from "
            "worse hotels at check-in, working pool and jacuzzi, and a "
            "walkable downtown location with lake view from the back."
        ),
        "long": (
            "Hampton's brand standards translate well in LHC. Reviewers "
            "praise cleanliness, hot-meal breakfast variety, helpful staff "
            "(multiple guests mention being saved at check-in after fleeing "
            "other LHC hotels), and a back-of-property lake view. Pool and "
            "jacuzzi reliably operational. Walkable to the Rockabilly Reunion "
            "venue and other downtown events. Notable downsides reported: "
            "elevator outages, occasional housekeeping miscommunications "
            "(room service refused without guest knowledge), and one "
            "infamous left-behind beer can. Best for travelers wanting "
            "predictable chain quality near downtown."
        ),
    },
    "f7cee8f6": {  # Days Inn by Wyndham Lake Havasu -- 1049r, 3.8*, hotel
        "short": (
            "Budget chain hotel two blocks from London Bridge (1049+ reviews, "
            "3.8 stars). Reviewers value the price and walkable location but "
            "warn of dated rooms, paper-thin walls, broken hot tub, $20/night "
            "pet fee, and cleanliness complaints including occasional bedbug "
            "concerns. Inspect the room on arrival."
        ),
        "long": (
            "A budget option whose location/price merits often outweigh "
            "cleanliness concerns -- but read recent reviews carefully. Two "
            "blocks from London Bridge and the waterfront walkway. "
            "Pet-friendly with a $20/night fee. Reviewers describe undersized "
            "fitted sheets, scratchy towels, no hot water in the bathtub, "
            "paper-thin walls (breakfast-bar noise carries into adjacent "
            "rooms), drapes that don't fully cover windows, and a "
            "non-functional hot tub during multiple recent stays. Some "
            "recent reviews flag bedbug signs on box-springs and lingering "
            "marijuana smell. Best for travelers prioritizing walkable "
            "London Bridge access on a tight budget who can tolerate "
            "compromise on room quality."
        ),
    },
    "e6ffa5d2": {  # Travelodge by Wyndham Lake Havasu -- 901r, 4.0*, hotel (Slice E NEW)
        "short": (
            "Renovated chain hotel with a strong service reputation (901+ "
            "reviews, 4.0 stars). Reviewers praise the modernized rooms with "
            "new bathrooms, lake views from some rooms, walkable location for "
            "festivals (Rockabilly Reunion, Hot Rodz car show), and front-desk "
            "team Ophelia/'O' for above-and-beyond hospitality. No elevator -- "
            "request a first-floor room if mobility matters."
        ),
        "long": (
            "Recently renovated property where the rooms exceed chain-brand "
            "expectations. Reviewers consistently mention Ophelia (sometimes "
            "spelled 'O') at the front desk as a standout; modernized king-bed "
            "rooms with new bathrooms and good shower water pressure; clean "
            "spacious layout; lake-view rooms worth requesting. Pre-check-in "
            "available so key pickup is fast. Standard chain-fare breakfast "
            "(eggs, sausage, waffles, cereal, bagels) -- yogurt and fruit "
            "would round it out. No elevator (request first floor for "
            "mobility). One reported friction: an awkward front-desk "
            "interaction about reheated leftover food. Best for repeat LHC "
            "visitors attending annual car shows or concerts who prioritize "
            "a clean modernized room with helpful staff."
        ),
    },
    "d9e4d59a": {  # Crazy Horse Campgrounds -- 840r, 3.8*, campground
        "short": (
            "Lakefront campground with mixed reviews (840+ reviews, 3.8 "
            "stars). Reviewers split between praising lake-view sites, "
            "friendly staff, and clean bathrooms, and warning of $80/night "
            "pricing, broken laundry and shower facilities, restrictive dog "
            "breed policies, poorly maintained roads, and at least one "
            "management dispute that escalated to law enforcement."
        ),
        "long": (
            "The largest LHC campground by review volume. Lake-view sites "
            "are large with power and water (no sewer on lakeview spots); "
            "staff at check-in often described as friendly; bathrooms "
            "frequently kept clean. Documented issues: 9 broken laundry "
            "machines reported in a single review, no hot water in shower "
            "facilities, $80/night pricing complaints, restrictive policies "
            "on mixed-breed dogs that resemble Shepherds (reportedly denied "
            "entry), big potholes and unclear road markings in the loop "
            "roads, and at least one documented incident where a management "
            "dispute over a non-functional electrical pedestal escalated to "
            "law enforcement and a 30-minute eviction with no refund. "
            "Reservations reportedly hard to reach by phone. Best for "
            "self-contained RVers wanting the lakefront who can tolerate "
            "property quirks; less suited for tent campers, breed-sensitive "
            "dog owners, or guests expecting concierge-level conflict "
            "resolution."
        ),
    },
    "2a7e2973": {  # Studio 6 Hotel Lake Havasu -- 755r, 3.3*, motel
        "short": (
            "Budget motel with serious cleanliness concerns (755+ reviews, "
            "3.3 stars). Multiple recent reviewers report uncleaned rooms "
            "with hair/dirt/BLOOD on bedding, broken hot tub falsely "
            "advertised, health-inspection notices on pool gates, full-time "
            "RV residents in the parking lot, and difficult booking.com "
            "refund process. Inspect before unloading."
        ),
        "long": (
            "The lowest-rated property in LHC's top-10 for guest experience. "
            "Reviewers across multiple recent stays describe rooms requiring "
            "immediate request for a different unit due to visible filth "
            "(blood reported on mattresses, hair on bedding, dirt on "
            "surfaces). Hot tub repeatedly broken; pool reportedly under a "
            "health-inspector notice during one stay (guests still allowed "
            "in the gate but not the water). Apparent permanent RV residents "
            "in the parking lot near the pool with overnight disturbances. "
            "Refunds via booking.com difficult to obtain -- some guests "
            "report being charged the full $670 stay despite cancelling. One "
            "5-star outlier praises the staff and location but is far from "
            "representative. Best for: experienced budget travelers who "
            "inspect the room before unloading, with backup booking options "
            "ready. NOT recommended for families or first-time visitors."
        ),
    },
    "63dcc759": {  # Island Suites -- 748r, 4.3*, hotel
        "short": (
            "Highly-rated extended-stay hotel near London Bridge (748+ "
            "reviews, 4.3 stars). Reviewers praise clean kitchenette rooms, "
            "a heated pool drawing repeat guests, friendly attentive staff "
            "(Ember mentioned by name for above-and-beyond service), and a "
            "walkable location to restaurants and grocery stores. One "
            "reviewer extended their stay to a month."
        ),
        "long": (
            "A repeat-visit favorite -- the highest-rated hotel in the "
            "top-10. Each room includes a kitchenette (fridge, microwave), "
            "making it well-suited for longer stays. Reviewers consistently "
            "mention the heated pool as the catalyst for extending stays; "
            "the staff -- Ember named specifically for above-and-beyond "
            "service (one guest received a late-night fresh bagel plated "
            "with butter and cream cheese) -- is repeatedly cited. Beds "
            "described as extra comfy with no 'hotel smell.' Continental "
            "breakfast has good options. King-bed rooms and a hot-tub area "
            "available. Location walkable to London Bridge, restaurants, "
            "and grocery. One reviewer notes furniture has become more worn "
            "since a prior visit (occasional chairs uncomfortable). Best "
            "for travelers wanting extended-stay flexibility, families "
            "needing kitchenette amenities, or anyone valuing personalized "
            "hospitality over chain anonymity."
        ),
    },
    "24cdcabf": {  # Havasu Dunes Resort -- 712r, 4.4*, resort_hotel
        "short": (
            "Highest-rated lodging in LHC's top-10 (712 reviews, 4.4 stars). "
            "Reviewers praise the resort-style multi-night experience: clean "
            "one- and two-bedroom condominium units, accommodating staff who "
            "pre-position ground-floor rooms for mobility needs, on-property "
            "activities for kids, pool with handicap accessibility lifts, "
            "and proximity to a beach with skate park and playground."
        ),
        "long": (
            "The top-rated property in LHC's top-10. Operates as a timeshare/"
            "condo resort with one- and two-bedroom units, on-property "
            "activities, complementary laundry, Chromecast streaming, "
            "security staff, and a swimming pool with handicap lifts -- a "
            "rare amenity. Reviewers consistently mention pristine room "
            "conditions, fully-stocked kitchen and bathroom amenities, "
            "last-minute ground-floor accommodation for guests with "
            "accessibility needs, and quick Uber access for off-site "
            "outings. Note: 'GetAways at Havasu Dunes Resort' (separate "
            "Google listing, same physical address at 620 Lake Havasu Ave) "
            "is the booking-management entity; both listings resolve to the "
            "same property. Best for families on multi-night to weeklong "
            "stays who prioritize space, kitchen amenities, on-site "
            "entertainment, and accessibility."
        ),
    },
    "4c0ab37f": {  # Sway Hotel -- 638r, 4.3*, hotel
        "short": (
            "Recently remodeled boutique hotel near London Bridge (638+ "
            "reviews, 4.3 stars). Reviewers praise clean rooms with first-"
            "class finishes, friendly staff (Katherine and Desiree named), "
            "a heated outdoor pool, and views -- but flag paper-thin walls, "
            "ongoing renovations affecting common areas, and a small room "
            "footprint."
        ),
        "long": (
            "Modernized property with above-grade finishes for its price "
            "band. Recently remodeled rooms feature first-rate bathrooms, "
            "comfortable beds, and modern interiors. Outdoor pool described "
            "as 'spic and span.' EV/van charging available in the parking "
            "lot. Staff Katherine and Desiree mentioned by multiple "
            "reviewers for genuine helpfulness. A short walk to London "
            "Bridge and the lake shoreline walkway. Significant downsides: "
            "walls have minimal sound insulation (one reviewer attending a "
            "bike race reported neighbors slamming doors, fighting, and "
            "police called at 12:30 AM disrupting sleep before the event); "
            "fresh-paint and adhesive smell can be strong in just-remodeled "
            "rooms; small room footprint described by one guest as 'shoe "
            "box.' Best for couples or solo travelers wanting modernized "
            "rooms near the waterfront who can tolerate variable noise."
        ),
    },
    "2290daa8": {  # Super 8 by Wyndham Lake Havasu City -- 629r, 3.0*, hotel
        "short": (
            "Lowest-rated chain hotel in the top-10 (629+ reviews, 3.0 "
            "stars). Reviews split sharply: some praise budget-friendly "
            "clean rooms, lake views, hot tub, and an owner-operator named "
            "Mario; others report cockroaches and bedbug evidence, dirty "
            "rooms, and refund difficulties through booking.com. Inspect "
            "the room before unloading."
        ),
        "long": (
            "A property with the widest review spread in the top-10. The "
            "5-star reviews describe a clean budget-friendly hotel with a "
            "working hot tub, lakefront views, and a beloved front-desk "
            "owner-operator named Mario who treats guests 'like family.' "
            "The 1-star reviews -- concentrated in recent months -- report "
            "cockroaches sighted on beds (multiple sightings across stays), "
            "bedbug evidence on mattresses, and difficulty getting refunds "
            "through third-party booking sites (front-desk acknowledged the "
            "issue but couldn't issue a refund for non-direct bookings). "
            "The disparity suggests inconsistent room-quality control. Best "
            "for: budget travelers who request to inspect their assigned "
            "room before bringing in luggage, ideally booking directly with "
            "the hotel (not third-party) for refund flexibility. NOT "
            "recommended for guests sensitive to bugs or who want "
            "guaranteed-clean accommodations sight-unseen."
        ),
    },
}


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    """Resolve Entity by id-prefix (first 8 chars). Asserts exactly one
    active match."""
    rows = session.scalars(
        select(Entity).where(Entity.id.like(prefix + "%"), Entity.is_active == 1)
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(
            f"prefix-resolution collision: {len(rows)} active entities match "
            f"id LIKE {prefix!r}; expected exactly 1."
        )
    return rows[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        applied = 0
        skipped = 0
        for prefix, notes in CROWD_NOTES_TOP10.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  [skip] not found: id LIKE {prefix!r}")
                skipped += 1
                continue
            # JSON column -- pass dict directly per 5.3 f35d5e4 gotcha.
            ent.crowd_notes = notes
            ent.updated_at = _utc_now_naive()
            short_preview = notes["short"][:60].replace("\n", " ")
            print(
                f"  [apply] {ent.name!r:55s}  {short_preview!r}..."
            )
            applied += 1

        print(f"\n=== Summary ===\n  applied: {applied}\n  skipped: {skipped}")

        # Self-verify: count cat-10 entities with long-form crowd_notes.
        cat10 = session.scalars(
            select(Category).where(Category.slug == "lodging-vacation-rentals")
        ).one()
        all_cat10 = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                and_(
                    EntityCategory.category_id == cat10.id,
                    Entity.is_active == 1,
                )
            )
        ).all()
        with_long = sum(
            1
            for e in all_cat10
            if isinstance(e.crowd_notes, dict) and e.crowd_notes.get("long")
        )
        print(
            f"  cat-10 entities with long-form crowd_notes: "
            f"{with_long} (gate-4 target: >= 10)"
        )

        if args.dry_run:
            print("\n[dry-run] rolling back; no DB writes.")
            session.rollback()
        else:
            session.commit()
            print("\n[apply] committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
