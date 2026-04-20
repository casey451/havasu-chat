"""Tier 1 regex + template responses (see HAVASU_CHAT_MASTER.md §3.3, §7, §8).

Exports:

- ``INTENT_PATTERNS`` — ordered ``(intent, compiled_regex)`` pairs. The Step 3
  classifier consumes this in order; first match wins. More specific intents
  come before broader ones (e.g. WEBSITE before PHONE before HOURS before DATE).
- ``TEMPLATES`` — per-intent response variants with ``.format(**slots)`` placeholders.
  Each variant is authored to pass the §7 voice audit: 1–2 sentences, contractions,
  no filler, no follow-up questions, direct answer then stop.
- ``render(intent, entity, data, variant)`` — produces a Tier 1 string or ``None``
  when any required slot is missing. Per §3.9, ``None`` triggers fall-through to
  Tier 2 — callers must not substitute a generic apology.

Special cases from §3.3 / §8:

- ``COST_LOOKUP`` with ``CONTACT_FOR_PRICING`` (or ``show_pricing_cta=True`` on the
  entity) switches to the call-for-pricing variant and requires a phone slot.
- ``HOURS_LOOKUP`` with ``closed_today=True`` in ``data`` switches to the
  closed-state variant.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping
from datetime import date
from typing import Any


INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("WEBSITE_LOOKUP", re.compile(r"\b(website|site|url|web address)\b")),
    ("PHONE_LOOKUP", re.compile(r"\b(phone number|phone|contact number|call them|number)\b")),
    ("AGE_LOOKUP", re.compile(r"\b(age groups?|age range|age requirements?|ages?|how old|youngest age)\b")),
    ("COST_LOOKUP", re.compile(r"\b(how much|cost|costs|pricing|price|fees?)\b")),
    ("TIME_LOOKUP", re.compile(r"\b(what time|start time|opening time|closing time|open time|close time)\b")),
    ("HOURS_LOOKUP", re.compile(r"\b(hours|open now|open right now)\b")),
    ("LOCATION_LOOKUP", re.compile(r"\b(where|located|location|address)\b")),
    ("DATE_LOOKUP", re.compile(r"\b(when|dates?)\b")),
]


TEMPLATES: dict[str, list[str]] = {
    # DATE_LOOKUP is also used for NEXT_OCCURRENCE in tier1_handler — ISO dates are spoken (no YYYY-MM-DD).
    "DATE_LOOKUP": [
        "{program} is {date}.",
        "The next {program} is {date}.",
        "{program}'s on {date}.",
    ],
    "TIME_LOOKUP": [
        "{program} starts at {time}.",
        "It kicks off at {time}.",
        "Starts {time}.",
    ],
    "LOCATION_LOOKUP": [
        "{name} is at {address}.",
        "It's at {address}.",
        "Address: {address}.",
    ],
    "COST_LOOKUP": [
        "{program} is {cost}.",
        "Runs {cost}.",
        "Cost: {cost}.",
    ],
    "COST_LOOKUP_CONTACT": [
        "{name} doesn't post pricing — call {phone}.",
        "No public pricing. Call {name} at {phone}.",
    ],
    "PHONE_LOOKUP": [
        "{name}: {phone}.",
        "Call them at {phone}.",
        "{phone}.",
    ],
    "HOURS_LOOKUP": [
        "{name} is open {hours}.",
        "Hours: {hours}.",
    ],
    "HOURS_LOOKUP_CLOSED_TODAY": [
        "{name} is closed today.",
        "Closed today — back tomorrow.",
    ],
    "WEBSITE_LOOKUP": [
        "{name}: {website}",
        "Site: {website}",
    ],
    "AGE_LOOKUP": [
        "{program} is for ages {age_range}.",
        "Ages {age_range}.",
    ],
}


_REQUIRED_SLOTS: dict[str, tuple[str, ...]] = {
    "DATE_LOOKUP": ("program", "date"),
    "TIME_LOOKUP": ("program", "time"),
    "LOCATION_LOOKUP": ("name", "address"),
    "COST_LOOKUP": ("program", "cost"),
    "PHONE_LOOKUP": ("name", "phone"),
    "HOURS_LOOKUP": ("name", "hours"),
    "WEBSITE_LOOKUP": ("name", "website"),
    "AGE_LOOKUP": ("program", "age_range"),
}

CONTACT_FOR_PRICING = "CONTACT_FOR_PRICING"

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _naturalize_iso_date_slot(value: str) -> str:
    """Turn YYYY-MM-DD into spoken dates; leave ranges and prose unchanged."""
    v = (value or "").strip()
    m = _ISO_DATE.match(v)
    if not m:
        return value
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    dt = date(y, mo, d)
    return f"{dt.strftime('%A')}, {dt.strftime('%B')} {dt.day}, {dt.year}"


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _build_slots(entity: Any, data: Mapping[str, Any] | None) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    for field in ("provider_name", "name", "address", "phone", "website", "hours"):
        val = _get(entity, field)
        if val:
            slots[field] = val
    if "name" not in slots and "provider_name" in slots:
        slots["name"] = slots["provider_name"]
    if "program" not in slots and "provider_name" in slots:
        slots["program"] = slots["provider_name"]
    if data:
        for k, v in data.items():
            if v is not None and v != "":
                slots[k] = v
    return slots


def _pick(variants: list[str], variant: int | None) -> str:
    if variant is not None:
        return variants[variant % len(variants)]
    return random.choice(variants)


def render(
    intent: str,
    entity: Any,
    data: Mapping[str, Any] | None = None,
    variant: int | None = None,
) -> str | None:
    """Return a Tier 1 string, or ``None`` when the template can't be filled.

    ``None`` is the signal for the router (§3.6) to fall through to Tier 2 — never
    substitute a generic apology here.
    """
    if intent not in _REQUIRED_SLOTS:
        return None

    data_map = data or {}

    if intent == "COST_LOOKUP":
        cost = data_map.get("cost")
        show_cta = bool(_get(entity, "show_pricing_cta") or data_map.get("show_pricing_cta"))
        if cost == CONTACT_FOR_PRICING or (cost in (None, "") and show_cta):
            slots = _build_slots(entity, data)
            if not slots.get("name") or not slots.get("phone"):
                return None
            return _pick(TEMPLATES["COST_LOOKUP_CONTACT"], variant).format(**slots)

    if intent == "HOURS_LOOKUP" and data_map.get("closed_today"):
        slots = _build_slots(entity, data)
        if not slots.get("name"):
            return None
        return _pick(TEMPLATES["HOURS_LOOKUP_CLOSED_TODAY"], variant).format(**slots)

    slots = _build_slots(entity, data)
    for required in _REQUIRED_SLOTS[intent]:
        if not slots.get(required):
            return None

    if intent == "DATE_LOOKUP" and slots.get("date") is not None:
        slots["date"] = _naturalize_iso_date_slot(str(slots["date"]))

    try:
        return _pick(TEMPLATES[intent], variant).format(**slots)
    except (KeyError, IndexError):
        return None
