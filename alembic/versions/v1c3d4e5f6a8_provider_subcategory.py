"""Master spec §3.1 / P0 Task 2: providers.subcategory second level.

Adds the nullable ``subcategory`` column + index. Data backfill is a separate
idempotent step (``scripts/backfill_subcategory.py``) so this migration stays
purely structural and re-runs cleanly on any environment.

Revision ID: v1c3d4e5f6a8
Revises: v1b2c3d4e5f7
Create Date: 2026-06-01
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v1c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "v1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("subcategory", sa.String(), nullable=True))
    op.create_index("ix_providers_subcategory", "providers", ["subcategory"])


def downgrade() -> None:
    op.drop_index("ix_providers_subcategory", table_name="providers")
    op.drop_column("providers", "subcategory")
