"""Tier 2 zero-token shortcut for business listing queries (Slice D).

The standard Tier 2 path calls Anthropic Haiku twice per query — once for the
parser (query → :class:`Tier2Filters`) and once for the formatter (rows → reply
text). For simple business-listing shapes ("find me a barber in LHC", "any good
coffee shops", "where can I get a haircut"), both LLM calls are avoidable: the
category is recoverable by regex, and the response shape is short enough to
template deterministically. This module owns that fast path.

Design notes
------------
- The shortcut is **conservative**: it only fires when the query starts with one
  of a small set of listing predicates ("find me a", "any good", "show me", …),
  and bails when the query also carries event-shaped tokens (weekday names,
  "tonight", "this week", "happening", "event", "class", "league") — those
  belong on the LLM parser path which understands time windows.
- A miss returns ``None``, signalling the caller to fall through to the existing
  LLM parser. There is no "wrong shortcut" failure mode; worst case is wasted
  cycles on a query the LLM parser would have caught anyway.
- The deterministic formatter only emits provider rows. Mixed event/program
  results from the same listing-shaped query (rare) still flow through the LLM
  formatter via the standard path.

Wired from :func:`app.chat.tier2_handler.try_tier2_with_usage` ahead of the
parser call.
"""

from __future__ import annotations

import re
from typing import Any

from app.chat.tier2_schema import Tier2Filters

# Verb phrases that signal a listing intent. Order inside the alternation matters:
# longer phrases first so "where can i find" wins over "where".
_LISTING_PREFIX = re.compile(
    r"^\s*("
    # Slice F5: trailing-article fragment is `(?:an\s+|a\s+|some\s+)?` — order matters
    # (longer "an" first) and each alternative requires a trailing space so "find an X"
    # doesn't get truncated to "n X" by greedy-leftmost matching the bare "a".
    r"where\s+can\s+i\s+(?:find|get)\s+(?:an\s+|a\s+|some\s+)?|"
    # Bug fix (post-Slice-F shadow run): for "where is/are/'s" the article is REQUIRED.
    # Without the article, "where is mudshark brewing" was wrongly matching as a listing
    # shape and absorbing the specific-entity question. Now "where's a barber" matches,
    # "where is mudshark brewing" doesn't (defers to LOCATION_LOOKUP Tier 1).
    r"where(?:'s|\s+is|\s+are)\s+(?:an\s+|a\s+|some\s+)|"
    r"find\s+(?:me\s+)?(?:an\s+|a\s+|some\s+)?|"
    r"show\s+me\s+(?:an\s+|a\s+|some\s+)?|"
    r"give\s+me\s+(?:an\s+|a\s+|some\s+)?|"
    r"list\s+(?:of\s+)?(?:all\s+)?(?:the\s+)?|"
    r"any\s+(?:good\s+)?|"
    r"are\s+there\s+(?:any\s+)?(?:good\s+)?|"
    # Slice F5: widen for natural phrasings ("what are some", "got any", "recommend").
    r"what\s+(?:are\s+)?(?:some\s+|the\s+)?(?:good\s+|best\s+)?|"
    r"got\s+(?:any\s+|a\s+)?(?:good\s+)?|"
    r"recommend\s+(?:me\s+)?(?:an\s+|a\s+|any\s+|some\s+)?(?:good\s+)?|"
    # Voice-battery 2026-05-08: first-person need/want phrasings for category
    # listings. "I need a plumber" / "I'm looking for a barber" / "I want a
    # coffee shop" all currently fall through to Tier 3 with a generic
    # provider context that doesn't include the requested category. Article
    # is required so "I need to call iron wolf" still defers to Tier 1
    # PHONE_LOOKUP.
    r"i\s+need\s+(?:an\s+|a\s+|some\s+)|"
    r"i\s+want\s+(?:an\s+|a\s+|some\s+)|"
    r"i'?m\s+looking\s+for\s+(?:an\s+|a\s+|some\s+)|"
    r"looking\s+for\s+(?:an\s+|a\s+|some\s+)"
    r")",
    re.IGNORECASE,
)

# Locality suffix stripped from the category so the search term stays clean.
# "barbers in lake havasu city" -> "barbers"; "haircut near me" -> "haircut".
_LOCALITY_SUFFIX = re.compile(
    r"\s+(?:in|near|around|by)\s+(?:lhc|lake\s+havasu(?:\s+city)?|here|me|town|the\s+area)\.?\s*$",
    re.IGNORECASE,
)

_TRIM_TAIL = re.compile(r"[?\.!\s]+$")

