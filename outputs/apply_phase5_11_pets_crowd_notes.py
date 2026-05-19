"""Apply long-form crowd_notes to the top-10 pets (cat-11) entities.

Closes Phase 5.11 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` -- Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Drafts sourced from each entity's ``Provider.google_review_snippets``
(own column on Provider, NOT inside ``attributes`` -- per the 5.4
close-out 4 source-path correction). Top-10 surfaced via
``outputs/phase5_11_top10_discovery.py`` against
``Provider.google_review_count`` desc, taken post-2-apply (so the
Slice E NEW creates are eligible -- 6 of the top-10 are Slice E
entries: Dorita's Place #2, Bow Wow's Pet Clips #6, Grooming By Jodi
#7, A Cut Above Grooming #8, Wizard of Pawz #9, Beautiful Beards Pet
Spaw #10).

Mirrors ``apply_phase5_10_lodging_crowd_notes.py`` shape exactly:
id-prefix-keyed dict, ``--dry-run`` first, idempotent (overwrites
existing crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized through
5.4/5.5/5.6/5.7/5.8/5.9/5.10):** ``Entity.crowd_notes`` is mapped as
JSON; SQLAlchemy serializes dicts on write. Pass the dict directly --
do NOT ``json.dumps()`` first.

Snippet coverage in the 5.11 top-10 was **100% (5 snippets each)** --
abundant signal for hand-curating. The notes focus on cat-11-specific
themes per kickoff 4 rubric: staff care for animals, cleanliness,
pricing transparency, scheduling availability, named staff callouts
(groomer-pup consistency is a major signal in LHC), kid- and
family-friendliness, training methodology, facility size/layout,
safety supervision. The top-10 is dominated by grooming venues (7 of
10) + 2 vets + 2 pet stores -- training/boarding venues didn't crack
the top-10 (highest non-baseline boarding/training entry was Picky
Mickie's Overnight Pet Sitting at 9r).

Three named-staff threads in the snippets worth surfacing in long-form
notes: Daniel (Paws and Claws front desk), Becky (Wizard of Pawz
owner-operator), Bethany/Tami/Laura/Nathaniel/Hope (Beautiful Beards
multi-groomer team). The 5.11 lane includes one franchise multi-
place_id observation (Beautiful Beards 3 listings -- north + south
locations + Boutique retail arm; only south-Spaw made the top-10).

Usage:
    python outputs/apply_phase5_11_pets_crowd_notes.py --dry-run
    python outputs/apply_phase5_11_pets_crowd_notes.py
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
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "71e0553d": {  # Paws and Claws Animal Care -- 361r, 4.7*, veterinary_care
        "short": (
            "Highly-rated LHC vet (361+ reviews, 4.7 stars) known for "
            "transparent estimates-before-work, educational explanations "
            "(Dr. Wendy reportedly pulls out veterinary textbooks to show "
            "owners what's happening), and exceptional reception care from "
            "Daniel during routine and end-of-life visits. Welcomes "
            "out-of-town visitors in emergencies. Treats pets 'like their "
            "own kids.'"
        ),
        "long": (
            "A consistently positive 361-review track record built around "
            "two named threads: Dr. Wendy's teaching approach (multiple "
            "reviewers describe her pulling out veterinary reference "
            "books mid-appointment to show owners the exact condition "
            "being treated) and Daniel at the front desk (repeatedly "
            "praised for warmth, smile, and compassionate hands-on "
            "support during euthanasia visits). The standard intake "
            "includes an itemized estimate with owner sign-off before any "
            "work proceeds -- a transparency thread visible across "
            "multiple reviews. Operationally inclusive: vacationers "
            "report being seen on short notice when their home vet "
            "wasn't available, and the clinic was specifically called "
            "out for welcoming non-locals during the regional vet "
            "shortage. The team handles routine care, dental surgeries, "
            "and end-of-life with the same patience. Best for owners "
            "wanting a vet who explains the why and gives them time to "
            "decide."
        ),
    },
    "a85376ad": {  # Dorita's Place -- 347r, 4.8*, pet_store (Slice E NEW)
        "short": (
            "Independent boutique pet shop on McCulloch Blvd N (347+ "
            "reviews, 4.8 stars). All-natural focus with minimal "
            "big-brand inventory; specializes in supplements for "
            "GI-sensitive dogs. Owner Dorita and staff are known for "
            "personal service, knowledgeable product advice, and "
            "ordering items not in stock. Treats for visiting dogs; "
            "easy-to-navigate layout."
        ),
        "long": (
            "An owner-operator pet shop where the curation, not the "
            "square footage, is the draw. Dorita stocks an all-natural-"
            "leaning inventory with named-brand callouts (Dr. Marty pet "
            "food, GI-supportive supplements) and reviewers consistently "
            "mention staff who know the products well and will offer to "
            "special-order items that aren't in stock. Service is "
            "personal: the owner is named in multiple reviews and "
            "described as going 'above and beyond' for repeat customers "
            "and emergencies. The layout is easy to navigate even on "
            "first visit; visiting dogs get a treat at the counter. Best "
            "for: owners frustrated by big-box pet-store sameness who "
            "want a knowledgeable conversation about their pet's diet, "
            "or who need a specialty product (raw, all-natural, "
            "GI-sensitive) the chains don't carry."
        ),
    },
    "bef22b83": {  # Animal Hospital of Havasu -- 228r, 4.4*, veterinary_care
        "short": (
            "Established LHC vet with long-standing client relationships "
            "(228+ reviews, 4.4 stars). Dr. Buckman cited by multiple "
            "long-term clients for attentive, kind care across "
            "puppy-through-senior life stages. **Important caveat per "
            "1-star reviews:** practice does NOT accept non-local "
            "emergencies even when checkbook is open -- vacationers "
            "should plan to use Paws and Claws (also LHC) or a Lake "
            "Havasu City emergency vet for travel-related urgencies."
        ),
        "long": (
            "The 4.4-star aggregate masks a sharp policy split. Local "
            "and long-term clients consistently rate this 5 stars -- "
            "praising Dr. Buckman's continuity of care from "
            "puppy through senior years, the staff's compassion during "
            "end-of-life visits, and the kind front-desk treatment. "
            "Long-term LHC residents call it 'the great Veterinary "
            "Hospital we were able to find when we first moved here.' "
            "But: 1-star reviews concentrate on a specific friction -- "
            "the practice declines emergency walk-ins from out-of-town "
            "visitors (one reviewer named the receptionist, Bradley, who "
            "delivered the policy), citing a local-clientele-only "
            "intake. The contrast with Paws and Claws (which welcomes "
            "vacation emergencies) is conspicuous in the review thread. "
            "Best for: LHC residents wanting a long-term primary-care "
            "vet relationship. NOT recommended for snowbirds or "
            "vacationers needing emergency care -- choose Paws and "
            "Claws or a 24-hour clinic instead."
        ),
    },
    "eb1b531c": {  # Exotic Pet Kingdom -- 144r, 4.4*, pet_store
        "short": (
            "Long-running LHC pet shop on Challenger Drive (144+ "
            "reviews, 4.4 stars). Historically the area's exotic-animal "
            "destination (reptiles, birds, tree frogs, chameleons); 2025 "
            "reviews report inventory has narrowed toward aquarium "
            "supplies and gaming retail with reduced live-animal "
            "selection. Healthy fish (guppies highlighted); some recent "
            "cleanliness/odor concerns flagged."
        ),
        "long": (
            "A store with a generation of LHC loyalty whose 2025 "
            "review trend marks an identity-in-transition. Long-time "
            "customers describe the historical Exotic Pet Kingdom: "
            "chameleons, tree frogs, geckos, birds, an in-house mascot "
            "or two ('Mo' is named affectionately), knowledgeable staff "
            "on reptile and bird care. Aquarium specialists report "
            "healthy fish to this day -- snowflake-veriegated guppies "
            "called out in late-2025 reviews settling well into home "
            "tanks. The recent friction in reviews: multiple 2025 "
            "1-and-2-star ratings note the live-exotic inventory has "
            "shrunk dramatically, the store is now mostly aquarium "
            "supplies and gaming retail, and at least one visitor "
            "reported a strong urine odor. Customer foot traffic is "
            "still steady. Best for: aquarium hobbyists looking for "
            "healthy stock and reasonable selection. Less reliable for "
            "the broader exotic-pet shopping the store was historically "
            "known for; call ahead before driving in for a specific "
            "reptile or bird."
        ),
    },
    "3c8bcf8f": {  # Bubbles N Bows Grooming Salon -- 109r, 4.7*, pet_care
        "short": (
            "Maricopa Ave grooming salon (109+ reviews, 4.7 stars). "
            "Bethany cited by multiple reviewers as the team lead. "
            "Notably willing to groom large dogs (70-lb Newfypoo "
            "highlighted -- many salons turn down dogs this size). "
            "Spotlessly clean shop, careful intake process where the "
            "team learns each new dog before starting. Treats and toys "
            "sold on-site. Cats welcome (lion cuts available)."
        ),
        "long": (
            "A salon that consistently passes the size-and-temperament "
            "test other groomers won't. Reviewers traveling for the "
            "winter season called Bubbles N Bows after being declined "
            "by multiple LHC competitors for their 70-pound Newfypoo "
            "and walked out with their dog 'looking better than ever.' "
            "Bethany is the named groomer in several reviews; the "
            "broader 'two young ladies' (Maltipoo regulars Ophie and "
            "Zoie callout) get repeated praise for being patient with "
            "anxious dogs and meticulous about avoiding nicks. The "
            "first-visit intake is its own selling point: reviewers "
            "describe the team explicitly learning the dog's "
            "temperament before the cut starts -- one new client called "
            "out their dog being 'not cryin or shaking' at pickup. The "
            "shop is repeatedly described as clean and well-stocked "
            "with treats and small toys. Cats accommodated for lion "
            "cuts. Best for: large-breed owners or anxious pets that "
            "other groomers have declined; first-timers wanting a "
            "careful intake."
        ),
    },
    "b2a757ca": {  # Bow Wow's Pet Clips -- 107r, 4.8*, pet_care (Slice E NEW)
        "short": (
            "McCulloch Blvd N grooming salon (107+ reviews, 4.8 stars). "
            "Consistent groomer-per-pup assignment is a recurring theme "
            "-- repeat clients describe getting the same person every "
            "visit, which their dogs visibly prefer. Full service: cuts, "
            "nails, glands, ears, lion cuts. Higher end on price ('pricy "
            "but worth it'); call ahead for immediate service."
        ),
        "long": (
            "A long-tenure McCulloch Blvd N salon whose review thread "
            "emphasizes consistency over price. Multi-year clients "
            "consistently rate this 5 stars on the strength of two "
            "operational choices: every dog gets the same groomer at "
            "every visit (one reviewer's dog 'loves him' specifically), "
            "and the price-for-prestige posture is open about "
            "itself ('pricy but well worth it' is a direct quote). The "
            "service breadth is full -- bath, cut, nails, ears, gland "
            "expression, themed cuts including lion -- and reviewers "
            "share before-and-after photos that show consistent "
            "execution. Booking is responsive: calling ahead reportedly "
            "secures immediate slots. The salon has been used by "
            "long-time clients since at least 2021. Best for: clients "
            "who value the dog-meets-groomer relationship over "
            "shopping on price, and who want full-service grooming "
            "rather than just a nail trim or bath."
        ),
    },
    "35e3bdaf": {  # Grooming By Jodi -- 96r, 4.9*, pet_care (Slice E NEW)
        "short": (
            "McCulloch Blvd N grooming salon (96+ reviews, 4.9 stars). "
            "Owner Jodi + groomer Marty cited by name. Known for fast "
            "appointment availability -- multiple vacation visitors got "
            "same-day or next-morning slots. Specialties include dog "
            "dye services, senior-dog care (Maltese specifically called "
            "out), and tear-stain treatment. Reasonably priced."
        ),
        "long": (
            "A salon whose 4.9-star aggregate is built on three "
            "operational strengths surfaced across the review thread. "
            "First: appointment availability is unusually fast for "
            "LHC -- multiple vacation and snowbird reviewers report "
            "calling and being seen within 24 hours, including for "
            "senior dogs needing special care. Second: the team handles "
            "specialty work most groomers don't -- dog dye services "
            "(one reviewer's senior Maltese came out 'looking like a "
            "new dog'), tear-stain treatment for white-faced breeds, "
            "and gentle handling for boisterous puppies. Third: named "
            "staff are part of the appeal -- Jodi (owner) and Marty are "
            "called out repeatedly, with multiple reviewers describing "
            "the team as 'paying special attention to each dog they "
            "care for.' Pricing is described as reasonable. Best for: "
            "owners with senior dogs, anxious dogs, or specialty needs "
            "(dye, tear stains) who want responsive scheduling and "
            "named-groomer continuity."
        ),
    },
    "bcb71716": {  # A Cut Above Grooming -- 93r, 4.6*, pet_care (Slice E NEW)
        "short": (
            "McCulloch Blvd N grooming salon (93+ reviews, 4.6 stars). "
            "Shandie and Dylan cited by name. Notably cheap nail trims "
            "at $10 each (vs $30 elsewhere). Long-time clientele -- "
            "Old English Sheepdog families particularly devoted. Mixed "
            "1-star signals around overbooking and a debit-card "
            "surcharge complaint; otherwise consistent quality at "
            "fair prices."
        ),
        "long": (
            "A long-tenure McCulloch Blvd N salon whose review profile "
            "is shaped by two threads. The positive thread (4-and-5 "
            "star, multi-year clientele): nail trims at $10 each "
            "(reviewers explicitly compare to $30 at Ann Arbor MI), "
            "reasonably-priced full grooming, named groomers Shandie "
            "and Dylan with consistent execution, and breed-specific "
            "experience cited (Old English Sheepdog regulars in "
            "particular). The friction thread (1-star, scattered): one "
            "reviewer reported being booked on a day with too many "
            "dogs, leaving their dog in a kennel for hours without "
            "fresh water and feeling rushed at pickup; a separate "
            "1-star complaint flagged a $2.28 debit-card surcharge that "
            "the customer believed violated federal rules. The negative "
            "signals are not concentrated -- the 4.6 average reflects "
            "an overall solid baseline with occasional volume-related "
            "service dips. Best for: budget-conscious owners wanting "
            "cheap nail trims or routine grooming, especially "
            "long-tenured breeds; book mid-week to avoid the "
            "overbooking risk."
        ),
    },
    "78545515": {  # Wizard of Pawz -- 73r, 4.9*, pet_care (Slice E NEW)
        "short": (
            "Acoma Blvd grooming salon (73+ reviews, 4.9 stars). "
            "Owner-operator Becky (often with her daughter assisting) "
            "praised by multiple reviewers as 'best groomer in 2.5 "
            "years of traveling.' Squeezes vacation customers in on "
            "short notice. Strong with non-shed breeds (Schnoodle, "
            "Schnauzer, Mini Labradoodle). Fast nail service: 3 dogs "
            "done in 10 minutes."
        ),
        "long": (
            "An Acoma Blvd salon that punches well above its 73-review "
            "weight on the strength of one named groomer. Becky is the "
            "owner and the primary groomer (often with her daughter "
            "helping), and reviewers across travel-heavy review years "
            "(2022 to 2026) consistently describe her as the best "
            "groomer they've found anywhere -- one snowbird couple in "
            "2.5 years of traveling with their mini labradoodle wrote "
            "they 'wish they could take her on their journey.' The "
            "operational draws are speed and breadth: a multi-dog "
            "household had three dogs' nails clipped in under ten "
            "minutes for the same price as one dog at the vet; Becky "
            "is praised for sharing dry-skin and at-home care advice "
            "during grooming. The salon's reach is regional: out-of-"
            "town visitors get short-notice slots. Best for: visitors "
            "needing a short-notice groom, owners with multiple dogs "
            "needing nails done, or non-shed-coat breeds where the "
            "groomer's eye for the breed matters."
        ),
    },
    "ba821a5b": {  # Beautiful Beards Pet Spaw -- 54r, 5.0*, pet_care (Slice E NEW)
        "short": (
            "Beautiful Beards south-side Spaw on Birch Square E (54+ "
            "reviews, perfect 5.0 stars). Multi-groomer team with "
            "Tami, Laura, Nathaniel, and Hope all named in recent "
            "reviews. Patient with anxious dogs (waits for them to "
            "settle before starting); photo updates sent to owners "
            "post-groom. Part of a 3-listing Beautiful Beards franchise "
            "(north + south locations + a Boutique retail arm)."
        ),
        "long": (
            "The south-side location of a 3-listing Beautiful Beards "
            "franchise that has earned a perfect 5.0 across 54+ "
            "reviews. The strength is depth of team: Tami, Laura, "
            "Nathaniel, and Hope are all named across different recent "
            "reviews, each with at least one repeat customer thread, "
            "suggesting the salon avoids the single-groomer-bottleneck "
            "problem that can constrain other LHC salons. Operational "
            "signals: groomers wait for stressed dogs to be ready to "
            "start (one 6-lb Maltipoo owner described being kept "
            "informed throughout); post-groom pictures sent to the "
            "owner are a recurring detail across multi-year clients. "
            "The 'Spaw' branding extends to the experience -- multiple "
            "reviewers describe their dogs as 'stoked' or 'pampered' "
            "after visits. The other two Beautiful Beards Google "
            "listings (a north-side Spaw and a separate Boutique retail "
            "arm) are V1.5 consolidation candidates. Best for: owners "
            "with anxious pets that need patient handling, "
            "small-breed pups, or anyone who wants photo confirmation "
            "of how a new grooming experience went."
        ),
    },
}


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_entity_by_prefix(session, prefix: str):
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

        # Self-verify: count cat-11 entities with long-form crowd_notes.
        cat11 = session.scalars(
            select(Category).where(Category.slug == "pets")
        ).one()
        all_cat11 = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                and_(
                    EntityCategory.category_id == cat11.id,
                    Entity.is_active == 1,
                )
            )
        ).all()
        with_long = sum(
            1
            for e in all_cat11
            if isinstance(e.crowd_notes, dict) and e.crowd_notes.get("long")
        )
        print(
            f"  cat-11 entities with long-form crowd_notes: "
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
