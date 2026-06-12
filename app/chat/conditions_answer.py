"""Deterministic live-conditions answers for the chat pipeline (Phase 6).

QA diagnostic 2026-06-12 (P1-4): "what is the water temperature today?",
"is it too windy to kayak this afternoon?", "what's the air quality?" answered
inconsistently — Tier 3 sometimes wove conditions in, but other phrasings hit an
out-of-scope refusal or a grab-bag. The live data already exists in the
conditions cache (`build_conditions_api_payload`); this module answers the
common value-seeking conditions questions directly, before the catalog tiers, so
they're consistent regardless of routing.

Scope discipline: fires ONLY on value-seeking conditions questions ("how windy
is it", "water temp today"). A place question with a weather modifier ("a
dog-friendly place to cool off in hot weather") does NOT match here — it has no
value-seeking pattern — and falls through to the catalog tiers unchanged.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Dimension detectors (ordered: most specific first). Each value-seeking pattern
# maps to one conditions dimension we can answer from the cache.
_WATER_TEMP_RE = re.compile(
    r"\bwater\s+temp(?:erature)?\b|\bhow\s+(?:warm|cold)\s+is\s+the\s+water\b", re.I
)
_LAKE_LEVEL_RE = re.compile(
    r"\b(?:lake|water)\s+level\b|\blake\s+gauge\b|\bhow\s+(?:high|low)\s+is\s+the\s+(?:lake|water)\b",
    re.I,
)
_AQI_RE = re.compile(r"\bair\s+quality\b|\baqi\b|\bhow'?s\s+the\s+air\b|\bis\s+it\s+smok", re.I)
_WIND_RE = re.compile(
    r"\bhow\s+windy\b|\btoo\s+windy\b|\bis\s+it\s+windy\b|\bwind\s+(?:speed|today|"
    r"right\s+now|conditions|outlook)\b|\bwindy\s+(?:today|out|right\s+now|this\s+"
    r"(?:morning|afternoon|evening))\b",
    re.I,
)
_ALERTS_RE = re.compile(
    r"\b(?:weather|heat|safety|wind)\s+(?:advisor|alert|warning)|\bany\s+(?:advisor|alert|"
    r"warning)s?\b|\bnws\s+alert|\bheat\s+advisory\b",
    re.I,
)
_AIR_TEMP_RE = re.compile(
    r"\bair\s+temp(?:erature)?\b|\bhow\s+(?:hot|cold|warm)\s+is\s+it\b|\bis\s+it\s+"
    r"(?:too\s+)?(?:hot|cold)\b|\btemperature\s+(?:today|right\s+now|outside|now)\b|"
    r"\bhow'?s\s+the\s+heat\b|\bwhat'?s\s+the\s+temp(?:erature)?\b",
    re.I,
)
_GENERAL_WEATHER_RE = re.compile(
    r"\bwhat'?s\s+the\s+weather\b|\bweather\s+(?:right\s+now|today|like|outlook)\b|"
    r"\bhow'?s\s+the\s+weather\b",
    re.I,
)
_PADDLE_RE = re.compile(r"\b(?:kayak|paddle|sup|canoe|paddleboard|row)\w*\b", re.I)


def detect_conditions_dimension(query: str) -> str | None:
    """Return the conditions dimension a value-seeking query asks about, else None."""
    q = query or ""
    if _WATER_TEMP_RE.search(q):
        return "water_temp"
    if _LAKE_LEVEL_RE.search(q):
        return "lake_level"
    if _AQI_RE.search(q):
        return "aqi"
    if _WIND_RE.search(q):
        return "wind"
    if _ALERTS_RE.search(q):
        return "alerts"
    if _AIR_TEMP_RE.search(q):
        return "air_temp"
    if _GENERAL_WEATHER_RE.search(q):
        return "general"
    return None


def _i(val: object) -> int | None:
    try:
        return round(float(val))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


_SOURCE_NUDGE = "Conditions update through the day — see the Today strip on askhava.com for the latest."


def _format(dimension: str, payload: dict, query: str) -> str | None:
    """Format a concise answer for ``dimension`` from a conditions payload."""
    if dimension == "water_temp":
        wt = _i(payload.get("water_temp_f"))
        if wt is None:
            return (
                "I don't have a current water-temperature reading right now — the USGS gauge "
                "isn't reporting. golakehavasu.com or a launch ramp can confirm."
            )
        stale = " (last good reading — may be a bit behind)" if payload.get("water_temp_is_stale") else ""
        return f"Lake Havasu's water is about {wt}°F right now{stale}. {_SOURCE_NUDGE}"

    if dimension == "lake_level":
        ft = payload.get("lake_gauge_ft")
        if ft is None:
            return f"I don't have a current lake-level reading right now. {_SOURCE_NUDGE}"
        return f"Lake Havasu is sitting at about {ft} ft right now. {_SOURCE_NUDGE}"

    if dimension == "aqi":
        aqi = _i(payload.get("current_aqi"))
        if aqi is None:
            return f"I don't have a current air-quality reading right now. {_SOURCE_NUDGE}"
        param = payload.get("current_aqi_parameter")
        band = (
            "good" if aqi <= 50 else "moderate" if aqi <= 100
            else "unhealthy for sensitive groups" if aqi <= 150 else "unhealthy"
        )
        param_txt = f" ({param})" if param else ""
        return f"Air quality is {aqi}{param_txt} right now — {band}. {_SOURCE_NUDGE}"

    if dimension == "wind":
        mph = _i(payload.get("wind_speed_mph"))
        if mph is None:
            return f"I don't have a current wind reading right now. {_SOURCE_NUDGE}"
        card = payload.get("wind_direction_cardinal")
        from_txt = f" out of the {card}" if card else ""
        if mph < 8:
            feel = "light — good for paddling"
        elif mph <= 15:
            feel = "breezy but manageable; the water can chop up in the afternoon"
        else:
            feel = "strong — expect chop, and use caution on the open water"
        if _PADDLE_RE.search(query or ""):
            feel = feel.replace("for paddling", "for getting on the water")
        return f"Winds are about {mph} mph{from_txt} right now — {feel}. {_SOURCE_NUDGE}"

    if dimension == "alerts":
        alerts = payload.get("active_nws_alerts") or []
        if not alerts:
            return (
                "No active National Weather Service alerts for Lake Havasu right now. "
                "Heat is the usual concern in summer — plan water and shade."
            )
        names = []
        for a in alerts[:3]:
            if isinstance(a, dict):
                names.append(a.get("event") or a.get("headline") or "alert")
            else:
                names.append(str(a))
        return f"Active NWS alert(s) for Lake Havasu: {', '.join(names)}. Check askhava.com for details."

    if dimension in ("air_temp", "general"):
        t = _i(payload.get("current_temp_f"))
        if t is None:
            return f"I don't have a current temperature reading right now. {_SOURCE_NUDGE}"
        heat = _i(payload.get("heat_index_f"))
        sky = payload.get("sky_condition")
        bits = [f"It's about {t}°F in Lake Havasu right now"]
        if heat is not None and heat - t >= 4:
            bits.append(f"feels like {heat}°F")
        if dimension == "general":
            if sky:
                bits.append(str(sky).lower())
            mph = _i(payload.get("wind_speed_mph"))
            if mph is not None:
                bits.append(f"wind ~{mph} mph")
        lead = ", ".join(bits) + "."
        if t >= 100:
            lead += " Plan early-morning or indoor/shaded options and bring water."
        return f"{lead} {_SOURCE_NUDGE}"

    return None


def answer_conditions(query: str, db: "Session") -> str | None:
    """Direct answer for a value-seeking conditions question, or None to fall through."""
    dimension = detect_conditions_dimension(query)
    if dimension is None:
        return None
    from app.conditions.api_payload import build_conditions_api_payload

    payload = build_conditions_api_payload(db) or {}
    return _format(dimension, payload, query)
