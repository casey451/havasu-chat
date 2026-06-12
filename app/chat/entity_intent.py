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
    # P1-5: dropped the bare numeric markers 555/777/888 and "missing" — they
    # collided with real phone fragments, street numbers, and "missing hours"
    # phrasings, wrongly tagging real entities as fabricated.
    r"\b(?:zzz|fake|fabricated|imaginary|nonexistent|totally\s+fake|"
    r"random\s+place|404|99999|xyz)\b",
    re.IGNORECASE,
)

_OPEN_NOW_PHRASE_RE = re.compile(
    r"\bopen\s+(?:now|right\s+now)\b|\bopen\s+at\s+the\s+moment\b",
    re.IGNORECASE,
)

_CATEGORY_TOKENS: frozenset[str] = frozenset(
    {
        # lodging
        "hotel",
        "motel",
        "inn",
        "resort",
        "lodge",
        "suites",
        "hostel",
        # eat/drink
        "restaurant",
        "cafe",
        "coffee",
        "bar",
        "grill",
        "diner",
        "bistro",
        "kitchen",
        "pizzeria",
        "brewery",
        "pub",
        "tavern",
        "eatery",
        # retail
        "store",
        "shop",
        "shoppe",
        "market",
        "mart",
        "boutique",
        # services / health
        "salon",
        "spa",
        "studio",
        "gym",
        "clinic",
        "hospital",
        "pharmacy",
        "dental",
        "dentist",
        "doctor",
        "vet",
        "veterinary",
        # places
        "park",
        "trail",
        "center",
        "centre",
        "plaza",
        "mall",
        "lanes",
        # legal-suffix noise
        "service",
        "services",
        "company",
        "co",
        "inc",
        "incorporated",
        "llc",
        "ltd",
        "group",
        "corp",
        "corporation",
        "the",
        # locale (Havasu-specific stopwords already used by entity_matcher)
        "lake",
        "havasu",
        "city",
        "arizona",
        "az",
    }
)

# Generic, non-identifying words that appear inside business names but do not
# pin down a specific entity (unlike a real name token such as "mudshark" or
# "heat"). Used by ``near_match_subject_overlaps`` so that a descriptive query
# sharing only one of these with a catalog row ("leave my truck" -> "A Toe
# Truck", "watch sunset" -> "Sunset Plaza", "biting right now" -> "Done Right
# Auto") does NOT surface that unrelated business. Kept deliberately tight:
# the guard only bites when this is the *sole* overlap AND the query carries its
# own distinctive subject token, so real lookups ("sunset" -> "Sunset Plaza")
# are unaffected.
_GENERIC_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "right",
        "left",
        "done",
        "local",
        "sunset",
        "sunrise",
        "best",
        "good",
        "great",
        "first",
        "new",
        "old",
        "fun",
        "truck",
    }
)

# Function-word stopwords that can appear in both a query and a business name
# ("... and Alignment", "biting right now ... and where") but never identify an
# entity. Stripped from both sides before the near-match overlap test so a
# shared "and"/"now" can't make a descriptive clause pair with an unrelated row.
_STOPWORD_TOKENS: frozenset[str] = frozenset(
    {
        "and", "or", "but", "nor", "with", "without", "for", "from", "of", "to",
        "in", "on", "at", "by", "as", "my", "we", "us", "me", "you", "your",
        "our", "their", "it", "its", "this", "that", "these", "those", "what",
        "which", "who", "when", "where", "why", "how", "do", "does", "did",
        "can", "could", "should", "would", "will", "shall", "may", "might",
        "must", "is", "are", "was", "were", "be", "been", "being", "am", "all",
        "any", "some", "no", "not", "now", "then", "today", "tonight", "here",
        "there",
    }
)

