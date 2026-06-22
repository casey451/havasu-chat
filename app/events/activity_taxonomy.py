"""Single source of truth for event/class *activity-type* classification.

P1 retires the render-time ``_CLASS_SUBGROUPS`` heuristic that used to live
inside :mod:`app.home.events_views`. The keyword taxonomy now lives here so it
can be consumed at the *routing/taxonomy* layer — both the events-page render
(typed Fitness & classes subsections) and ingest (stamping a stable
``activity:<slug>`` tag on a class occurrence) classify a class the same way.

A class resolves to one typed subgroup label (Yoga, Pilates, Martial Arts,
Aquatic fitness, Dance, Gymnastics, Strength & Cardio, Pickleball). Genuinely
unclassifiable rows fall into the honest "Other classes" residue (e.g. "Riding
Lessons") — a named, ordered subsection, never an untyped wall.
"""

from __future__ import annotations

import re
from typing import Any

from app.categories.subcategories import is_martial_arts_name

# Title-keyword classifier, word-boundary matched in specificity order.
CLASS_SUBGROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Yoga", ("yoga", "vinyasa")),
    ("Pilates", ("pilates", "reformer", "barre")),
    # Aquatic fitness — pool CLASSES (lap swim, water aerobics, aqua zumba). Open
    # Swim / Family Swim are drop-in rec and route to "Happening today" instead
    # (see app.home.event_buckets.is_dropin_rec). Checked before Strength so
    # "Aqua Zumba" lands here, not under Zumba.
    ("Aquatic fitness", (
        "lap swim", "water aerobics", "water fitness", "water exercise",
        "aqua", "aquacise", "aquatic", "water polo", "deep water",
    )),
    ("Martial Arts", (
        "martial", "karate", "jiu jitsu", "jiu-jitsu", "bjj", "taekwondo",
        "judo", "mma", "kickbox", "muay thai", "no-gi", "no gi", "kali",
        "combat", "self defense", "self-defense", "boxing", "dojo",
        "open mat", "rolls", "rolling", "grappling", "sparring", "wrestling",
    )),
    ("Dance", ("dance", "ballet", "tap", "jazz", "hip hop", "hip-hop", "ballroom")),
    ("Gymnastics", ("gymnastics", "tumbling", "tumbler", "tumble", "cheer", "ninja", "trampoline")),
    ("Strength & Cardio", (
        "strength", "weight", "crossfit", "cross fit", "bootcamp", "boot camp",
        "hiit", "cardio", "spin", "cycling", "zumba", "aerobic", "conditioning",
        "sculpt", "circuit",
    )),
    # Gentle / senior-leaning movement classes (tai chi, qigong, low-impact,
    # arthritis, balance) — typed so they don't fall into the untyped residue.
    ("Mind & Body", (
        "tai chi", "qigong", "qi gong", "meditation", "mindfulness",
        "stretch", "mobility", "low impact", "low-impact", "arthritis", "balance",
    )),
    # Scheduled racquet/court classes & clinics. All-day open play is drop-in rec
    # and routes to "Happening today", so it never reaches this subsection.
    ("Pickleball", ("pickleball", "racquetball", "tennis clinic")),
)
SUBGROUP_ORDER: tuple[str, ...] = (
    "Yoga", "Pilates", "Strength & Cardio", "Mind & Body", "Aquatic fitness",
    "Dance", "Gymnastics", "Martial Arts", "Pickleball", "Other classes",
)
FALLBACK_LABEL = "Other classes"

# Stable activity slugs (for ingest tags / data-driven routing). One per typed
# subgroup label; the residue maps to None (no activity tag).
SUBGROUP_SLUGS: dict[str, str] = {
    "Yoga": "yoga",
    "Pilates": "pilates",
    "Aquatic fitness": "aquatic",
    "Martial Arts": "martial-arts",
    "Dance": "dance",
    "Gymnastics": "gymnastics",
    "Strength & Cardio": "strength-cardio",
    "Mind & Body": "mind-body",
    "Pickleball": "pickleball",
}

# Explicit martial-arts venues whose NAME carries no discipline token, so the
# shared catalog name detector (is_martial_arts_name) can't catch them. Substring
# matched, lower-cased.
MARTIAL_ARTS_VENUES: tuple[str, ...] = (
    "bridge city",
    "arevalo",
)


def classify_class_subgroup(title: str, venue: str | None = None) -> str:
    """Map a fitness/class occurrence to a type subsection.

    Venue wins first: any class at a martial-arts studio files under Martial Arts
    regardless of title. The catalog's own name detector
    (:func:`app.categories.subcategories.is_martial_arts_name`) covers every dojo
    whose name carries a discipline token; ``MARTIAL_ARTS_VENUES`` catches
    token-less stragglers. Otherwise fall back to the title-keyword classifier.
    """
    vlow = (venue or "").lower()
    if is_martial_arts_name(venue) or any(v in vlow for v in MARTIAL_ARTS_VENUES):
        return "Martial Arts"
    low = title.lower()
    for label, hints in CLASS_SUBGROUPS:
        for h in hints:
            if re.search(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b", low):
                return label
    return FALLBACK_LABEL


def activity_slug(title: str, venue: str | None = None) -> str | None:
    """Stable activity slug for a class (e.g. "yoga", "martial-arts"), or None
    when it lands in the "Other classes" residue. Suitable for an ingest tag."""
    return SUBGROUP_SLUGS.get(classify_class_subgroup(title, venue))


def split_class_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Fitness & classes rows into ordered type
    subsections, omitting empty ones (honest-omission). Row order preserved."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = classify_class_subgroup(row.get("title") or "", row.get("venue"))
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out
