# Havasu Chat — search pipeline snapshot

Full copies of four modules for handoff (e.g. Claude). Re-copy from source if this drifts after edits.

## app/core/search.py

`python
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
from app.core.slots import extract_broaden_category, extract_search_label
from app.db.models import Event

ensure_dotenv_loaded()

SEARCH_QUERY_EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_RELEVANCE_THRESHOLD = 0.35
KEYWORD_RELEVANCE_THRESHOLD = 0.35

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


@dataclass(frozen=True)
class SearchOutcome:
    events: list[Event]
    suppressed_low_relevance: bool = False
    slot_filter_exhausted: bool = False
    honest_no_match: bool = False


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
            client = OpenAI(api_key=api_key)
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
    return query.order_by(Event.date.asc(), Event.start_time.asc()).all()


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
) -> SearchOutcome:
    """Semantic + keyword search. When strict_relevance is True, apply 0.35 cutoffs."""
    query_text = query_message.strip() or " ".join(keywords) or activity_type or "events"
    query_embedding, embedding_from_openai = generate_query_embedding_with_source(query_text)
    dim = len(query_embedding)

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
        )

    with_emb: list[tuple[Event, float]] = []
    without_emb: list[Event] = []

    for event in candidates:
        emb = event.embedding
        if emb and len(emb) == dim:
            score = cosine_similarity(query_embedding, emb)
            with_emb.append((event, score))
        else:
            without_emb.append(event)

    if strict_relevance and embedding_from_openai and with_emb:
        best = max(s for _, s in with_emb)
        if best < EMBEDDING_RELEVANCE_THRESHOLD:
            with_emb = []
        else:
            with_emb = [(e, s) for e, s in with_emb if s >= EMBEDDING_RELEVANCE_THRESHOLD]

    with_emb.sort(key=lambda x: (-x[1], x[0].date, x[0].start_time))
    emb_scores: dict[str, float] = {e.id: s for e, s in with_emb}
    embedded_events = [e for e, _ in with_emb]

    text_terms = _unique_terms(list(keywords))
    keyword_rows: list[tuple[Event, float]] = []
    if strict_relevance:
        for e in without_emb:
            if text_terms and not _event_matches_keyword_terms(e, text_terms):
                continue
            score, ok = _keyword_passes_threshold(query_text, e, True, audience_hint=audience_hint)
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

    merged.sort(key=lambda x: (-x[1], x[0].date, x[0].start_time))
    out_events = [e for e, _ in merged]

    suppressed = False
    if strict_relevance and embedding_from_openai and not out_events and candidates:
        had_emb_scores = [
            cosine_similarity(query_embedding, e.embedding)
            for e in candidates
            if e.embedding and len(e.embedding) == dim
        ]
        if had_emb_scores and max(had_emb_scores) < EMBEDDING_RELEVANCE_THRESHOLD:
            suppressed = True
        elif not had_emb_scores and without_emb:
            best_kw = max(
                (_keyword_score_and_fields(query_text, e, audience_hint=audience_hint)[0] for e in without_emb),
                default=0.0,
            )
            if best_kw < KEYWORD_RELEVANCE_THRESHOLD:
                suppressed = True

    honest_no_match = (
        strict_relevance
        and not out_events
        and bool(candidates)
        and any(t in _QUERY_ACTIVITY_TOKENS for t in _query_tokens(query_text))
    )

    return SearchOutcome(
        out_events,
        suppressed_low_relevance=suppressed,
        slot_filter_exhausted=False,
        honest_no_match=honest_no_match,
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
`

## app/core/intent.py

