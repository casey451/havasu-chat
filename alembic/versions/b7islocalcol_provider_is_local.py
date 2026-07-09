"""B7: add providers.is_local (locality tri-state)

Revision ID: b7islocalcol
Revises: f2adcr8a9b0c
Create Date: 2026-06-14

Additive only — one NEW nullable column on ``providers``. No backfill here: the
column ships NULL ("unknown") for every existing row and is populated separately
by ``scripts/backfill_is_local.py`` (dry-run by default). Nothing reads the
column yet, so this is dormant on deploy.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7islocalcol"
down_revision: Union[str, Sequence[str], None] = "f2adcr8a9b0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("is_local", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("providers", "is_local")
