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
# the lhc_bmx / havasu_youth youth-source loaders).
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
        "toptracer",
    }
)

# Positive kid/family signals in a title. Word-boundary matched.
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
    # Youth venues added 2026-06-12 (BMX, trampoline, glow bowling, Toptracer,
    # arcades, mini golf, splash pads). These read as kid/family activities;
    # the adult veto below still wins if an adult marker is also present.
    r"bmx|balance\s+bike|"
    r"trampoline|bounce|jump\s+time|glow\s+in\s+the\s+park|"
    r"rock\s*&?\s*bowl|glow\s+bowl\w*|cosmic\s+bowl\w*|family\s+bowl\w*|"
    r"top\s*tracer|night\s+golf|"
    r"arcade|mini[\s-]*golf|splash\s+pad|bounce\s+house"
    r")\b",
    re.IGNORECASE,
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


def is_family_event(title: str | None, tags: list[str] | None = None) -> bool:
    """True when the occurrence positively reads as a kid/family thing."""
    t = (title or "").strip()
    if t and _ADULT_TITLE_RE.search(t):
        return False
    if t and _FAMILY_TITLE_RE.search(t):
        return True
    for tag in tags or []:
        if isinstance(tag, str) and tag.strip().lower() in _FAMILY_TAGS:
            return True
    return False
