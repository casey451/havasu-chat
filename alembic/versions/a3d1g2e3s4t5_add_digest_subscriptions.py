"""Phase A3: digest_subscriptions opt-in table.

Adds the ``digest_subscriptions`` table backing the "This weekend in Havasu"
weekend-digest opt-in (see :class:`app.db.models.DigestSubscription`). Purely
additive; reversible. Distinct from ``alert_subscriptions`` (conditions/traffic
alerts) so the two opt-in surfaces never share state.

NOTE: sibling Phase-A lanes also branch off ``d1e2f3a4b5c6``; this may create
parallel alembic heads needing an ``alembic merge`` by Casey. We do NOT run
``alembic upgrade`` here.

Revision ID: a3d1g2e3s4t5
Revises: d1e2f3a4b5c6
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a3d1g2e3s4t5"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "digest_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "delivery_channel",
            sa.String(length=16),
            nullable=False,
            server_default="email",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "delivery_channel IN ('email')",
            name="ck_digest_subscriptions_delivery_channel",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "delivery_channel",
            name="uq_digest_subscriptions_user_channel",
        ),
    )
    op.create_index(
        "ix_digest_subscriptions_user_id",
        "digest_subscriptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_digest_subscriptions_user_id",
        table_name="digest_subscriptions",
    )
    op.drop_table("digest_subscriptions")
