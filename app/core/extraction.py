from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, time

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()


EXTRACTION_PROMPT = """Extract event details from the following text.
Return ONLY valid JSON with exactly these keys:
title, date, start_time, location_name, description, event_url, contact_name, contact_phone.
Use ISO date format YYYY-MM-DD and HH:MM:SS for time when possible.
event_url: full http(s) link if present, else empty string.
contact_name and contact_phone: only if explicitly mentioned; else empty string.
Do not include markdown or extra commentary.

Text:
{message}
"""


TAGS_PROMPT = """Generate 5 to 10 short, lowercase tags describing this event.

Tags should cover, when applicable:
- Event type (e.g. concert, race, market, festival, class, tournament)
- Audience (e.g. kids, family, adults, seniors, 21plus)
- Activities (e.g. music, dance, food, art, sports, fitness, educational)
- Free or paid
- Indoor or outdoor
- Daytime or evening

Return ONLY a JSON array of lowercase strings. No markdown, no commentary, no extra text.

Example: ["concert", "live music", "family", "outdoor", "evening", "free"]

Event:
Title: {title}
Location: {location_name}
Description: {description}
"""

TIME_PATTERN = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
DATE_WORDS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def extract_event(message: str) -> dict:
    extracted = _extract_with_openai(message)
    fallback = _heuristic_extract(message)
    event = {
        "title": _title_case(fallback["title"]),
        "date": fallback["date"],
        "start_time": fallback["start_time"],
        "location_name": _title_case(fallback["location_name"]),
        "description": fallback["description"],
        "event_url": fallback["event_url"],
        "contact_name": fallback["contact_name"],
        "contact_phone": fallback["contact_phone"],
    }
    if extracted is not None and extracted.get("description"):
        ai_desc = str(extracted["description"]).strip()
        if len(ai_desc) >= 20:
            event["description"] = ai_desc
    if extracted is not None:
        for key in ("event_url", "contact_name", "contact_phone"):
            val = extracted.get(key)
            if val is None:
                continue
            s = str(val).strip()
            if not s:
                continue
            if key == "event_url" and len(s) >= 4:
                event[key] = s
            elif key == "contact_name":
                event[key] = s
            elif key == "contact_phone":
                event[key] = s
    event["embedding"] = generate_embedding(_embedding_input(event))
    event["tags"] = generate_event_tags(event)
    return event


def generate_event_tags(event: dict) -> list[str]:
    """Generate 5-10 short lowercase tags for an event using OpenAI.

    Returns an empty list when OPENAI_API_KEY is missing, the OpenAI client is
    unavailable, the API call raises, or the response does not parse as a JSON
    array of strings. Callers are expected to treat an empty list as "untagged".
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return []

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=TAGS_PROMPT.format(
                title=str(event.get("title", "")).strip(),
                location_name=str(event.get("location_name", "")).strip(),
                description=str(event.get("description", "")).strip(),
            ),
        )
        raw_text = response.output_text.strip()
    except Exception:
        return []

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        tag = item.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= 10:
            break
    return tags


def _extract_with_openai(message: str) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=EXTRACTION_PROMPT.format(message=message),
        )

        raw_text = response.output_text.strip()
    except Exception:
        return None

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    return {
        "title": str(parsed.get("title", "")).strip(),
        "date": str(parsed.get("date", "")).strip(),
        "start_time": str(parsed.get("start_time", "")).strip(),
        "location_name": str(parsed.get("location_name", "")).strip(),
        "description": str(parsed.get("description", "")).strip(),
        "event_url": str(parsed.get("event_url", "")).strip(),
        "contact_name": str(parsed.get("contact_name", "")).strip(),
        "contact_phone": str(parsed.get("contact_phone", "")).strip(),
    }


def _heuristic_extract(message: str) -> dict:
    return {
        "title": _extract_title(message),
        "date": _extract_date(message),
        "start_time": _extract_time(message),
        "location_name": _extract_location(message),
        "description": message.strip(),
        "event_url": _extract_url(message),
        "contact_name": "",
        "contact_phone": _extract_phone(message),
    }


def _extract_url(message: str) -> str:
    m = re.search(r"(https?://[^\s<>\"']+)", message, re.IGNORECASE)
    if m:
        return m.group(1).rstrip(").,]")
    m = re.search(r"\b(www\.[^\s<>\"']+)", message, re.IGNORECASE)
    if m:
        return "https://" + m.group(1).rstrip(").,]")
    return ""


def _extract_phone(message: str) -> str:
    m = re.search(
        r"\b(\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b",
        message,
    )
    if m:
        return m.group(0).strip()
    return ""


def _extract_title(message: str) -> str:
    cleaned = re.split(
        r"\b(?:on|at|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
        message,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return cleaned.strip(" .,!?\n\t").title()


def _extract_date(message: str) -> str:
    lowered = message.lower()
    today = date.today()

    if "today" in lowered:
        return today.isoformat()
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()

    for day_name, weekday in DATE_WORDS.items():
        if day_name in lowered:
            days_ahead = (weekday - today.weekday()) % 7
            days_ahead = 7 if days_ahead == 0 else days_ahead
            return (today + timedelta(days=days_ahead)).isoformat()

    return today.isoformat()


def _extract_time(message: str) -> str:
    match = TIME_PATTERN.search(message)
    if not match:
        return "09:00:00"

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()

    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0

    return time(hour=hour, minute=minute).isoformat()


def _extract_location(message: str) -> str:
    match = re.search(r"\bat\s+([a-z0-9\s]+)", message, re.IGNORECASE)
    if not match:
        return "Location TBD"
    return match.group(1).strip(" .,!?\n\t").title()


def _title_case(value: str) -> str:
    return value.strip().title()


def generate_embedding(text: str) -> list[float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=api_key)
            response = client.embeddings.create(model="text-embedding-3-small", input=text)
            return list(response.data[0].embedding)
        except Exception:
            return _deterministic_embedding(text)
    return _deterministic_embedding(text)


def _embedding_input(event: dict) -> str:
    return " | ".join(
        [
            str(event.get("title", "")).strip(),
            str(event.get("location_name", "")).strip(),
            str(event.get("description", "")).strip(),
            str(event.get("event_url", "")).strip(),
        ]
    )


def _deterministic_embedding(text: str, dimensions: int = 32) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    counts = Counter(tokens)
    vector = [0.0] * dimensions

    for token, count in counts.items():
        index = hash(token) % dimensions
        vector[index] += float(count)

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]
