"""Apply long-form crowd_notes to the top-10 health-wellness-care entities.

Closes Phase 5.4 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks this
entry as a profile-page entry.

Source-of-truth for the drafts:
``outputs/phase5_4_health_wellness_crowd_notes_top10_staged.md``

Mirrors ``apply_phase5_3_home_property_crowd_notes.py`` shape exactly:
id-keyed dict, ``--dry-run`` first, idempotent (overwrites existing
crowd_notes), self-verifies via with-crowd_notes count.

**JSON-column gotcha (per 5.3 ``f35d5e4``):** ``Entity.crowd_notes`` is
mapped as JSON (app/db/models.py); SQLAlchemy serializes dicts on write
and deserializes on read. Pass the dict directly — do NOT
``json.dumps()`` first, which double-encodes and stores a quoted-and-
escaped string.

Usage:
    python outputs/apply_phase5_4_health_wellness_crowd_notes.py --dry-run
    python outputs/apply_phase5_4_health_wellness_crowd_notes.py
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
# Sourced from outputs/phase5_4_health_wellness_crowd_notes_top10_staged.md
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "7b3b9ad2": {
        "short": (
            "Havasu's most-reviewed dentist — Dr. Shamos delivers same-day "
            "emergency care; reviewers note variable assistant interactions."
        ),
        "long": (
            "1,610 reviews at 4.9★ make this Havasu's highest-volume dental "
            "practice. Reviewers consistently single out Dr. Ilan Shamos for "
            "same-day appointments on broken crowns and tooth emergencies, "
            "painless crown work, and long-tenured patient relationships "
            "(multi-year, multi-decade). Front-desk staff get strong praise; "
            "assistant-level interactions are more variable, with a few "
            "pointed reviews about specific exchanges. Located on Jamaica "
            "Blvd S."
        ),
    },
    "2fb8ba0c": {
        "short": (
            "Urgent care with same-day appointments — PA Joie Tedder and PA "
            "Michelle get repeat callouts for thorough, patient-first visits."
        ),
        "long": (
            "1,589 reviews at 4.6★. The repeated-name pattern: PA Joie Tedder "
            "and PA Michelle are both singled out by multiple reviewers for "
            "spending real time on diagnosis, explaining preventative care, "
            "and listening rather than rushing. Same-day appointments for "
            "respiratory and acute issues are the typical use case; "
            "travelers and out-of-network patients give it strong marks. "
            "Wait times for booked appointments occasionally run long when "
            "the clinic is busy. Located on Mesquite Ave."
        ),
    },
    "298b4e4f": {
        "short": (
            "Dermatology that runs on time — Cassandra and Persephonie "
            "Tweeten get repeat callouts for thorough, unrushed exams."
        ),
        "long": (
            "1,425 reviews at 4.9★. Two providers dominate the reviews: "
            "Cassandra and PA Persephonie Tweeten — both repeatedly named "
            "for thorough mole and skin checks, on-time scheduling, and "
            "unrushed appointments. Short-notice availability and timely "
            "follow-up calls and messages are repeated themes. Located on "
            "Mesquite Ave in the medical corridor."
        ),
    },
    "9901f739": {
        "short": (
            "Medical + cosmetic dermatology — PAs Alice D. and Nikki Guzzo "
            "take the time for complex cases."
        ),
        "long": (
            "1,306 reviews at 4.9★. Reviewers consistently name PAs Alice D. "
            "and Nikki Guzzo as the standout providers — Alice for complex "
            "long-term skin conditions where she lays out treatment options "
            "patiently, Nikki for thorough exams with strong patient "
            "education. MAs Mindy, Amy, and Taylor get repeat callouts for "
            "warm front-of-house. Both medical and cosmetic dermatology "
            "services. Located on Mesquite Ave."
        ),
    },
    "c0c70cf4": {
        "short": (
            "Family dentistry with a strong hygienist team — Jessica and "
            "Rachel get repeat callouts for thorough, anxiety-friendly "
            "cleanings."
        ),
        "long": (
            "1,098 reviews at 4.8★. Drs. Lynn and Osbon lead the practice; "
            "hygienists Jessica and Rachel are named most often in reviews, "
            "specifically for thorough cleanings and an upbeat, anxiety-"
            "friendly approach. A repeated reviewer pattern: California "
            "transplants finding a new dentist they trust after long-term "
            "out-of-state relationships. NPI-verified. Located on Lake "
            "Havasu Ave."
        ),
    },
    "0dc35bae": {
        "short": (
            "Dentistry with same-day emergency crown work — Dr. Kurtz and "
            "team get strong reviewer praise; front-office interactions "
            "occasionally noted as cooler."
        ),
        "long": (
            "1,071 reviews at 4.9★. Reviewers single out Dr. Kurtz and "
            "hygienist Liz for a warm, informative chair-side approach, plus "
            "same-day emergency work — a notable thread is travelers "
            "(boondockers, Quartzsite RVers) getting fit in for emergency "
            "crown replacements. Assistants Amber, Wendy, and Jade get "
            "repeated positive callouts. A small number of reviews flag "
            "front-office and finance interactions as less warm. "
            "NPI-verified. Located on McCulloch Blvd N."
        ),
    },
    "c76c490b": {
        "short": (
            "Modern urgent care with online appointments and a spotless "
            "facility — most visits are quick, with electronic results "
            "delivery."
        ),
        "long": (
            "903 reviews at 4.8★. Reviewers consistently call out the "
            "facility itself (spotless, modern) and the workflow (online "
            "appointments, fast electronic results) as differentiators vs. "
            "peer urgent-care clinics. Most visits described as quick "
            "start-to-finish; the negative outliers involve longer waits and "
            "front-desk friction on more complex visits. NPI-verified. "
            "Located on Mesquite Ave."
        ),
    },
    "b30ec634": {
        "short": (
            "Busy budget gym — Saylor and Tyler get repeat callouts for "
            "upbeat service and clean equipment; Black Card popular with "
            "RVers passing through."
        ),
        "long": (
            "768 reviews at 4.4★. Staff named in reviews — Saylor and Tyler "
            "for the floor, Raven for signups — consistently get warm praise "
            "for upbeat service and well-maintained equipment. Notable "
            "secondary use case: RV travelers and road-trippers using the "
            "Black Card for showers and hydromassage as they pass through "
            "Havasu. Peak hours run crowded; one full-time trainer covers a "
            "large member base. Located on McCulloch Blvd N."
        ),
    },
    "17d02400": {
        "short": (
            "Eye care with Dr. Senica strongly preferred — reviewers "
            "consistently flag overbooking on busy days."
        ),
        "long": (
            "761 reviews at 4.7★. Dr. Senica (sometimes spelled Seneca in "
            "reviews) is the standout — repeatedly named for unrushed exams "
            "and genuine patient relationships; Dr. Sipperly also gets "
            "positive mentions. Reviewers' repeated criticism is "
            "overbooking on peak days, with multi-hour waits noted; "
            "regulars suggest booking early-morning or late-afternoon "
            "slots. NPI-verified. Located on Capri Blvd."
        ),
    },
    "4f070a25": {
        "short": (
            "Multi-provider primary care — FNP April, Dr. Ashley Mulder, "
            "Cynthia Harper, and Christian Grandell each have their own "
            "named-by-name fan base."
        ),
        "long": (
            "619 reviews at 4.8★. The reviewer pattern: this is a multi-"
            "provider primary-care office where FNP April, Dr. Ashley Mulder, "
            "FNP Christian Grandell, Cynthia Harper, and Dr. Rozelle each "
            "have their own named-by-name following. A recent practice "
            "merger/buyout brought transfer patients in; reviewers note "
            "Megan at check-in for going out of her way on pricing and "
            "scheduling. Located on Mesquite Ave."
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

        # Self-verify — count health-wellness-care entities with crowd_notes
        # that include both "short" and "long" keys.
        print()
        print("=" * 70)
        print("Self-verify — health-wellness-care entities with long-form crowd_notes")
        print("=" * 70)
        n_with_long = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                WHERE c.slug = 'health-wellness-care'
                  AND e.is_active = 1
                  AND e.crowd_notes IS NOT NULL
                  AND e.crowd_notes LIKE '%"long"%'
                """
            )
        ).scalar()
        print(f"  entities with long-form crowd_notes: {n_with_long}")
        if n_with_long is not None and n_with_long >= 10:
            print(
                "Phase 5.4 acceptance gate item 4 (top-10 long-form "
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
