"""Apply long-form crowd_notes to the top-10 shopping-essentials entities.

Closes Phase 5.6 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Drafts sourced from each entity's ``Provider.google_review_snippets``
(own column on Provider, NOT inside ``attributes`` — per the 5.4
close-out §4 source-path correction). Top-10 selected post-§2-flip-
extension (excludes the 2 medical_clinic eye-care providers — Lake
Havasu Family Eyecare + Barnet Dulaney Perkins — that flip out of
shopping-essentials via apply_phase5_6_shopping_audit.py).

Mirrors ``apply_phase5_5_auto_rv_fuel_crowd_notes.py`` shape exactly:
id-keyed dict, ``--dry-run`` first, idempotent (overwrites existing
crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized in 5.4 + 5.5):**
``Entity.crowd_notes`` is mapped as JSON; SQLAlchemy serializes dicts
on write. Pass the dict directly — do NOT ``json.dumps()`` first.

Usage:
    python outputs/apply_phase5_6_shopping_crowd_notes.py --dry-run
    python outputs/apply_phase5_6_shopping_crowd_notes.py
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
# Drafted from Provider.google_review_snippets per entity. Operator edits
# inline before live apply if any text needs adjustment.
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "ae4dbf09": {  # Hobby Lobby — 1,515 reviews, 4.6★
        "short": (
            "Wide craft and decor selection with consistently organized "
            "shelves; staff get repeat callouts for friendly help. One "
            "recurring caveat: 'sale' end-cap signage sometimes references "
            "the original ticket price, not a discount — read tags carefully."
        ),
        "long": (
            "1,515 reviews at 4.6★ on Kiowa Ave — Lake Havasu's most-"
            "reviewed crafting and home-decor retailer. Reviewers "
            "consistently praise store organization, ease of finding items, "
            "and staff friendliness ('always so welcoming,' 'goes above and "
            "beyond'). Mark Estep flags the affordable t-shirts and hoodies "
            "as a sleeper deal worth checking. One recurring 3-star "
            "complaint: '40% off' end-cap promotions sometimes reference "
            "the original ticket price (which is yellow), not a discount — "
            "read tags carefully. Politics-aware shoppers should know the "
            "chain's stances; some reviews surface this as a counter-point "
            "to product quality."
        ),
    },
    "fc4b3041": {  # Ross Dress for Less — 1,131 reviews, 4.3★
        "short": (
            "Discount apparel and home goods in a 'treasure hunt' format. "
            "Cleaner and better-stocked than most Ross locations per repeat "
            "reviewers — but dressing-room staff customer service is "
            "polarized, with a recurring 1-star pattern."
        ),
        "long": (
            "1,131 reviews at 4.3★ on McCulloch Blvd N. Reviewers describe "
            "Ross as a treasure-hunt format across apparel, accessories, "
            "and secondary-market home items at discounted prices. Strong "
            "praise on cleanliness and stocking — 'never seen a Ross so "
            "fully stocked, clean and organized.' The recurring negative "
            "pattern is dressing-room staff: multiple separate reviewers "
            "report rudeness specifically from the dressing-room team "
            "across different visits, not isolated to one shift. Items at "
            "this location skew toward standup mirrors, home decor, winter "
            "apparel, and one-off finds."
        ),
    },
    "33b4d5a3": {  # Big 5 Sporting Goods — 611 reviews, 4.3★
        "short": (
            "Sporting goods and outdoor gear with named staff who get "
            "repeat callouts for product expertise — Ryan on kayak "
            "purchases, BrianW on lake fishing. Convenient stop on the way "
            "to Lake Havasu State Park."
        ),
        "long": (
            "611 reviews at 4.3★ on Lake Havasu Ave. Strong reputation for "
            "staff product knowledge — Ryan is named multiple times for "
            "above-and-beyond service on kayak purchases (including a "
            "Christmas-Eve walk-in scramble), and BrianW gets cited as a "
            "lake-fishing expert who helps beginners get set up with basics "
            "and gear. Stock includes pickleball shoes, hiking shoes, "
            "athletic socks, kayaks, and fishing tackle. Specific-item "
            "stock-outs do happen. Reviewers regularly note the proximity "
            "to Lake Havasu State Park as a convenience factor for trip prep."
        ),
    },
    "daada0e7": {  # Michael Alan Furnishings — 611 reviews, 4.9★
        "short": (
            "Locally-owned furniture store with a 4.9★ rating across 611 "
            "reviews — design associate Shay Kay is the named-most-often "
            "figure for in-store help; the delivery team (Brandon, Nate, "
            "Mason, John, Tyler) gets warm callouts for careful install."
        ),
        "long": (
            "611 reviews at 4.9★ on W Acoma Blvd — the highest-rated entry "
            "by review-volume in shopping-essentials. Design associate "
            "Shaylina Kay (spelled Shaylina / Shalina / Shay Kay across "
            "reviews) is the standout — repeat customers describe her "
            "finding the right couch, custom upholstery, and coordinating "
            "pillows in a single visit. The delivery team also gets named "
            "callouts: Brandon, Nate, Mason, John, and Tyler are "
            "repeatedly cited as professional, careful with the home, and "
            "thorough on testing powered/recliner pieces post-install. "
            "Sectional and leather sofas are the most-mentioned product "
            "categories. Best fit for design-help shoppers who want "
            "hand-holding through upholstery + accessory coordination."
        ),
    },
    "789ee7eb": {  # ReConnected Phone & Device Repair — 601 reviews, 5.0★
        "short": (
            "Phone and device repair with a perfect 5.0★ at 601 reviews — "
            "Logan James gets named most often for same-day screen "
            "repairs (~1 hour turnaround). One outlier 1-star MacBook "
            "keyboard damage report."
        ),
        "long": (
            "601 reviews at 5.0★ on McCulloch Blvd N #19. Logan James is "
            "the named-most-often staff member — repeat reviewers describe "
            "him fixing screens, charging ports, and iPad/iPhone issues "
            "with ~1-hour same-day turnaround, including a Saturday-3:45pm "
            "walk-in. Zach also gets warm mentions for power-button "
            "diagnostics. Most common repair types in reviews: cracked "
            "screens, water-damage charging ports, dead batteries, "
            "button replacement. One recurring 1-star outlier: a 2024 "
            "MacBook Pro 16 charging-port repair that allegedly melted "
            "the keyboard from the warming pad — single-incident report, "
            "not a pattern. Screen protectors offered as add-on. The "
            "go-to LHC stop for same-day phone repair."
        ),
    },
    "5246b152": {  # Story Cannabis Dispensary Lake Havasu — 541 reviews, 4.7★
        "short": (
            "Lake Havasu's most-reviewed dispensary — budtenders Thomas, "
            "Kayla, Jess B., Trey, and Brenden get repeat callouts for "
            "strain knowledge and deal-stacking. First Friday events are "
            "a draw."
        ),
        "long": (
            "541 reviews at 4.7★ on London Bridge Rd. Named budtenders "
            "with repeat callouts: Thomas (wax + infused pre-rolls "
            "expert), Kayla, Jess B., Trey, and Brenden. First Friday "
            "events run engagement promos (Jeopardy-style trivia with "
            "bong giveaways). Reviewers consistently note customer-service "
            "polish ('attitude above and beyond'), strain-knowledge depth, "
            "and deal-stacking value across pre-rolls, flower, and "
            "concentrates. Out-of-town visitors caring for LHC parents "
            "cite it as a reliable medical-cannabis stop. Located near "
            "the London Bridge."
        ),
    },
    "453d34e0": {  # Dillard's — 527 reviews, 4.2★
        "short": (
            "Department store on AZ-95 with polarized counter-service "
            "reviews — Roy (watches), Alana (cologne), Angelina (perfume), "
            "and Roxy (makeup) get named-positive callouts; the "
            "perfume-counter is also the recurring 1-star sore point."
        ),
        "long": (
            "527 reviews at 4.2★ on AZ-95. The named positive callouts "
            "cluster around fragrance, watches, and makeup: Roy for "
            "watch-fitting (Citizen Eco-Drive sizing), Alana for cologne "
            "recommendations and time spent on fit, Angelina and Roxy "
            "('sparkling personalities') for perfume and makeup. "
            "Top-quality merchandise is the recurring 5-star praise "
            "theme. The recurring 1-star pattern is also the perfume "
            "counter — multiple separate reviewers describe being "
            "ignored or dismissed by Estée Lauder / fragrance-counter "
            "staff. Pattern is location-specific and consistent across "
            "several months of reviews. Clean store, organized layout, "
            "well-maintained restrooms."
        ),
    },
    "372e6348": {  # Crown Ace Hardware — 434 reviews, 4.4★
        "short": (
            "Independent hardware with a 'greeted at the door' service "
            "model; Ms Kim is the named Traeger-grill specialist. "
            "Selection praised; pricing flagged as higher than the "
            "warehouse-store alternatives."
        ),
        "long": (
            "434 reviews at 4.4★ on Sweetwater Ave. The consistent "
            "review theme is door-greeting service — 'what can I help "
            "you find?' within seconds of entry, a differentiator from "
            "big-box hardware. Ms Kim is the named Traeger Grill "
            "supplies expert, and Crown Ace reportedly carries the "
            "biggest Traeger accessory selection in town per repeat "
            "reviewers. A store cat is mentioned as a small detail. "
            "Recurring negative: pricing — 'customer service is "
            "excellent but prices are downright ridiculous.' Crown Ace "
            "runs higher than Home Depot / Lowe's, which reviewers note "
            "as the trade-off for the hands-on service model."
        ),
    },
    "71bb6f9a": {  # Dollar General (Jamaica Blvd) — 377 reviews, 4.0★
        "short": (
            "Discount staple on Jamaica Blvd with polarized staff reviews "
            "— Kevin Rodriguez and other team members praised; multiple "
            "separate 1-star reports cite manager rudeness and refusal to "
            "accept bills larger than $20."
        ),
        "long": (
            "377 reviews at 4.0★ on Jamaica Blvd N. Customer experience "
            "is polarized: positive 5-star reviews consistently praise "
            "specific staff (Kevin Rodriguez named) for being respectful, "
            "understanding, and helpful with restocking and item "
            "location. Negative reviews — a substantial recurring cluster "
            "— cite the manager hanging up on customers, refusing to "
            "assist, and being 'extremely rude'; multiple separate "
            "reviewers filed corporate complaints. The store refuses "
            "bills larger than $20. Two other Dollar Generals are within "
            "a 6-mile radius — competitor locations are mentioned in "
            "reviews as better-maintained alternatives if this one's "
            "service falls short."
        ),
    },
    "30bdd1e1": {  # Dollar General (Kiowa) — 349 reviews, 4.1★
        "short": (
            "Discount staple on Kiowa Blvd that's improved significantly "
            "per multi-year reviewers — assistant manager Jen named for "
            "the turnaround. Late-night (9pm) stocking holds up; small "
            "fee-/bill-restriction caveats apply."
        ),
        "long": (
            "349 reviews at 4.1★ on N Kiowa Blvd. Multi-year reviewers "
            "describe a significant operational improvement from earlier "
            "issues — assistant manager Jen is named for the turnaround "
            "in cleanliness, organization, and stocking levels. "
            "Reviewers note the store is well-stocked at 9pm, cashiers "
            "are helpful with inventory locations, and overall it's the "
            "'best Dollar General in the area' per local repeat "
            "customers. The recurring 1-star pattern involves a "
            "$5-holder fee, a $100-bill restriction, and one "
            "interpersonal complaint (single reviewer, not a pattern)."
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
            print(f"  {ent.name!r:55s}  applied (short={len(notes['short'])} chars, long={len(notes['long'])})")
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

        # Self-verify — count shopping-essentials entities with non-empty long
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
                WHERE c.slug = 'shopping-essentials'
                  AND e.is_active = 1
                  AND e.crowd_notes IS NOT NULL
                  AND json_extract(e.crowd_notes, '$.long') IS NOT NULL
                  AND length(json_extract(e.crowd_notes, '$.long')) > 200
                """
            )
        ).scalar()
        print(f"  shopping-essentials entities with long-form crowd_notes (>200 chars): {result}")
        if result >= 10:
            print(
                "Phase 5.6 acceptance gate item 4 (top-10 by reviews have "
                "long-form crowd_notes) CLEARED."
            )
        else:
            print(
                f"WARN: only {result} entries have long-form notes; expected ≥10"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
