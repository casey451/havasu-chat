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
    # Golf (NEW 2026-06-25): course tee-times, Toptracer driving range, indoor
    # simulators, lessons, tournaments. Placed BEFORE Sports & Racing so a golf
    # title types here; "disc golf" is a FIELD sport (PDGA) — guarded in
    # :func:`classify_class_subgroup` so it routes to Sports & Racing, not Golf
    # (Lake Havasu Golf Club East is itself a disc-golf course: same venue, two
    # activities).
    ("Golf", (
        "golf", "toptracer", "top tracer", "golf simulator", "indoor golf",
        "driving range", "tee time",
    )),
    # Outdoor / field / court / racing sports (most of the calendar's "classes"
    # are really sports — Casey 2026-06-24). BMX racing and the team/court sports
    # type here instead of falling into the "Other classes" residue. Pickleball /
    # tennis keep their own subgroup above; aquatics/martial arts already typed.
    ("Sports & Racing", (
        "bmx", "motocross", "pump track", "pump-track", "balance bike", "strider",
        "basketball", "volleyball", "soccer", "baseball", "softball", "kickball",
        "flag football", "track and field", "disc golf", "skate", "skateboard",
    )),
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
    "Dance", "Gymnastics", "Golf", "Martial Arts", "Pickleball", "Sports & Racing",
    "Other classes",
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
    "Golf": "golf",
    "Strength & Cardio": "strength-cardio",
    "Mind & Body": "mind-body",
    "Pickleball": "pickleball",
    "Sports & Racing": "sports-racing",
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
    # "disc golf" matches the Golf keyword "golf" but is a FIELD sport (PDGA), not
    # ball golf — route it to Sports & Racing instead (the negative guard the
    # plan §5.3 calls for; same venue can host both, so this must be by title).
    if by_title == "Golf" and re.search(r"\bdisc\s+golf\b", (title or "").lower()):
        return "Sports & Racing"
    if by_title is not None:
        return by_title
    if provider_activity:
        return provider_activity
    return FALLBACK_LABEL


def activity_slug(title: str, venue: str | None = None) -> str | None:
    """Stable activity slug for a class (e.g. "yoga", "martial-arts"), or None
    when it lands in the "Other classes" residue. Suitable for an ingest tag."""
    return SUBGROUP_SLUGS.get(classify_class_subgroup(title, venue))


# ── Pickleball facet split (Phase 5, Casey 2026-06-25) ────────────────────────
# The flat "Pickleball" subgroup under Fitness & Sports splits into three facets
# the layout doc calls for, plus an honest base for the folded-in racquet/tennis
# and generic-lesson rows. Court hours are tag-driven: the pickleball loader
# stamps ``facet:open-play`` + ``indoor:true|false`` on its court-hours rows and
# ``facet:competition`` on round-robins/leagues/PickleFest, so the split reads
# tags rather than re-parsing titles. Tennis stays folded ("Pickleball &
# Racquet" base) per Casey — split tennis later only if its volume grows.
PB_OUTDOOR_LABEL = "Pickleball — Court Hours (Outdoor)"
PB_INDOOR_LABEL = "Pickleball — Court Hours (Indoor)"
PB_COMPETITION_LABEL = "Pickleball — Leagues & Competitions"
PB_BASE_LABEL = "Pickleball & Racquet"
PICKLEBALL_FACET_ORDER: tuple[str, ...] = (
    PB_OUTDOOR_LABEL, PB_INDOOR_LABEL, PB_COMPETITION_LABEL, PB_BASE_LABEL,
)


def classify_pickleball_facet(tags: list[str] | None) -> str:
    """Map a Pickleball/Racquet row to its facet from the stamped tags.

    Precedence: a competition tag (round-robin / league / PickleFest) wins; then
    court-hours rows (``facet:open-play`` or ``facet:hours``) split Indoor vs
    Outdoor by the ``indoor:true`` flag; everything else (lessons, clinics,
    tennis, generically-named pickleball classes) is the honest base."""
    tagset = {str(t).strip().lower() for t in (tags or [])}
    if "facet:competition" in tagset:
        return PB_COMPETITION_LABEL
    if tagset & {"facet:open-play", "facet:hours"}:
        return PB_INDOOR_LABEL if "indoor:true" in tagset else PB_OUTDOOR_LABEL
    return PB_BASE_LABEL


def split_pickleball_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition the Pickleball subgroup's rows into its ordered facets, omitting
    empty ones (honest-omission). Row order preserved within each facet."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(classify_pickleball_facet(row.get("tags")), []).append(row)
    out: list[dict[str, Any]] = []
    for label in PICKLEBALL_FACET_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


