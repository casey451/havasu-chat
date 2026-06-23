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
    # Pickleball is checked BEFORE Aquatic fitness so a "Pickleball Round Robin -
    # Lake Havasu City Aquatic Center" (the pool's name is in the title) files
    # under Pickleball, not Aquatic — the activity word wins over a venue word.
    ("Pickleball", ("pickleball", "racquetball", "tennis clinic")),
    # Aquatic fitness — pool CLASSES (lap swim, water aerobics, aqua zumba). Open
    # Swim / Family Swim are drop-in rec and route to "Happening today" instead
    # (see app.home.event_buckets.is_dropin_rec). Checked before Strength so
    # "Aqua Zumba" lands here, not under Zumba.
    ("Aquatic fitness", (
        "lap swim", "water aerobics", "water fitness", "water exercise",
        "aqua", "aquacise", "aquatic", "water polo", "deep water",
        "swim lesson", "swim league", "water wellness", "swim team",
    )),
    ("Martial Arts", (
        "martial", "karate", "jiu jitsu", "jiu-jitsu", "bjj", "taekwondo",
        "judo", "mma", "kickbox", "muay thai", "no-gi", "no gi", "kali",
        "combat", "self defense", "self-defense", "boxing", "dojo",
        "open mat", "rolls", "rolling", "grappling", "sparring", "wrestling",
    )),
    ("Dance", (
        "dance", "dancing", "ballet", "tap", "jazz", "hip hop", "hip-hop",
        "ballroom", "salsa", "pointe",
    )),
    ("Gymnastics", ("gymnastics", "tumbling", "tumbler", "tumble", "cheer", "ninja", "trampoline")),
    ("Strength & Cardio", (
        "strength", "weight", "crossfit", "cross fit", "bootcamp", "boot camp",
        "hiit", "cardio", "spin", "cycling", "zumba", "aerobic", "conditioning",
        "sculpt", "circuit", "fit & flex", "fit and flex", "flex",
    )),
    # Gentle / senior-leaning movement classes (tai chi, qigong, low-impact,
    # arthritis, balance) — typed so they don't fall into the untyped residue.
    ("Mind & Body", (
        "tai chi", "qigong", "qi gong", "meditation", "mindfulness",
        "stretch", "mobility", "low impact", "low-impact", "arthritis", "balance",
    )),
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


# Directory-category / EntityCategory slug → class subgroup label. Lets a class
# whose TITLE carries no activity keyword ("Morning Flow", "Elementary B",
# "Boys Athletics") inherit its activity from the PROVIDER it's published under
# (a yoga studio's classes are Yoga, a dance studio's are Dance). Substring
# matched against the provider's category slugs, longest-first so "yoga-and-
# pilates" wins over a bare "pilates".
_PROVIDER_SLUG_TO_LABEL: tuple[tuple[str, str], ...] = (
    ("yoga-and-pilates", "Yoga"),
    ("dance-studios", "Dance"),
    ("martial-arts", "Martial Arts"),
    ("gymnastics", "Gymnastics"),
    ("pilates", "Pilates"),
    ("yoga", "Yoga"),
    ("dance", "Dance"),
)


def _title_subgroup(title: str) -> str | None:
    """The title-keyword subgroup, or None when nothing matches (no fallback)."""
    low = (title or "").lower()
    for label, hints in CLASS_SUBGROUPS:
        for h in hints:
            if re.search(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b", low):
                return label
    return None


def provider_activity_label(
    provider_name: str | None, category_slugs: list[str] | None = None
) -> str | None:
    """Derive a class subgroup label from the PROVIDER, or None.

    Two signals, in order: (1) the provider's NAME run through the same keyword
    classifier ("Ballet Havasu" → Dance, "...Gymnastics & All Star Cheer" →
    Gymnastics, "Amalaya Yoga" → Yoga); (2) its directory/EntityCategory slugs
    ("dance-studios" → Dance) for token-less names ("Arizona Coast Performing
    Arts"). Used as a fallback when the class title itself carries no activity
    keyword, so a yoga studio's generically-named classes leave "Other classes".
    """
    by_name = _title_subgroup(provider_name or "")
    if by_name is not None:
        return by_name
    for slug in category_slugs or []:
        s = (slug or "").lower()
        for needle, label in _PROVIDER_SLUG_TO_LABEL:
            if needle in s:
                return label
    return None


def classify_class_subgroup(
    title: str, venue: str | None = None, provider_activity: str | None = None
) -> str:
    """Map a fitness/class occurrence to a type subsection.

    Precedence: (1) martial-arts VENUE wins — any class at a dojo files under
    Martial Arts regardless of title (the catalog name detector
    :func:`app.categories.subcategories.is_martial_arts_name` + the token-less
    ``MARTIAL_ARTS_VENUES`` stragglers); (2) the class TITLE's own activity
    keyword (specificity — a Pilates class at a yoga studio is Pilates);
    (3) the PROVIDER's activity (``provider_activity``, derived via
    :func:`provider_activity_label`) so a generically-named class inherits its
    studio's discipline instead of falling to "Other classes"; (4) the honest
    "Other classes" residue.
    """
    vlow = (venue or "").lower()
    if is_martial_arts_name(venue) or any(v in vlow for v in MARTIAL_ARTS_VENUES):
        return "Martial Arts"
    by_title = _title_subgroup(title)
    if by_title is not None:
        return by_title
    if provider_activity:
        return provider_activity
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
        label = classify_class_subgroup(
            row.get("title") or "", row.get("venue"), row.get("activity")
        )
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


# ── Music & nightlife subsections (P2) ────────────────────────────────────────
# The "Music & nightlife" group splits into typed subsections the same way
# Fitness & classes does: Live Music (bands/concerts/acoustic), Comedy & Theater
# (stand-up/improv/plays), and an honest residual for everything else the bucket
# holds (DJ sets, karaoke, general nightlife). Driven by the shared event-type
# classifier so a bare band name still files under Live Music.
MUSIC_LIVE_LABEL = "Live Music"
MUSIC_COMEDY_LABEL = "Comedy & Theater"
MUSIC_FALLBACK_LABEL = "More music & nightlife"
MUSIC_SUBGROUP_ORDER: tuple[str, ...] = (
    MUSIC_LIVE_LABEL,
    MUSIC_COMEDY_LABEL,
    MUSIC_FALLBACK_LABEL,
)


def classify_music_subgroup(
    title: str, tags: list[str] | None = None, venue: str | None = None
) -> str:
    """Map a Music & nightlife row to its typed subsection. Comedy/theater wins
    over live music when both signal (a comedy night at a music venue is comedy);
    anything with no performance type (DJ/karaoke) lands in the honest residual."""
    from app.events.event_type_tags import (
        COMEDY,
        classify_event_type,
        is_strong_live_music,
    )

    types = classify_event_type(title=title, tags=tags, venue=venue)
    if COMEDY in types:
        return MUSIC_COMEDY_LABEL
    if is_strong_live_music(title, venue):
        return MUSIC_LIVE_LABEL
    return MUSIC_FALLBACK_LABEL


def split_music_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Music & nightlife rows into ordered subsections,
    omitting empty ones (honest-omission). Comedy & Theater simply doesn't render
    on a day with none — that is the "where volume warrants" behavior."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = classify_music_subgroup(
            row.get("title") or "", row.get("tags"), row.get("venue")
        )
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in MUSIC_SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out
