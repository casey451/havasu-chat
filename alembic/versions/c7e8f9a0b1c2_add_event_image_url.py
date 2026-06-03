"""ED-3: add events.image_url (optional event image).

Purely additive (one nullable column); reversible. Lets the event permalink render
an ``<img>`` when an image URL is known — recovered by the field backfill from a
scrambled description's ``Image:`` line, or set on ingest.

Revision ID: c7e8f9a0b1c2
Revises: b1f2a3c4d5e6
Create Date: 2026-06-03
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "b1f2a3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("image_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "image_url")