# Reverse of SUBGROUP_SLUGS, so a row's explicit ``activity:<slug>`` tag picks its
# Fitness subsection label tag-first (the Phase-2 canonical read) — e.g. a
# "PickleFest" row carries ``activity:pickleball`` but no "pickleball" in its
# title, so the title classifier alone would mis-file it under "Other classes".
_SLUG_TO_SUBGROUP: dict[str, str] = {slug: label for label, slug in SUBGROUP_SLUGS.items()}


def _row_class_label(row: dict[str, Any]) -> str:
    """The Fitness subsection label for a row: an explicit ``activity:<slug>`` tag
    wins (tag-first), else the title/venue/provider classifier."""
    for t in row.get("tags") or []:
        s = str(t)
        if s.startswith("activity:"):
            label = _SLUG_TO_SUBGROUP.get(s.split(":", 1)[1] or "")
            if label:
                return label
    return classify_class_subgroup(
        row.get("title") or "", row.get("venue"), row.get("activity")
    )


def split_class_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Fitness & classes rows into ordered type
    subsections, omitting empty ones (honest-omission). Row order preserved.

    The Pickleball subgroup is further split into its Court Hours (Indoor/Outdoor)
    and Leagues & Competitions facets (Phase 5) — those facet subgroups take its
    slot in the ordered output."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(_row_class_label(row), []).append(row)
    out: list[dict[str, Any]] = []
    for label in SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if not sub_rows:
            continue
        if label == "Pickleball":
            out.extend(split_pickleball_facets(sub_rows))
        else:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


# ── Unified activity classifier (calendar reorg, Casey 2026-06-25) ────────────
# Phase 1 promotes this module to THE single classifier for *every* calendar
# activity — not just the Fitness & Sports subgroups. The new non-fitness
# activities route to OTHER top-level buckets:
#   • arts / cooking / maker / learning → "learn"   (Classes & Workshops)
#   • theater                            → "music"   (Theater & Performing Arts)
#   • games / bowling / billiards /      → "events"  (Things to Do — the
#     trampoline / family-fun                          Games & Social and the
#                                                       Bowling/Billiards/Family
#                                                       Fun sections)
# These are stamped ONCE, at ingest, as a single ``activity:<slug>`` tag (plus
# facet/audience tags) so every surface is a pure read (the render side is wired
# in Phase 2). The slugs are namespaced (``activity:games``) so they are inert to
# the bare-word tier classifier in :mod:`app.home.sandstone` until Phase 2 reads
# them explicitly — which is why this phase changes no surface.

# Specific non-fitness activity keywords, in specificity order. Checked BEFORE the
# fitness classifier so an unambiguous craft/game/venue word wins over a fitness
# keyword ("Paint & Sip" is arts, never a workout; "Mexican Train Dominoes" is a
# game). Generic learning words ("workshop", "seminar") are deliberately NOT here
# — they are too broad to outrank fitness ("Yoga Workshop" must stay yoga), so
# they are a fallback below (:data:`_LEARNING_GENERIC`).
NONFITNESS_SUBGROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("theater", (
        "theater", "theatre", "musical", "performing arts", "improv",
        "playhouse", "matinee", "drama club",
    )),
    ("games", (
        "party bridge", "duplicate bridge", "bridge club", "pinochle",
        "mexican train", "dominoes", "domino", "hand & foot", "hand and foot",
        "bingo", "ping pong", "table tennis", "canasta", "mahjong", "mah jongg",
        "euchre", "cribbage", "bunco", "board game", "card game",
    )),
    ("cooking", (
        "cooking class", "cooking", "culinary", "baking class", "cake decorating",
    )),
    ("arts", (
        "paint & sip", "paint and sip", "sip & paint", "sip and paint",
        "stained glass", "polymer clay", "terrarium", "pottery", "ceramics",
        "art class", "art walk", "arts & crafts", "arts and crafts", "open art",
        "windchime", "wind chime", "jewelry making", "watercolor", "mosaic",
        "quilting", "sewing class", "knitting", "crochet", "scrapbook",
    )),
    ("maker", ("maker", "cake pop", "slime", "robotics", "stem workshop", "3d print")),
    ("bowling", (
        "bowling", "cosmic bowl", "glow bowl", "rock & bowl", "rock and bowl", "keglers",
    )),
    ("billiards", (
        "billiards", "pool hall", "pool league", "8-ball", "9-ball",
        "8 ball", "9 ball", "snooker", "dart league",
    )),
    ("trampoline", ("trampoline", "jump time", "glow in the park")),
    ("family-fun", ("arcade", "laser tag", "mini golf", "go kart", "go-kart", "bounce house")),
)
# Generic instruction words → "learning" (Classes & Workshops). Fallback ONLY,
# after the fitness classifier, so a "Yoga Workshop" stays yoga and only a
# genuinely non-fitness workshop/seminar lands in learning.
_LEARNING_GENERIC: tuple[str, ...] = (
    "seminar", "lecture", "workshop", "lifelong learning", "genealogy",
    "computer class", "book club", "language class", "financial literacy",
)

