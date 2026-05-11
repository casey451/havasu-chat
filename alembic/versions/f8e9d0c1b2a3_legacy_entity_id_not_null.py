"""Phase 1D — NOT NULL on legacy entity_id FK columns (dual-write complete).

Revision ID: f8e9d0c1b2a3
Revises: b2c3d4e5f6a7
Create Date: 2026-05-11

After Phase 1D dual-write helpers populate ``entity_id`` on every new insert,
flip the nullable FK to NOT NULL so legacy rows always reference ENTITY.

SQLite uses batch alter for portability with FK replay.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f8e9d0c1b2a3"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.alter_column(
            "entity_id",
            existing_type=sa.String(),
            nullable=False,
        )
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.alter_column(
            "entity_id",
            existing_type=sa.String(),
            nullable=False,
        )
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.alter_column(
            "entity_id",
            existing_type=sa.String(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.alter_column(
            "entity_id",
            existing_type=sa.String(),
            nullable=True,
        )
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.alter_column(
            "entity_id",
            existing_type=sa.String(),
            nullable=True,
        )
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.alter_column(
            "entity_id",
            existing_type=sa.String(),
            nullable=True,
        )