`python
from __future__ import annotations

import re
from typing import Any

from app.core.slots import extract_activity_family, extract_audience, extract_date_range

# Intent labels returned by detect_intent(message, session)
HARD_RESET = "HARD_RESET"
SOFT_CANCEL = "SOFT_CANCEL"
GREETING = "GREETING"
LISTING_INTENT = "LISTING_INTENT"
ADD_EVENT = "ADD_EVENT"
SERVICE_REQUEST = "SERVICE_REQUEST"
DEAL_SEARCH = "DEAL_SEARCH"
REFINEMENT = "REFINEMENT"
SEARCH_EVENTS = "SEARCH_EVENTS"
UNCLEAR = "UNCLEAR"

_HARD_RESET_PHRASES = (
    "start over",
    "start from scratch",
    "cancel everything",
    "wipe everything",
)

_SOFT_CANCEL_PHRASES = (
    "never mind",
    "nevermind",
    "forget it",
    "nvm",
    "actually never mind",
    "scratch that",
)

_LISTING_PHRASES = (
    "show me all",
    "show all",
    "show everything",
    "show me everything",
    "list all",
    "list everything",
    "all events",
    "all of them",
    "everything",
    "what do you have",
    "what've you got",
    "what do you got",
    "what events",
    "what's on",
    "whats on",
    "what is on",
    "what's happening",
    "whats happening",
    "what's going on",
    "whats going on",
    "in your system",
    "in the system",
)

_ADD_CREATION_MARKERS = (
    "i'm hosting",
    "im hosting",
    "we're hosting",
    "were hosting",
    "i am hosting",
    "i'm running",
    "im running",
    "we're organizing",
    "were organizing",
    "i'm teaching",
    "im teaching",
    "add an event",
    "add event",
    "post an event",
    "submit an event",
    "registering",
    "tickets at",
    "ticket link",
    "eventbrite",
    "rsvp at",
    "there's a ",
    "theres a ",
    "there is a ",
)

_SERVICE_MARKERS = (
    "plumber",
    "electrician",
    "hvac",
    "roof repair",
    "my water heater",
    "who does ",
    "i need a ",
    "is broken",
    "fix my ",
)

_DEAL_MARKERS = (
    "deal",
    "coupon",
    "specials",
    "happy hour",
    "discount",
    "promo code",
)

SINGLE_WORD_ACTIVITIES = frozenset(
    {
        "golf",
        "tennis",
        "yoga",
        "pickleball",
        "basketball",
        "bjj",
        "pilates",
        "hiking",
        "running",
        "swimming",
        "crossfit",
        "zumba",
        "barre",
        "cycling",
    }
)

GREETING_TOKENS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "hiya",
        "howdy",
        "morning",
        "evening",
        "good morning",
        "good afternoon",
        "good evening",
        "hi there",
        "hey there",
        "hello there",
    }
)

CONFIRMATION_PHRASES = ["yes", "yep", "correct", "looks good", "that's right", "thats right"]
REJECTION_PHRASES = ["no", "nope", "not quite", "incorrect", "wrong"]

SKIP_OPTIONAL_CONTACT_PHRASES = (
    "skip",
    "no thanks",
    "none",
    "n/a",
    "nothing",
    "not needed",
    "pass",
)


def _word_boundary(lowered: str, word: str) -> bool:
    return bool(re.search(rf"(^|[^a-z0-9]){re.escape(word)}([^a-z0-9]|$)", lowered))


def is_hard_reset(message: str) -> bool:
    msg = message.lower().strip()
    if any(p in msg for p in _HARD_RESET_PHRASES):
        return True
    if _word_boundary(msg, "reset"):
        return True
    return False


def is_soft_cancel(message: str) -> bool:
    msg = message.lower().strip()
    if any(p in msg for p in _SOFT_CANCEL_PHRASES):
        return True
    if _word_boundary(msg, "cancel") and "cancel everything" not in msg:
        # standalone cancel → soft unless phrased as total wipe
        return True
    return False


def is_cancel_or_restart(message: str) -> bool:
    """True for full reset (hard) or soft bail phrases."""
    return is_hard_reset(message) or is_soft_cancel(message)


def _has_time_or_date_reference(msg: str) -> bool:
    lowered = msg.lower()
    if extract_date_range(msg) is not None:
        return True
    if any(x in lowered for x in ("today", "tomorrow", "tonight", "this weekend", "next week")):
        return True
    if re.search(r"\b\d{1,2}\s*(:\d{2})?\s*(am|pm)\b", lowered):
        return True
    if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)\b", lowered):
        return True
    if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", lowered):
        return True
    if re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", lowered):
        return True
    if re.search(r"\b(at|@)\s*\d{1,2}\b", lowered):
        return True
    return False


def _add_creation_language(msg: str) -> bool:
    m = msg.lower()
    if any(marker in m for marker in _ADD_CREATION_MARKERS):
        return True
    if "http://" in m or "https://" in m:
        return True
    if re.search(r"\badd\b", m) and _has_time_or_date_reference(msg):
        return True
    return False


def _add_meta_intent_question(msg: str) -> bool:
    """How-to / permission questions about posting an event — ADD_EVENT without a date yet."""
    m = msg.lower().strip().rstrip("?!.")
    phrases = (
        "can i add an event",
        "can we add an event",
        "could i add an event",
        "how do i add an event",
        "how to add an event",
        "how can i add an event",
        "where do i add an event",
        "where can i add an event",
        "i want to add an event",
        "i'd like to add an event",
        "id like to add an event",
        "can i post an event",
        "how do i post an event",
        "could we add an event",
    )
    return any(p in m for p in phrases)


def _active_non_search_flow(session: dict[str, Any]) -> bool:
    return bool(
        session.get("partial_event")
        or session.get("awaiting_confirmation")
        or session.get("awaiting_optional_contact")
        or session.get("awaiting_missing_field")
        or session.get("awaiting_duplicate_confirmation")
        or session.get("awaiting_merge_details")
        or session.get("awaiting_review_offer")
    )


def _listing_hit(msg: str) -> bool:
    m = msg.lower()
    return any(p in m for p in _LISTING_PHRASES)


def _refinement_looks_like_filter(message: str) -> bool:
    stripped = message.lower().strip().rstrip("?").strip()
    words = stripped.split()
    if len(words) == 1 and words[0] in SINGLE_WORD_ACTIVITIES:
        return True
    if extract_date_range(message):
        return True
    if extract_activity_family(message):
        return True
    if extract_audience(message):
        return True
    if len(stripped) <= 24 and extract_activity_family(message) is None and len(words) == 1:
        return words[0] in ("sports", "arts", "kids", "family", "outdoors", "learning", "classes")
    return False


def open_ended_search_message(message: str) -> bool:
    m = message.lower().strip()
    return m in (
        "what's good?",
        "whats good?",
        "what's good",
        "whats good",
        "surprise me",
        "anything fun?",
        "anything fun",
    )


def detect_intent(message: str, session: dict[str, Any] | None = None) -> str:
    session = session or {}
    msg = message.strip()
    lowered = msg.lower()

    if is_hard_reset(msg):
        return HARD_RESET
    if is_soft_cancel(msg):
        return SOFT_CANCEL

    flow = session.get("flow") or {}
    awaiting = flow.get("awaiting")

    if is_greeting(msg) and not _listing_hit(msg) and not _active_non_search_flow(session):
        return GREETING

    if _listing_hit(msg):
        return LISTING_INTENT

    if any(s in lowered for s in _SERVICE_MARKERS):
        return SERVICE_REQUEST
    if any(s in lowered for s in _DEAL_MARKERS):
        return DEAL_SEARCH

    if _add_meta_intent_question(msg):
        return ADD_EVENT

    if awaiting == "narrow_followup" and _refinement_looks_like_filter(msg):
        return REFINEMENT

    stripped_q = lowered.rstrip("?").strip()
    words = stripped_q.split()
    if len(words) == 1 and words[0] in SINGLE_WORD_ACTIVITIES:
        return SEARCH_EVENTS

    if _add_creation_language(msg) and _has_time_or_date_reference(msg):
        return ADD_EVENT

    if _add_creation_language(msg) and not _has_time_or_date_reference(msg):
        return SEARCH_EVENTS

    if len(msg) < 3 and not _active_non_search_flow(session) and awaiting is None:
        return UNCLEAR

    return SEARCH_EVENTS


def is_confirmation(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in CONFIRMATION_PHRASES)


def is_rejection(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in REJECTION_PHRASES)


def is_skip_optional_contact(message: str) -> bool:
    msg = message.lower().strip()
    if is_rejection(message):
        return True
    return any(p in msg for p in SKIP_OPTIONAL_CONTACT_PHRASES)


def is_greeting(message: str) -> bool:
    m = message.lower().strip().rstrip("!?")
    if not m:
        return False
    if m in GREETING_TOKENS:
        return True
    parts = m.split()
    if len(parts) <= 3 and parts[0] in ("hi", "hello", "hey") and len(m) <= 32:
        return True
    return False


def escape_to_search(message: str) -> bool:
    """User abandons add flow for browsing."""
    m = message.lower()
    return any(
        x in m
        for x in (
            "just looking",
            "only looking",
            "was just looking",
            "what's on",
            "whats on",
            "show me events",
            "looking for what's on",
        )
    )
`

