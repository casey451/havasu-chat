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
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.home import events_views

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
    if _AUD_RE.search(s):
        out["aud"] = "kids"
        out["type"] = out["type"] or "family"
    m = _AGE_RE.search(s)
    if m:
        out["age"] = m.group(1)
        out["aud"] = "kids"
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


_DISCOVERY_RE = re.compile(
    r"\b(events?|things? to do|what'?s (?:on|happening|going on)|happening|tonight|"
    r"this weekend|weekend|this week|calendar|live music|concerts?|festival|"
    r"farmers? ?market|family fun|do (?:today|tonight|this))\b",
    re.I,
)


def is_discovery_query(q: str) -> bool:
    """True when a free-text query is a 'what's happening' discovery ask.

    Used by the concierge intent-router to send discovery queries to /calendar
    (vs a directory leaf for a service/business query). Deterministic: any
    extracted day/time/type/audience filter, or an explicit discovery phrase.
    """
    f = parse_calendar_query(q)
    if f["days"] or f["part"] or f["type"] or f["aud"]:
        return True
    return bool(_DISCOVERY_RE.search((q or "").lower()))


def _first_hour(time_label: str) -> float | None:
    """The first clock hour in a time label (24h), or None for TBD/all-day."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", (time_label or "").lower())
    if not m:
        return None
    h = int(m.group(1)) % 12
    if m.group(3) == "pm":
        h += 12
    return h + (int(m.group(2)) / 60 if m.group(2) else 0)


def _passes_part(time_label: str, part: str) -> bool:
    if not part:
        return True
    h = _first_hour(time_label)
    if h is None:  # all-day / TBD rows have no specific time — never filtered out
        return True
    lo, hi = _PART_WINDOWS[part]
    return lo <= h < hi


def _qs(**params: str) -> str:
    clean = {k: v for k, v in params.items() if v}
    return "/calendar" + ("?" + urlencode(clean) if clean else "")


def _title(part: str, type_: str, aud: str, age: str, day_labels: list[str], all_week: bool) -> str:
    if age:
        return f"Plans for your {age}-year-old"
    if aud == "kids":
        return "Family plans"
    if type_ and type_ != "events":
        return {"music": "Live music", "water": "On the water", "classes": "Classes",
                "family": "Family plans"}.get(type_, "Events & classes")
    if set(day_labels) == {"Sat", "Sun"}:
        return "This weekend"
    if day_labels == ["Today"]:
        return "Tonight" if part == "evening" else "Today in Havasu"
    if all_week:
        return "Events & classes this week"
    return "Events & classes"


def build_calendar(
    db: Session,
    *,
    q: str = "",
    aud: str = "",
    age: str = "",
    part: str = "",
    type_: str = "",
    days_param: str = "",
    today: date,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the /calendar view-model from real per-day events + classes."""
    # Seed filters from the free-text query only when not already set explicitly.
    parsed = parse_calendar_query(q)
    aud = aud or parsed["aud"]
    age = age or parsed["age"]
    part = part or parsed["part"]
    type_ = type_ if type_ in TYPE_TO_KEY else parsed["type"]
    family = aud == "kids"

    # The 7-day window: today + next 6, each with a dow label ("Today" for day 0).
    window = []
    for i in range(WINDOW_DAYS):
        d = today + timedelta(days=i)
        window.append({"date": d, "label": "Today" if i == 0 else _DOW[d.weekday()],
                       "iso": d.isoformat(), "daynum": d.day})

    # Resolve which days to show. Explicit `days` param wins; else parsed query;
    # else the whole window.
    want = [x for x in (days_param or "").split(",") if x] or parsed["days"]
    want = ["Today" if w == "today" else w for w in want]
    # "+1" (tomorrow) → that day's actual label.
    if "+1" in want and len(window) > 1:
        want = [window[1]["label"] if w == "+1" else w for w in want]
    selected = [c for c in window if c["label"] in want] if want else window
    if not selected:
        selected = window
    day_labels = [c["label"] for c in selected]
    all_week = len(selected) == len(window)

    type_key = TYPE_TO_KEY.get(type_, "")
    columns: list[dict[str, Any]] = []
    total = 0
    for col in selected:
        groups = events_views.day_groups(db, day=col["date"], family=family, now=now)
        items: list[dict[str, Any]] = []
        for g in groups:
            if type_key and g["key"] != type_key:
                continue
            rows = []
            if g.get("subgroups"):
                for sub in g["subgroups"]:
                    rows += sub["rows"]
            else:
                rows += g.get("rows", [])
            for r in rows:
                if not _passes_part(r.get("time_label", ""), part):
                    continue
                items.append({
                    "time_label": r.get("time_label", ""),
                    "title": r.get("title", ""),
                    "venue": r.get("venue"),
                    "url": r.get("url"),
                    "kind": "class" if g["key"] == "classes" else "event",
                    "group": g["key"],
                    "_h": _first_hour(r.get("time_label", "")),
                })
        items.sort(key=lambda it: (it["_h"] is None, it["_h"] or 0))
        total += len(items)
        # Key is "entries" (not "items"): Jinja's ``col.items`` resolves to the
        # dict's .items() method, shadowing a key named "items".
        columns.append({"label": col["label"], "iso": col["iso"], "daynum": col["daynum"],
                        "is_today": col["label"] == "Today", "count": len(items), "entries": items})

    # "Hava understood" removable chips — each links to /calendar without that filter.
    base = {"q": q, "aud": aud, "age": age, "part": part, "type": type_,
            "days": "" if all_week else ",".join(day_labels)}

    def _without(**drop: str) -> str:
        p = dict(base)
        p.update(drop)
        return _qs(**p)

    chips: list[dict[str, str]] = []
    if aud == "kids":
        chips.append({"label": f"Kids · age {age}" if age else "Kids",
                      "remove_url": _without(aud="", age="")})
    if not all_week:
        for c in selected:
            chips.append({"label": c["label"],
                          "remove_url": _without(days=",".join(x for x in day_labels if x != c["label"]))})
    if part:
        chips.append({"label": PART_LABELS[part], "remove_url": _without(part="")})
    if type_ in TYPE_LABELS:
        chips.append({"label": TYPE_LABELS[type_], "remove_url": _without(type="")})

    # Control options (segmented links). active + url per option.
    def _seg(field: str, current: str, options: list[tuple[str, str]]) -> list[dict[str, Any]]:
        out = []
        for val, label in options:
            p = dict(base)
            p[field] = val
            out.append({"label": label, "active": current == val, "url": _qs(**p)})
        return out

    return {
        "q": q,
        "title": _title(part, type_, aud, age, day_labels, all_week),
        "total": total,
        "columns": columns,
        "chips": chips,
        "understood": bool(q.strip() or aud or part or type_ or not all_week),
        "all_week": all_week,
        "window": window,
        "selected_labels": day_labels,
        "day_toggle_urls": [
            {**c, "active": c["label"] in day_labels,
             "url": _qs(**{**base, "days": ("" if (all_week and c["label"] in day_labels)
                                            else ",".join(dict.fromkeys(
                                                day_labels + [c["label"]] if c["label"] not in day_labels
                                                else [x for x in day_labels if x != c["label"]])))})}
            for c in window
        ],
        "seg_part": _seg("part", part, [("", "Any time"), ("morning", "Morning"),
                                        ("afternoon", "Afternoon"), ("evening", "Evening")]),
        "seg_type": _seg("type", type_, [("", "All"), ("events", "Around town"), ("music", "Music"),
                                         ("family", "Family"), ("water", "Lake"), ("classes", "Classes")]),
        "seg_aud": _seg("aud", aud, [("", "Anyone"), ("kids", "Kids")]),
    }