# Voice battery 2026-05-08 (§4.1 typo tolerance): small alias map for common
# misspellings of service-trade categories. Applied token-by-token after
# locality stripping so "i need a plumer" → category "plumber" before the
# downstream SQL filter (which does ILIKE against Provider.category /
# google_primary_category and won't match across edit distance). Conservative —
# only the obvious misspellings of trades we actually carry. Add entries as
# new typos surface in chat_logs.
_CATEGORY_TOKEN_ALIASES: dict[str, str] = {
    # plumbing
    "plumer": "plumber",
    "plummer": "plumber",
    "plumming": "plumbing",
    # barbering
    "barbar": "barber",
    "barbor": "barber",
    "barbur": "barber",
    # electrical
    "elektrician": "electrician",
    "electrision": "electrician",
    "electricion": "electrician",
    "electrican": "electrician",
    # mechanic / auto
    "mecanic": "mechanic",
    "mechanik": "mechanic",
    "mechinic": "mechanic",
    # veterinary
    "vetrinarian": "veterinarian",
    "veternarian": "veterinarian",
    "vetrinary": "veterinary",
    "veternary": "veterinary",
    # food / drink
    "resturant": "restaurant",
    "restaraunt": "restaurant",
    "restuarant": "restaurant",
    "coffe": "coffee",
    "cofee": "coffee",
    "coffey": "coffee",
    # pharmacy / health
    "pharamcy": "pharmacy",
    "pharmasy": "pharmacy",
    "pharmcy": "pharmacy",
    # trades / misc
    "carpentar": "carpenter",
    "carpentor": "carpenter",
    "landscapper": "landscaper",
    "gymn": "gym",
    "salaon": "salon",
    # NB: "saloon" is intentionally NOT mapped to "salon" — in Lake Havasu the
    # word reads as a bar/tavern variant, not a misspelling of salon.
}


def _normalize_category_typos(category: str) -> str:
    """Token-level alias replacement for common service-trade misspellings.

    Lowercases each token before lookup so "Plumer" still normalizes. Returns
    the joined string in the original token order, preserving any tokens not
    in the alias map. Pure string-in / string-out — no side effects, safe to
    run in front of the existing event-shape and word-count guards.
    """
    if not category:
        return category
    tokens = category.split()
    if not tokens:
        return category
    out = [_CATEGORY_TOKEN_ALIASES.get(t.lower(), t) for t in tokens]
    return " ".join(out)

# Optional one-line landscape beat before the listing header (voice battery / rubric alignment).
# Keys are matched as substrings of the lowercased category from the shortcut extractor.
_BUSINESS_FRAMING_BY_CATEGORY_SUBSTR: tuple[tuple[str, str], ...] = (
    ("barber", "Cuts in Havasu are mostly small independents:"),
    ("haircut", "Cuts in Havasu are mostly small independents:"),
    ("salon", "Salons here range from quick cuts to full-day spa-style spots:"),
    ("coffee", "Coffee in Havasu skews drive-thru and chain-heavy, but a few sit-down spots run:"),
    ("restaurant", "Dining in Havasu spans casual lakeside to chain favorites:"),
    ("food", "Dining in Havasu spans casual lakeside to chain favorites:"),
    ("pizza", "Pizza runs from thin-crust locals to familiar delivery names:"),
    ("mexican", "Mexican spots here lean fast-casual with a few sit-down standouts:"),
    ("burger", "Burger stops skew classic American drive-up and counter-service:"),
    ("vet", "Vets in Havasu are a small handful of well-established practices:"),
    ("veterinar", "Vets in Havasu are a small handful of well-established practices:"),
    ("gym", "Gyms range from big-box fitness to smaller specialty studios:"),
    ("yoga", "Yoga and movement studios are few but dialed-in for locals:"),
    ("nail", "Nail spots tend to be compact salons with steady walk-in flow:"),
    ("spa", "Spa and wellness picks are limited — worth booking ahead:"),
    ("hotel", "Lodging clusters along the channel with a few standout independents:"),
    ("motel", "Lodging clusters along the channel with a few standout independents:"),
    ("brew", "Beer skews toward brewpub energy with a strong lake-weekend crowd:"),
    ("bar ", "Bars split between lakeside hangouts and neighborhood watering holes:"),
    ("bar", "Bars split between lakeside hangouts and neighborhood watering holes:"),
)

