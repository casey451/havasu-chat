from __future__ import annotations

import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time as time_type, timedelta
from typing import Any, Literal

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.core.conversation_copy import (
    LISTING_NUDGE_ACTIVITY_SET,
    LISTING_NUDGE_DATE_SET,
    LISTING_NUDGE_NONE,
    NO_MATCH_BROADEN,
    NO_MATCH_HONEST,
    NOTHING_FOR_ACTIVITY,
    NOTHING_IN_RANGE,
    SEARCH_INTRO_MANY,
)
from app.bootstrap_env import ensure_dotenv_loaded
from app.core.dedupe import cosine_similarity
from app.core.intent import open_ended_search_message
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.search_log import is_search_diag_verbose
from app.core.slots import extract_broaden_category, extract_search_label
from app.db.models import Event

ensure_dotenv_loaded()


_SPECIFIC_PHRASES = (
    # Water sports & races
    "boat race", "boat racing", "regatta", "poker run", "speedboat race",
    "desert storm", "jet ski", "jetski", "waverunner", "kayak", "paddleboard",
    "sup", "canoe", "jet boat", "boat tour", "sunset cruise", "fishing tournament",
    # Beaches & parks
    "london bridge beach", "rotary park", "lake havasu state park",
    "cattail cove", "sara park",
    # Land activities
    "hiking", "mountain bike", "mtb", "atv", "utv", "off-road", "dune",
    "golf tournament", "tee time", "balloon ride", "balloon festival",
    # Sightseeing
    "london bridge", "lighthouse", "english village", "museum",
    # Family / kids venues
    "trampoline", "trampoline park", "altitude", "bowling", "havasu lanes",
    "cosmic bowling", "arcade", "mini golf", "scooter's", "aquatic center",
    "swimming pool", "playground", "sunshine indoor play",
    # Dining & drinks
    "happy hour", "brewery", "distillery", "copper still", "hava bite",
    "taproom", "food truck", "farmers market", "sunset market",
    # Entertainment
    "concert", "live music", "band", "dj", "dance", "karaoke",
    "festival", "parade", "fireworks", "car show", "motorcycle",
    "bike night", "rockabilly",
    # Wellness
    "yoga", "pilates", "fitness class", "spa",
)


def _query_has_specific_noun(message: str) -> bool:
    """Detect if the user named a specific thing we should honestly report on."""
    lowered = message.lower()
    return any(p in lowered for p in _SPECIFIC_PHRASES)


def _matching_specific_phrases(text: str) -> list[str]:
    """Return which specific phrases from _SPECIFIC_PHRASES appear in text."""
    lowered = text.lower()
    return [p for p in _SPECIFIC_PHRASES if p in lowered]


SEARCH_QUERY_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_RELEVANCE_THRESHOLD = 0.35
KEYWORD_RELEVANCE_THRESHOLD = 0.35
SPECIFIC_QUERY_EMBEDDING_THRESHOLD = 0.55  # raised bar for specific-noun queries

DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

ACTIVITY_TYPES = {
    "martial_arts": ["karate", "martial", "bjj", "judo", "taekwondo", "dojo"],
    "sports": [
        "sport",
        "soccer",
        "basketball",
        "football",
        "tennis",
        "swim",
        "gym",
        "golf",
        "pickleball",
        "volleyball",
        "yoga",
        "pilates",
        "crossfit",
        "running",
        "gymnastics",
    ],
    "arts": ["art", "music", "dance", "theater", "craft", "paint"],
    "education": ["class", "workshop", "stem", "science", "coding", "math", "reading"],
    "outdoors": ["hike", "park", "trail", "camping", "outdoor"],
}

SearchStrategy = Literal[
    "RUN_BROAD",
    "RUN_FILTERED",
    "RUN_WITH_NUDGE",
    "CLARIFY_DATE",
]

NARROW_DOWN_CLOSING = (
    "\n\nWant me to narrow it down? Just tell me what you're in the mood for 👍"
)

SEARCH_ZERO = "Nothing yet! You can add one by telling me the details."

SEARCH_FEW_INTRO = "Here are your matches:"

GROUP_EMOJI = {
    "Martial Arts": "🥋",
    "Sports": "⚽",
    "Arts": "🎪",
    "Education": "📚",
    "Outdoors": "🥾",
    "General": "📌",
}


