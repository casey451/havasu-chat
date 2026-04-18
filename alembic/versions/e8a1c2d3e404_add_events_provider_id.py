"""add events.provider_id fk to providers

Revision ID: e8a1c2d3e404
Revises: e8a1c2d3e403
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a1c2d3e404"
down_revision: Union[str, Sequence[str], None] = "e8a1c2d3e403"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_events_provider_id_providers",
            "providers",
            ["provider_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("fk_events_provider_id_providers", type_="foreignkey")
        batch_op.drop_column("provider_id")
