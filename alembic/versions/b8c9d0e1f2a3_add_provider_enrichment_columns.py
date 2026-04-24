"""add provider enrichment columns for google bulk import (Phase 8.11a)

Revision ID: b8c9d0e1f2a3
Revises: f3a1b2c3d4e5
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "f3a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("google_place_id", sa.String(), nullable=True))
    op.create_index("ix_providers_google_place_id", "providers", ["google_place_id"])
    op.add_column("providers", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("providers", sa.Column("lng", sa.Float(), nullable=True))
    op.add_column("providers", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("providers", sa.Column("match_confidence", sa.Float(), nullable=True))
    op.add_column("providers", sa.Column("enrichment_version", sa.String(), nullable=True))
    op.add_column("providers", sa.Column("raw_enrichment_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("providers", "raw_enrichment_json")
    op.drop_column("providers", "enrichment_version")
    op.drop_column("providers", "match_confidence")
    op.drop_column("providers", "embedding")
    op.drop_column("providers", "lng")
    op.drop_column("providers", "lat")
    op.drop_index("ix_providers_google_place_id", table_name="providers")
    op.drop_column("providers", "google_place_id")