# Tokens that suggest an event / temporal shape — defer to the LLM parser. The leading
# space prevents partial-word matches (e.g. "league" inside "Lake League Park").
_EVENT_SHAPE_TOKENS: tuple[str, ...] = (
    " this week",
    " this weekend",
    " tonight",
    " today",
    " tomorrow",
    " monday",
    " tuesday",
    " wednesday",
    " thursday",
    " friday",
    " saturday",
    " sunday",
    " happening",
    " event",
    " events",
    " class",
    " classes",
    " program",
    " programs",
    " league",
    " leagues",
    " lesson",
    " lessons",
    # Slice F bug fix: Tier 1 factual keywords inside the extracted category mean the
    # query is asking for a specific lookup, not a category listing. Without these,
    # "what are the hours for X" wrongly fires the listing shortcut.
    " hours",
    " hour",
    " phone",
    " contact info",
    " website",
    " address",
    " rating",
    " ratings",
    " review",
    " reviews",
)


def _strip_locality_and_punct(s: str) -> str:
    cleaned = _LOCALITY_SUFFIX.sub("", s)
    cleaned = _TRIM_TAIL.sub("", cleaned)
    return cleaned.strip()


def _pluralize_for_header(category: str) -> str:
    """Coerce the listing header to plural form for natural phrasing.

    "find me a barber" → category="barber" → header "A few barbers in Lake Havasu City"
    "any good coffee shops" → category="coffee shops" → header unchanged
    """
    parts = (category or "").strip().split()
    if not parts:
        return "places"
    last = parts[-1]
    # Already plural / mass noun — leave alone.
    if last.endswith(("ss", "us", "is", "s")):
        return category
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        parts[-1] = last[:-1] + "ies"
        return " ".join(parts)
    if last.endswith(("sh", "ch", "x")):
        parts[-1] = last + "es"
        return " ".join(parts)
    parts[-1] = last + "s"
    return " ".join(parts)


def _landscape_framing_for_category(category: str) -> str | None:
    """Return a short opening line when `category` matches a known substring."""
    c = (category or "").lower().strip()
    if not c:
        return None
    for needle, line in _BUSINESS_FRAMING_BY_CATEGORY_SUBSTR:
        if needle in c:
            return line
    return None


def try_business_listing_shortcut(query: str) -> Tier2Filters | None:
    """Return a :class:`Tier2Filters` for a listing-shaped query, or ``None``.

    On match, ``parser_confidence`` is fixed at 0.9 (above the Tier 2 threshold of 0.7)
    so the existing handler accepts the filters without LLM input. ``category`` holds
    the lowercased extracted term; everything else stays at the schema defaults.
    """
    if not query or not query.strip():
        return None
    nq = query.strip()
    m = _LISTING_PREFIX.match(nq)
    if not m:
        return None
    rest = nq[m.end():].strip()
    if not rest:
        return None
    category = _strip_locality_and_punct(rest)
    if not category:
        return None
    # Normalize common service-trade typos before downstream guards so "i need a
    # plumer" extracts as "plumber" and reaches the SQL filter intact.
    category = _normalize_category_typos(category)
    low_padded = " " + category.lower()
    if any(tok in low_padded for tok in _EVENT_SHAPE_TOKENS):
        return None
    # Two-word category cap — anything longer is more likely a free-form question
    # than a category lookup. "find me a coffee shop" -> "coffee shop" (2 words, OK);
    # "find me the best place for kids on a hot day" -> too long, defer.
    if len(category.split()) > 3:
        return None
    return Tier2Filters(
        category=category.lower(),
        parser_confidence=0.9,
        fallback_to_tier3=False,
    )


def render_business_listing(rows: list[dict[str, Any]], category: str) -> str | None:
    """Render up to five provider rows as a short deterministic listing.

    Returns ``None`` when no provider rows are present so the caller can fall through
    to the gap response. Phone / address are added when present; nothing else is
    surfaced (rating + hours stay terse — Tier 1 owns those when the user asks).
    """
    provider_rows = [r for r in rows if r.get("type") == "provider"]
    if not provider_rows:
        return None
    cat_label = _pluralize_for_header(category)
    lines: list[str] = []
    for row in provider_rows[:5]:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        bits: list[str] = [name]
        addr = str(row.get("address") or "").strip()
        phone = str(row.get("phone") or "").strip()
        if addr:
            bits.append(addr)
        if phone:
            bits.append(phone)
        lines.append("• " + " — ".join(bits))
    if not lines:
        return None
    header = f"A few {cat_label} in Lake Havasu City:"
    framing = _landscape_framing_for_category(category)
    if framing:
        return framing + "\n\n" + header + "\n\n" + "\n".join(lines)
    return header + "\n\n" + "\n".join(lines)
