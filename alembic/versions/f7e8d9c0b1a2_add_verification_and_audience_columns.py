"""add verification timestamps, sponsor verified_fields_present, chat audience_signal

Lane S1 — Phase 1 schema additions (disclosure renderer + cohort analytics).

* ``providers``: ``last_verified_at`` (nullable), ``verification_method`` (nullable,
  CHECK allows manual / scraper / owner_confirmed / npi_registry / none).
* ``events``: ``last_verified_at`` (nullable).
* ``sponsors``: ``verified_fields_present`` (NOT NULL, server default false).
* ``chat_logs``: ``audience_signal`` (nullable, CHECK visitor / local / ambiguous).

Partial index ``ix_chat_logs_audience_signal`` supports Phase 2 cohort queries.

Revision ID: f7e8d9c0b1a2
Revises: 2a3b4c5d6e7f
Create Date: 2026-05-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7e8d9c0b1a2"
down_revision: Union[str, Sequence[str], None] = "2a3b4c5d6e7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("verification_method", sa.String(32), nullable=True))
        batch_op.create_check_constraint(
            "ck_providers_verification_method",
            sa.text(
                "verification_method IS NULL OR verification_method IN ("
                "'manual', 'scraper', 'owner_confirmed', 'npi_registry', 'none'"
                ")"
            ),
        )

    op.add_column("events", sa.Column("last_verified_at", sa.DateTime(), nullable=True))

    op.add_column(
        "sponsors",
        sa.Column(
            "verified_fields_present",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    with op.batch_alter_table("chat_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("audience_signal", sa.String(16), nullable=True))
        batch_op.create_check_constraint(
            "ck_chat_logs_audience_signal",
            sa.text(
                "audience_signal IS NULL OR audience_signal IN ('visitor', 'local', 'ambiguous')"
            ),
        )

    op.create_index(
        "ix_chat_logs_audience_signal",
        "chat_logs",
        ["audience_signal"],
        postgresql_where=sa.text("audience_signal IS NOT NULL"),
        sqlite_where=sa.text("audience_signal IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_logs_audience_signal", table_name="chat_logs")

    with op.batch_alter_table("chat_logs", schema=None) as batch_op:
        batch_op.drop_constraint("ck_chat_logs_audience_signal", type_="check")
        batch_op.drop_column("audience_signal")

    op.drop_column("sponsors", "verified_fields_present")

    op.drop_column("events", "last_verified_at")

    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_providers_verification_method", type_="check")
        batch_op.drop_column("verification_method")
        batch_op.drop_column("last_verified_at")
