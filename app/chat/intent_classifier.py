"""Two-stage intent classifier (Phase 2.1 — concierge handoff §3.2, §5 Phase 2).

Stage 1: mode ∈ ask | contribute | correct | chat (regex + keyword heuristics).
Stage 2: sub-intent within mode. Ask Tier-1-aligned sub-intents come from
``tier1_templates.INTENT_PATTERNS`` (first match wins; do not duplicate those
regexes). Additional ask sub-intents use separate heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.chat.entity_intent import detect_multi_domain_category_slugs
from app.chat.entity_matcher import CANONICAL_EXTRAS, match_entity_with_rows
from app.chat.intents.dicts import parse_age_band
from app.chat.normalizer import normalize
from app.chat.tier1_templates import INTENT_PATTERNS
from app.core.intent import detect_out_of_scope_category
from app.core.slots import extract_date_range

_ENTITY_NAMES: tuple[str, ...] = tuple(sorted(CANONICAL_EXTRAS.keys()))

# --- Stage 1: mode heuristics (patterns not copied from tier1_templates) ---

_CORRECT_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(actually it is|actually it's|actually it is)\b"),
    re.compile(r"\b(that is wrong|that's wrong|that is incorrect|that's incorrect)\b"),
    re.compile(r"\b(is not at|isn't at|not at that address)\b"),
    re.compile(r"\b(moved to|changed to|relocated to)\b"),
    re.compile(r"\b(now it is|now it's)\b"),
    re.compile(r"\bused to be\b"),
    re.compile(r"\b(you have the wrong|wrong phone|wrong address|wrong time)\b"),
    re.compile(r"\bthe (phone|address|time|date|location|hours|website)\b.+\bis actually\b"),
    # Slice F (post-shadow): "their hours/address/phone are now X" — third-person
    # corrections that don't trip "now it is" / "actually it's".
    re.compile(r"\btheir\s+\w+\s+(?:is|are)\s+now\b"),
    re.compile(r"\b(?:hours|address|phone|website|location)\s+(?:is|are)\s+now\b"),
)

_CONTRIBUTE_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(there is a|there is an)\b"),
    re.compile(
        r"\bthere is a\b.+\b(happening|scheduled|this weekend|on saturday|on sunday|on friday)\b"
    ),
    re.compile(r"\b(just opened|grand opening)\b"),
    re.compile(r"\bnew event\b"),
    re.compile(r"\b(i want to add|want to add|need to add|going to add)\b"),
    re.compile(r"\bput in a\b"),
    re.compile(r"\b(post an event|submit an event|submit this event)\b"),
    re.compile(r"\bi have a .+ to add\b"),
    re.compile(r"\b(adding a|adding an|adding my|adding the)\b"),
    re.compile(r"^\s*new business\b"),
    re.compile(r"^\s*new program\b"),
    re.compile(r"\badding weekly\b"),
    re.compile(r"^\s*adding karate\b"),
    re.compile(r"\bnew youth program\b"),
    re.compile(r"\bwe are having\b"),
    re.compile(r"\b(i am hosting|hosting a)\b"),
)

_GREETING_ONLY = re.compile(
    r"^\s*(hi|hey|hello|howdy|good morning|good afternoon|good evening|what is up|sup)\b"
    r"([\s,!.]*)(there|you|everyone|team)?[\s,!.]*$",
    re.IGNORECASE,
)

_REAL_ESTATE_CHAT = re.compile(
    r"\b(buy a house|buying a house|buy a home|sell my house|sell our house|real estate|realtor|mortgage|"
    r"home prices|list my home)\b",
    re.IGNORECASE,
)

_SMALL_TALK = re.compile(
    r"^\s*(thanks|thank you|thx|ty|appreciate it|much appreciated|how are you|how is it going|"
    r"you are the best|you rock|bye|goodbye|good night|goodnight)\b[\s,!.]*$",
    re.IGNORECASE,
)

_NEXT_OCCURRENCE = re.compile(
    r"\b(when is the next|when's the next|when is the upcoming|next occurrence of)\b|"
    r"\bnext\s+(bmx|race|class|session|game|event|meet|meeting|show|concert|fireworks)\b",
    re.IGNORECASE,
)

# Narrow list-by-category: avoid stealing Tier-1 "what time / when / how much / age" lookups.
_LIST_BY_CATEGORY = re.compile(
    r"\b(any good|show me all|list every|find me all)\b.+\b(leagues|classes|programs|lessons)\b|"
    r"\b(what|any)\b.+\b(leagues)\b.+\b(in|around|near|for)\b|"
    r"\bprograms for\b.+\b(kids|toddlers|teens|children|families)\b|"
    r"\bactivities for kids\b|"
    r"\blist of\b.+\b(classes|programs|lessons)\b|"
    r"\bfind\b.+\b(karate|soccer|swim|tennis|basketball|gymnastics)\b.+\b(classes|programs|lessons|leagues)\b|"
    r"\bwhat\b.+\b(soccer|basketball|tennis|swim)\b.+\b(leagues)\b|"
    r"\bwhat\b.+\b(programs|classes)\b.+\b(exist|available|here|in town|in havasu)\b",
    re.IGNORECASE,
)

_OPEN_NOW_DISAMBIG = re.compile(
    # Slice F4: widen so bare "is X open" / "open today" / "open tonight" route to
    # OPEN_NOW (compute current state) rather than HOURS_LOOKUP (full-week dump).
    # Two anchored constraints keep this from over-matching:
    # - bare "is X open" must START the query (so "what hour is X open" stays HOURS_LOOKUP).
    # - bare "is X open" must END the query (so "is X open late on friday" stays HOURS_LOOKUP).
    # Voice-battery 2026-05-07: added "can I go to/visit X right now" — the user
    # is asking about current accessibility, not full-week hours. Requires both
    # the visit-action verb and "right now"/"now" to avoid promoting future-day
    # queries ("can I visit X next Tuesday") to OPEN_NOW.
    r"(?:"
    r"\bopen now\b|\bopen right now\b|\bcurrently open\b|\bopen at the moment\b|"
    r"\bare you open(?:\s+now)?\b|\bis it open(?:\s+now)?\b|"
    r"^is\s+\w+(?:\s+\w+){0,4}\s+open\s*$|"
    r"\bopen today\b|\bopen tonight\b|"
    r"\bcan\s+i\s+(?:go\s+to|visit|stop\s+by|drop\s+by|head\s+(?:to|over))\b.*\b(?:right\s+now|now)\b"
    r")",
    re.IGNORECASE,
)

_BUSINESS_CONTRIBUTE = re.compile(
    r"\b(address|phone number|hours|corner of|suite|storefront|shop|retail|"
    r"we are open|call us at|located at)\b",
    re.IGNORECASE,
)

# Stream B (2026-05-07) — common business-shape nouns. Without this, "adding a new
# yoga studio on swanson" falls through to NEW_EVENT (default branch) because the
# message has no day/time and no _BUSINESS_CONTRIBUTE keyword.
_BUSINESS_NOUNS = re.compile(
    r"\b(studio|salon|spa|cafe|coffee shop|restaurant|bar|brewery|pub|gym|"
    r"market|store|boutique|bakery|grill|kitchen|truck|food truck|barber|barbershop)\b",
    re.IGNORECASE,
)

# Stream B — URL/domain marker for sub_intent suffix. Loose match: full URLs and
# bare domains. False-negative is fine (template falls back to NO_URL).
_URL_MARKER = re.compile(
    r"(https?://\S+)"
    r"|(\b[\w-]+\.(?:com|net|org|gov|io|co|us|biz|info)(?:/\S*)?\b)",
    re.IGNORECASE,
)

_PROGRAM_CONTRIBUTE = re.compile(
    r"\b(weekly|ages?\s+\d|age group|class schedule|enrollment|sign up for|"
    r"lessons every|sessions every|program runs)\b",
    re.IGNORECASE,
)

# Backlog #43 — urgent-phrasing detector. Routes "right now" / "urgent" / "ASAP"
# / "emergency" / "immediately" / "right away" / "right this [minute]" queries
# to URGENT_NOW so disclosure_render.select_placement_regime can map them to
# EMERGENCY_URGENT instead of falling through OPEN_ENDED → SPECIFIC_QUALITY
# (which suppresses sponsored on what should be a high-stakes query).
_URGENT_NOW = re.compile(
    r"\b(?:"
    r"right\s+now|urgent|asap|emergency|immediately|right\s+away|"
    r"right\s+this(?:\s+(?:minute|second|instant))?"
    r")\b",
    re.IGNORECASE,
)

# 2026-06-07 (USE_INTENT_LAYER follow-up). A kids/age-band activity browse like
# "what activities can my 8 year old do after school hours" carries an incidental
# "hours" token ("after school hours") that the HOURS_LOOKUP regex matches. Since
# HOURS_LOOKUP is in the intent layer's entity-factual deferral set, the turn
# dies in the gap template instead of reaching kids_lessons. These two patterns
# detect the browse shape so :func:`classify` can keep that incidental "hours"
# from claiming HOURS_LOOKUP when no entity resolved.
_KIDS_ACTIVITY_BROWSE_RE = re.compile(
    r"\b(activities|activity|after[\s-]?school|classes|class|programs?|lessons?)\b",
    re.IGNORECASE,
)
_KID_TOKEN_RE = re.compile(
    r"\b(kid|kids|child|children|youth|toddler|toddlers|teen|teens)\b",
    re.IGNORECASE,
)


def _count_correct_hits(nq: str) -> int:
    return sum(1 for p in _CORRECT_MARKERS if p.search(nq))


def _count_contribute_hits(nq: str) -> int:
    return sum(1 for p in _CONTRIBUTE_MARKERS if p.search(nq))


def _mode_and_base_confidence(raw: str, nq: str) -> tuple[str, float, str | None]:
    """Return (mode, confidence, chat_sub_hint).

    ``chat_sub_hint`` is GREETING | SMALL_TALK when mode is chat; else None.
    """
    if not nq:
        return "ask", 0.4, None

    c_hits = _count_correct_hits(nq)
    co_hits = _count_contribute_hits(nq)

    if c_hits >= 2:
        return "correct", 1.0, None
    if c_hits == 1:
        return "correct", 0.85, None

    if co_hits >= 2:
        return "contribute", 0.95, None
    if co_hits == 1:
        return "contribute", 0.8, None

    if _GREETING_ONLY.match(nq) and "?" not in raw:
        return "chat", 0.9, "GREETING"

    if _SMALL_TALK.match(nq):
        return "chat", 0.85, "SMALL_TALK"

    if _REAL_ESTATE_CHAT.search(nq):
        return "chat", 0.9, "OUT_OF_SCOPE"

    if detect_out_of_scope_category(raw) is not None:
        return "chat", 0.88, "OUT_OF_SCOPE"

    return "ask", 0.72, None


def _ask_sub_intent(nq: str) -> tuple[str, float]:
    """Stage 2 for ask mode. Tier-1 regexes first, then list/next heuristics."""
    if _NEXT_OCCURRENCE.search(nq):
        return "NEXT_OCCURRENCE", 0.78

    for intent_name, pattern in INTENT_PATTERNS:
        if pattern.search(nq):
            if intent_name == "HOURS_LOOKUP" and _OPEN_NOW_DISAMBIG.search(nq):
                return "OPEN_NOW", 0.82
            return intent_name, 0.88

    if _LIST_BY_CATEGORY.search(nq):
        return "LIST_BY_CATEGORY", 0.75

    if _OPEN_NOW_DISAMBIG.search(nq):
        return "OPEN_NOW", 0.7

    # After the specific sub_intents but before OPEN_ENDED — so AGE_LOOKUP /
    # COST_LOOKUP / OPEN_NOW still win when both shapes match, but plain
    # urgent phrasing ("plumber, water leak right now") promotes from the
    # safe-default SPECIFIC_QUALITY into the EMERGENCY_URGENT regime.
    if _URGENT_NOW.search(nq):
        return "URGENT_NOW", 0.78

    return "OPEN_ENDED", 0.68


def _contribute_sub_intent(raw: str, nq: str) -> tuple[str, float]:
    # Headline program-intake phrasing wins over weekday/time signals.
    if (
        re.search(r"^\s*new program\b", nq)
        or re.search(r"\badding weekly\b", nq)
        or re.search(r"\bnew youth program\b", nq)
        or re.search(r"^\s*adding karate\b", nq)
    ):
        return "NEW_PROGRAM", 0.84
    # Stream B: business-shape nouns ("yoga studio", "coffee shop", "taco truck")
    # win over the weekday/time fallback — those messages typically describe a
    # venue, not a one-time event, even when they happen to mention a day.
    if _BUSINESS_NOUNS.search(nq):
        return "NEW_BUSINESS", 0.8
    if extract_date_range(raw) is not None or re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|am\b|pm\b|\d{1,2}:\d{2})\b",
        nq,
    ):
        return "NEW_EVENT", 0.82
    if _PROGRAM_CONTRIBUTE.search(nq):
        return "NEW_PROGRAM", 0.78
    if _BUSINESS_CONTRIBUTE.search(nq):
        return "NEW_BUSINESS", 0.78
    return "NEW_EVENT", 0.65


def contribute_has_url(raw: str) -> bool:
    """Stream B — URL presence on a contribute message picks WITH_URL vs NO_URL.

    Kept on the classifier (not the handler) so router observability can log
    the with/without-URL distinction without re-parsing the message.
    """
    return bool(raw and _URL_MARKER.search(raw))


def _merge_confidence(mode_conf: float, sub_conf: float, entity_score: float | None) -> float:
    base = (mode_conf + sub_conf) / 2.0
    if entity_score is not None and entity_score >= 0.9:
        return min(1.0, max(base, 0.95))
    if entity_score is not None and entity_score >= 0.75:
        return min(1.0, max(base, 0.82))
    return min(1.0, base)


@dataclass(frozen=True)
class IntentResult:
    mode: str  # 'ask' | 'contribute' | 'correct' | 'chat'
    sub_intent: str | None
    confidence: float  # 0.0 - 1.0
    entity: str | None
    raw_query: str
    normalized_query: str
    multi_domain_category_slugs: tuple[str, ...] | None = None


def classify(query: str) -> IntentResult:
    """Classify a single user utterance (no DB — entity match uses seed canonical names)."""
    raw = query.strip()
    nq = normalize(query)

    mode, mode_conf, chat_hint = _mode_and_base_confidence(raw, nq)

    sub: str | None
    sub_conf: float
    if mode == "ask":
        sub, sub_conf = _ask_sub_intent(nq)
    elif mode == "contribute":
        sub, sub_conf = _contribute_sub_intent(raw, nq)
    elif mode == "correct":
        sub, sub_conf = "CORRECTION", 0.9
    else:
        sub = chat_hint or "SMALL_TALK"
        sub_conf = 0.82

    ent_hit = match_entity_with_rows(raw, _ENTITY_NAMES)
    entity: str | None = None
    entity_score: float | None = None
    if ent_hit:
        entity, score = ent_hit
        entity_score = score / 100.0
    if mode == "ask":
        from app.chat.entity_intent import (
            is_category_open_now_listing,
            query_mentions_fake_entity_marker,
        )
        from app.chat.tier2_business_shortcut import try_business_listing_shortcut

        if query_mentions_fake_entity_marker(raw):
            entity = None
            entity_score = None
        elif sub not in (
            "PHONE_LOOKUP",
            "WEBSITE_LOOKUP",
            "HOURS_LOOKUP",
            "LOCATION_LOOKUP",
            "RATING_LOOKUP",
            "REVIEW_COUNT_LOOKUP",
            "TIME_LOOKUP",
            "OPEN_NOW",
        ) and (try_business_listing_shortcut(raw) is not None or is_category_open_now_listing(raw)):
            entity = None
            entity_score = None

        # A kids/age-band activity browse ("what activities can my 8 year old do
        # after school hours") matched HOURS_LOOKUP only on the incidental "hours"
        # in "after school hours". With no resolved entity (weak match) it is a
        # category listing, not a single-entity hours lookup -- reclassify off the
        # entity-factual sub_intent so the intent layer can route it to
        # kids_lessons. Real hours asks ("is mudshark open on sundays") carry no
        # kids/activity framing and are untouched.
        if (
            sub == "HOURS_LOOKUP"
            and entity is None
            and _KIDS_ACTIVITY_BROWSE_RE.search(nq)
            and (parse_age_band(nq) or _KID_TOKEN_RE.search(nq))
        ):
            sub, sub_conf = "LIST_BY_CATEGORY", 0.75

    conf = _merge_confidence(mode_conf, sub_conf, entity_score)
    if mode == "ask" and sub == "OPEN_ENDED" and conf < 0.4:
        conf = 0.42

    multi = detect_multi_domain_category_slugs(raw)

    return IntentResult(
        mode=mode,
        sub_intent=sub,
        confidence=round(conf, 3),
        entity=entity,
        raw_query=raw,
        normalized_query=nq,
        multi_domain_category_slugs=multi,
    )
