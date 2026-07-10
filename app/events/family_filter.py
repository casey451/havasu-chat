"""Family-mode event filter — "show me only the kid things".

Powers the ``?family=1`` toggle on ``/events-ui``. Family mode is
positive-match: an occurrence shows ONLY when its title or tags carry a kid /
family signal, and never when an adult-only marker is present. So the Aquatic
Center's "Open Swim" and "Free Family Swim" stay, while "Aqua Challenge" and
"Sippin' with the Somm" drop — exactly the calendar a parent is looking for.

Heuristic by design (most rows carry no structured age data); tuned against
the live June 2026 calendar. Misses are honest omissions — never fabricated
matches — and the keyword lists are the single place to extend coverage.
"""

from __future__ import annotations

import re

# Tags written by the ingest loaders (parks_rec_loader audience tagging, plus
# the WS12 lhc_bmx / havasu_youth youth-source loaders).
_FAMILY_TAGS = frozenset(
    {
        "youth",
        "kids",
        "kid",
        "family",
        "children",
        "teen",
        "teens",
        "all ages",
        "toddler",
        "bmx",
        "bowling",
        "glow",
        "trampoline",
    }
)

# Positive kid/family signals in a title. Word-boundary matched.
#
# The second block (2026-06) catches youth gym / dance / martial-arts CLASS
# names that carry no obvious "kids/youth" word but are unmistakably for
# children — e.g. gymnastics "Tiny Tumblers" / "Gymtots", a dojo's "Littles
# Gi" / "Little Ninjas", "Pee Wee" sports, "Mommy & Me", "Pre-K"/"Preschool"
# classes. Without these the calendar filed Universal Sonics' "Tiny Tumblers"
# and The Tap Room's "Littles Gi" under Fitness & classes, not Kids & Family.
# Kept high-precision (no bare "little"/"mini"/"tiny") so adult rows like
# "A Little Lunch Music" don't get pulled in; the adult veto still wins first.
_FAMILY_TITLE_RE = re.compile(
    r"\b("
    r"kids?|child(?:ren)?|toddlers?|teens?|youth|junior|family|families|"
    r"all\s+ages|"
    r"open\s+swim|family\s+swim|swim\s+lessons?|"
    r"story\s*times?|story\s+hour|"
    r"camps?|scouts?|"
    r"baby|babies|babysit\w*|"
    r"lego|minecraft|pok[eé]mon|spongebob|"
    r"crafts?\s+for\s+kids|"
    r"skate\s+night|roller\s+skat\w*|skate\s+park|"
    r"youth\s+edition|"
    # WS12 youth venues (BMX, trampoline, glow bowling, arcades, mini golf,
    # splash pads). These read as kid/family activities; the adult veto below
    # still wins if an adult marker is also present. (Toptracer / "night golf"
    # deliberately excluded — that fixture was dropped as venue-hours, not an
    # event; see app/events/scrapers/havasu_youth.py.)
    r"bmx|balance\s+bike|"
    r"trampoline|bounce|jump\s+time|glow\s+in\s+the\s+park|"
    r"rock\s*&?\s*bowl|glow\s+bowl\w*|cosmic\s+bowl\w*|family\s+bowl\w*|"
    r"arcade|mini[\s-]*golf|splash\s+pad|bounce\s+house|"
    # youth class-name patterns
    r"tumbl(?:e|es|er|ers|ing)?|gymtots?|tots?|"
    # Universal Sonics' youth gymnastics blocks carry no kid word in the title.
    r"boys?\s+athletics?|rec\s+gym|"
    r"pee\s*-?\s*wee|lil\b|"
    r"littles|little\s+(?:ninjas?|dragons?|tigers?|kickers?|stars?|movers?|hawks?|gym)|"
    r"tiny\s+(?:tots?|tumblers?|dancers?|ninjas?|hawks?)|"
    r"pre-?k|preschool|kinder(?:garten)?|"
    r"mommy\s*(?:&|and|n|\+)?\s*me|parent\s*(?:&|and|n|\+)?\s*tot|"
    r"creative\s+(?:dance|movement)|"
    # youth-dance + kids-activity names that carry no generic kid word
    r"tiny\s+toes|pre-?ballet|pre-?tap|ballet\s+beginnings|rec\s+cheer|"
    r"pony|lead\s+line"
    r")\b",
    re.IGNORECASE,
)

# Venues/providers whose programming is entirely for children, so every class
# published under them is a Kids & Family item even when the title carries no kid
# word (a homeschool enrichment center, a youth gymnastics/cheer gym). Substring
# matched, lower-cased; kept to providers with NO adult offerings so an adult
# class can't be misrouted. (Mixed-age studios like Ballet Havasu are NOT here —
# their classes route by title.)
_FAMILY_VENUE_HINTS: tuple[str, ...] = (
    "desert bloom learning center",
    "universal sonics",
)