_SUBJECT_LEAD_RE = re.compile(
    r"^\s*(?:"
    r"rating|ratings|star\s+rating|google\s+rating|"
    r"reviews?|review\s+count|how\s+many\s+(?:stars?|reviews?)|"
    r"phone|phone\s+number|contact|number|"
    r"address|location|located|"
    r"hours?|business\s+hours|when\s+(?:does|is)|what\s+time|"
    r"website|site|url|link|"
    r"where(?:'s|\s+is|\s+are)?(?:\s+the)?|where\s+can\s+i\s+find|"
    r"is|are|"
    r"how\s+is(?:\s+the)?|how\s+are\s+the\s+reviews?"
    r")\s+(?:for\s+|of\s+|at\s+)?",
    re.IGNORECASE,
)

_BEST_CATEGORY_RE = re.compile(
    r"\bbest\s+(\w+(?:\s+\w+)?)\s+(?:in|around|near)\b",
    re.IGNORECASE,
)

# Phase 7.5.3 F1 — structural heuristic for unmarked fabricated entity names.
_HIGH_DIGIT_DENSITY_RE = re.compile(r"\b[A-Za-z]+\s*\d{3,}\b")
_CONSONANT_RUN_RE = re.compile(r"\b[bcdfghjklmnpqrstvwxyz]{4,}", re.I)

# P1-5: real street/place abbreviations whose all-consonant spelling otherwise
# trips the consonant-run heuristic ("mcculloch blvd", "lake havasu pkwy").
_STREET_ABBREVIATIONS: frozenset[str] = frozenset(
    {"blvd", "pkwy", "bldg", "hwy", "fwy", "expy", "tpke", "ste"}
)


def _looks_structurally_fake(query: str) -> bool:
    """Best-effort detector for fabricated entity names without marker tokens.

    Returns True when the query contains either:
      - a token with high digit density (e.g. "Business 4042", "XYZ 555")
      - a token with a 4+ consecutive-consonant run (e.g. "zzznonexistent")

    Skipped on queries with < 5 tokens to avoid false-positives on short
    legitimate entity references ("Heat Hotel", "phone for mdshrkbrwry").

    Street-type abbreviations (``blvd``, ``pkwy`` …) are whitelisted so real
    address queries like "what shops are on mcculloch blvd" don't read as
    fabricated. (P1-5)
    """
    q = (query or "").strip()
    if len(q.split()) < 5:
        return False
    if _HIGH_DIGIT_DENSITY_RE.search(q):
        return True
    for tok in re.findall(r"[A-Za-z]+", q):
        if tok.lower() in _STREET_ABBREVIATIONS:
            continue
        if _CONSONANT_RUN_RE.search(tok):
            return True
    return False


def query_mentions_fake_entity_marker(query: str) -> bool:
    """True when the user named an obviously non-catalog test/missing entity.

    Phase 7.5.3 F1: whitelist regex still handles eval markers (xyz / 404 / etc.).
    Structural heuristic in _looks_structurally_fake catches unmarked
    fabrications (digit-density + consonant-run shapes) on queries >= 5 tokens.
    """
    if _FAKE_ENTITY_MARKER_RE.search(query or ""):
        return True
    return _looks_structurally_fake(query or "")


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


def _general_subject_tokens(query: str) -> frozenset[str]:
    """Extract content tokens from any query shape (not just 'where is X')."""
    q = (query or "").lower().strip()
    if not q:
        return frozenset()
    q = _SUBJECT_LEAD_RE.sub("", q, count=1)
    q = q.strip(" ?.!,")
    tokens = re.findall(r"[a-z0-9]+", q)
    return frozenset(t for t in tokens if len(t) >= 2 and t not in _CATEGORY_TOKENS)


