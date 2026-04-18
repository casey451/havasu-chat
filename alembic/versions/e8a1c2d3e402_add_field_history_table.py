"""add field_history table

Revision ID: e8a1c2d3e402
Revises: e8a1c2d3e401
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a1c2d3e402"
down_revision: Union[str, Sequence[str], None] = "e8a1c2d3e401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "field_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("submitted_by_session", sa.String(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column(
            "confirmations",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "disputes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("resolution_deadline", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_value", sa.Text(), nullable=True),
        sa.Column("resolution_source", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_field_history_entity_field",
        "field_history",
        ["entity_type", "entity_id", "field_name"],
        unique=False,
    )
    op.create_index(
        "ix_field_history_state_resolution_deadline",
        "field_history",
        ["state", "resolution_deadline"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_field_history_state_resolution_deadline",
        table_name="field_history",
    )
    op.drop_index("ix_field_history_entity_field", table_name="field_history")
    op.drop_table("field_history")
