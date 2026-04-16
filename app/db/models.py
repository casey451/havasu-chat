from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import uuid4

from sqlalchemy import Date, DateTime, JSON, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.schemas.event import EventCreate


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    normalized_title: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location_name: Mapped[str] = mapped_column(String, nullable=False)
    location_normalized: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="live", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    created_by: Mapped[str] = mapped_column(String, default="user", nullable=False)
    admin_review_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @classmethod
    def from_create(cls, payload: EventCreate) -> "Event":
        title = payload.title.strip()
        location_name = payload.location_name.strip()
        return cls(
            title=title,
            normalized_title=title.lower().strip(),
            date=payload.date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            location_name=location_name,
            location_normalized=location_name.lower().strip(),
            description=payload.description.strip(),
            event_url=payload.event_url.strip(),
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            tags=payload.tags,
            embedding=payload.embedding,
            status=payload.status,
            created_by=payload.created_by,
            admin_review_by=payload.admin_review_by,
        )