# Every activity slug → its top-level calendar bucket key. The fitness slugs (the
# values of :data:`SUBGROUP_SLUGS`) all map to "classes"; the new non-fitness
# slugs map to "learn" / "events" / "music". (Golf is added in Phase 3 → classes.)
ACTIVITY_BUCKET: dict[str, str] = {
    **{slug: "classes" for slug in SUBGROUP_SLUGS.values()},
    "arts": "learn",
    "cooking": "learn",
    "maker": "learn",
    "learning": "learn",
    "theater": "music",
    "games": "events",
    "bowling": "events",
    "billiards": "events",
    "trampoline": "events",
    "family-fun": "events",
}

# Themed recurring sessions that are destination events in their own right
# (Cosmic Bowling, Glow in the Park) → facet:special, so they render as distinct
# dated events rather than collapsing into a venue's hours line (plan §4.6).
_SPECIAL_RE = re.compile(
    r"\b(cosmic|glow(?:\s+in\s+the\s+park)?|neon|blacklight|black light|"
    r"dive[- ]in|after dark|rock\s*[&n]?\s*bowl)\b",
    re.IGNORECASE,
)
# Leagues / tournaments / round-robins → facet:competition (golf leagues,
# pickleball round-robins/PickleFest, pool/dart leagues are all this shape).
_COMPETITION_RE = re.compile(
    r"\b(tournament|league|round[- ]?robin|picklefest|championship|playoff)s?\b",
    re.IGNORECASE,
)
# Audience facets (drive the Kids & Family / Seniors overlays in Phase 2).
_AUDIENCE_YOUTH_RE = re.compile(
    r"\b(kid|kids|youth|children|child|toddler|junior|teen|tween|family|families|"
    r"mommy|story\s*time|tiny\s*tot)\b",
    re.IGNORECASE,
)


