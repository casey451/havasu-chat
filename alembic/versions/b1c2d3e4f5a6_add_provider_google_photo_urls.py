"""add providers.google_photo_urls JSON (v48 photo resolver)

Revision ID: b1c2d3e4f5a6
Revises: acc50395da86
Create Date: 2026-05-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "acc50395da86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "providers", sa.Column("google_photo_urls", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("providers", "google_photo_urls")