## app/core/slots.py

`python
"""Structured search slots extracted from user text (Phase 8.5)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, TypedDict

DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# Maps to keys used by app.core.search.ACTIVITY_TYPES
FAMILY_ALIASES: dict[str, list[str]] = {
    "martial_arts": [
        "karate",
        "martial",
        "bjj",
        "judo",
        "taekwondo",
        "dojo",
        "jiu",
    ],
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
        "baseball",
        "lacrosse",
        "yoga",
        "pilates",
        "crossfit",
        "zumba",
        "barre",
        "cycling",
        "running",
        "hiking",
        "gymnastics",
    ],
    "arts": [
        "art",
        "music",
        "dance",
        "theater",
        "theatre",
        "craft",
        "paint",
        "painting",
        "pottery",
        "choir",
        "band",
    ],
    "education": [
        "class",
        "workshop",
        "stem",
        "science",
        "coding",
        "math",
        "reading",
        "learn",
        "tutor",
        "school",
    ],
    "outdoors": [
        "hike",
        "park",
        "trail",
        "camping",
        "outdoor",
        "lake",
        "river",
        "kayak",
    ],
}


class DateRange(TypedDict):
    start: date
    end: date


def _next_weekday(start_date: date, weekday: int, allow_today: bool) -> date:
    days_ahead = (weekday - start_date.weekday()) % 7
    if days_ahead == 0 and not allow_today:
        days_ahead = 7
    return start_date + timedelta(days=days_ahead)


def extract_date_range(text: str) -> DateRange | None:
    lowered = text.lower()
    today = date.today()

    if "today" in lowered:
        return {"start": today, "end": today}
    if "tomorrow" in lowered:
        t = today + timedelta(days=1)
        return {"start": t, "end": t}

    if "this weekend" in lowered:
        saturday = _next_weekday(today, 5, allow_today=True)
        sunday = saturday + timedelta(days=1)
        return {"start": saturday, "end": sunday}

    if "next week" in lowered:
        monday = _next_weekday(today, 0, allow_today=False)
        if monday <= today:
            monday += timedelta(days=7)
        return {"start": monday, "end": monday + timedelta(days=6)}

    for day_name, weekday in DAY_NAMES.items():
        if day_name in lowered:
            target = _next_weekday(today, weekday, allow_today=True)
            return {"start": target, "end": target}

    # "Saturday at 9" style — weekday already caught
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lowered)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            target = date(y, mo, d)
            if target >= today:
                return {"start": target, "end": target}
        except ValueError:
            pass

    return None


def _term_matches_in_text(lowered: str, term: str) -> bool:
    """Avoid false positives (e.g. 'gym' matching inside 'gymnastics')."""
    if len(term) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered))
    return term in lowered


def extract_activity_family(text: str) -> str | None:
    lowered = text.lower()
    order = ["martial_arts", "sports", "arts", "education", "outdoors"]
    for key in order:
        for term in FAMILY_ALIASES.get(key, []):
            if _term_matches_in_text(lowered, term):
                return key
    return None


def extract_audience(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\b\d{1,2}\s*year\s*old\b", lowered):
        return "kids"
    if any(
        x in lowered
        for x in (
            "kids",
            "kid ",
            " kid",
            "children",
            "child",
            "toddler",
            "tweens",
            "teens",
            "teenager",
            "youth",
            "my daughter",
            "my son",
            "for students",
        )
    ):
        return "kids"
    if any(x in lowered for x in ("adults only", "21+", "grown-up", "grown ups", "adult night")):
        return "adults"
    if "family" in lowered or "whole family" in lowered or "families" in lowered:
        return "family"
    return None


def extract_location_hint(text: str) -> str | None:
    # Light heuristic: "at X" or "near X" for multi-word place names
    m = re.search(r"\b(?:at|near)\s+([A-Za-z0-9][A-Za-z0-9\s,'-]{2,60})", text, re.I)
    if m:
        hint = m.group(1).strip()
        if len(hint) > 2:
            return hint[:120]
    return None


def merge_date_range(existing: DateRange | None, new_range: DateRange | None) -> DateRange | None:
    if new_range is not None:
        return new_range
    return existing


def merge_activity_family(existing: str | None, new_val: str | None) -> str | None:
    if new_val is not None:
        return new_val
    return existing


def merge_audience(existing: str | None, new_val: str | None) -> str | None:
    if new_val is not None:
        return new_val
    return existing


def merge_location_hint(existing: str | None, new_val: str | None) -> str | None:
    if new_val is not None:
        return new_val
    return existing


def push_recent_utterance(search_block: dict[str, Any], phrase: str) -> None:
    p = phrase.strip()
    if len(p) < 2:
        return
    utter: list[str] = search_block.setdefault("recent_utterances", [])
    utter.append(p)
    while len(utter) > 3:
        utter.pop(0)


def slots_filled(slots: dict[str, Any]) -> dict[str, bool]:
    return {
        "date": slots.get("date_range") is not None,
        "activity": slots.get("activity_family") is not None,
        "audience": slots.get("audience") is not None,
        "location": bool((slots.get("location_hint") or "").strip()),
    }


def _is_weekend_date_range(dr: dict[str, date] | None) -> bool:
    if not dr:
        return False
    span = (dr["end"] - dr["start"]).days
    return span == 1


def extract_search_label(message: str, slots: dict[str, Any]) -> str:
    """Human-readable label for what the user searched for (relevance UX)."""
    lowered = message.lower().strip()
    dr = slots.get("date_range")

    if "gymnastics" in lowered:
        if "class" in lowered or "classes" in lowered:
            return "gymnastics classes"
        if any(x in lowered for x in ("kid", "child", "daughter", "son", "toddler")):
            return "gymnastics classes for kids"
        return "gymnastics"

    if "golf" in lowered and "lesson" in lowered:
        return "golf lessons"

    if "yoga" in lowered and ("this weekend" in lowered or "weekend" in lowered or _is_weekend_date_range(dr)):
        return "yoga events coming up"

    if "activities" in lowered and ("kid" in lowered or "child" in lowered) and _is_weekend_date_range(dr):
        return "kids activities this weekend"

    af = slots.get("activity_family")
    if dr and af == "sports" and _is_weekend_date_range(dr):
        return "weekend sports events"

    if af == "sports" and not dr:
        return "sports events"
    if af == "arts" and not dr:
        return "arts events"
    if af == "education" and not dr:
        return "learning events"
    if af == "outdoors" and not dr:
        return "outdoor events"
    if af == "martial_arts" and not dr:
        return "martial arts events"

    if dr and not af:
        if _is_weekend_date_range(dr):
            return "weekend events"
        return "events for that time"

    # Prefer a distinctive token from the message (longer non-stop words)
    stop = {
        "the",
        "a",
        "an",
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
        "week",
        "weekend",
        "kids",
        "child",
        "children",
        "looking",
        "find",
        "show",
        "tell",
        "about",
        "please",
        "something",
        "things",
        "going",
        "are",
        "there",
        "near",
        "today",
        "tomorrow",
    }
    words = [w for w in re.findall(r"[a-z]{3,}", lowered) if w not in stop]
    if words:
        focus = max(words, key=len)
        if len(focus) >= 4:
            return focus.replace("_", " ")

    return "events matching that"


def extract_broaden_category(slots: dict[str, Any]) -> str | None:
    """Short noun phrase for the broaden line; None if no helpful filter context."""
    aud = slots.get("audience")
    dr = slots.get("date_range")
    af = slots.get("activity_family")

    if aud == "kids":
        return "kids activities"
    if dr:
        if _is_weekend_date_range(dr):
            return "weekend events"
        return "events around those dates"
    if af == "sports":
        return "sports"
    if af == "arts":
        return "arts & music"
    if af == "education":
        return "classes"
    if af == "outdoors":
        return "outdoor activities"
    if af == "martial_arts":
        return "martial arts"
    return None
`

