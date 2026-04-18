from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_VALID_DAYS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ProgramBase(BaseModel):
    title: str
    description: str
    activity_category: str
    age_min: int | None = None
    age_max: int | None = None
    schedule_days: list[str] = Field(default_factory=list)
    schedule_start_time: str
    schedule_end_time: str
    location_name: str
    location_address: str | None = None
    cost: str | None = None
    provider_name: str
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_url: str | None = None
    source: str = "admin"
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None

    @field_validator(
        "title",
        "description",
        "activity_category",
        "location_name",
        "provider_name",
        mode="before",
    )
    @classmethod
    def strip_required_strings(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("title")
    @classmethod
    def title_length(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Title must be at least 3 characters long.")
        return v

    @field_validator("description")
    @classmethod
    def description_length(cls, v: str) -> str:
        if len(v) < 20:
            raise ValueError("Description must be at least 20 characters long.")
        return v

    @field_validator("activity_category")
    @classmethod
    def category_length(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("activity_category must be at least 2 characters long.")
        return v

    @field_validator("provider_name")
    @classmethod
    def provider_length(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("provider_name must be at least 2 characters long.")
        return v

    @field_validator("location_name")
    @classmethod
    def location_length(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Location must be at least 3 characters long.")
        return v

    @field_validator("schedule_start_time", "schedule_end_time")
    @classmethod
    def validate_hhmm(cls, v: str) -> str:
        if not isinstance(v, str) or not _HHMM_RE.match(v):
            raise ValueError("Schedule times must be in HH:MM format (e.g. 09:00).")
        return v

    @field_validator("schedule_days")
    @classmethod
    def validate_days(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError("schedule_days must be day-name strings.")
            lowered = item.strip().lower()
            if lowered not in _VALID_DAYS:
                raise ValueError(
                    f"'{item}' is not a valid day name. Use monday..sunday."
                )
            cleaned.append(lowered)
        return cleaned

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed = {"provider", "parent", "admin", "scraped"}
        if v not in allowed:
            raise ValueError(f"source must be one of {sorted(allowed)}.")
        return v

    @field_validator("age_min", "age_max")
    @classmethod
    def age_non_negative(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("Age values must be non-negative.")
        return v

    @field_validator("contact_phone")
    @classmethod
    def phone_looks_reasonable(cls, v: str | None) -> str | None:
        if v is None:
            return None
        digits = re.sub(r"\D", "", v)
        if len(digits) < 10:
            raise ValueError("Phone should include an area code and number (at least 10 digits).")
        return v

    @field_validator("contact_email")
    @classmethod
    def email_looks_reasonable(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if "@" not in v or "." not in v.split("@", 1)[-1]:
            raise ValueError("contact_email must look like an email address.")
        return v


class ProgramCreate(ProgramBase):
    pass


class ProgramRead(ProgramBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
