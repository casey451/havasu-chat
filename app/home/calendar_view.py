"""``GET /calendar`` view-model — the customized events+classes calendar (Phase 2b).

The discovery destination the concierge routes to. Parses a free-text query into
filters (days / time-of-day / type / audience), pulls REAL events + classes per
day via ``events_views.day_groups``, and builds filtered day columns plus the
removable "Hava understood" chips. Fully server-rendered — every control is a
link that reloads ``/calendar?…`` (no SPA, shareable, accessible). No fabricated
data: a day with nothing matching renders an honest empty column.
"""

from __future__ import annotations

import re
from typing import Any

WINDOW_DAYS = 7

#: ``type`` param value → the ``day_groups`` bucket key it filters to.
TYPE_TO_KEY = {"events": "events", "music": "music", "family": "family",
               "water": "water", "classes": "classes"}
TYPE_LABELS = {"events": "Around town", "music": "Music", "family": "Family",
               "water": "Lake & boating", "classes": "Classes"}
PART_LABELS = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening"}
_PART_WINDOWS = {"morning": (5, 12), "afternoon": (12, 17), "evening": (17, 24)}

# Free-text → filter keyword maps (deterministic, no LLM; complements the
# app/chat classifiers, which resolve category nouns but not day/time/audience).
_TYPE_WORDS = [
    ("music", r"\b(live music|music|concert|band|dj|nightlife|karaoke)\b"),
    ("water", r"\b(lake|boat|boating|water|paddle|kayak|sandbar|channel|cruise)\b"),
    ("classes", r"\b(class|classes|yoga|pilates|spin|pickleball|fitness|workout|barre|aerobics)\b"),
    ("family", r"\b(family|kid|kids|child|children|toddler|story ?time)\b"),
    ("events", r"\b(food|drink|dining|happy hour|taco|brunch|market|farmers)\b"),
]
_AUD_RE = re.compile(r"\b(kid|kids|child|children|toddler|family|son|daughter|year[\s-]?old|yo)\b", re.I)
# Senior audience intent ("what is there for seniors this week"). Checked before
# the kids matcher so a senior ask narrows to senior programming. Kept precise
# (no "bridge" — that's the London Bridge here) to avoid false positives.
_SENIOR_AUD_RE = re.compile(r"\b(senior|seniors|55\s*\+|older adults?|retirees?)\b", re.I)
_AGE_RE = re.compile(r"\b(\d{1,2})\s*(?:year[\s-]?old|yr|yo)\b", re.I)
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DOW_WORDS = {"monday": "Mon", "mon": "Mon", "tuesday": "Tue", "tue": "Tue", "tues": "Tue",
              "wednesday": "Wed", "wed": "Wed", "thursday": "Thu", "thu": "Thu", "thurs": "Thu",
              "friday": "Fri", "fri": "Fri", "saturday": "Sat", "sat": "Sat",
              "sunday": "Sun", "sun": "Sun"}


def parse_calendar_query(q: str) -> dict[str, Any]:
    """Extract calendar filters from a free-text query. Empty fields when absent."""
    s = (q or "").strip().lower()
    out: dict[str, Any] = {"part": "", "type": "", "aud": "", "age": "", "days": []}
    if not s:
        return out
    if "morning" in s:
        out["part"] = "morning"
    elif "afternoon" in s:
        out["part"] = "afternoon"
    elif any(w in s for w in ("evening", "tonight", "night", "after dark")):
        out["part"] = "evening"
    for key, pat in _TYPE_WORDS:
        if re.search(pat, s):
            out["type"] = key
            break
    if _SENIOR_AUD_RE.search(s):
        out["aud"] = "seniors"
    elif _AUD_RE.search(s):
        out["aud"] = "kids"
        out["type"] = out["type"] or "family"
    m = _AGE_RE.search(s)
    if m:
        out["age"] = m.group(1)
        out["aud"] = out["aud"] or "kids"
    days: list[str] = []
    if "today" in s or "tonight" in s:
        days.append("Today")
    if "tomorrow" in s:
        days.append("+1")
    if "weekend" in s:
        days += ["Sat", "Sun"]
    if re.search(r"\bthis week\b", s) or re.search(r"\ball week\b", s):
        days = []  # the whole window (note: \b so "this weekend" doesn't match)
    for word, dow in _DOW_WORDS.items():
        if re.search(rf"\b{word}\b", s):
            days.append(dow)
    # de-dup, preserve order
    out["days"] = list(dict.fromkeys(days))
    return out


# Explicit EVENT nouns only (2026-07-01 consolidated audit A3). The old
# matcher also fired on any parsed type/part/audience token, which captured
# evergreen directory asks: "waterfront dining"/"happy hour" via the events
# type words, "nightlife"/"date night" via the "night" part token, "party boat
# rental"/"lake havasu state park" via the water tokens, and bare "things to
# do". Those now route to real directory surfaces (leaf_query); /calendar is
# only for explicit time or event intent. ("things to do this weekend" still
# reaches the calendar via the days parse below.)
_DISCOVERY_RE = re.compile(
    r"\b(events?|calendar|what'?s (?:on|happening|going on)|happening|"
    r"concerts?|festival|live music|farmers? ?market|do (?:today|tonight|this))\b",
    re.I,
)


def is_discovery_query(q: str) -> bool:
    """True when a free-text query carries explicit time or event intent.

    Used by the concierge intent-router to send discovery queries to /calendar
    (vs a directory leaf for a service/business query). Deterministic: a parsed
    DAY filter (today / tonight / tomorrow / weekend / a weekday / this week is
    handled by the day-toggle default) or an explicit event noun. A parsed
    type/part/audience token alone no longer routes here -- "happy hour" is a
    bars ask, not a calendar ask.
    """
    s = (q or "").lower()
    f = parse_calendar_query(q)
    # "this week"/"all week" parse to days == [] (the whole window), so check
    # the phrase itself -- it is explicit time intent all the same.
    if f["days"] or re.search(r"\b(?:this|all) week\b", s):
        return True
    return bool(_DISCOVERY_RE.search(s))


# (build_calendar and its private helpers were deleted 2026-07-02: the legacy
# /calendar list view they rendered was removed with the HOME_REDESIGN flag
# collapse — the v4 month grid uses redesign.calendar_month_view. The intent
# parser above stays: chat routing (app/home/chat_route.py) still uses
# is_discovery_query/parse_calendar_query. NOTE: the legacy view's free-text
# narrowing ("for seniors" chip etc.) has no v4 equivalent — if that filter
# should exist on the v4 calendar it's a new feature, not a revert.)