def _phrase_hit(low: str, hints: tuple[str, ...]) -> bool:
    """Word-boundary match of any hint in already-lowercased text (mirrors the
    fitness :func:`_title_subgroup` matcher, phrases + a plural/gerund tail)."""
    for h in hints:
        if re.search(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b", low):
            return True
    return False


def classify_activity(
    title: str,
    venue: str | None = None,
    tags: list[str] | None = None,
    provider_activity: str | None = None,
) -> str | None:
    """The single canonical activity slug for any calendar row, or ``None``.

    Precedence: (1) a specific non-fitness activity keyword (arts/cooking/maker/
    games/theater/bowling/billiards/trampoline/family-fun) wins over fitness, so
    a craft or social-game title is never mistaken for a workout; (2) the fitness
    classifier (:func:`classify_class_subgroup` → its slug); (3) a generic
    learning word ("workshop"/"seminar") as a fallback → ``learning``. Returns
    ``None`` for non-activity rows (markets, festivals, civic) — they carry no
    ``activity:*`` tag and route by the existing tier logic.
    """
    low = (title or "").lower()
    for slug, hints in NONFITNESS_SUBGROUPS:
        if _phrase_hit(low, hints):
            return slug
    fitness = SUBGROUP_SLUGS.get(classify_class_subgroup(title, venue, provider_activity))
    if fitness:
        return fitness
    if _phrase_hit(low, _LEARNING_GENERIC):
        return "learning"
    return None


def activity_bucket(slug: str | None) -> str | None:
    """Top-level calendar bucket key for an activity slug, or ``None``."""
    return ACTIVITY_BUCKET.get(slug) if slug else None


def event_activity_tags(
    title: str,
    venue: str | None = None,
    tags: list[str] | None = None,
    provider_activity: str | None = None,
) -> list[str]:
    """Canonical namespaced tags to stamp on a row at ingest: one
    ``activity:<slug>`` (when classifiable) plus ``facet:special`` /
    ``facet:competition`` / ``audience:youth`` / ``audience:senior`` where
    derivable. Namespaced so they are inert to the bare-word tier classifier
    until the surfaces read them (Phase 2). Order-stable, no duplicates."""
    out: list[str] = []
    slug = classify_activity(title, venue, tags, provider_activity)
    if slug:
        out.append(f"activity:{slug}")
    low = (title or "").lower()
    if _SPECIAL_RE.search(low):
        out.append("facet:special")
    if _COMPETITION_RE.search(low):
        out.append("facet:competition")
    tagset = {str(t).strip().lower() for t in (tags or [])}
    if "senior" in tagset or "seniors" in tagset:
        out.append("audience:senior")
    if _AUDIENCE_YOUTH_RE.search(low) or tagset & {"family", "youth", "kids"}:
        out.append("audience:youth")
    # De-dup while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


# ── Phase 2 render: surfaces read the activity tag (tag-first, classify back) ──
def resolve_activity(
    title: str,
    venue: str | None = None,
    tags: list[str] | None = None,
    provider_activity: str | None = None,
) -> str | None:
    """The activity slug for a *rendered* row: read the canonical
    ``activity:<slug>`` tag stamped at ingest (Phase 1) when present, else fall
    back to the SAME classifier (:func:`classify_activity`). Tag-first means a
    backfilled row is a pure read; the fallback keeps pre-backfill rows and
    render-time Schedule occurrences (which carry no tag, only a provider
    activity label) correct — one classifier, no divergent re-parsing."""
    for t in tags or []:
        s = str(t)
        if s.startswith("activity:"):
            return s.split(":", 1)[1] or None
    return classify_activity(title, venue, tags, provider_activity)


# ── Classes & Workshops (learn) subsections ───────────────────────────────────
LEARN_ARTS_LABEL = "Arts & Crafts"
LEARN_PAINT_LABEL = "Paint & Sip"
LEARN_COOKING_LABEL = "Cooking"
LEARN_MAKER_LABEL = "Maker"
LEARN_LEARNING_LABEL = "Lifelong Learning"
LEARN_SUBGROUP_ORDER: tuple[str, ...] = (
    LEARN_ARTS_LABEL, LEARN_PAINT_LABEL, LEARN_COOKING_LABEL,
    LEARN_MAKER_LABEL, LEARN_LEARNING_LABEL,
)
_PAINT_SIP_RE = re.compile(r"\b(paint\s*[&n]?\s*sip|sip\s*[&n]?\s*paint)\b", re.IGNORECASE)


def classify_learn_subgroup(
    title: str, tags: list[str] | None = None, activity: str | None = None
) -> str:
    """Map a Classes & Workshops row to its subsection. Paint & Sip splits out of
    Arts & Crafts by title (it is the social-craft variant); otherwise the
    activity slug picks the section, with arts as the honest default."""
    if _PAINT_SIP_RE.search(title or ""):
        return LEARN_PAINT_LABEL
    slug = resolve_activity(title, None, tags, activity)
    if slug == "cooking":
        return LEARN_COOKING_LABEL
    if slug == "maker":
        return LEARN_MAKER_LABEL
    if slug == "learning":
        return LEARN_LEARNING_LABEL
    return LEARN_ARTS_LABEL


def split_learn_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Classes & Workshops rows into ordered
    subsections, omitting empty ones (honest-omission). Row order preserved."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = classify_learn_subgroup(
            row.get("title") or "", row.get("tags"), row.get("activity")
        )
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in LEARN_SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


# ── Things to Do (events) subsections — Phase 5 cluster + games + specials ─────
# "Things to Do" used to render flat. Phase 5 splits it WHEN there is themed
# content to separate (Casey 2026-06-25): the Bowling/Billiards/Family-Fun venue
# cluster (their hours), an all-ages Games & Social section (public bingo/cards
# that aren't senior-gated — senior games live under Seniors), and Special
# Sessions (Cosmic Bowling, Glow in the Park — destination events that must read
# as dated happenings, NOT fold into a venue's hours line). Everything else stays
# in the residual "Around Town". The split is applied only when a specialised
# subsection is present, so a plain market/festival day is unchanged (events_views).
EVENTS_AROUND_LABEL = "Around Town"
EVENTS_SPECIAL_LABEL = "Special Sessions"
EVENTS_GAMES_LABEL = "Games & Social"
EVENTS_FUNZONE_LABEL = "Bowling, Billiards & Family Fun"
EVENTS_SUBGROUP_ORDER: tuple[str, ...] = (
    EVENTS_AROUND_LABEL, EVENTS_SPECIAL_LABEL, EVENTS_GAMES_LABEL, EVENTS_FUNZONE_LABEL,
)
# Activity slugs that form the Bowling/Billiards/Family-Fun venue cluster.
_FUNZONE_SLUGS: frozenset[str] = frozenset({"bowling", "billiards", "trampoline", "family-fun"})


