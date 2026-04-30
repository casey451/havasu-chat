from __future__ import annotations

import re
from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_event_url(value: str) -> str:
    s = value.strip()
    if not s:
        return s
    lower = s.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return s
    if "." in s:
        return f"https://{s}"
    return s


class EventBase(BaseModel):
    title: str
    date: date
    end_date: date | None = None
    start_time: time
    end_time: time | None = None
    location_name: str
    description: str
    event_url: str
    source_url: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_recurring: bool = False
    source: str | None = None
    embedding: list[float] | None = None
    status: str = "live"
    created_by: str = "user"
    admin_review_by: datetime | None = None

    @model_validator(mode="after")
    def end_date_on_or_after_start(self) -> EventBase:
        if self.end_date is not None and self.end_date < self.date:
            raise ValueError("end_date must be on or after date")
        return self

    @field_validator("title", "location_name", "description", "event_url", mode="before")
    @classmethod
    def strip_strings(cls, v: str | date | time | None) -> str | date | time | None:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("contact_name", "contact_phone", mode="before")
    @classmethod
    def empty_contact_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    @field_validator("event_url", mode="after")
    @classmethod
    def validate_loose_url(cls, v: str) -> str:
        v = normalize_event_url(v)
        if not v:
            raise ValueError("Add a link (website, Facebook, Eventbrite, etc.).")
        lower = v.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return v
        if "." in v:
            return v
        raise ValueError("That link should start with http(s):// or look like a website (include a dot).")

    @field_validator("title")
    @classmethod
    def title_length(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Title must be at least 3 characters long.")
        return v

    @field_validator("location_name")
    @classmethod
    def location_length(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Location must be at least 3 characters long.")
        return v

    @field_validator("description")
    @classmethod
    def description_length(cls, v: str) -> str:
        if len(v) < 20:
            raise ValueError("Description must be at least 20 characters long.")
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


class EventCreate(EventBase):
    pass


class EventRead(EventBase):
    id: str
    normalized_title: str
    location_normalized: str
    created_at: datetime

    model_config = {"from_attributes": True}
