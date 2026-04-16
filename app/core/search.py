from __future__ import annotations

import math
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.core.conversation_copy import SEARCH_EMPTY, SEARCH_INTRO_MANY
from app.core.dedupe import cosine_similarity
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
    "sports": ["sport", "soccer", "basketball", "football", "tennis", "swim", "gym"],
    "arts": ["art", "music", "dance", "theater", "craft", "paint"],
    "education": ["class", "workshop", "stem", "science", "coding", "math", "reading"],
    "outdoors": ["hike", "park", "trail", "camping", "outdoor"],
}

GROUP_EMOJI = {
    "Martial Arts": "🥋",
    "Sports": "⚽",
    "Arts": "🎪",
    "Education": "📚",
    "Outdoors": "🥾",
    "General": "📌",
}


def extract_search_context(message: str) -> dict[str, Any]:
    lowered = message.lower()
    return {
        "date_context": _extract_date_context(lowered),
        "activity_type": _extract_activity_type(lowered),
        "keywords": _extract_keywords(lowered),
    }


def generate_query_embedding(text: str) -> list[float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and OpenAI is not None:
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model=SEARCH_QUERY_EMBEDDING_MODEL, input=text.strip() or " ")
        return list(response.data[0].embedding)
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

    text_terms = _unique_terms(list(keywords) + ([activity_type] if activity_type else []))

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
    query_text = " ".join(
        part for part in [query_message.strip(), " ".join(keywords), activity_type or ""] if part
    ).strip() or "events"

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

    text_terms = _unique_terms(list(keywords) + ([activity_type] if activity_type else []))

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


def _group_heading(category: str) -> str:
    emoji = GROUP_EMOJI.get(category, "📌")
    if category == "Arts":
        return f"{emoji} Fun Activities"
    if category == "Education":
        return f"{emoji} Learning & Classes"
    return f"{emoji} {category}"


def format_results(events: list[Event]) -> str:
    if not events:
        return SEARCH_EMPTY

    if len(events) == 1:
        e = events[0]
        url_bit = f"\n{e.event_url}" if getattr(e, "event_url", None) else ""
        return (
            f"Found one that might work: {e.title} — {e.date.isoformat()} at "
            f"{e.start_time.isoformat()} ({e.location_name}){url_bit}"
        )

    grouped: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        grouped[_classify_event_type(event)].append(event)

    lines = [SEARCH_INTRO_MANY]
    for group_name in sorted(grouped.keys(), key=lambda g: (g != "General", g)):
        group_events = grouped[group_name]
        lines.append(_group_heading(group_name))
        for event in group_events:
            url_bit = f" — {event.event_url}" if getattr(event, "event_url", None) else ""
            lines.append(
                f"  • {event.title} — {event.date.isoformat()} at {event.start_time.isoformat()} "
                f"({event.location_name}){url_bit}"
            )
    return "\n".join(lines)


def missing_search_fields(context: dict[str, Any]) -> str | None:
    if context.get("date_context") is None:
        return "When works for you — this weekend, or a specific day?"
    if context.get("activity_type") is None:
        return "What kind of thing — sports, arts, something else?"
    return None


def merge_search_context(existing: dict[str, Any], new_context: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "date_context": new_context.get("date_context") or existing.get("date_context"),
        "activity_type": new_context.get("activity_type") or existing.get("activity_type"),
        "keywords": _merge_keywords(existing.get("keywords", []), new_context.get("keywords", [])),
    }
    return merged


def _extract_date_context(lowered: str) -> dict[str, date] | None:
    today = date.today()

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

    return None


def _extract_activity_type(lowered: str) -> str | None:
    for activity_type, terms in ACTIVITY_TYPES.items():
        if any(term in lowered for term in terms):
            return activity_type
    return None


def _extract_keywords(lowered: str) -> list[str]:
    words = [word.strip(".,!?") for word in lowered.split()]
    stopwords = {
        "for",
        "my",
        "the",
        "a",
        "an",
        "this",
        "next",
        "week",
        "weekend",
        "something",
        "looking",
        "find",
        "going",
        "on",
        "what",
        "any",
        "old",
        "year",
    }
    return [word for word in words if len(word) > 2 and word not in stopwords]


def _next_weekday(start_date: date, weekday: int, allow_today: bool) -> date:
    days_ahead = (weekday - start_date.weekday()) % 7
    if days_ahead == 0 and not allow_today:
        days_ahead = 7
    return start_date + timedelta(days=days_ahead)


def _classify_event_type(event: Event) -> str:
    text = f"{event.title} {event.description}".lower()
    order = ["martial_arts", "sports", "arts", "education", "outdoors"]
    for key in order:
        terms = ACTIVITY_TYPES[key]
        if any(term in text for term in terms):
            return key.replace("_", " ").title()
    return "General"


def _merge_keywords(existing: list[str], new: list[str]) -> list[str]:
    ordered = []
    for word in existing + new:
        if word and word not in ordered:
            ordered.append(word)
    return ordered
