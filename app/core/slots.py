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

    if "today" in lowered or "tonight" in lowered:
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


QUERY_SYNONYMS: dict[str, list[str]] = {
    "boat race": ["regatta", "boat racing", "poker run"],
    "boat races": ["regatta", "boat racing", "poker run"],
    "live music": ["concert", "band", "acoustic", "dj", "open mic"],
    "music": ["concert", "band", "acoustic", "dj"],
    "food": ["dining", "restaurant", "tasting", "food truck"],
    "drinks": ["happy hour", "cocktail", "bar", "brewery", "wine"],
    "shopping": ["market", "boutique", "vendor", "craft fair"],
    "fitness": ["workout", "gym", "class", "training"],
    "kids activities": ["family", "youth", "children"],
    "things to do": ["event", "activity", "happening"],
}


def expand_query_synonyms(message: str) -> list[str]:
    """Return extra keywords to search for based on common synonyms."""
    lowered = message.lower()
    extras: list[str] = []
    for phrase, synonyms in QUERY_SYNONYMS.items():
        if phrase in lowered:
            extras.extend(synonyms)
    return extras