def emit_search_diag_embedding_block(
    flags_text: str,
    *,
    is_specific_query: bool,
    embedding_from_openai: bool,
    effective_threshold: float,
    with_emb: list[tuple[Any, float]],
) -> None:
    """Stdout diagnostics for embedding search; no-op unless ``SEARCH_DIAG_VERBOSE`` is set."""
    if not is_search_diag_verbose():
        return
    import sys as _sys

    _sys.stdout.flush()
    print(
        f"[search_diag] query={flags_text!r} is_specific={is_specific_query} "
        f"from_openai={embedding_from_openai} threshold={effective_threshold:.2f} "
        f"candidates={len(with_emb)}",
        flush=True,
    )
    for _ev, _sc in sorted(with_emb, key=lambda x: -x[1])[:5]:
        print(f"  [{_sc:.4f}] {_ev.title!r}", flush=True)


_WEEKDAY_LONG = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_MONTH_LONG = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# If the user names a sport/activity, do not let audience heuristics match unrelated events.
_QUERY_ACTIVITY_TOKENS = frozenset(
    {
        "soccer",
        "basketball",
        "football",
        "tennis",
        "golf",
        "pickleball",
        "volleyball",
        "baseball",
        "lacrosse",
        "hockey",
        "rugby",
        "swimming",
        "gymnastics",
        "wrestling",
        "fencing",
        "rowing",
        "cycling",
        "running",
        "marathon",
        "yoga",
        "pilates",
        "karate",
        "judo",
        "opera",
        "ballet",
        "theater",
        "theatre",
    }
)

_KEYWORD_STOP = frozenset(
    {
        "the",
        "for",
        "and",
        "with",
        "any",
        "some",
        "what",
        "when",
        "where",
        "this",
        "next",
        "that",
        "from",
        "have",
        "are",
        "you",
        "your",
        "can",
        "how",
        "about",
        "into",
        "near",
        "there",
        "looking",
        "find",
        "show",
        "tell",
        "please",
        "something",
        "things",
        "going",
        "week",
        "weekend",
        "today",
        "tomorrow",
        "kids",
        "child",
        "children",
        "year",
        "old",
        "girl",
        "boy",
    }
)

_LISTING_PHRASES_SHORT = (
    "events",
    "things to do",
    "happening",
    "whats on",
    "what's on",
    "whats going on",
    "what's going on",
    "fun",
    "activities",
)

_GENERIC_SHORT_QUERY_TERMS = frozenset(
    {
        "any",
        "this",
        "that",
        "these",
        "those",
        "week",
        "month",
        "today",
        "tonight",
        "tomorrow",
        "next",
        "in",
        "on",
        "for",
        "show",
        "event",
        "events",
        "things",
        "happening",
        "fun",
        "activities",
        "to",
        "do",
        "sports",
        "arts",
        "education",
        "outdoors",
        "classes",
        "learning",
        "kids",
        "family",
    }
)

_MULTIWORD_STRICT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "any",
        "some",
        "of",
        "in",
        "at",
        "on",
        "for",
        "this",
        "that",
        "these",
        "those",
    }
)


@dataclass(frozen=True)
class SearchOutcome:
    events: list[Event]
    suppressed_low_relevance: bool = False
    slot_filter_exhausted: bool = False
    honest_no_match: bool = False
    all_recurring: bool = False


def decide_search_strategy(
    slots: dict[str, Any],
    listing_mode: bool,
    message: str,
) -> SearchStrategy:
    if listing_mode:
        return "RUN_BROAD"

    has_date = slots.get("date_range") is not None
    has_act = bool(slots.get("activity_family"))
    has_aud = bool(slots.get("audience"))
    has_loc = bool((slots.get("location_hint") or "").strip())

    if has_date and has_act:
        return "RUN_FILTERED"
    if has_date and has_aud and not has_act:
        return "RUN_WITH_NUDGE"
    if has_date and not has_act and not has_aud and not has_loc:
        return "RUN_WITH_NUDGE"
    if has_act and not has_date:
        return "RUN_WITH_NUDGE"
    if has_aud and not has_date and not has_act:
        return "RUN_WITH_NUDGE"
    if has_loc:
        return "RUN_WITH_NUDGE"

    if not has_date and not has_act and not has_aud and not has_loc:
        if open_ended_search_message(message):
            return "CLARIFY_DATE"
        return "RUN_WITH_NUDGE"

    return "RUN_WITH_NUDGE"


