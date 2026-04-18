"""expand programs with concierge columns

Revision ID: e8a1c2d3e403
Revises: e8a1c2d3e402
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a1c2d3e403"
down_revision: Union[str, Sequence[str], None] = "e8a1c2d3e402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode to add foreign keys (table rebuild).
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "show_pricing_cta",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        batch_op.add_column(sa.Column("cost_description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("schedule_note", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "draft",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        batch_op.add_column(
            sa.Column(
                "pending_review",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        batch_op.add_column(sa.Column("admin_review_by", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_programs_provider_id_providers",
            "providers",
            ["provider_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_programs_provider_id_providers", type_="foreignkey")
        batch_op.drop_column("admin_review_by")
        batch_op.drop_column("pending_review")
        batch_op.drop_column("draft")
        batch_op.drop_column("schedule_note")
        batch_op.drop_column("cost_description")
        batch_op.drop_column("show_pricing_cta")
        batch_op.drop_column("provider_id")
