"""Two-stage intent classifier (Phase 2.1 — concierge handoff §3.2, §5 Phase 2).

Stage 1: mode ∈ ask | contribute | correct | chat (regex + keyword heuristics).
Stage 2: sub-intent within mode. Ask Tier-1-aligned sub-intents come from
``tier1_templates.INTENT_PATTERNS`` (first match wins; do not duplicate those
regexes). Additional ask sub-intents use separate heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.chat.entity_matcher import CANONICAL_EXTRAS, match_entity_with_rows
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
)

_CONTRIBUTE_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(there is a|there is an)\b"),
    re.compile(r"\bthere is a\b.+\b(happening|scheduled|this weekend|on saturday|on sunday|on friday)\b"),
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
    r"\b(open now|open right now|currently open|open at the moment|are you open now|is it open now)\b",
    re.IGNORECASE,
)

_BUSINESS_CONTRIBUTE = re.compile(
    r"\b(address|phone number|hours|corner of|suite|storefront|shop|retail|"
    r"we are open|call us at|located at)\b",
    re.IGNORECASE,
)

_PROGRAM_CONTRIBUTE = re.compile(
    r"\b(weekly|ages?\s+\d|age group|class schedule|enrollment|sign up for|"
    r"lessons every|sessions every|program runs)\b",
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

    conf = _merge_confidence(mode_conf, sub_conf, entity_score)
    if mode == "ask" and sub == "OPEN_ENDED" and conf < 0.4:
        conf = 0.42

    return IntentResult(
        mode=mode,
        sub_intent=sub,
        confidence=round(conf, 3),
        entity=entity,
        raw_query=raw,
        normalized_query=nq,
    )
