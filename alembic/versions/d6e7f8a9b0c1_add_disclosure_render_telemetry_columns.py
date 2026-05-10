"""add disclosure renderer observability columns on chat_logs (P2.OBS.1)

Typed scalar columns for Phase 2 audit queries (GROUP BY / aggregates).
Partial index supports cohort reads where disclosure ran.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chat_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("disclosure_regime", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("disclosure_sponsor_id", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("disclosure_tone_allowlist_passed", sa.Boolean(), nullable=True)
        )
        batch_op.add_column(sa.Column("disclosure_eligible", sa.Boolean(), nullable=True))
        batch_op.create_check_constraint(
            "ck_chat_logs_disclosure_regime",
            sa.text(
                "disclosure_regime IS NULL OR disclosure_regime IN ("
                "'specific_quality', 'generic_category', 'emergency_urgent'"
                ")"
            ),
        )

    op.create_index(
        "ix_chat_logs_disclosure_regime",
        "chat_logs",
        ["disclosure_regime"],
        postgresql_where=sa.text("disclosure_regime IS NOT NULL"),
        sqlite_where=sa.text("disclosure_regime IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_logs_disclosure_regime", table_name="chat_logs")

    with op.batch_alter_table("chat_logs", schema=None) as batch_op:
        batch_op.drop_constraint("ck_chat_logs_disclosure_regime", type_="check")
        batch_op.drop_column("disclosure_eligible")
        batch_op.drop_column("disclosure_tone_allowlist_passed")
        batch_op.drop_column("disclosure_sponsor_id")
        batch_op.drop_column("disclosure_regime")