def classify_events_subgroup(
    title: str, tags: list[str] | None = None, activity: str | None = None
) -> str:
    """Map a Things-to-Do row to its subsection.

    A ``facet:special`` row (Cosmic Bowling, Glow in the Park) is a destination
    event → Special Sessions, surfaced apart from the venue's regular hours. Then
    the funzone cluster (bowling/billiards/trampoline/family-fun activity) is its
    hours section, all-ages games (``activity:games``) are Games & Social, and
    everything else is the residual Around Town."""
    tagset = {str(t).strip().lower() for t in (tags or [])}
    if "facet:special" in tagset:
        return EVENTS_SPECIAL_LABEL
    slug = resolve_activity(title, None, tags, activity)
    if slug in _FUNZONE_SLUGS:
        return EVENTS_FUNZONE_LABEL
    if slug == "games":
        return EVENTS_GAMES_LABEL
    return EVENTS_AROUND_LABEL


def split_events_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Things-to-Do rows into ordered subsections,
    omitting empty ones (honest-omission). Row order preserved. The caller only
    applies this when a non-residual subsection exists (so plain days stay flat)."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = classify_events_subgroup(
            row.get("title") or "", row.get("tags"), row.get("activity")
        )
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in EVENTS_SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


# ── Seniors group — internal sub-split (the gated group stays browsable) ───────
# Senior Center programming is gated (age/membership) and grouped under Seniors
# ONLY (never cross-listed into the public buckets — that routing lives in
# events_views). Inside the group it sub-splits by activity so it is still
# scannable, per the layout doc.
SENIOR_GAMES_LABEL = "Games & Social"
SENIOR_FITNESS_LABEL = "Fitness & Movement"
SENIOR_ARTS_LABEL = "Arts & Crafts"
SENIOR_SOCIAL_LABEL = "Social, Music & Meals"
SENIOR_SPECIAL_LABEL = "Special"
SENIOR_SUBGROUP_ORDER: tuple[str, ...] = (
    SENIOR_GAMES_LABEL, SENIOR_FITNESS_LABEL, SENIOR_ARTS_LABEL,
    SENIOR_SOCIAL_LABEL, SENIOR_SPECIAL_LABEL,
)
_SENIOR_SPECIAL_RE = re.compile(
    r"\b(awareness|christmas|thanksgiving|halloween|holiday|new year|"
    r"grand (?:re-?)?opening|anniversary|celebration|special event)\b",
    re.IGNORECASE,
)
_SENIOR_SOCIAL_RE = re.compile(
    r"\b(lunch|luncheon|dinner|breakfast|brunch|potluck|meal|coffee|social|"
    r"music jam|jam session|karaoke|movie|bingo night)\b",
    re.IGNORECASE,
)


def classify_senior_subgroup(
    title: str, tags: list[str] | None = None, activity: str | None = None
) -> str:
    """Map a senior occurrence to its internal subsection (Games & Social,
    Fitness & Movement, Arts & Crafts, Social/Music/Meals, Special)."""
    low = (title or "")
    tagset = {str(t).strip().lower() for t in (tags or [])}
    if "facet:special" in tagset or _SENIOR_SPECIAL_RE.search(low):
        return SENIOR_SPECIAL_LABEL
    slug = resolve_activity(title, None, tags, activity)
    # Cards / board games AND the Senior Center pool room read as Games & Social
    # (the layout groups "Open Billiards" with Pinochle/Bridge under Seniors).
    if slug in ("games", "billiards"):
        return SENIOR_GAMES_LABEL
    if slug in ("arts", "maker"):
        return SENIOR_ARTS_LABEL
    if activity_bucket(slug) == "classes":
        return SENIOR_FITNESS_LABEL
    if _SENIOR_SOCIAL_RE.search(low):
        return SENIOR_SOCIAL_LABEL
    # theater / cooking / learning / unclassified senior items read as social.
    return SENIOR_SOCIAL_LABEL


def split_senior_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Seniors rows into ordered internal subsections,
    omitting empty ones (honest-omission). Row order preserved."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = classify_senior_subgroup(
            row.get("title") or "", row.get("tags"), row.get("activity")
        )
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in SENIOR_SUBGROUP_ORDER:
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
