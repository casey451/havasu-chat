"""Apply long-form crowd_notes to the top-10 on-the-water entities.

Closes Phase 5.2 acceptance gate item 4 ("Top-10 marinas + ramps have
crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks this
entry as a profile-page entry.

Source-of-truth for the drafts:
``outputs/phase5_2_on_the_water_crowd_notes_top10_staged.md``

Pattern matches apply_crowd_notes_top17.py from Phase 5.1: id-keyed
dict, ``--dry-run`` first, idempotent (overwrites existing crowd_notes),
self-verifies via on-the-water-with-crowd_notes count.

Usage:
    python outputs/apply_on_the_water_crowd_notes_top10.py --dry-run
    python outputs/apply_on_the_water_crowd_notes_top10.py
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
from app.db.models import Category, Entity  # noqa: E402

# entity_id 8-char prefix -> {"short": str, "long": str}
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "99028be4": {
        "short": (
            "Top-rated rental fleet on the lake — pontoons, jet skis, "
            "Seadoos with knowledgeable staff."
        ),
        "long": (
            "Lake Havasu's highest-volume rental operation (540+ reviews, "
            "4.8★). Pontoons, jet skis, and Seadoos run clean and well-"
            "maintained. Crew (Nate, Nathan, Noah) get singled out repeatedly "
            "for patience with first-time renters. Dog-friendly. Located on "
            "McCulloch Blvd at the marina end."
        ),
    },
    "7b2cc749": {
        "short": (
            "Five-star boat and jet ski rentals — quick text-back booking, "
            "premium boats, easy pickup at the bridge."
        ),
        "long": (
            "464 reviews and still a perfect 5.0★ — rare on the lake. Quick "
            "text-back booking (often <5min), 'nicest boat we've ever rented' "
            "is a recurring line. Staff (James, Matt, Parker) make first-time "
            "renters comfortable; pickup at the end of the bridge. Pontoons, "
            "jet skis, tubes. Located on N Lake Havasu Ave."
        ),
    },
    "3eeb1137": {
        "short": (
            "The AZ↔CA ferry across to Havasu Landing — air-conditioned "
            "terminal, bring cash."
        ),
        "long": (
            "The only ferry service across Lake Havasu, running AZ↔CA to "
            "Havasu Landing Resort/Casino. Short clean ride, air-conditioned "
            "waiting area. Bring cash — the ticket machine has been flaky "
            "with cards. Copper Canyon boat tours depart from the same "
            "terminal and sell out fast on holiday weekends (Labor Day, July "
            "4th). Located on Shoreline Trail at the McCulloch Blvd end."
        ),
    },
    "9118ee9d": {
        "short": (
            "ATVs, Can-Ams, and boats — owner Chris delivers to your Airbnb "
            "and stages the trip."
        ),
        "long": (
            "Versatile rental fleet (ATVs, Can-Ams, boats) with hands-on "
            "owner Chris who'll deliver to your Airbnb and arrange staging. "
            "Guided ATV trips with Jason head out on trails with photo stops "
            "and local history along the way. Located on London Bridge Rd "
            "near the channel."
        ),
    },
    "8ce77957": {
        "short": (
            "Flagship marina — 6-lane ramp, slip rentals, fuel pumps. "
            "Reserve slips online for event weekends."
        ),
        "long": (
            "Lake Havasu's main public marina: 6-lane concrete ramp at a "
            "gentle slope, generous parking, slip rentals (bookable online), "
            "and fuel pumps. Day-use fee is $21 (card at the gatehouse). Long "
            "walk back from the parking area to the dock. For holiday/event "
            "weekends, book slips ahead and arrive early to beat the ramp "
            "lineup. Located at McCulloch Blvd N near London Bridge."
        ),
    },
    "1016c727": {
        "short": (
            "Pontoon rentals — friendly office staff (Cheryl, Mary, Toni) "
            "and easy ramp launches."
        ),
        "long": (
            "Family-friendly pontoon rental shop. Office on Industrial Blvd; "
            "Toni launches from the ramp so you don't deal with the trailer. "
            "Cheryl and Theresa handle bookings — patient with first-time "
            "renters. Get busy on Saturday mornings; book ahead. 4.2★ rating "
            "with consistent praise for staff communication."
        ),
    },
    "b5b50d10": {
        "short": (
            "Perfect 5-star jet ski rental — owner Rob calls personally to "
            "confirm weather and conditions."
        ),
        "long": (
            "247 reviews, all 5★ — owner Rob runs it personally and pre-calls "
            "every customer with weather/wind advisories ('today might be "
            "choppy, you may want to reschedule'). Tight safety briefings, "
            "takes photos/videos of riders as a bonus. Smaller operation than "
            "the big shops, but consistently the highest-rated jet ski rental "
            "in town. Located on Acoma Ln."
        ),
    },
    "308417e2": {
        "short": (
            "Jet skis and kayaks right on the beach — owner Frenchie is "
            "laid-back and accommodating."
        ),
        "long": (
            "Right on the beach off McCulloch Blvd — kayaks and jet skis "
            "without the trailer hassle. Owner Frenchie is consistently "
            "described as personable and flexible (waived late-return fees "
            "show up in multiple reviews). Off-season is the time for "
            "one-on-one attention."
        ),
    },
    "1f64b259": {
        "short": (
            "Tripletoons and UTVs — launch at Pirates Cove for the trip "
            "down through Topock Gorge."
        ),
        "long": (
            "Tripletoon pontoon rentals and 2/4-seat UTVs, with owners Blaine "
            "and Holly. Operating from an office on Kiowa Ave; launch "
            "typically happens at Pirates Cove (Park Moabi) or you trailer "
            "yourself. The Tripletoon Topock Gorge trip gets highlighted as "
            "memorable by reviewers. Owners spend time up front with tips "
            "about the lake before you head out."
        ),
    },
    "a63febcb": {
        "short": (
            "Newer northern marina — 6-lane ramp, fuel, slips, on-site store, "
            "well kept and uncrowded."
        ),
        "long": (
            "The newer marina at the north end (Havasu Riviera Pkwy, 86406). "
            "Six-lane concrete ramp, multiple gas pumps, well-laid-out slips, "
            "and an on-site store. Reviewers consistently note 'new and "
            "gorgeous' and the staff is responsive. Less of a holiday-weekend "
            "bottleneck than Lake Havasu Marina, but the trade-off is the "
            "longer drive from downtown."
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
        for prefix, notes in CROWD_NOTES_TOP10.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                missing += 1
                continue
            ent.crowd_notes = notes
            ent.updated_at = now_naive
            print(f"  {ent.name!r}  ->  short={notes['short'][:60]!r}...")
            applied += 1

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  applied: {applied}")
        print(f"  missing: {missing}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify
        print()
        print("=" * 70)
        print("Self-verify -- on-the-water entities with crowd_notes")
        print("=" * 70)
        otw_cat_id = session.scalar(
            select(Category.id).where(Category.slug == "on-the-water")
        )
        total = session.execute(
            text(
                """
                SELECT COUNT(*) FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                WHERE ec.category_id = :cid
                  AND e.is_active = 1
                  AND e.crowd_notes IS NOT NULL
                """
            ),
            {"cid": otw_cat_id},
        ).scalar_one()
        print(f"  on-the-water entities with crowd_notes: {total}")
        print()
        if total >= 10:
            print(
                "Phase 5.2 §6 acceptance gate item 4 (Top-10 marinas + ramps "
                "have crowd_notes) CLEARED."
            )
        else:
            print(
                f"WARN: only {total} on-the-water entities have crowd_notes; "
                f"need 10 for gate item 4."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
