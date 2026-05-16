"""Apply long-form crowd_notes to the top-10 home-property-services entities.

Closes Phase 5.3 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks this
entry as a profile-page entry.

Source-of-truth for the drafts:
``outputs/phase5_3_home_property_crowd_notes_top10_staged.md``

Pattern matches apply_on_the_water_crowd_notes_top10.py from Phase 5.2:
id-keyed dict, ``--dry-run`` first, idempotent (overwrites existing
crowd_notes), self-verifies via with-crowd_notes count.

Usage:
    python outputs/apply_phase5_3_home_property_crowd_notes.py --dry-run
    python outputs/apply_phase5_3_home_property_crowd_notes.py
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
# Sourced from outputs/phase5_3_home_property_crowd_notes_top10_staged.md
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "2faa5a8b": {
        "short": (
            "Havasu's most-reviewed contractor — HVAC, plumbing, and "
            "general home services with consistent 5-star feedback."
        ),
        "long": (
            "By far the most-reviewed home-services contractor in Lake "
            "Havasu (4,075 reviews, 5.0★). HVAC is the core trade but "
            "reviewers also book them for plumbing (sink installs, water-"
            "heater work) and general home services — a true multi-trade "
            "operation. Technicians named in reviews — Alex, Garrett — "
            "get singled out for thorough explanations and on-time "
            "arrivals. Same-day or next-day for routine calls. Located "
            "on N Kiowa Blvd."
        ),
    },
    "282a7c95": {
        "short": (
            "Reliable HVAC with same-day response — Chris S. is the go-to tech."
        ),
        "long": (
            "936 reviews at 4.9★. Reviewers single out Chris S. for "
            "clear communication (calls 10 min before arrival) and "
            "same-day response on broken units. Technician Eliel also "
            "gets repeat mentions for warranty and condo work. Located "
            "on N Lake Havasu Ave; primarily residential service area."
        ),
    },
    "a60dbf6d": {
        "short": (
            "Lake Havasu's high-volume plumber — Kris and Brian handle "
            "anything from water softeners to main-line repairs."
        ),
        "long": (
            "912 reviews holding steady at 5.0★ — rare for a plumber at "
            "this volume. Standout techs (Kris, Brian, Jeff) are named "
            "in reviews for water-softener installs, main-line repairs, "
            "and emergency same-day fixes. Dispatch (Lisa) gets praise "
            "for fast turnaround — often dispatching field techs within "
            "30 min of a call. Located on Sweetwater Ave."
        ),
    },
    "9e6330f7": {
        "short": (
            "Family-run plumbing with honest pricing — competitive vs. "
            "the larger franchises."
        ),
        "long": (
            "637 reviews at 4.8★. Notable reviewer pattern: people "
            "switching after getting a 'ridiculous' quote from a larger "
            "plumber. Justin and Riley get named for working with "
            "financing on bigger jobs. Punctual, written estimates, "
            "family-run feel. Located on Empire Dr."
        ),
    },
    "83b51e1c": {
        "short": (
            "HVAC with a strong on-time + responsive reputation — 5★ "
            "across 462 reviews."
        ),
        "long": (
            "Tina, Mike, and Matthew form the core team; Ryan and Ruben "
            "get tech callouts. Reviewers single them out for old-"
            "fashioned habits: returning phone calls promptly, showing "
            "up at the scheduled time, providing repair-vs-replace "
            "options without upsell pressure. Located on Rainbow Ave N."
        ),
    },
    "0f915f0d": {
        "short": (
            "Air duct + dryer vent cleaning with before/after photos and "
            "live video documentation."
        ),
        "long": (
            "Specialized air duct + dryer vent cleaning, 5.0★ across "
            "345 reviews. Techs Garrett Gustafson, Justin, and Greg Cox "
            "get specific callouts for showing live video of the work "
            "plus before/after photos. Pricing routinely undercuts the "
            "6+ quotes reviewers describe getting. Located on Saddleback Dr."
        ),
    },
    "f1c2b5ec": {
        "short": (
            "Pest and termite control — short-notice scheduling, "
            "attentive techs."
        ),
        "long": (
            "Truly Nolen's local franchise on W Acoma Blvd. Reviewers "
            "single out Mike, Jesse, and Michael Darling for thorough "
            "explanations and willingness to take same-day or next-day "
            "calls. Notable: techs sweep cobwebs (spiders, daddy long "
            "legs) without being asked. Termite + general pest with "
            "quarterly service plans."
        ),
    },
    "961564b4": {
        "short": (
            "Self-storage on Sweetwater — Suzette and Mona keep the "
            "property immaculate and onboarding fast."
        ),
        "long": (
            "259 reviews at 4.9★ for what's typically a low-touch "
            "business. The differentiator is the office team: Suzette "
            "and Mona get named in nearly every review. 'Property is "
            "immaculate' and 'sign-up was fast and easy' are repeated "
            "phrases. Long-tenured customers (multi-year units) mention "
            "them by name across the review history. Located on "
            "Sweetwater Ave."
        ),
    },
    "b1eb3396": {
        "short": (
            "Sears-branded appliance repair — typically dispatched "
            "through warranty companies; mixed tech quality."
        ),
        "long": (
            "Sears Home Services franchise on McCulloch Blvd. 244 "
            "reviews at 4.5★. Most calls come through home-warranty "
            "companies (FAHW, 2-10). Reviewer experience varies "
            "meaningfully by assigned technician — Jody and Steven get "
            "clear praise for diagnostic accuracy, while first-tech-"
            "misdiagnosis stories show up too. Best for in-warranty "
            "appliance fixes when other options aren't quick."
        ),
    },
    "8d46747f": {
        "short": (
            "Owner-operated plumbing — Craig and Jason on big and small "
            "jobs alike."
        ),
        "long": (
            "Owner-operated plumbing on Holly Ave. 243 reviews at 4.8★. "
            "Owner Craig and tech Jason both get named — reviewers "
            "describe them as knowledgeable, willing to explain the "
            "work (e.g. snake-line routing), and clean installers (Moen "
            "Flo valves + washing-machine shut-offs are called out "
            "specifically). Best for whole-house installs, water "
            "filtration, and shut-off-valve work."
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
            # Entity.crowd_notes is mapped as JSON (app/db/models.py:671);
            # SQLAlchemy serializes dicts on write + deserializes on read.
            # Earlier draft of this script called json.dumps(note) first,
            # which caused double-encoding (stored as '"{...escaped...}"').
            # Pass the dict directly so the stored value is plain JSON.
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

        # Self-verify — count home-property-services entities with
        # crowd_notes that include both "short" and "long" keys.
        print()
        print("=" * 70)
        print("Self-verify — home-property-services entities with long-form crowd_notes")
        print("=" * 70)
        n_with_long = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                WHERE c.slug = 'home-property-services'
                  AND e.is_active = 1
                  AND e.crowd_notes IS NOT NULL
                  AND e.crowd_notes LIKE '%"long"%'
                """
            )
        ).scalar()
        print(f"  entities with long-form crowd_notes: {n_with_long}")
        if n_with_long is not None and n_with_long >= 10:
            print(
                "Phase 5.3 §6 acceptance gate item 4 (top-10 long-form "
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
