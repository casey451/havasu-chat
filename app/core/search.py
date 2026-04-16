from __future__ import annotations

import math
import os
import re
from collections import defaultdict
from datetime import date, time as time_type, timedelta
from typing import Any, Literal

from dotenv import load_dotenv
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
    NOTHING_FOR_ACTIVITY,
    NOTHING_IN_RANGE,
    SEARCH_INTRO_MANY,
)
from app.core.dedupe import cosine_similarity
from app.core.intent import open_ended_search_message
from app.db.models import Event

load_dotenv()

SEARCH_QUERY_EMBEDDING_MODEL = "text-embedding-ada-002"

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


def generate_query_embedding(text: str) -> list[float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=api_key)
            response = client.embeddings.create(model=SEARCH_QUERY_EMBEDDING_MODEL, input=text.strip() or " ")
            return list(response.data[0].embedding)
        except Exception:
            return _deterministic_embedding_1536(text)
    return _deterministic_embedding_1536(text)


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


def search_events(
    db: Session,
    date_context: dict[str, date] | None,
    activity_type: str | None,
    keywords: list[str],
    query_message: str = "",
) -> list[Event]:
    """Semantic + keyword search; query_message should be the latest user phrase only (Phase 8.5)."""
    query_text = query_message.strip() or " ".join(keywords) or activity_type or "events"
    query_embedding = generate_query_embedding(query_text)
    dim = len(query_embedding)

    base_q = _base_future_events_query(db, date_context)
    candidates: list[Event] = base_q.all()

    if activity_type:
        terms = ACTIVITY_TYPES.get(activity_type, [])
        if terms:
            candidates = [e for e in candidates if any(t in f"{e.title} {e.description}".lower() for t in terms)]

    with_emb: list[tuple[Event, float]] = []
    without_emb: list[Event] = []

    for event in candidates:
        emb = event.embedding
        if emb and len(emb) == dim:
            score = cosine_similarity(query_embedding, emb)
            with_emb.append((event, score))
        else:
            without_emb.append(event)

    with_emb.sort(key=lambda x: x[1], reverse=True)
    ordered_embedded = [e for e, _ in with_emb]

    if not without_emb:
        return ordered_embedded

    # Keywords only — activity_type is already applied as a semantic bucket filter above.
    text_terms = _unique_terms(list(keywords))
    keyword_hits = [e for e in without_emb if _event_matches_keyword_terms(e, text_terms)]
    keyword_hits.sort(key=lambda ev: (ev.date, ev.start_time))

    seen = {e.id for e in ordered_embedded}
    for e in keyword_hits:
        if e.id not in seen:
            ordered_embedded.append(e)
            seen.add(e.id)

    return ordered_embedded


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


def format_search_results(
    events: list[Event],
    strategy: SearchStrategy,
    slots: dict[str, Any],
    *,
    append_narrow_hint: bool | None = None,
) -> str:
    if not events:
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