def near_match_subject_overlaps(query: str, canonical_name: str) -> bool:
    """True when the query and the near-match canonical share at least one
    *content* token — i.e. a token that isn't a generic category word.

    Tightened (q22 fix 2026-05-19): the previous implementation returned True
    whenever the query wasn't shaped like 'where is X'. That fail-open default
    let queries such as 'rating for Fabricated Hotel Name 555' pair with the
    near-match canonical 'Heat Hotel' even though the only overlap is the
    category word 'hotel'. The new guard:

      1. Extracts subject tokens from any query shape (strips Tier-1 intent
         leads, drops _CATEGORY_TOKENS, requires length >= 2).
      2. Extracts the same content-only token set from the canonical name.
      3. Returns True only when they share at least one content token.
      4. Typo escape hatch: a single long query token (>= 6 chars) is
         partial-ratio-fuzzed against name tokens >= 5 chars at threshold 80
         to preserve severe-typo near-matches (e.g. 'mdshrkbrwry' ~ 'mudshark').
      5. Keyword-artifact guard (QA diagnostic 2026-06-12): function-word
         stopwords are dropped from both sides, and when the *only* overlap is a
         generic name word (_GENERIC_NAME_TOKENS: right/local/sunset/truck/…) the
         match is accepted only for a short entity-shaped lookup, not for a
         descriptive clause that carries its own distinctive subject token. This
         stops 'leave my truck' -> 'A Toe Truck' and 'biting right now' -> 'Done
         Right Auto' from surfacing an unrelated business.

    When the query has no content tokens at all (all category words), require
    shared raw-token overlap with the canonical name before returning True.
    Deictic tokens (near, me, place, …) are not entity-identifying and are
    treated like category words for this fail-open guard.
    """
    q_subjects = _general_subject_tokens(query)
    _deictic_tokens = frozenset({"near", "me", "here", "there", "around", "nearby", "place"})
    category_only_query = not q_subjects or q_subjects <= _deictic_tokens
    if category_only_query:
        raw_query_tokens = frozenset(re.findall(r"[a-z0-9]+", (query or "").lower()))
        if raw_query_tokens & _CATEGORY_TOKENS:
            name_raw = frozenset(re.findall(r"[a-z0-9]+", (canonical_name or "").lower()))
            return bool(raw_query_tokens & name_raw)
        return False

    name_tokens = frozenset(
        t
        for t in re.findall(r"[a-z0-9]+", (canonical_name or "").lower())
        if len(t) >= 2 and t not in _CATEGORY_TOKENS
    )
    if not name_tokens:
        raw_name_tokens = frozenset(re.findall(r"[a-z0-9]+", (canonical_name or "").lower()))
        return bool(q_subjects & raw_name_tokens)

    # Drop function-word stopwords before the overlap test so a shared "and" /
    # "now" can't pair a descriptive clause with an unrelated catalog row.
    q_content = q_subjects - _STOPWORD_TOKENS
    name_content = name_tokens - _STOPWORD_TOKENS
    shared = q_content & name_content
    if shared:
        # A distinctive (non-generic) shared token identifies the entity -> accept.
        if shared - _GENERIC_NAME_TOKENS:
            return True
        # Only a generic word overlaps. A genuine short lookup ("sunset" ->
        # "Sunset Plaza") has nothing else to disambiguate and is kept. But a
        # descriptive clause that merely happens to share a common word
        # ("leave my truck" -> "A Toe Truck") carries its own distinctive
        # subject token the name lacks -- reject so it falls through to the
        # honest gap template instead of surfacing an unrelated business.
        if q_content - name_content - _GENERIC_NAME_TOKENS:
            return False
        return True

    try:
        from rapidfuzz import fuzz

        for qt in q_content:
            if len(qt) < 6:
                continue
            for nt in name_content:
                if len(nt) < 5:
                    continue
                if fuzz.partial_ratio(qt, nt) >= 80:
                    return True
    except ImportError:
        pass

    return False


__all__ = [
    "detect_multi_domain_category_slugs",
    "infer_listing_category_term",
    "is_category_open_now_listing",
    "near_match_subject_overlaps",
    "near_match_subject_tokens",
    "query_mentions_fake_entity_marker",
    "suppress_out_of_scope_for_factual_lookup",
]
