from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, Text, Time
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
    source: Mapped[str] = mapped_column(String, default="admin", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    created_by: Mapped[str] = mapped_column(String, default="user", nullable=False)
    admin_review_by: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @classmethod
    def from_create(cls, payload: EventCreate) -> "Event":
        title = payload.title.strip()
        location_name = payload.location_name.strip()
        source = (getattr(payload, "source", None) or "admin").strip() or "admin"
        verified_in = getattr(payload, "verified", None)
        # Admin-submitted entries are auto-verified; other sources stay unverified
        # until AA-3's claim flow (or admin edit).
        verified = bool(verified_in) if verified_in is not None else source == "admin"
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
            source=source,
            verified=verified,
            created_by=payload.created_by,
            admin_review_by=payload.admin_review_by,
        )


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    activity_category: Mapped[str] = mapped_column(String, nullable=False)
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_days: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    schedule_start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    schedule_end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    location_name: Mapped[str] = mapped_column(String, nullable=False)
    location_address: Mapped[str | None] = mapped_column(String, nullable=True)
    cost: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source: Mapped[str] = mapped_column(String, default="admin", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
