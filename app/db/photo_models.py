"""Owner-uploaded photo ORM model, sliced out of app/db/models.py (audit
2026-07-01 decomposition).

Registered with ``Base.metadata`` the same way ``monetization_models`` is: it
imports only ``Base`` (+ SQLAlchemy) and never ``app.db.models`` or
``entity_dual_write``, so importing it is cycle-free regardless of load order.
Its ``Entity`` / ``User`` links are string relationships, resolved lazily at
mapper-configure time, so no cross-model import is needed here.

``app.db.models`` re-exports ``Photo`` so every existing
``from app.db.models import Photo`` keeps resolving.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models import Entity, User


class Photo(Base):
    """Owner-uploaded photo for an Entity (commercial / place in V1).

    FK to entities.id with ON DELETE CASCADE (master plan §4 Phase 2 amendment
    over the design memo's polymorphic-no-FK shape — Phase 1's ENTITY pivot
    unifies the target). Entity.entity_type discriminates; no duplicate column
    on photos. App-layer validation on insert: assert
    entities.entity_type IN ('commercial', 'place'). Events + programs are
    NOT photo-uploadable in V1 — guarded at the route level.
    """

    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading', 'processing', 'live', 'flagged', 'deleted')",
            name="ck_photos_status",
        ),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_photos_mime_type",
        ),
        Index("ix_photos_entity_id", "entity_id"),
        Index("ix_photos_uploaded_by_user_id", "uploaded_by_user_id"),
        Index("ix_photos_status", "status"),
        Index("ix_photos_image_hash", "image_hash"),
        Index("ix_photos_entity_hash_status", "entity_id", "image_hash", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    cdn_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    medium_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    hero_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hero: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="uploading", server_default="uploading"
    )
    processing_error: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])
    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_user_id])
