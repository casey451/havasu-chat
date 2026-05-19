"""Multi-domain intent heuristics for cross-entity chat (Phase 7)."""

from __future__ import annotations

import re

# Nouns that imply a Tier-1 category slug (subset used in cross-entity tests).
_NOUN_TO_CATEGORY_SLUGS: dict[str, tuple[str, ...]] = {
    "pizza": ("eat-drink",),
    "library": ("community-civic", "outdoors-parks-trails"),
    "libraries": ("community-civic", "outdoors-parks-trails"),
    "dog": ("pets", "eat-drink", "outdoors-parks-trails"),
    "dogs": ("pets", "eat-drink", "outdoors-parks-trails"),
    "pet": ("pets",),
    "pets": ("pets",),
    "breakfast": ("eat-drink",),
    "brunch": ("eat-drink",),
    "coffee": ("eat-drink",),
    "cafe": ("eat-drink",),
    "restaurant": ("eat-drink",),
    "grocery": ("shopping-essentials",),
    "groceries": ("shopping-essentials",),
    "park": ("outdoors-parks-trails",),
    "parks": ("outdoors-parks-trails",),
    "trail": ("outdoors-parks-trails",),
    "trails": ("outdoors-parks-trails",),
    "hotel": ("lodging-vacation-rentals",),
    "lodging": ("lodging-vacation-rentals",),
    "plumber": ("home-property-services",),
    "vet": ("pets", "health-wellness-care"),
}

_CONNECTOR_RE = re.compile(
    r"\b(?:and|with|where\s+i\s+can\s+also|as\s+well\s+as)\b",
    re.IGNORECASE,
)


def detect_multi_domain_category_slugs(query: str) -> tuple[str, ...] | None:
    """Return category slugs when the query spans multiple domains, else None."""
    q = (query or "").lower()
    if not q.strip():
        return None

    hits: list[str] = []
    seen_slugs: set[str] = set()
    tokens = set(re.findall(r"[a-z']+", q))
    for noun, slugs in _NOUN_TO_CATEGORY_SLUGS.items():
        if noun in tokens or re.search(rf"\b{re.escape(noun)}\b", q):
            for slug in slugs:
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    hits.append(slug)

    if len(hits) >= 2:
        return tuple(hits)

    if _CONNECTOR_RE.search(q) and len(hits) >= 1:
        # "groceries and coffee" — connector + at least one category noun.
        extra = [s for s in _infer_second_slug_from_connector(q) if s not in seen_slugs]
        combined = hits + extra
        if len(set(combined)) >= 2:
            return tuple(dict.fromkeys(combined))

    return None


def _infer_second_slug_from_connector(q: str) -> list[str]:
    """When a connector is present, scan both sides for category nouns."""
    out: list[str] = []
    for noun, slugs in _NOUN_TO_CATEGORY_SLUGS.items():
        if re.search(rf"\b{re.escape(noun)}\b", q):
            out.extend(slugs)
    return out


_FACTUAL_LOOKUP_RE = re.compile(
    r"\b(?:rating|reviews?|review\s+count|wait(?:\s+time)?|"
    r"phone\s+number|website|hours|address|location)\b",
    re.IGNORECASE,
)

_CATEGORY_OPEN_NOW_RE = re.compile(
    r"\b(?:restaurants?|cafes?|coffee\s+shops?|bars?|veterinarians?|"
    r"pharmacies|groceries|stores?|shops?)\b",
    re.IGNORECASE,
)

_FAKE_ENTITY_MARKER_RE = re.compile(
    r"\b(?:zzz|fake|fabricated|imaginary|nonexistent|totally\s+fake|"
    r"random\s+place|missing|404|99999|888|777|555|xyz)\b",
    re.IGNORECASE,
)

_OPEN_NOW_PHRASE_RE = re.compile(
    r"\bopen\s+(?:now|right\s+now)\b|\bopen\s+at\s+the\s+moment\b",
    re.IGNORECASE,
)

_BEST_CATEGORY_RE = re.compile(
    r"\bbest\s+(\w+(?:\s+\w+)?)\s+(?:in|around|near)\b",
    re.IGNORECASE,
)


def query_mentions_fake_entity_marker(query: str) -> bool:
    """True when the user named an obviously non-catalog test/missing entity."""
    return bool(_FAKE_ENTITY_MARKER_RE.search(query or ""))


def suppress_out_of_scope_for_factual_lookup(message: str) -> bool:
    """Keep rating/wait/hours-style lookups in ask mode (not chat OUT_OF_SCOPE)."""
    return bool(_FACTUAL_LOOKUP_RE.search(message or ""))


def is_category_open_now_listing(query: str) -> bool:
    """True when the user asks which venues in a category are open now."""
    q = query or ""
    return bool(_CATEGORY_OPEN_NOW_RE.search(q) and _OPEN_NOW_PHRASE_RE.search(q))


def infer_listing_category_term(query: str) -> str | None:
    """Category noun for listing/rec queries (e.g. pizza, barber, vet)."""
    q = (query or "").lower()
    tokens = set(re.findall(r"[a-z']+", q))
    for noun in _NOUN_TO_CATEGORY_SLUGS:
        if noun in tokens or re.search(rf"\b{re.escape(noun)}\b", q):
            return noun
    m = _BEST_CATEGORY_RE.search(q)
    if m:
        term = m.group(1).strip().lower()
        if term in _NOUN_TO_CATEGORY_SLUGS:
            return term
        for alias, canonical in (
            ("barbershop", "barber"),
            ("barbers", "barber"),
            ("restaurants", "restaurant"),
        ):
            if term == alias:
                return canonical
    return None


def near_match_subject_tokens(query: str) -> frozenset[str]:
    """Subject tokens from a location-style query (e.g. library from 'where is the library')."""
    q = (query or "").lower()
    m = re.search(
        r"\bwhere(?:'s|\s+is|\s+are)\s+(?:the\s+)?([a-z][a-z\s'-]{2,40})\s*$",
        q,
    )
    if not m:
        return frozenset()
    subject = m.group(1).strip()
    stop = frozenset({"the", "a", "an", "at", "in", "on"})
    return frozenset(t for t in re.findall(r"[a-z]+", subject) if t not in stop)


def near_match_subject_overlaps(query: str, canonical_name: str) -> bool:
    """True when the query subject shares a token with the near-match name."""
    subjects = near_match_subject_tokens(query)
    if not subjects:
        return True
    name_tokens = frozenset(re.findall(r"[a-z]+", (canonical_name or "").lower()))
    return bool(subjects & name_tokens)


__all__ = [
    "detect_multi_domain_category_slugs",
    "infer_listing_category_term",
    "is_category_open_now_listing",
    "near_match_subject_overlaps",
    "near_match_subject_tokens",
    "query_mentions_fake_entity_marker",
    "suppress_out_of_scope_for_factual_lookup",
]
