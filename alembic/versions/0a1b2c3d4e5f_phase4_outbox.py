"""Phase 4.1 — must-not-lose ``outbox`` table for the background-jobs scaffold.

Revision ID: 0a1b2c3d4e5f
Revises: e1f2a3b4c5d6
Create Date: 2026-05-13

Phase 4.1 (Option A locked per ``docs/maintainability/background_job_infrastructure_decision.md``)
adds an Outbox row per must-not-lose job. V1 consumer is the magic-link
send path (silent Resend failure would cost a user signup). The redrive
script ``scripts/outbox_redrive.py`` sweeps for ``pending`` rows older
than 30s and invokes :func:`app.core.background.deliver_outbox_row` per
row on a Railway cron cadence (5 minutes per design memo §6.2).

State machine (enforced via CHECK constraint on ``state``):

    pending --(deliver_outbox_row picks up)--> in_flight
    in_flight --(handler succeeded)--> delivered
    in_flight --(transient failure)--> pending (attempts += 1)
    in_flight --(attempts >= 5)--> failed

Portability:
- ``sa.JSON()`` for the payload column — both Postgres and SQLite OK
  (Phase 1A ``b32fa2d6d1e0_add_hours_structured_to_providers.py`` precedent).
- ``sa.String(length=N)`` for stable VARCHAR widths.
- ``sa.func.now()`` for timestamp defaults (NOT ``sa.text('CURRENT_TIMESTAMP')``).
- ``sa.true()`` / ``sa.false()`` would be the pattern for Boolean defaults
  but no Boolean column here.
- Integer column ``attempts`` uses ``server_default="0"`` (Phase 2B.1 photos
  precedent at column ``display_order``).
- ``state`` + ``kind`` use VARCHAR + CHECK constraint (NOT Postgres-native
  ENUM) per the Option-A scope guardrail and Phase 2A.1 ``users.role``
  precedent.
- Indexes on ``(state, created_at)`` (redrive-poll selectivity) and ``(kind)``
  (operator inspection).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('magic_link', 'sponsor_notification', 'image_processing', 'other')",
            name="ck_outbox_kind",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'in_flight', 'delivered', 'failed')",
            name="ck_outbox_state",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
    )
    op.create_index(
        "ix_outbox_state_created_at",
        "outbox",
        ["state", "created_at"],
        unique=False,
    )
    op.create_index("ix_outbox_kind", "outbox", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_outbox_kind", table_name="outbox")
    op.drop_index("ix_outbox_state_created_at", table_name="outbox")
    op.drop_table("outbox")
