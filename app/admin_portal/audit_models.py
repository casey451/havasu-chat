"""AdminAuditLog — standalone model on its OWN declarative Base.

Deliberately not on ``app.db.models.Base``: keeping it off the shared
metadata means alembic autogenerate cannot pick it up while the portal
is unwired, and importing this package never mutates app-wide state.
Mirrors the ``Job`` pattern: additive, standalone, no FKs.

The table is created by alembic migration ``e9b5d7f3a1c6`` (already promoted
into ``alembic/versions``). On any DB where that migration hasn't run yet,
``audit_enabled()`` is False and the portal skips audit writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, Text, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

AUDIT_TABLE_NAME = "admin_audit_log"


class PortalBase(DeclarativeBase):
    pass


class AdminAuditLog(PortalBase):
    """One row per admin action taken through the portal."""

    __tablename__ = AUDIT_TABLE_NAME
    __table_args__ = (
        Index("ix_admin_audit_log_created_at", "created_at"),
        Index("ix_admin_audit_log_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="admin")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


def audit_enabled(db: Session) -> bool:
    """True when the audit table exists in the connected database."""
    bind = db.get_bind()
    return inspect(bind).has_table(AUDIT_TABLE_NAME)


def record_audit(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: str,
    detail: str | None = None,
) -> None:
    """Best-effort audit write; silently a no-op until the table exists.

    Caller owns the commit — the row rides the same transaction as the
    action it describes, so action+audit land (or roll back) together.
    """
    if not audit_enabled(db):
        return
    db.add(
        AdminAuditLog(
            action=action, target_type=target_type, target_id=target_id, detail=detail
        )
    )
