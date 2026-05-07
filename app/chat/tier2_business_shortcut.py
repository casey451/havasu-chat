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
    r"where\s+can\s+i\s+(?:find|get)\s+(?:a|an|some\s+)?|"
    r"where(?:'s|\s+is|\s+are)\s+(?:a|an|some\s+)?|"
    r"find\s+(?:me\s+)?(?:a|an|some\s+)?|"
    r"show\s+me\s+(?:a|an|some\s+)?|"
    r"give\s+me\s+(?:a|an|some\s+)?|"
    r"list\s+(?:of\s+)?(?:all\s+)?(?:the\s+)?|"
    r"any\s+(?:good\s+)?|"
    r"are\s+there\s+(?:any\s+)?(?:good\s+)?"
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
    return header + "\n\n" + "\n".join(lines)