## app/chat/router.py

`python
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter

from app.core.conversation_copy import (
    ADDED_LIVE,
    CHAT_SOFT_FAIL,
    CLARIFY_DATE,
    DEAL_STUB_REPLY,
    DUPLICATE_PROMPT,
    ESCAPE_HATCH_REPLY,
    GREETING_MID_SEARCH,
    GREETING_REPLY,
    HARD_RESET_REPLY,
    MERGE_FOLLOWUP,
    MERGE_KEPT,
    MERGE_UPDATED,
    MISSING_FIELD_GLITCH,
    REJECTION_FIX,
    SERVICE_STUB_REPLY,
    SOFT_CANCEL_REPLY,
    STALE_SESSION_REPLY,
    UNCLEAR_REPLY,
    preview_event_line,
)
from app.core.dedupe import find_duplicate
from app.core.event_quality import (
    CONTACT_OPTIONAL_PROMPT,
    FIELD_PROMPTS,
    REVIEW_OFFER_MESSAGE,
    SUBMITTED_REVIEW_MESSAGE,
    apply_user_reply_to_field,
    build_pending_review_create,
    first_invalid_field,
    has_any_contact,
    normalize_partial_event,
    try_build_event_create,
)
from app.core.extraction import _embedding_input, _extract_phone, extract_event, generate_embedding
from app.core.intent import (
    ADD_EVENT,
    DEAL_SEARCH,
    GREETING,
    HARD_RESET,
    LISTING_INTENT,
    REFINEMENT,
    SEARCH_EVENTS,
    SERVICE_REQUEST,
    SOFT_CANCEL,
    UNCLEAR,
    detect_intent,
    escape_to_search,
    is_confirmation,
    is_greeting,
    is_hard_reset,
    is_rejection,
    is_skip_optional_contact,
    is_soft_cancel,
)
from app.core.search import (
    SearchOutcome,
    apply_audience_location_filters,
    decide_search_strategy,
    format_search_results,
    search_events,
)
from app.core.session import (
    arm_session_blocking,
    blocking_session_expired,
    clear_add_branch,
    clear_current_flow,
    clear_session_state,
    get_flow,
    get_search,
    get_session,
    set_flow_awaiting,
    soft_clear_awaits,
)
from app.core.slots import (
    extract_activity_family,
    extract_audience,
    extract_date_range,
    extract_location_hint,
    merge_activity_family,
    merge_audience,
    merge_date_range,
    merge_location_hint,
    push_recent_utterance,
)
from app.db.chat_logging import log_chat_turn
from app.db.database import get_db
from app.db.models import Event
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def _wants_last_result_expansion(message: str) -> bool:
    m = message.lower().strip()
    return any(
        x in m
        for x in (
            "all of them",
            "all those",
            "those events",
            "these events",
            "show full details",
            "every one",
        )
    )


def _session_idle_for_greeting(session: dict) -> bool:
    flow = get_flow(session)
    if flow.get("awaiting") in ("clarify_date", "clarify_activity"):
        return False
    return not (
        session.get("awaiting_review_offer")
        or session.get("awaiting_missing_field")
        or session.get("awaiting_optional_contact")
        or session.get("awaiting_duplicate_confirmation")
        or session.get("awaiting_merge_details")
        or session.get("awaiting_confirmation")
        or session.get("partial_event")
    )


def _apply_slots_from_message(session: dict, message: str, *, listing_intent: bool) -> None:
    search = get_search(session)
    slots = search["slots"]
    lm = search.get("listing_mode", False)

    dr = extract_date_range(message)
    af = extract_activity_family(message)
    aud = extract_audience(message)
    loc = extract_location_hint(message)

    slots["date_range"] = merge_date_range(slots.get("date_range"), dr)
    slots["activity_family"] = merge_activity_family(slots.get("activity_family"), af)
    slots["audience"] = merge_audience(slots.get("audience"), aud)
    slots["location_hint"] = merge_location_hint(slots.get("location_hint"), loc)

    if listing_intent:
        search["listing_mode"] = True
    elif dr or af or aud or loc:
        search["listing_mode"] = False

    if len(message.strip()) >= 2 and not is_greeting(message):
        push_recent_utterance(search, message)


def _slot_keywords(slots: dict) -> list[str]:
    loc = (slots.get("location_hint") or "").strip()
    if not loc:
        return []
    return [w for w in re.split(r"\s+", loc.lower()) if len(w) > 2]


def _run_search_core(session: dict, db: Session, message: str, strategy: str) -> tuple[list[Event], str]:
    search = get_search(session)
    slots = search["slots"]
    utter = search.get("recent_utterances") or []
    query_message = utter[-1] if utter else message

    date_ctx = slots.get("date_range")
    if isinstance(date_ctx, dict):
        date_ctx = {"start": date_ctx["start"], "end": date_ctx["end"]}

    activity = slots.get("activity_family")
    keywords = _slot_keywords(slots)

    strict_rel = strategy != "RUN_BROAD"
    outcome = search_events(
        db=db,
        date_context=date_ctx,
        activity_type=activity,
        keywords=keywords,
        query_message=query_message,
        strict_relevance=strict_rel,
        audience_hint=slots.get("audience"),
    )
    events = apply_audience_location_filters(
        outcome.events,
        slots.get("audience"),
        slots.get("location_hint"),
    )
    outcome_used: SearchOutcome = outcome
    if outcome.events and not events and strict_rel:
        outcome_used = SearchOutcome(
            [],
            suppressed_low_relevance=True,
            slot_filter_exhausted=False,
            honest_no_match=False,
        )

    if _wants_last_result_expansion(message):
        ids = search.get("last_result_set", {}).get("ids") or []
        if ids:
            by_id = {e.id: e for e in events}
            ordered = [by_id[i] for i in ids if i in by_id]
            if ordered:
                events = ordered

    body = format_search_results(
        events,
        strategy,
        slots,
        message=message,
        outcome=outcome_used,
    )
    search["last_result_set"] = {
        "ids": [e.id for e in events],
        "query_signature": query_message[:200],
    }
    return events, body


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("120/minute")
def chat(request: Request, payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    message = payload.message.strip()
    try:
        log_chat_turn(db, payload.session_id, message, "user", None)
        resp = _chat_inner(payload, message, db)
        arm_session_blocking(get_session(payload.session_id))
        log_chat_turn(db, payload.session_id, resp.response, "assistant", resp.intent)
        return resp
    except Exception:
        logging.exception("chat handler failure")
        try:
            db.rollback()
        except Exception:
            pass
        return ChatResponse(response=CHAT_SOFT_FAIL, intent="UNCLEAR", data={})


def _chat_inner(payload: ChatRequest, message: str, db: Session) -> ChatResponse:
    session_id = payload.session_id
    session = get_session(session_id)

    if blocking_session_expired(session):
        soft_clear_awaits(session)
        return ChatResponse(response=STALE_SESSION_REPLY, intent="UNCLEAR", data={})

    if is_hard_reset(message):
        clear_session_state(session_id)
        return ChatResponse(response=HARD_RESET_REPLY, intent=HARD_RESET, data={})

    if is_soft_cancel(message):
        clear_current_flow(session)
        return ChatResponse(response=SOFT_CANCEL_REPLY, intent=SOFT_CANCEL, data={})

    if session.get("awaiting_optional_contact"):
        return _handle_optional_contact_reply(session, message, db)

    if session.get("awaiting_review_offer"):
        if is_confirmation(message):
            created = _store_pending_review(session["partial_event"], db)
            clear_session_state(session_id)
            return ChatResponse(
                response=SUBMITTED_REVIEW_MESSAGE,
                intent=ADD_EVENT,
                data={"event_id": created.id, "status": "pending_review"},
            )
        if is_rejection(message):
            session["awaiting_review_offer"] = False
            session["field_retry_counts"] = {}
            inv = first_invalid_field(session["partial_event"])
            if inv:
                session["awaiting_missing_field"] = inv
                return ChatResponse(
                    response=FIELD_PROMPTS[inv],
                    intent=ADD_EVENT,
                    data={"partial_event": session["partial_event"]},
                )
            return _after_partial_update(session)

    if session.get("awaiting_missing_field"):
        return _handle_missing_field_reply(session, message, db)

    if session["awaiting_duplicate_confirmation"] and session["duplicate_candidate_event"]:
        if is_confirmation(message):
            existing_event = db.get(Event, session["duplicate_match_id"])
            session["awaiting_duplicate_confirmation"] = False
            session["awaiting_merge_details"] = True
            return ChatResponse(
                response=MERGE_FOLLOWUP.format(
                    title=existing_event.title,
                    date=existing_event.date.isoformat(),
                    time=existing_event.start_time.isoformat(),
                    location=existing_event.location_name,
                ),
                intent=ADD_EVENT,
                data={"existing_event_id": existing_event.id},
            )

        if is_rejection(message):
            created_event = _store_event(session["duplicate_candidate_event"], db)
            clear_session_state(session_id)
            return ChatResponse(
                response=ADDED_LIVE,
                intent=ADD_EVENT,
                data={"event_id": created_event.id},
            )

    if session["awaiting_merge_details"] and session["duplicate_match_id"]:
        existing_event = db.get(Event, session["duplicate_match_id"])
        if is_rejection(message):
            clear_session_state(session_id)
            return ChatResponse(
                response=MERGE_KEPT,
                intent=ADD_EVENT,
                data={"event_id": existing_event.id},
            )

        merged_event = _merge_into_existing_event(existing_event, session["duplicate_candidate_event"], message, db)
        clear_session_state(session_id)
        return ChatResponse(
            response=MERGE_UPDATED.format(title=merged_event.title),
            intent=ADD_EVENT,
            data={"event_id": merged_event.id},
        )

    if session["awaiting_confirmation"] and session["partial_event"]:
        if is_confirmation(message):
            duplicate = find_duplicate(session["partial_event"], db)
            if duplicate is not None:
                session["awaiting_confirmation"] = False
                session["awaiting_duplicate_confirmation"] = True
                session["duplicate_candidate_event"] = dict(session["partial_event"])
                session["duplicate_match_id"] = duplicate.id
                return ChatResponse(
                    response=DUPLICATE_PROMPT.format(title=duplicate.title),
                    intent=ADD_EVENT,
                    data={"duplicate_event_id": duplicate.id},
                )

            created_event = _store_event(session["partial_event"], db)
            clear_session_state(session_id)
            return ChatResponse(
                response=ADDED_LIVE,
                intent=ADD_EVENT,
                data={"event_id": created_event.id},
            )

        if is_rejection(message):
            session["awaiting_confirmation"] = False
            return ChatResponse(
                response=REJECTION_FIX,
                intent=ADD_EVENT,
                data={"partial_event": session["partial_event"]},
            )

    if escape_to_search(message) and (
        session.get("partial_event") or session.get("awaiting_confirmation")
    ):
        clear_add_branch(session)
        set_flow_awaiting(session, None)
        _apply_slots_from_message(session, message, listing_intent=False)
        session["current_intent"] = SEARCH_EVENTS
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=f"{ESCAPE_HATCH_REPLY}\n\n{body}",
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    flow_early = get_flow(session)
    if flow_early.get("awaiting") in ("clarify_date", "clarify_activity"):
        _apply_slots_from_message(session, message, listing_intent=False)
        set_flow_awaiting(session, None)
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        if strategy == "CLARIFY_DATE" and not get_search(session)["slots"].get("date_range"):
            set_flow_awaiting(session, "clarify_date")
            return ChatResponse(response=CLARIFY_DATE, intent=SEARCH_EVENTS, data={"search": get_search(session)})
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        session["current_intent"] = SEARCH_EVENTS
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    intent = detect_intent(message, session)

    if intent == GREETING:
        flow = get_flow(session)
        if flow.get("awaiting") == "narrow_followup":
            return ChatResponse(response=GREETING_MID_SEARCH, intent=GREETING, data={})
        if _session_idle_for_greeting(session):
            return ChatResponse(response=GREETING_REPLY, intent=GREETING, data={})
        return ChatResponse(response=GREETING_REPLY, intent=GREETING, data={})

    if intent == SERVICE_REQUEST:
        return ChatResponse(response=SERVICE_STUB_REPLY, intent=SERVICE_REQUEST, data={})

    if intent == DEAL_SEARCH:
        return ChatResponse(response=DEAL_STUB_REPLY, intent=DEAL_SEARCH, data={})

    if intent == LISTING_INTENT:
        clear_add_branch(session)
        _apply_slots_from_message(session, message, listing_intent=True)
        session["current_intent"] = LISTING_INTENT
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            True,
            message,
        )
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=LISTING_INTENT,
            data={"count": len(events), "search": get_search(session)},
        )

    if intent == REFINEMENT:
        _apply_slots_from_message(session, message, listing_intent=False)
        session["current_intent"] = SEARCH_EVENTS
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    if intent == ADD_EVENT:
        extracted = extract_event(message)
        session["partial_event"] = extracted
        _attach_embedding(session["partial_event"])
        session["current_intent"] = ADD_EVENT
        get_flow(session)["current"] = "add_event"
        return _after_partial_update(session)

    if session["current_intent"] == ADD_EVENT and session["partial_event"] and not session["awaiting_confirmation"]:
        extracted = extract_event(message)
        session["partial_event"] = _merge_event_updates(session["partial_event"], extracted)
        _attach_embedding(session["partial_event"])
        return _after_partial_update(session)

    if intent == UNCLEAR:
        return ChatResponse(response=UNCLEAR_REPLY, intent=intent, data={})

    if intent == SEARCH_EVENTS:
        _apply_slots_from_message(session, message, listing_intent=False)
        session["current_intent"] = SEARCH_EVENTS
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        if strategy == "CLARIFY_DATE":
            set_flow_awaiting(session, "clarify_date")
            return ChatResponse(response=CLARIFY_DATE, intent=SEARCH_EVENTS, data={"search": get_search(session)})
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    return ChatResponse(response=UNCLEAR_REPLY, intent=UNCLEAR, data={})


def _attach_embedding(partial: dict) -> None:
    partial["embedding"] = generate_embedding(_embedding_input(partial))


def _finalize_add_flow(session: dict) -> ChatResponse:
    partial = normalize_partial_event(session["partial_event"] or {})
    session["partial_event"] = partial
    inv = first_invalid_field(partial)
    if inv:
        session["awaiting_missing_field"] = inv
        session["awaiting_confirmation"] = False
        session["awaiting_optional_contact"] = False
        return ChatResponse(
            response=FIELD_PROMPTS[inv],
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )
    session["awaiting_missing_field"] = None
    if not session.get("contact_optional_answered"):
        if has_any_contact(partial):
            session["contact_optional_answered"] = True
        else:
            session["awaiting_optional_contact"] = True
            session["awaiting_confirmation"] = False
            return ChatResponse(
                response=CONTACT_OPTIONAL_PROMPT,
                intent=ADD_EVENT,
                data={"partial_event": partial},
            )
    session["awaiting_optional_contact"] = False
    session["awaiting_confirmation"] = True
    return ChatResponse(
        response=_preview_message(partial),
        intent=ADD_EVENT,
        data={"partial_event": partial},
    )


def _after_partial_update(session: dict) -> ChatResponse:
    partial = normalize_partial_event(session["partial_event"])
    session["partial_event"] = partial
    return _finalize_add_flow(session)


def _handle_missing_field_reply(session: dict, message: str, db: Session) -> ChatResponse:
    field = session["awaiting_missing_field"]
    if not field or not session["partial_event"]:
        session["awaiting_missing_field"] = None
        return ChatResponse(response=MISSING_FIELD_GLITCH, intent=ADD_EVENT, data={})

    partial = apply_user_reply_to_field(field, message, session["partial_event"])
    _attach_embedding(partial)
    session["partial_event"] = partial

    still_bad = first_invalid_field(partial) == field
    if still_bad:
        counts = session["field_retry_counts"]
        counts[field] = counts.get(field, 0) + 1
        session["field_retry_counts"] = counts
        if counts[field] >= 2:
            session["awaiting_review_offer"] = True
            session["awaiting_missing_field"] = None
            return ChatResponse(
                response=REVIEW_OFFER_MESSAGE,
                intent=ADD_EVENT,
                data={"partial_event": partial},
            )
        return ChatResponse(
            response=f"Hmm, that didn't quite work — {FIELD_PROMPTS[field]}",
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )

    counts = session["field_retry_counts"]
    if field in counts:
        del counts[field]
    session["awaiting_missing_field"] = None

    next_inv = first_invalid_field(partial)
    if next_inv:
        session["awaiting_missing_field"] = next_inv
        return ChatResponse(
            response=FIELD_PROMPTS[next_inv],
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )

    return _finalize_add_flow(session)


def _handle_optional_contact_reply(session: dict, message: str, db: Session) -> ChatResponse:
    partial = dict(session.get("partial_event") or {})
    if is_skip_optional_contact(message):
        session["contact_optional_answered"] = True
        session["awaiting_optional_contact"] = False
        session["awaiting_confirmation"] = True
        return ChatResponse(
            response=_preview_message(partial),
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )

    extracted = extract_event(message)
    merged = _merge_event_updates(partial, extracted)
    phone = _extract_phone(message)
    if phone:
        merged["contact_phone"] = phone
    left = message
    if phone:
        left = left.replace(phone, " ")
    left = re.sub(r"\s+", " ", left).strip()
    cn = (extracted.get("contact_name") or "").strip() if extracted.get("contact_name") else ""
    if cn:
        merged["contact_name"] = cn
    elif left and len(left) > 1:
        merged["contact_name"] = left[:200]

    session["partial_event"] = merged
    _attach_embedding(merged)
    session["contact_optional_answered"] = True
    session["awaiting_optional_contact"] = False
    session["awaiting_confirmation"] = True
    return ChatResponse(
        response=_preview_message(merged),
        intent=ADD_EVENT,
        data={"partial_event": merged},
    )


def _preview_message(event: dict) -> str:
    d = event.get("date", "date TBD")
    if hasattr(d, "isoformat"):
        d = d.isoformat()
    t = event.get("start_time", "time TBD")
    if hasattr(t, "isoformat"):
        t = t.isoformat()
    lines = [
        preview_event_line(
            str(event.get("title", "Untitled")),
            str(d),
            str(t),
            str(event.get("location_name", "somewhere TBD")),
        )
        .replace("Sound right?", "")
        .strip()
    ]
    url = (event.get("event_url") or "").strip()
    if url:
        lines.append(f"Link: {url}")
    cn = (event.get("contact_name") or "").strip() if event.get("contact_name") else ""
    cp = (event.get("contact_phone") or "").strip() if event.get("contact_phone") else ""
    if cn:
        lines.append(f"Contact: {cn}")
    if cp:
        lines.append(f"Phone: {cp}")
    body = "\n".join(lines) + "\n\nSound right?"
    return body


def _merge_event_updates(existing: dict, updates: dict) -> dict:
    merged = dict(existing)
    for key, value in updates.items():
        if value:
            merged[key] = value
    return merged


def _store_event(event_data: dict, db: Session) -> Event:
    payload = try_build_event_create(event_data)
    event = Event.from_create(payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _store_pending_review(event_data: dict, db: Session) -> Event:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deadline = now + timedelta(hours=72)
    payload = build_pending_review_create(event_data, admin_review_by=deadline)
    event = Event.from_create(payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _merge_into_existing_event(existing_event: Event, candidate_event: dict, message: str, db: Session) -> Event:
    updates = extract_event(message)

    if not existing_event.description.strip() and candidate_event.get("description"):
        existing_event.description = candidate_event["description"]

    if candidate_event.get("description") and candidate_event["description"] not in existing_event.description:
        existing_event.description = f"{existing_event.description} {candidate_event['description']}".strip()

    if updates.get("description") and updates["description"] not in existing_event.description:
        existing_event.description = f"{existing_event.description} {updates['description']}".strip()

    if candidate_event.get("event_url") and not (existing_event.event_url or "").strip():
        existing_event.event_url = str(candidate_event["event_url"]).strip()
    if candidate_event.get("contact_name") and not existing_event.contact_name:
        existing_event.contact_name = str(candidate_event["contact_name"]).strip()
    if candidate_event.get("contact_phone") and not existing_event.contact_phone:
        existing_event.contact_phone = str(candidate_event["contact_phone"]).strip()

    existing_event.embedding = candidate_event.get("embedding") or existing_event.embedding
    db.add(existing_event)
    db.commit()
    db.refresh(existing_event)
    return existing_event
`

