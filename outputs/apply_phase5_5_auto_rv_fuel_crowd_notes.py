"""Apply long-form crowd_notes to the top-10 auto-rv-fuel entities.

Closes Phase 5.5 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Source-of-truth for the drafts:
``outputs/phase5_5_auto_rv_fuel_crowd_notes_top10_staged.md``

Mirrors ``apply_phase5_4_health_wellness_crowd_notes.py`` shape
exactly: id-keyed dict, ``--dry-run`` first, idempotent (overwrites
existing crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized in 5.4):**
``Entity.crowd_notes`` is mapped as JSON (app/db/models.py); SQLAlchemy
serializes dicts on write and deserializes on read. Pass the dict
directly — do NOT ``json.dumps()`` first, which double-encodes and
stores a quoted-and-escaped string.

Usage:
    python outputs/apply_phase5_5_auto_rv_fuel_crowd_notes.py --dry-run
    python outputs/apply_phase5_5_auto_rv_fuel_crowd_notes.py
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
# Sourced from outputs/phase5_5_auto_rv_fuel_crowd_notes_top10_staged.md
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "d7dae97c": {
        "short": (
            "Havasu's most-reviewed auto business — service advisor Jen gets "
            "repeat callouts; sales team runs low-pressure, with remote "
            "fly-buy support across the tri-state area."
        ),
        "long": (
            "5,938 reviews at 4.8★ — the highest-volume auto business in the "
            "directory. Service advisor Jen is repeatedly singled out for "
            "tracking down nuisance issues (squeaks, recall items) without "
            "making service feel like a hassle. Sales staff named most often: "
            "Jericho, Keith, Brian, and Darrin for in-person deals; Christian "
            "for same-day truck deliveries on remote fly-buys (3.5-hour "
            "drives across state lines). Waiting room amenities (free snacks, "
            "coffee, comfortable seating) are a repeat theme. Tri-state "
            "reach: long-distance buyers from CA, NV, and TX cite remote "
            "deal closing as a differentiator. Located on Showplace Ave "
            "near the airport corridor."
        ),
    },
    "bb2aeca3": {
        "short": (
            "Service advisor Brent Johnson is the standout — repeat callouts "
            "for accommodating diesel and RV-towing customers stuck mid-trip."
        ),
        "long": (
            "3,457 reviews at 4.7★. Service advisor Brent Johnson is the "
            "named-most-often figure — multiple long-form reviews describe "
            "him sourcing parts, scheduling 5-recalls-while-you-wait, and "
            "tracking down specialty oil additives for transient diesel-truck "
            "customers. Service advisor Randy and sales rep Amanda also get "
            "warm mentions. Waiting room (clean, comfortable, complimentary "
            "refreshments) gets repeat positive callouts. One 1-star outlier "
            "is a recall-gone-wrong post that the same reviewer copy-pasted "
            "verbatim across all three Anderson rooflines — worth noting but "
            "not weighted as a pattern. Located on AZ-95."
        ),
    },
    "22480f81": {
        "short": (
            "Sales rep Brent Denning gets named most often — repeat customers "
            "cite no-pressure approach; service advisor Ed has long tenure."
        ),
        "long": (
            "2,576 reviews at 4.8★. Sales rep Brent Denning is the standout "
            "— named in multiple reviews for finding specific vehicles "
            "quickly (the 'right Mustang' example) without back-and-forth. "
            "Service advisor Ed has tenure measured in years and is the "
            "go-to for repeat customers (3rd-concurrent-Nissan reviewers "
            "mention him by name). Fly-buy support from Vegas via Elias "
            "gets positive callouts. The same recall copy-paste 1-star as "
            "the other Anderson rooflines appears here — same caveat. "
            "Located on AZ-95."
        ),
    },
    "890e5895": {
        "short": (
            "Chris, Madyson, and boat-trailer tire specialist Billy get "
            "repeat callouts — fast walk-in turnaround on stocked tires + "
            "competitive ordering for non-stock sizes."
        ),
        "long": (
            "2,559 reviews at 4.8★. Counter staff Chris, Madyson, and Billy "
            "(boat-trailer tire specialist) are the most-named figures. "
            "Walk-in turnaround on stocked tires is fast; non-stock sizes "
            "get competitive special-order pricing. A repeat reviewer "
            "pattern: free favors and good-faith gestures — tail-light "
            "replacements done in the parking lot at no charge, warranty "
            "work on batteries the shop wasn't required to honor. "
            "Trailer-tire expertise is a noted niche. Located on "
            "Countryshire Ave."
        ),
    },
    "cbe5f6e2": {
        "short": (
            "No-haggle sales — Casey, Eddie, Brad R., Enrique, and Arnold "
            "each get named-by-name; closer Alberto noted for no-pressure "
            "upsells."
        ),
        "long": (
            "1,086 reviews at 4.7★. The pattern: this is a multi-rep sales "
            "floor where Casey, Eddie, Brad R., Enrique, and Arnold each "
            "have their own named-by-name fan base — reviewers tend to "
            "attribute the deal experience to the specific rep they worked "
            "with. Closer Alberto gets warm callouts for no-pressure upsells "
            "at the finance step. Complete deals run 3-4 hours from greeting "
            "to delivery, with vehicles washed and gassed at handover. "
            "Located on N Lake Havasu Ave."
        ),
    },
    "b85deaa4": {
        "short": (
            "Family-owned local with NASCAR-pit-stop teamwork — out-of-state "
            "RVers and road-trippers get diesel/RV prep, fluid top-offs, "
            "and dog treats."
        ),
        "long": (
            "720 reviews at 4.9★. Family-owned local; reviewers describe the "
            "workflow as 'NASCAR pit maneuver' — under-10-minute oil changes "
            "with multi-staff teamwork. The repeat use case: out-of-state "
            "visitors (CA, NY, NE) prepping for long drives home "
            "(3,500-mile road trips mentioned). Service goes beyond the oil "
            "— fluid top-offs, wiper + filter changes, safety inspections, "
            "no-pressure recommendations. Dog treats for canine passengers "
            "are part of the visit. Located on McCulloch Blvd S."
        ),
    },
    "6d0f5116": {
        "short": (
            "Sales rep Ali leads the named-praise list — zero-game pricing "
            "with Manager Nathan; service runs on integrity (free "
            "fifth-wheel rattle diagnosis viral example)."
        ),
        "long": (
            "693 reviews at 4.3★. Sales rep Ali is the most-named figure — "
            "zero-game pricing in tandem with Manager Nathan. Eric, Nolan, "
            "Zach Tevin, and Frank all get named-by-name in individual "
            "transactions; finance manager Noah gets repeated low-pressure "
            "callouts; accessories specialist Dante named for small-package "
            "add-ons. Service department is integrity-rated — a viral "
            "reviewer example: a diesel F-250 RV-puller came in for a "
            "suspected serious fifth-wheel rattle; the service manager "
            "rode along to diagnose, found a loose RV pin-box bolt, "
            "tightened it, and waved off the charge. Sister business "
            "Riverview Auto Sales (Nick, Chelsea) is named in trade-in "
            "praise. Located on Industrial Blvd."
        ),
    },
    "9c787d9c": {
        "short": (
            "Self-serve car wash with touchless drive-thru + hand-wash bays; "
            "$12 wash includes vacuum token. Strong pressure; touchless can "
            "be aggressive on older vehicles."
        ),
        "long": (
            "491 reviews at 4.6★. Self-serve format with both touchless "
            "drive-thru and hand-wash bays; $12 wash includes a vacuum token "
            "with generous interior-cleaning time. Reviewer-noted strengths: "
            "hand-wash bay has strong water pressure, pre-scrub buckets for "
            "bug guts provided, accepts credit cards / quarters / $1 / $5 "
            "bills. Reviewer caveats: the touchless system is aggressive "
            "(a few reviews caution against using it on older or recently-"
            "purchased vehicles), peak hours get crowded, and occasional "
            "reports of music-blasting in adjacent bays. No change given "
            "for paper bills. Located on Maricopa Ave."
        ),
    },
    "f21dbf7c": {
        "short": (
            "Counter staff Austin and Tom get repeat named praise for "
            "battery replacement help; pricing ~$50 below the competing "
            "chain across town."
        ),
        "long": (
            "426 reviews at 4.4★. Counter staff Austin (named for tough "
            "battery installs — Jeep under-seat batteries, the "
            "difficult-access jobs) and Tom (named for battery education + "
            "warranty honoring) are the most-named figures. Multiple "
            "reviewers cite consistent pricing ~$50 below the competing "
            "chain across town as the differentiator. A "
            "warranty-replacement-not-strictly-required pattern repeats. "
            "One 1-star outlier flagged a single counter-staff member as "
            "dismissive on a specific hose-clamp request — worth noting "
            "alongside the bulk of warm reviews. Located on Lake Havasu Ave."
        ),
    },
    "cd3f4f51": {
        "short": (
            "Owner/manager Santone is the named figure — Friday-afternoon "
            "transmission rescues + turbocharger work; one thread flags "
            "differential treatment of women vs. men callers."
        ),
        "long": (
            "390 reviews at 4.9★. Owner/manager Santone (sometimes spelled "
            "'Santene' or 'Santon' in reviews) is the named figure across "
            "most positive reviews — Friday-afternoon transmission-line "
            "rescue for a boat-towing customer, turbocharger replacement "
            "on Lincolns with secondary-issue diagnostics done with "
            "integrity, and consistently cheaper repair quotes than the "
            "dealer alternative. A small but pointed thread of reviews "
            "flags differential treatment when a woman vs. her boyfriend "
            "asks for the same work — worth noting alongside the bulk of "
            "strong reviews. One additional 1-star outlier for walk-in "
            "rudeness from a staff member. Located on Commander Dr."
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
        already = 0
        for prefix, note in CROWD_NOTES_TOP10.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                missing += 1
                continue
            # Entity.crowd_notes is mapped as JSON (app/db/models.py);
            # SQLAlchemy serializes dicts on write + deserializes on read.
            # The 5.3 f35d5e4 bug was calling json.dumps(note) before
            # assignment, which double-encoded to a quoted string. Pass the
            # dict directly so the stored value is plain JSON.
            existing = ent.crowd_notes
            if existing == note:
                already += 1
                print(f"  {ent.name!r}  [already correct]")
                continue
            ent.crowd_notes = note
            ent.updated_at = now_naive
            applied += 1
            print(f"  {ent.name!r}  [applied]")

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  applied              : {applied}")
        print(f"  already correct      : {already}")
        print(f"  missing entity_id    : {missing}")
        print(f"  total in top-10 dict : {len(CROWD_NOTES_TOP10)}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify — count auto-rv-fuel entities with crowd_notes that
        # include both "short" and "long" keys.
        print()
        print("=" * 70)
        print("Self-verify — auto-rv-fuel entities with long-form crowd_notes")
        print("=" * 70)
        n_with_long = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                WHERE c.slug = 'auto-rv-fuel'
                  AND e.is_active = 1
                  AND e.crowd_notes IS NOT NULL
                  AND e.crowd_notes LIKE '%"long"%'
                """
            )
        ).scalar()
        print(f"  entities with long-form crowd_notes: {n_with_long}")
        if n_with_long is not None and n_with_long >= 10:
            print(
                "Phase 5.5 acceptance gate item 4 (top-10 long-form "
                "crowd_notes) CLEARED."
            )
        else:
            print(
                f"WARN: only {n_with_long} have long-form crowd_notes; "
                "gate item 4 needs ≥10."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
