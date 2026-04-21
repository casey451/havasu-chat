"""Tier 2 structured filters (Phase 4.1) — schema for parser output / Phase 4.2 queries."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

_TIME_WINDOWS = frozenset(
    {"today", "tomorrow", "this_week", "this_weekend", "this_month", "upcoming"}
)
_DAYS = frozenset(
    {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
)


class Tier2Filters(BaseModel):
    # Entity-level
    entity_name: Optional[str] = None  # "Altitude", "Bridge City Combat"
    category: Optional[str] = None  # "bmx", "gymnastics", "dance" — free text

    # Demographic
    age_min: Optional[int] = None  # from "6-year-old" → 6
    age_max: Optional[int] = None  # from "ages 5–12" → 12

    # Spatial
    location: Optional[str] = None  # "Sara Park", "Rotary Park", "downtown"

    # Temporal
    day_of_week: Optional[List[str]] = None  # ["saturday"], ["saturday","sunday"] for "weekend"
    time_window: Optional[str] = None  # one of: today, tomorrow, this_week, ...

    open_now: bool = False

    # Routing signal
    parser_confidence: float = Field(..., ge=0.0, le=1.0)
    fallback_to_tier3: bool = False

    @field_validator("open_now", mode="before")
    @classmethod
    def _open_now_coerce(cls, v: object) -> bool:
        if v is None:
            return False
        return bool(v)

    @field_validator("time_window")
    @classmethod
    def _time_window_allowed(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in _TIME_WINDOWS:
            raise ValueError("time_window must be one of the allowed window strings")
        return v

    @field_validator("day_of_week")
    @classmethod
    def _day_of_week_allowed(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        normalized: list[str] = []
        for d in v:
            low = d.lower()
            if low not in _DAYS:
                raise ValueError("day_of_week entries must be english weekday names")
            normalized.append(low)
        return normalized
