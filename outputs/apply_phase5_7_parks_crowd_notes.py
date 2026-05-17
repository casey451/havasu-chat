"""Apply long-form crowd_notes to the top-10 outdoors-parks-trails entities.

Closes Phase 5.7 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Drafts sourced from each entity's ``Provider.google_review_snippets``
(own column on Provider, NOT inside ``attributes`` — per the 5.4
close-out §4 source-path correction). Top-10 surfaced via
``outputs/phase5_7_top10_discovery.py`` against
``Provider.google_review_count`` desc, taken post-§2-flip (so the
3 FLIPped entities — Buses By The Bridge, Desert Storm HQ, Parks &
Recreation Department — are no longer in cat-7 and don't pollute the
top-10 surface).

Mirrors ``apply_phase5_6_shopping_crowd_notes.py`` shape exactly:
id-prefix-keyed dict, ``--dry-run`` first, idempotent (overwrites
existing crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized in 5.4 + 5.5
+ 5.6):** ``Entity.crowd_notes`` is mapped as JSON; SQLAlchemy
serializes dicts on write. Pass the dict directly — do NOT
``json.dumps()`` first.

Snippet coverage in the post-§2-flip top-10 was **100% (5 snippets
each)** — abundant raw signal for hand-curating. The notes focus on
park-specific themes (amenities, shade, water access, trail quality,
seasonal heat, named-feature callouts) per kickoff §4 rubric.

Usage:
    python outputs/apply_phase5_7_parks_crowd_notes.py --dry-run
    python outputs/apply_phase5_7_parks_crowd_notes.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity  # noqa: E402

# entity_id 8-char prefix -> {"short": str, "long": str}
# Drafted from Provider.google_review_snippets per entity. Operator
# edits inline before live apply if any text needs adjustment.
# Ordering matches the post-§2-flip top-10 by review_count desc.
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "c508dd52": {  # Lake Havasu State Park — 5046 reviews, 4.7★, state_park
        "short": (
            "Lake Havasu's flagship state park — lakefront campground "
            "with dry cabins, RV sites, multiple beach sections "
            "(including a dog beach), a 1.5-mile sunset trail, cactus "
            "garden, and on-site boat rentals. Walking distance to the "
            "London Bridge via the campground."
        ),
        "long": (
            "5,046 reviews at 4.7★ — Lake Havasu's most-reviewed park "
            "surface. The campground splits into a dry-cabin section "
            "(heat/AC, no water) and an RV section (most sites with "
            "great lake views); reviewers consistently praise staff for "
            "keeping the park clean. Beach access on the lakefront "
            "includes a dedicated dog beach. A 1.5-mile trail through "
            "cactus-garden territory leads to the sunset overlook — the "
            "most-recommended single feature. Boat rentals available "
            "within the park in 4-hour blocks. $50/night for water + "
            "electric + on-site dump. Walking distance to the London "
            "Bridge via the campground. Recurring 3-star complaint: "
            "shower facilities (push-button taps that only stay on "
            "briefly; \"warm not hot\" water). Some boat-traffic noise "
            "from the lake at peak season."
        ),
    },
    "dde56008": {  # Rotary Community Park & Playgrounds — 2564 reviews, 4.7★, park
        "short": (
            "Lake-front community park in the heart of LHC — beach "
            "access, multiple children's playgrounds, pavilions, "
            "replica lighthouses, and a wheelchair-friendly walking "
            "path that connects to the London Bridge. Pet-free + "
            "bike-free zones (clearly signed). Kayak launch off the "
            "sandy shore."
        ),
        "long": (
            "2,564 reviews at 4.7★ on the McCulloch Blvd lakefront. "
            "Standout features include the multiple children's "
            "playgrounds, the covered picnic-table pavilions "
            "overlooking the water, and the walking path that runs all "
            "the way to the London Bridge (wheelchair-accessible the "
            "full distance). The replica lighthouses scattered through "
            "the park get repeat callouts as a small-detail charm. "
            "**Pet-free beach** and **bike-free zone** — both clearly "
            "signed but enforcement is mostly trust-based; leashed dogs "
            "stay in the non-beach sections. Kayak launch off the sandy "
            "shore — the Lake Havasu Paddlers meet Monday / Wednesday / "
            "Friday at sunrise for the ~6-mile paddle around the "
            "island. Hot air balloon viewing during the festival is a "
            "seasonal draw. Free entry."
        ),
    },
    "7bb24a3a": {  # Cattail Cove State Park — 1121 reviews, 4.7★, state_park
        "short": (
            "South-of-Havasu state park with white-sand beach, separate "
            "dog beach, McKinny loop hiking, 30A/50A RV hookups, grills "
            "at each site, and a boat ramp. Cactus garden, "
            "amphitheater, horseshoes pit, and book/DVD/puzzle trade "
            "wall round out the chill campground vibe."
        ),
        "long": (
            "1,121 reviews at 4.7★ — south of LHC on the Bill Williams "
            "arm. The campground offers 30A sites + a handful of 50A "
            "spots, water and grills at each site, plus a dump station "
            "at exit. Two beach sections (human + dog) and the McKinny "
            "loop trail are the most-mentioned amenities, with the "
            "cactus garden, amphitheater, horseshoes pit, and "
            "book/DVD/puzzle trade wall noted as nice extras. Reviewers "
            "describe the rangers as friendly and the bathrooms as "
            "well-maintained. 14-day max stay. Dog-friendly throughout, "
            "with the dog beach + dog-walking levy + on-site pet "
            "stations getting specific callouts. Boat ramp with ample "
            "parking. Best fit for hikers and campers who want "
            "state-park-amenity polish without LHC-central crowding."
        ),
    },
    "1de53ec9": {  # Bill Williams River National Wildlife Refuge — 567 reviews, 4.7★, wildlife_refuge
        "short": (
            "Federal-land wildlife refuge south of LHC — peninsular "
            "trail (paved start, gravel back half), 3 wheelchair-"
            "accessible fishing docks, bird-watching, kayak/canoe "
            "launch into the marsh. Visitor center Mon–Fri only. The "
            "vault toilets get callouts as unusually clean."
        ),
        "long": (
            "567 reviews at 4.7★ — federal land managed by US Fish & "
            "Wildlife south of LHC. The Peninsular Trail starts paved "
            "(kid-friendly, sit-and-contemplate benches, photo "
            "opportunities) and transitions to gravel as you approach "
            "the delta peninsula tip. 3 fishing docks (all wheelchair-"
            "accessible) and 3 vault toilets (\"cleanest we have ever "
            "seen\" per a recurring callout) are the standout "
            "infrastructure. The visitor center is open Monday-Friday "
            "only (closed weekends due to staffing). Bird-watching for "
            "ducks, gulls, and marsh species is the most-cited primary "
            "activity. Kayak/canoe launch right at the marsh. Guided "
            "hikes and education classes on a published schedule. "
            "Reviewers describe the Bill Williams River Delta views as "
            "\"10 million dollar\" landscape — quieter and less-"
            "trafficked than the in-town parks."
        ),
    },
    "f881f795": {  # SARA Park — 469 reviews, 4.7★, park
        "short": (
            "LHC's largest multi-use outdoor complex — hiking trails "
            "(easy to 'The Crack' slot canyon with a 5-foot rope drop), "
            "disc golf, motocross + race-car track, RC airfield, "
            "shooting + archery ranges, mountain bike trails. Multiple "
            "parking lots; trails are well-signed but easy to get lost "
            "on — bring water."
        ),
        "long": (
            "469 reviews at 4.7★ — the city's largest multi-use outdoor "
            "complex, southwest of LHC proper. Multiple trail systems "
            "intersect (color-coded yellow / red / blue), ranging from "
            "easy walking to 'The Crack' (the yellow trail's slot-"
            "canyon section with narrow squeezes, a 5-foot rope drop, "
            "and boulder scrambles) which is the must-do feature for "
            "hikers comfortable with semi-tight spaces. Other on-"
            "property amenities: SARA Park Disc Golf Course (be aware "
            "of sharp rocks slicing softer plastic discs), the Lake "
            "Havasu Motocross Park, a remote control airfield, "
            "shooting + archery ranges, and mountain-bike trails. The "
            "main parking area has bathrooms + a covered bench/table; "
            "secondary lots are scattered for trail-specific access. "
            "Trails are well-marked but visitors regularly get lost — "
            "bring water and snap a phone photo of the trail map at "
            "the trailhead. Best fit for the active visitor with a "
            "full day to commit."
        ),
    },
    "7e07db65": {  # SARA Park Dog Park — 334 reviews, 4.6★, dog_park
        "short": (
            "Well-maintained dog park within the SARA Park complex — "
            "separate enclosed areas for large + small dogs, kiddie "
            "pools in the large-dog enclosure, fresh water bowls, big "
            "shade trees, and movable lawn chairs. Coyote sightings on "
            "the edge of town; supervise smaller dogs accordingly."
        ),
        "long": (
            "334 reviews at 4.6★ — a well-maintained dog park within "
            "the SARA Park complex on the west edge of LHC. Two "
            "enclosed areas split dogs by size (large vs small); both "
            "have shaded bench seating, movable lawn chairs, and "
            "kiddie pools in the large-dog enclosure. Plenty of fresh "
            "water bowls. Big shade trees throughout — multiple "
            "reviewers call out the shade as a Havasu-summer "
            "differentiator vs other parks. Ample parking including "
            "handicap spots; unisex bathroom out front. **Coyote "
            "sightings on the edge of town** is the recurring safety "
            "caveat — keep a watchful eye on smaller dogs. The most-"
            "cited negative is dog owners not picking up after their "
            "pets (a community-behavior issue, not a park-maintenance "
            "one). Friendly community of regulars; dogs reportedly "
            "well-behaved."
        ),
    },
    "62fb616c": {  # Avalon Park — 320 reviews, 4.4★, park
        "short": (
            "Compact local park with wide green spaces, walking paths, "
            "a playground, basketball court, dog-friendly area, and "
            "pavilions for picnics. Polarized reviews — \"great local "
            "park\" 5★s alongside recurring 1★ reports of aggressive "
            "off-leash dogs whose owners can't recall them."
        ),
        "long": (
            "320 reviews at 4.4★ on Avalon Ave — a compact local park "
            "aimed at residents rather than visitors. Wide green "
            "spaces + walking paths + a kids' playground + basketball "
            "court + dog-friendly areas + pavilions for picnics. "
            "Reviewers cite it as a \"birthday party spot\" with "
            "parking on multiple sides. **The recurring 1-star "
            "pattern is aggressive off-leash dogs:** multiple separate "
            "reviewers describe encounters with owners whose large "
            "breeds chase or threaten small dogs, with owners doubling "
            "down rather than recalling their pets. Pattern is "
            "consistent enough that small-dog owners may want to scout "
            "the off-leash area before entering or pick a different "
            "LHC park. Roma Mugar (one reviewer) explicitly compares "
            "it unfavorably to the SARA Park Dog Park's separated-by-"
            "size layout. Otherwise a pleasant neighborhood-park "
            "experience."
        ),
    },
    "d61b3513": {  # Jack Hardie Park — 271 reviews, 4.5★, park
        "short": (
            "Quiet shaded neighborhood park with beautiful old trees, "
            "4 swings (2 toddler + 2 older-kid), shaded picnic tables, "
            "pavilions, and green-grass running room. Direct park-"
            "front parking on two sides; \"peaceful\" is the recurring "
            "word in the reviews."
        ),
        "long": (
            "271 reviews at 4.5★ — a small, quiet neighborhood park "
            "honoring local figures. The standout feature in reviews "
            "is the mature shade trees — multiple reviewers note that "
            "the old trees absorb voice echo, making it unusually "
            "peaceful compared to other LHC parks. 4 swings (2 "
            "toddler swings + 2 standard) and a shaded playground; "
            "shaded picnic tables and pavilions are noted as ideal "
            "for family birthday parties. Open green space large "
            "enough for Frisbee or ball with leashed dogs. Direct "
            "park-front parking on two sides. Best fit for residents "
            "looking for a low-key spot to read, picnic, or let "
            "toddlers play — not a destination park, but consistently "
            "praised as one of LHC's most pleasant neighborhood "
            "surfaces."
        ),
    },
    "c95bb78e": {  # Bridgewater Links Golf Course — 245 reviews, 4.4★, golf_course
        "short": (
            "9-hole par-3/4 course connected to the London Bridge "
            "Resort — mountain scenery, manicured ponds, top-notch "
            "pro shop, very friendly staff. The short 9-hole format "
            "makes it playable in 110°F summer heat. Hosts community "
            "events including Relics & Rods Run To The Sun classic "
            "car shows."
        ),
        "long": (
            "245 reviews at 4.4★ — a 9-hole par-3/4 course attached "
            "to the London Bridge Resort. Reviewers consistently "
            "praise the mountain backdrop, the manicured greens with "
            "picturesque ponds, the pro shop quality, and the staff "
            "hospitality (\"super welcoming,\" \"very friendly and "
            "courteous\"). The 9-hole format is a key feature in the "
            "Havasu summer — \"who wants to play 18 in triple digits "
            "anyway?\" is the recurring summer-heat refrain — making "
            "the course viable in 110°F+ temps when full 18-hole "
            "courses are off the table. Hosts community events "
            "(Relics & Rods Run To The Sun classic car show is a "
            "recurring callout; veteran-fundraiser booths during car "
            "weekend). Despite being yards from the canal, the layout "
            "creates a secluded feel. Strong value reputation for the "
            "LHC golf surface."
        ),
    },
    "ce68ae90": {  # Sara Park Trail Head — 225 reviews, 4.8★, hiking_area
        "short": (
            "Trailhead access for SARA Park's slot-canyon / mountain "
            "hiking system — well-marked trails, big parking lot with "
            "bathroom, ~5-mile out-and-back to the lake via 'The "
            "Crack' (yellow trail) or with more elevation via the "
            "blue trail. Not recommended in Havasu summer heat."
        ),
        "long": (
            "225 reviews at 4.8★ — the highest-rated entry in the "
            "SARA Park complex (and the highest-rated outdoors-parks-"
            "trails entry by avg rating, slot-canyon hikes drive 5-"
            "star reviews). The main trailhead for the multi-trail "
            "system; most reviewers describe a ~5-mile out-and-back "
            "hike to the lake via the yellow trail (which includes "
            "'The Crack' slot-canyon section with narrow squeezes "
            "and a 5-foot rope drop) and back via the blue trail "
            "(more elevation, different scenery). Doable for families "
            "with reasonable hiking experience but **not recommended "
            "in Havasu summer heat** — November and spring are the "
            "recurring \"perfect\" months in reviews. Trails are "
            "well-marked but loose rocks and changing trail "
            "conditions require attention. Big parking lot with "
            "bathroom at the trailhead. The canyon scenery is the "
            "standout feature, with regular reviewer callouts that "
            "it's \"absolutely awesome\" and \"so rewarding.\""
        ),
    },
}


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    return session.scalars(
        select(Entity).where(Entity.id.like(f"{prefix}%"))
    ).first()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    now_naive = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as session:
        applied = 0
        missing = 0
        no_change = 0
        for prefix, notes in CROWD_NOTES_TOP10.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                missing += 1
                continue
            if ent.crowd_notes == notes:
                print(f"  {ent.name!r:55s}  no-change (already correct)")
                no_change += 1
                continue
            # Pass the dict directly — SQLAlchemy serializes on commit.
            # Do NOT json.dumps() first (5.3 f35d5e4 gotcha).
            ent.crowd_notes = notes
            ent.updated_at = now_naive
            print(
                f"  {ent.name!r:55s}  applied "
                f"(short={len(notes['short'])} chars, "
                f"long={len(notes['long'])})"
            )
            applied += 1

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  applied         : {applied}")
        print(f"  no-change       : {no_change}")
        print(f"  missing entity  : {missing}")
        print(f"  total in dict   : {len(CROWD_NOTES_TOP10)}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify — count outdoors-parks-trails entities with
        # non-empty long-form crowd_notes.
        print()
        print("=" * 70)
        print("Self-verify — long-form crowd_notes coverage")
        print("=" * 70)
        result = session.execute(
            text(
                """
                SELECT COUNT(*) FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                WHERE c.slug = 'outdoors-parks-trails'
                  AND e.is_active = 1
                  AND e.crowd_notes IS NOT NULL
                  AND json_extract(e.crowd_notes, '$.long') IS NOT NULL
                  AND length(json_extract(e.crowd_notes, '$.long')) > 200
                """
            )
        ).scalar()
        print(
            f"  outdoors-parks-trails entities with long-form crowd_notes "
            f"(>200 chars): {result}"
        )
        if result >= 10:
            print(
                "Phase 5.7 acceptance gate item 4 (top-10 by reviews have "
                "long-form crowd_notes) CLEARED."
            )
        else:
            print(
                f"WARN: only {result} entries have long-form notes; "
                f"expected >=10"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
