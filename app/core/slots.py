"""Structured search slots extracted from user text (Phase 8.5)."""

from __future__ import annotations

import re
from calendar import monthrange
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

    # "First Friday" is a recurring event name, not "next Friday" as a day filter.
    if "first friday" in lowered:
        return None

    if "today" in lowered or "tonight" in lowered:
        return {"start": today, "end": today}
    if "tomorrow" in lowered:
        t = today + timedelta(days=1)
        return {"start": t, "end": t}

    if "this weekend" in lowered:
        saturday = _next_weekday(today, 5, allow_today=True)
        sunday = saturday + timedelta(days=1)
        return {"start": saturday, "end": sunday}

    # "this week" check must come after "this weekend" (substring).
    if "this week" in lowered:
        sunday = _next_weekday(today, 6, allow_today=True)
        return {"start": today, "end": sunday}

    if "next week" in lowered:
        monday = _next_weekday(today, 0, allow_today=False)
        if monday <= today:
            monday += timedelta(days=7)
        return {"start": monday, "end": monday + timedelta(days=6)}

    if "next month" in lowered:
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        last_day = monthrange(year, month)[1]
        return {"start": date(year, month, 1), "end": date(year, month, last_day)}

    if "this month" in lowered:
        last_day = monthrange(today.year, today.month)[1]
        return {"start": today, "end": date(today.year, today.month, last_day)}

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
    # Water
    "boat race": ["regatta", "poker run", "boat racing", "speedboat race", "desert storm"],
    "boat races": ["regatta", "poker run", "boat racing", "speedboat race", "desert storm"],
    "jet ski": ["waverunner", "wave runner", "pwc", "personal watercraft", "seadoo"],
    "kayak": ["canoe", "paddle", "paddling"],
    "paddleboard": ["sup", "stand up paddle", "paddleboarding"],
    "boat tour": ["cruise", "lake tour", "sightseeing boat", "jet boat tour"],
    "fishing": ["angling", "bass fishing", "fishing tournament", "fishing derby"],
    # Land
    "hiking": ["hike", "trail", "trek", "trail walking"],
    "off-road": ["atv", "utv", "4x4", "side by side", "jeep tour", "dune"],
    "mountain bike": ["mtb", "bike trail", "cycling"],
    "golf": ["tee off", "golf course", "links", "tee time"],
    "balloon": ["hot air balloon", "balloon ride", "balloon festival"],
    # Family / kids
    "trampoline": ["trampoline park", "jumping", "altitude"],
    "bowling": ["bowl", "havasu lanes", "cosmic bowling"],
    "arcade": ["video games", "fun center", "scooter's"],
    "mini golf": ["putt putt", "miniature golf"],
    "kids": ["children", "family", "family-friendly", "toddler"],
    "kids activities": ["family", "youth", "children", "family-friendly"],
    "aquatic center": ["pool", "swimming pool", "public pool"],
    # Dining & drinks
    "live music": ["concert", "band", "acoustic", "dj", "open mic"],
    "music": ["concert", "band", "acoustic", "dj"],
    "food": ["dining", "restaurant", "tasting", "food truck"],
    "drinks": ["happy hour", "cocktail", "bar", "brewery", "wine"],
    "restaurant": ["dining", "eat", "food", "dinner"],
    "bar": ["pub", "lounge", "tavern", "drinks"],
    "happy hour": ["drinks special", "discount drinks"],
    "brewery": ["beer", "ale", "craft beer", "taproom"],
    "farmers market": ["market", "sunset market", "local market"],
    "food truck": ["food cart", "street food"],
    # Entertainment
    "concert": ["live music", "band", "show", "performance", "dj"],
    "festival": ["fest", "celebration"],
    "parade": ["procession", "march", "boat parade"],
    "fireworks": ["firework show", "pyrotechnics", "july 4", "4th of july", "independence day"],
    "car show": ["auto show", "classic car", "car meet"],
    "motorcycle": ["bike", "motorbike", "bike night"],
    "shopping": ["market", "boutique", "vendor", "craft fair"],
    # Wellness
    "yoga": ["stretching", "mindfulness class"],
    "fitness": ["workout", "exercise", "gym class", "pilates"],
    # General
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
