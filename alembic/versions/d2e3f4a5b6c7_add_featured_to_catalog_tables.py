"""add featured boolean to events / programs / providers (BUILD.md step 2)

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3c4d5e6
Create Date: 2026-05-08

Adds a `featured: bool` column to each of the three catalog tables. Used by
the new /home page to surface "Hava's pick" cards (one per row, three on the
home). Hand-curated for now via DB script; surfacing the toggle in /admin is
a deferred decision (see BUILD.md "Hava's pick" badges section).

Distinct from `Provider.tier` / `sponsored_until` / `featured_description` —
those are for paid spotlight placement (BUILD.md "Spotlight architecture").
`featured` is editorial; spotlight is commercial.

Additive only. Default false on all existing rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("events", "programs", "providers")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "featured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "featured")