# Adult-only markers — veto whatever the positive match said.
_ADULT_TITLE_RE = re.compile(
    r"\b("
    r"21\s*\+|18\s*\+|adults?\s+only|adults?\b|"
    r"wine|beer|brew\w*|sippin\w*|somm\w*|cocktails?|happy\s+hour|"
    r"casino|bar\s+crawl|"
    r"seniors?|elder\w*"
    r")\b",
    re.IGNORECASE,
)


def is_family_event(
    title: str | None, tags: list[str] | None = None, venue: str | None = None
) -> bool:
    """True when the occurrence positively reads as a kid/family thing.

    Decided by, in order: an adult-only veto (wine/21+/seniors); a kid/family
    TITLE word; a kids-only VENUE/provider (so a generically-named program at a
    homeschool center or youth gym still routes to Kids & Family); a family TAG.

    This is the broad ``?family=1`` predicate — it deliberately includes
    all-ages / family-friendly things (Cosmic Bowling, "Glow in the Park — All
    Ages", "Family Night Golf"). For the stricter "is this YOUTH-specific?"
    question (the "Youth <activity>" sub-section flag, the home-feed Kids tag),
    use :func:`is_youth_event`.
    """
    t = (title or "").strip()
    if t and _ADULT_TITLE_RE.search(t):
        return False
    if t and _FAMILY_TITLE_RE.search(t):
        return True
    vlow = (venue or "").lower()
    if vlow and any(h in vlow for h in _FAMILY_VENUE_HINTS):
        return True
    for tag in tags or []:
        if isinstance(tag, str) and tag.strip().lower() in _FAMILY_TAGS:
            return True
    return False


# Genuinely YOUTH-specific signal — STRICTER than is_family_event (Casey
# 2026-06-26: "Cosmic Bowling isn't youth bowling, it's just an event at the
# bowling alley; Glow in the Park isn't youth trampoline"). A family-friendly /
# all-ages event belongs in family mode but must NOT peel into a "Youth
# <activity>" sub-section. The "all ages" / bare-"family" markers (tag OR title)
# veto the youth read even when a loader stamped a ``kids``/``family`` tag; a
# genuine kid-only TITLE token still wins first.
_YOUTH_TAGS = frozenset(
    {"youth", "kids", "kid", "children", "child", "teen", "teens", "tween",
     "junior", "toddler", "toddlers"}
)
_YOUTH_TITLE_RE = re.compile(
    r"\b("
    r"kids?|child(?:ren)?|toddlers?|teens?|tweens?|youth|junior|jr|"
    r"story\s*times?|story\s+hour|"
    r"lego|minecraft|pok[eé]mon|"
    r"tumbl(?:e|es|er|ers|ing)?|gymtots?|"
    r"pee\s*-?\s*wee|"
    r"littles|little\s+(?:ninjas?|dragons?|tigers?|kickers?|stars?|movers?|hawks?|gym)|"
    r"tiny\s+(?:tots?|tumblers?|dancers?|ninjas?|hawks?)|"
    r"pre-?k|preschool|kinder(?:garten)?|"
    r"mommy\s*(?:&|and|n|\+)?\s*me|parent\s*(?:&|and|n|\+)?\s*tot|"
    r"swim\s+lessons?"
    r")\b",
    re.IGNORECASE,
)
_ALL_AGES_TAGS = frozenset({"all ages", "all-ages"})
_ALL_AGES_VETO_RE = re.compile(
    r"\ball[\s-]*ages\b|\bfamil(?:y|ies)\b|\bopen\s+swim\b", re.IGNORECASE
)


def is_youth_event(
    title: str | None, tags: list[str] | None = None, venue: str | None = None
) -> bool:
    """True only for genuinely youth-targeted occurrences.

    Order: an adult-only veto; a kid-only TITLE token (wins outright); an
    all-ages marker (``all ages`` tag, or an all-ages / bare-"family" / open-swim
    TITLE word) that vetoes the youth read even when a loader tagged the row
    ``kids``/``family``; a kids-only VENUE; finally a youth data TAG. So
    "Cosmic Bowling" (``all ages`` tag) and "Family Night Golf" read as NOT
    youth, while "Junior Jump Time" and a ``kids``-tagged "Wrestling" do.
    """
    t = (title or "").strip()
    if t and _ADULT_TITLE_RE.search(t):
        return False
    if t and _YOUTH_TITLE_RE.search(t):
        return True
    tagset = {str(x).strip().lower() for x in (tags or [])}
    if tagset & _ALL_AGES_TAGS or (t and _ALL_AGES_VETO_RE.search(t)):
        return False
    vlow = (venue or "").lower()
    if vlow and any(h in vlow for h in _FAMILY_VENUE_HINTS):
        return True
    return bool(tagset & _YOUTH_TAGS)