def generate_query_embedding_with_source(text: str) -> tuple[list[float], bool]:
    """Returns (vector, True) when OpenAI returned the embedding; else deterministic path (False)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
            response = client.embeddings.create(model=SEARCH_QUERY_EMBEDDING_MODEL, input=text.strip() or " ")
            return list(response.data[0].embedding), True
        except Exception:
            pass
    return _deterministic_embedding_1536(text), False


def generate_query_embedding(text: str) -> list[float]:
    return generate_query_embedding_with_source(text)[0]


def _deterministic_embedding_1536(text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    vector = [0.0] * 1536
    for token in tokens:
        h = hash(token)
        for i in range(16):
            idx = (h + i * 7919) % 1536
            vector[idx] += 1.0 / (i + 1)
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        return vector
    return [v / magnitude for v in vector]


def _base_future_events_query(db: Session, date_context: dict[str, date] | None) -> Any:
    today = date.today()
    query = db.query(Event).filter(Event.date >= today)
    if date_context:
        query = query.filter(and_(Event.date >= date_context["start"], Event.date <= date_context["end"]))
    return query


def _time_scoped_date(date_context: dict[str, date] | None) -> bool:
    return date_context is not None


def _apply_time_scoped_merged_sort(merged: list[tuple[Event, float]], time_scoped: bool) -> None:
    if time_scoped:
        merged.sort(
            key=lambda x: (x[0].is_recurring, -x[1], x[0].date, x[0].start_time),
        )
    else:
        merged.sort(key=lambda x: (-x[1], x[0].date, x[0].start_time))


def search_events_keyword_only(
    db: Session,
    date_context: dict[str, date] | None,
    activity_type: str | None,
    keywords: list[str],
) -> list[Event]:
    query = _base_future_events_query(db, date_context)
    text_terms = _unique_terms(list(keywords))
    for term in text_terms:
        like_term = f"%{term}%"
        query = query.filter(
            or_(
                func.lower(Event.title).like(like_term),
                func.lower(Event.description).like(like_term),
                func.lower(Event.location_name).like(like_term),
            )
        )
    if _time_scoped_date(date_context):
        query = query.order_by(
            Event.is_recurring.asc(),
            Event.date.asc(),
            Event.start_time.asc(),
        )
    else:
        query = query.order_by(Event.date.asc(), Event.start_time.asc())
    return query.all()


def _query_tokens(text: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 2 and t not in _KEYWORD_STOP
    ]


def _keyword_score_and_fields(
    query_text: str,
    event: Event,
    *,
    audience_hint: str | None = None,
) -> tuple[float, int]:
    tokens = _query_tokens(query_text)
    title = (event.title or "").lower()
    desc = (event.description or "").lower()
    tags = " ".join(str(t).lower() for t in (event.tags or []))
    fields = (title, desc, tags)
    blob_all = f"{title} {desc} {tags}"
    activity_terms = [t for t in tokens if t in _QUERY_ACTIVITY_TOKENS]
    if activity_terms and not any(t in blob_all for t in activity_terms):
        return (0.0, 0)
    fields_hit = 0
    matched = 0
    if tokens:
        for blob in fields:
            if any(tok in blob for tok in tokens):
                fields_hit += 1
        matched = sum(1 for tok in tokens if any(tok in f for f in fields))
        score = matched / len(tokens)
    else:
        score = 0.0

    if audience_hint == "kids" and any(
        k in blob_all for k in ("kid", "child", "youth", "teen", "family", "tween", "student")
    ):
        fields_hit = max(fields_hit, 1)
        score = max(score, KEYWORD_RELEVANCE_THRESHOLD)
    elif audience_hint == "adults" and ("adult" in blob_all or "21+" in blob_all):
        fields_hit = max(fields_hit, 1)
        score = max(score, KEYWORD_RELEVANCE_THRESHOLD)
    elif audience_hint == "family" and "family" in blob_all:
        fields_hit = max(fields_hit, 1)
        score = max(score, KEYWORD_RELEVANCE_THRESHOLD)

    return (score, fields_hit)


def _keyword_passes_threshold(
    query_text: str,
    event: Event,
    strict: bool,
    *,
    audience_hint: str | None = None,
) -> tuple[float, bool]:
    score, fields_hit = _keyword_score_and_fields(query_text, event, audience_hint=audience_hint)
    if fields_hit < 1:
        return (score, False)
    if strict and score < KEYWORD_RELEVANCE_THRESHOLD:
        return (score, False)
    return (score, True)


def search_events(
    db: Session,
    date_context: dict[str, date] | None,
    activity_type: str | None,
    keywords: list[str],
    query_message: str = "",
    *,
    strict_relevance: bool = True,
    audience_hint: str | None = None,
    flags_query: str | None = None,
) -> SearchOutcome:
    """Semantic + keyword search. When strict_relevance is True, apply relevance cutoffs.

    ``query_message`` may include synonym expansion for embeddings; ``flags_query`` should be the
    user's raw words (no expansion) so short-query and literal rules stay aligned with what they typed.
    """
    embedding_source = query_message.strip() or " ".join(keywords) or activity_type or "events"
    flags_text = (flags_query or query_message).strip() or embedding_source
    query_embedding, embedding_from_openai = generate_query_embedding_with_source(embedding_source)
    dim = len(query_embedding)

    is_specific_query = _query_has_specific_noun(flags_text)
    effective_threshold = SPECIFIC_QUERY_EMBEDDING_THRESHOLD if is_specific_query else EMBEDDING_RELEVANCE_THRESHOLD
    short_noun_focused = _is_short_noun_focused_query(flags_text)
    literal_terms = _literal_match_terms(flags_text) if short_noun_focused else set()
    require_literal_match = short_noun_focused and bool(literal_terms)

    base_q = _base_future_events_query(db, date_context)
    pre_activity: list[Event] = base_q.all()
    candidates = list(pre_activity)

    if activity_type:
        terms = ACTIVITY_TYPES.get(activity_type, [])
        if terms:
            candidates = [e for e in candidates if any(t in f"{e.title} {e.description}".lower() for t in terms)]

    if activity_type and not candidates and pre_activity:
        return SearchOutcome(
            [],
            suppressed_low_relevance=False,
            slot_filter_exhausted=True,
            honest_no_match=False,
            all_recurring=False,
        )

    pre_literal_candidates = list(candidates)
    literal_matched_ids: set[str] = set()
    if require_literal_match:
        candidates = [e for e in candidates if _event_matches_literal_query(e, literal_terms, flags_text)]
        literal_matched_ids = {e.id for e in candidates}

    with_emb: list[tuple[Event, float]] = []
    without_emb: list[Event] = []

    for event in candidates:
        emb = event.embedding
        if emb and len(emb) == dim:
            score = cosine_similarity(query_embedding, emb)
            with_emb.append((event, score))
        else:
            without_emb.append(event)

    if is_specific_query and with_emb:
        from app.core.slots import expand_query_synonyms as _expand_synonyms
        bonus_terms = _matching_specific_phrases(flags_text) + _expand_synonyms(flags_text)
        with_emb = [
            (
                e,
                s + 0.5
                if any(t in f"{e.title or ''} {e.description or ''}".lower() for t in bonus_terms)
                else s,
            )
            for e, s in with_emb
        ]

    emit_search_diag_embedding_block(
        flags_text,
        is_specific_query=is_specific_query,
        embedding_from_openai=embedding_from_openai,
        effective_threshold=effective_threshold,
        with_emb=with_emb,
    )

    # Apply threshold filter.
    # For real OpenAI embeddings use the computed threshold; for fallback (fake) embeddings
    # still apply filtering when the query is specific — keep only events that received the
    # +0.5 literal-match bonus (score > 0.45) so junk near-zero cosines are suppressed.
    if strict_relevance and with_emb:
        literal_id_set = literal_matched_ids if require_literal_match else set()
        if embedding_from_openai:
            non_literal_with_emb = [(e, s) for e, s in with_emb if e.id not in literal_id_set]
            best = max(s for _, s in non_literal_with_emb) if non_literal_with_emb else float("-inf")
            if best < effective_threshold:
                with_emb = [(e, s) for e, s in with_emb if e.id in literal_id_set]
            else:
                with_emb = [
                    (e, s)
                    for e, s in with_emb
                    if s >= effective_threshold or e.id in literal_id_set
                ]
        elif is_specific_query:
            with_emb = [
                (e, s)
                for e, s in with_emb
                if s > 0.45 or e.id in literal_id_set
            ]

    with_emb.sort(key=lambda x: (-x[1], x[0].date, x[0].start_time))
    emb_scores: dict[str, float] = {e.id: s for e, s in with_emb}
    embedded_events = [e for e, _ in with_emb]

    text_terms = _unique_terms(list(keywords))
    keyword_rows: list[tuple[Event, float]] = []
    if strict_relevance:
        for e in without_emb:
            if text_terms and not _event_matches_keyword_terms(e, text_terms):
                continue
            if require_literal_match and e.id in literal_matched_ids:
                keyword_rows.append((e, KEYWORD_RELEVANCE_THRESHOLD))
                continue
            score, ok = _keyword_passes_threshold(flags_text, e, True, audience_hint=audience_hint)
            if not ok:
                continue
            keyword_rows.append((e, score))
    else:
        for e in without_emb:
            keyword_rows.append((e, 0.0))

    keyword_rows.sort(key=lambda x: (-x[1], x[0].date, x[0].start_time))

    merged: list[tuple[Event, float]] = []
    seen: set[str] = set()
    for e in embedded_events:
        merged.append((e, emb_scores[e.id]))
        seen.add(e.id)
    for e, s in keyword_rows:
        if e.id not in seen:
            merged.append((e, s))
            seen.add(e.id)

    time_scoped = _time_scoped_date(date_context)
    _apply_time_scoped_merged_sort(merged, time_scoped)
    out_events = [e for e, _ in merged]

    from app.core import search_log as _sl

    _sl.log_candidates(flags_text, merged)

    suppressed = False
    if strict_relevance and embedding_from_openai and not out_events and candidates:
        had_emb_scores = [
            cosine_similarity(query_embedding, e.embedding)
            for e in candidates
            if e.embedding and len(e.embedding) == dim
        ]
        if had_emb_scores and max(had_emb_scores) < effective_threshold:
            suppressed = True
        elif not had_emb_scores and without_emb:
            best_kw = max(
                (_keyword_score_and_fields(flags_text, e, audience_hint=audience_hint)[0] for e in without_emb),
                default=0.0,
            )
            if best_kw < KEYWORD_RELEVANCE_THRESHOLD:
                suppressed = True

    honest_no_match = (
        strict_relevance
        and not out_events
        and bool(pre_literal_candidates if require_literal_match else candidates)
        and (
            any(t in _QUERY_ACTIVITY_TOKENS for t in _query_tokens(flags_text))
            or _query_has_specific_noun(flags_text)
            or require_literal_match
        )
    )

    all_recurring = (
        time_scoped
        and bool(out_events)
        and all(getattr(e, "is_recurring", False) for e in out_events)
    )

    return SearchOutcome(
        out_events,
        suppressed_low_relevance=suppressed,
        slot_filter_exhausted=False,
        honest_no_match=honest_no_match,
        all_recurring=all_recurring,
    )


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _event_matches_keyword_terms(event: Event, text_terms: list[str]) -> bool:
    if not text_terms:
        return True
    blob = f"{event.title} {event.description} {event.location_name}".lower()
    return all(term in blob for term in text_terms)


def _is_short_noun_focused_query(query_text: str) -> bool:
    lowered = query_text.lower().strip()
    if any(phrase in lowered for phrase in _LISTING_PHRASES_SHORT):
        return False
    words = re.findall(r"[a-z0-9']+", lowered)
    return 1 <= len(words) <= 2


def _literal_match_terms(query_text: str) -> set[str]:
    from app.core.slots import QUERY_SYNONYMS

    lowered = query_text.lower()
    terms: set[str] = set()
    terms.update(_matching_specific_phrases(lowered))

    for token in re.findall(r"[a-z0-9]+", lowered):
        if token not in _GENERIC_SHORT_QUERY_TERMS:
            terms.add(token)

    for key, syns in QUERY_SYNONYMS.items():
        group = [key, *syns]
        group_matches = any(_contains_term_boundary(lowered, term) for term in group)
        if group_matches:
            for term in group:
                clean = term.lower().strip()
                if clean and clean not in _GENERIC_SHORT_QUERY_TERMS:
                    terms.add(clean)
    return terms


def _query_required_tokens(query_text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", query_text.lower())
    return [t for t in tokens if t not in _MULTIWORD_STRICT_STOPWORDS]


def _event_matches_literal_query(event: Event, terms: set[str], query_text: str) -> bool:
    if not terms:
        return False
    blob = f"{event.title or ''} {event.description or ''} {' '.join(str(t) for t in (event.tags or []))}".lower()
    required = _query_required_tokens(query_text)
    ql = query_text.lower().strip()
    if len(required) >= 2:
        if _contains_term_boundary(blob, ql):
            return True
        if all(_contains_term_boundary(blob, token) for token in required):
            return True
        # Multi-word QUERY_SYNONYMS keys (e.g. "boat race"): the event may use synonym
        # phrases ("poker run") or stems ("boats", "racing") instead of raw tokens "boat"+"race".
        # Only apply for keys that appear in the query so single-word keys like "brewery" cannot
        # widen "brewery tour" via unrelated multi-word synonyms.
        from app.core.slots import QUERY_SYNONYMS as _QS

        for key, syns in _QS.items():
            if " " not in key.strip():
                continue
            if not _contains_term_boundary(ql, key):
                continue
            for phrase in (key, *syns):
                p = phrase.strip().lower()
                if " " in p and _contains_term_boundary(blob, p):
                    return True
        return False
    return any(_contains_term_boundary(blob, term) for term in terms)


def _contains_term_boundary(text: str, term: str) -> bool:
    clean = term.strip().lower()
    if not clean:
        return False
    if " " in clean:
        pattern = rf"(?<!\w){re.escape(clean)}(?!\w)"
    else:
        pattern = rf"\b{re.escape(clean)}\b"
    return re.search(pattern, text) is not None


def _format_long_date(d: date) -> str:
    return f"{_WEEKDAY_LONG[d.weekday()]}, {_MONTH_LONG[d.month]} {d.day}"


def _format_time_ampm(t: time_type) -> str:
    h24 = t.hour
    ampm = "AM" if h24 < 12 else "PM"
    h12 = h24 % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{t.minute:02d} {ampm}"


def _truncate_desc(text: str, limit: int = 120) -> str:
    cleaned = (text or "").replace("\n", " ").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _event_card(event: Event) -> str:
    desc = _truncate_desc(event.description or "")
    when = f"{_format_long_date(event.date)} · {_format_time_ampm(event.start_time)}"
    lines = [
        f"📅 {when}",
        f"📍 {event.location_name}",
        f"{event.title}",
        "",
        desc,
    ]
    url = (getattr(event, "event_url", None) or "").strip()
    if url:
        lines.append(f"🔗 {url}")
    cn = (event.contact_name or "").strip() if event.contact_name else ""
    cp = (event.contact_phone or "").strip() if event.contact_phone else ""
    if cn or cp:
        bits = " • ".join(x for x in (cn, cp) if x)
        lines.append(f"📞 {bits}")
    return "\n".join(lines)


def _group_heading(category: str) -> str:
    emoji = GROUP_EMOJI.get(category, "📌")
    if category == "Arts":
        return f"{emoji} Fun Activities"
    if category == "Education":
        return f"{emoji} Learning & Classes"
    return f"{emoji} {category}"


def _classify_event_type(event: Event) -> str:
    text = f"{event.title} {event.description}".lower()
    order = ["martial_arts", "sports", "arts", "education", "outdoors"]
    for key in order:
        terms = ACTIVITY_TYPES[key]
        if any(term in text for term in terms):
            return key.replace("_", " ").title()
    return "General"


def _empty_message_for_slots(slots: dict[str, Any], strategy: SearchStrategy) -> str:
    if slots.get("date_range") and not slots.get("activity_family"):
        return NOTHING_IN_RANGE
    if slots.get("activity_family") and not slots.get("date_range"):
        fam = slots["activity_family"].replace("_", " ")
        return NOTHING_FOR_ACTIVITY.format(activity=fam)
    return SEARCH_ZERO


def _honest_no_match_body(message: str, slots: dict[str, Any]) -> str:
    label = extract_search_label(message, slots)
    body = NO_MATCH_HONEST.format(label=label)
    cat = extract_broaden_category(slots)
    if cat:
        body += "\n\n" + NO_MATCH_BROADEN.format(category=cat)
    return body


def format_search_results(
    events: list[Event],
    strategy: SearchStrategy,
    slots: dict[str, Any],
    *,
    append_narrow_hint: bool | None = None,
    message: str = "",
    outcome: SearchOutcome | None = None,
) -> str:
    if not events:
        if outcome and (
            outcome.suppressed_low_relevance
            or outcome.slot_filter_exhausted
            or outcome.honest_no_match
        ):
            return _honest_no_match_body(message, slots)
        return _empty_message_for_slots(slots, strategy)

    nudge_line = ""
    if strategy == "RUN_WITH_NUDGE":
        if slots.get("date_range") and not slots.get("activity_family"):
            nudge_line = LISTING_NUDGE_DATE_SET
        elif slots.get("activity_family") and not slots.get("date_range"):
            nudge_line = LISTING_NUDGE_ACTIVITY_SET
        else:
            nudge_line = LISTING_NUDGE_NONE

    display_events = events
    more_note = ""
    if len(events) > 8:
        display_events = events[:8]
        more_note = f"\n\n…and {len(events) - 8} more — tell me a day or vibe to narrow."

    if len(display_events) == 1:
        e = display_events[0]
        body = f"Found one that might work:\n\n{_event_card(e)}"
        if nudge_line:
            body += f"\n\n{nudge_line}"
        return body

    if len(display_events) <= 3:
        parts = [SEARCH_FEW_INTRO, ""]
        for i, e in enumerate(display_events, start=1):
            parts.append(f"{i}.")
            parts.append(_event_card(e))
            parts.append("")
        body = "\n".join(parts).rstrip()
        if nudge_line:
            body += f"\n\n{nudge_line}"
        return body

    grouped: dict[str, list[Event]] = defaultdict(list)
    for event in display_events:
        grouped[_classify_event_type(event)].append(event)

    lines = [SEARCH_INTRO_MANY, ""]
    for group_name in sorted(grouped.keys(), key=lambda g: (g != "General", g)):
        group_events = grouped[group_name]
        lines.append(_group_heading(group_name))
        for event in group_events:
            lines.append(_event_card(event))
            lines.append("")
    body = "\n".join(lines).rstrip()
    use_narrow = append_narrow_hint if append_narrow_hint is not None else len(events) >= 4
    if use_narrow:
        body += NARROW_DOWN_CLOSING
    if more_note:
        body += more_note
    elif nudge_line and len(display_events) >= 4:
        body += f"\n\n{nudge_line}"
    return body


def format_results(events: list[Event], *, append_narrow_hint: bool | None = None) -> str:
    """Tests / callers: format with default strategy."""
    return format_search_results(
        events,
        "RUN_FILTERED",
        {},
        append_narrow_hint=append_narrow_hint,
        outcome=None,
    )


def apply_audience_location_filters(
    events: list[Event],
    audience: str | None,
    location_hint: str | None,
) -> list[Event]:
    out = list(events)
    if location_hint:
        h = location_hint.lower()
        loc_filtered = [e for e in out if h in (e.location_name or "").lower()]
        if loc_filtered:
            out = loc_filtered
    if audience == "kids":
        keys = ("kid", "child", "youth", "teen", "family", "student")
        aud_filtered = [e for e in out if any(k in f"{e.title} {e.description}".lower() for k in keys)]
        if aud_filtered:
            out = aud_filtered
    elif audience == "adults":
        aud_filtered = [
            e
            for e in out
            if "adult" in f"{e.title} {e.description}".lower() or "21" in f"{e.title} {e.description}"
        ]
        if aud_filtered:
            out = aud_filtered
    elif audience == "family":
        aud_filtered = [e for e in out if "family" in f"{e.title} {e.description}".lower()]
        if aud_filtered:
            out = aud_filtered
    return out


def _next_weekday(start_date: date, weekday: int, allow_today: bool) -> date:
    days_ahead = (weekday - start_date.weekday()) % 7
    if days_ahead == 0 and not allow_today:
        days_ahead = 7
    return start_date + timedelta(days=days_ahead)
