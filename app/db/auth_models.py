"""Auth / identity ORM models, sliced out of app/db/models.py (audit 2026-07-01
decomposition): User, MagicLinkToken, AuthSession, UserFavorite, Claim.

Registered with ``Base.metadata`` like ``monetization_models`` — imports only
``Base`` (+ SQLAlchemy/types), never ``app.db.models`` or ``entity_dual_write``,
so importing it is cycle-free regardless of load order. Every cross-model link
(``User`` ⇄ ``AlertSubscription`` / ``PeerRecommendation``, ``*`` → ``Entity``)
is a string relationship resolved lazily from the mapper registry, so no
cross-model import is needed at load time.

``app.db.models`` re-exports these so every existing ``from app.db.models import
User`` keeps resolving.
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
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import TZAwareDateTime

if TYPE_CHECKING:
    from app.db.models import AlertSubscription, Entity, PeerRecommendation


class User(Base):
    """End-user / merchant / admin identity.

    Created on first successful magic-link callback. Role defaults to
    'end_user'; promoted to 'merchant' implicitly on first verified Claim;
    promoted to 'admin' SQL-only (V1) — design memo §10 Q7.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('end_user', 'merchant', 'admin')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "preferred_mode IN ('default', 'boat')",
            name="ck_users_preferred_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # email is lower-cased at write time — see normalize helper in app/auth/email_helpers.py.
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="end_user", server_default="end_user"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="default", server_default="default"
    )

    alert_subscriptions: Mapped[list["AlertSubscription"]] = relationship(
        "AlertSubscription",
        back_populates="user",
        passive_deletes=True,
    )
    peer_recommendations: Mapped[list["PeerRecommendation"]] = relationship(
        "PeerRecommendation",
        back_populates="recommender",
        passive_deletes=True,
        # String form (resolved from the mapper registry) rather than a lambda
        # referencing PeerRecommendation directly — the class now lives in a
        # sibling module, and a direct reference would force a circular import.
        foreign_keys="[PeerRecommendation.recommender_user_id]",
    )


class MagicLinkToken(Base):
    """Short-lived single-use token emailed via Resend.

    Plaintext is never stored — only SHA-256 of plaintext lives in DB. Pattern
    mirrors Contribution.submitter_ip_hash at app/db/models.py:354.
    """

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("ix_magic_link_tokens_email", "email"),
        Index("ix_magic_link_tokens_token_hash", "token_hash", unique=True),
        Index("ix_magic_link_tokens_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # NOT a FK to users — User row may not exist at request-link time
    # (first-time login creates the row on successful callback).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 hex digest of plaintext token. 64 chars.
    expires_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    # 15 minutes from created_at by default.
    consumed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    requested_from_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class AuthSession(Base):
    """Long-lived authenticated session.

    Cookie name 'hava_session'. Cookie value = itsdangerous-signed AuthSession.id.
    Cookie is HttpOnly + Secure (prod) + SameSite=Lax. Session row is the source
    of truth for 'is logged in'; signature is the integrity check.

    Mirrors the admin-cookie pattern at app/admin/auth.py:30 but signs a session
    id (UUID) instead of {"ok": True}.

    Class name ``AuthSession`` avoids clashing with ``sqlalchemy.orm.Session`` on
    this module's namespace during import-time circular edges (Phase 2A.1).
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    # 30 days from created_at. Absolute, no idle-extension in V1.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class UserFavorite(Base):
    """User-saved Entity (Provider / Place / Event in V1; Programs deferred).

    NOTE: master plan §4 Phase 2 Lane 2A explicitly amended the design memo's
    polymorphic (entity_type, entity_id) shape to a single FK pointing at
    entities.id. Entity.entity_type already discriminates; no duplicate column
    needed. App-layer validation at insert time asserts entity.entity_type
    is in the favoritable set (see app/auth/favorites.py validators).
    """

    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", name="uq_user_favorites_user_entity"),
        Index("ix_user_favorites_user_id", "user_id"),
        Index("ix_user_favorites_entity_id", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])


class Claim(Base):
    """Business-owner claim on an Entity.

    V1 only accepts entity_type IN ('commercial', 'place') — events + programs
    are not claimable. Validation at insert time. Status flips from 'pending' to
    'verified' (or 'rejected') via the admin review queue. A verified claim is
    the bridge between User identity and merchant-facing edit affordances; the
    Provider profile flips viewer_is_owner to True when current_user has a
    verified claim for that provider's entity_id.
    """

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", name="uq_claims_user_entity"),
        CheckConstraint(
            "status IN ('pending', 'verified', 'rejected')",
            name="ck_claims_status",
        ),
        CheckConstraint(
            "verification_method IS NULL OR verification_method IN ("
            "'phone_call_initiated_by_us', 'phone_call_initiated_by_them', "
            "'in_person', 'email_confirmation', 'business_card_handoff'"
            ")",
            name="ck_claims_verification_method",
        ),
        Index("ix_claims_user_id", "user_id"),
        Index("ix_claims_entity_id", "entity_id"),
        Index("ix_claims_status", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    verification_method: Mapped[str | None] = mapped_column(String(48), nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])
    verifier: Mapped["User | None"] = relationship("User", foreign_keys=[verified_by])
