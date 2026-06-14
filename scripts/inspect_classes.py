"""Read-only (Phase D §3.2): inspect the class/program data to propose a fitness
subcategory taxonomy. Tallies Program.activity_category, infers a fitness
subcategory from each title, and counts class-tagged Events. No writes."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event, Program  # noqa: E402

# Ordered: first match wins. Open Swim is intentionally routed to Kids & Family
# per the brief (handled in display, not here — here we just label the activity).
SUBCATS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Open Swim (-> Kids & Family)", ("open swim", "rec swim", "recreational swim", "family swim")),
    ("Aquatic - other", ("aqua", "water aerobic", "lap swim", "swim lesson", "swim team",
                          "splash", "water fitness", "hydro")),
    ("Yoga", ("yoga",)),
    ("Pilates", ("pilates", "barre")),
    ("Martial Arts", ("jiu", "jitsu", "bjj", "karate", "taekwon", "judo", "kung fu",
                      "martial", "self-defense", "self defense", "boxing", "kickbox", "mma")),
    ("Dance", ("dance", "zumba", "ballet", "ballroom", "hip hop", "hip-hop", "tap ",
               "jazzercise", "line dancing")),
    ("Cycling / Spin", ("spin", "cycle", "cycling", "ride ")),
    ("Strength / Conditioning", ("strength", "weight", "crossfit", "bootcamp", "boot camp",
                                 "hiit", "circuit", "conditioning", "kettlebell", "tabata")),
    ("Cardio / Aerobics", ("aerobic", "cardio", "step ", "zumba")),
    ("Pickleball / Tennis", ("pickleball", "tennis", "racquet")),
    ("Horseback / Equestrian", ("horse", "equestrian", "riding")),
    ("Gymnastics / Tumbling", ("gymnast", "tumbl", "cheer")),
    ("Kids / Youth", ("kid", "youth", "junior", "child", "tot ", "toddler", "preschool",
                      "teen", "story time", "storytime")),
    ("Senior / Gentle", ("senior", "silver", "gentle", "chair ", "55+")),
    ("Walking / Running / Hiking", ("walk", "run ", "running", "hike", "hiking", "5k")),
)


def subcat_for(title: str, activity: str) -> str:
    hay = f"{title} {activity}".lower()
    for label, toks in SUBCATS:
        if any(t in hay for t in toks):
            return label
    return "(unclassified)"


def main() -> int:
    db = SessionLocal()
    try:
        progs = list(db.scalars(select(Program).where(Program.is_active.is_(True))))
        print(f"=== Programs: {len(progs)} active ===\n")

        print("By activity_category:")
        for cat, n in Counter((p.activity_category or "(none)") for p in progs).most_common():
            print(f"  {cat:28} {n}")

        print("\nInferred fitness subcategory:")
        for label, n in Counter(subcat_for(p.title or "", p.activity_category or "")
                                for p in progs).most_common():
            print(f"  {label:32} {n}")

        print("\nSample (unclassified) titles:")
        unc = sorted({p.title for p in progs
                      if subcat_for(p.title or "", p.activity_category or "") == "(unclassified)"})
        for t in unc[:40]:
            print(f"  {t}")

        # Class-tagged events give a sense of the calendar 'wall'.
        evs = list(db.scalars(select(Event).where(Event.status == "live")))
        classy = [e for e in evs if any(
            t in {"class", "fitness", "aquatic"} for t in (e.tags or []))]
        print(f"\n=== Live events: {len(evs)} total, {len(classy)} class/fitness/aquatic-tagged ===")
        print("DONE_MARKER")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
