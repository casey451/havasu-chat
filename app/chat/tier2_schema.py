"""Tier 2 structured filters (Phase 4.1) — schema for parser output / Phase 4.2 queries."""

from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_TIME_WINDOWS = frozenset(
    {
        "today",
        "tomorrow",
        "this_week",
        "this_weekend",
        "this_month",
        "upcoming",
        "next_week",
        "next_month",
    }
)
_MONTHS = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)
_SEASONS = frozenset({"spring", "summer", "fall", "winter"})
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
    time_window: Optional[str] = None  # simple canonical window tokens, or null when using structured dates
    month_name: Optional[
        Literal[
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    ] = None
    season: Optional[Literal["spring", "summer", "fall", "winter"]] = None
    date_exact: Optional[date] = None
    date_start: Optional[date] = None
    date_end: Optional[date] = None

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

    @field_validator("month_name", mode="before")
    @classmethod
    def _month_name_normalize(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).lower().strip()
        if s not in _MONTHS:
            raise ValueError("month_name must be a full english month name in lowercase")
        return s  # type: ignore[return-value]

    @field_validator("season", mode="before")
    @classmethod
    def _season_normalize(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).lower().strip()
        if s not in _SEASONS:
            raise ValueError("season must be one of: spring, summer, fall, winter")
        return s  # type: ignore[return-value]

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

    @model_validator(mode="after")
    def _temporal_non_overlap(self) -> Tier2Filters:
        tw = self.time_window is not None
        mn = self.month_name is not None
        se = self.season is not None
        de = self.date_exact is not None
        dr = self.date_start is not None or self.date_end is not None
        n_groups = int(tw) + int(mn) + int(se) + int(de) + int(dr)
        if n_groups > 1:
            raise ValueError(
                "at most one of: time_window, month_name, season, date_exact, or date_start/date_end"
            )
        if (
            self.date_start is not None
            and self.date_end is not None
            and self.date_start > self.date_end
        ):
            raise ValueError("date_start must be on or before date_end")
        return self
