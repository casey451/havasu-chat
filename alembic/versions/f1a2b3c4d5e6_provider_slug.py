"""Add Provider.slug column + backfill from provider_name.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-05-13

Adds a URL-safe slug column to providers, backfills from provider_name
with collision handling, and flips the NOT NULL constraint after the
backfill. See app/utils/slug.py for the slug shape.

"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "untitled"


def _make_unique(base, used, max_length=96):
    base = base[:max_length].rstrip("-") or "untitled"
    if base not in used:
        used.add(base)
        return base
    n = 2
    while True:
        candidate = f"{base}-{n}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_providers_slug", ["slug"], unique=True)

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, provider_name FROM providers ORDER BY id")).fetchall()
    used: set[str] = set()
    for row in rows:
        rid = row[0]
        pname = row[1]
        slug = _make_unique(_slugify(pname), used)
        conn.execute(
            sa.text("UPDATE providers SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": rid},
        )

    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(length=120), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_index("ix_providers_slug")
        batch_op.drop_column("slug")
