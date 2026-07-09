"""movie_showtimes table

Dedicated table for movie showtimes (the /movies surface), off the events
pipeline. Boolean columns use ``sa.false()`` server defaults so the emitted DDL
is valid on BOTH Postgres (``DEFAULT false``) and SQLite (``DEFAULT 0``) — the
previous integer ``0`` default passed on SQLite but failed on prod Postgres with
``DatatypeMismatch: column "is_sold_out" is of type boolean but default
expression is of type integer``.

Revision ID: bae799ca267d
Revises: a1b2c3d4e5f7
Create Date: 2026-06-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import app.db.types

revision = "bae799ca267d"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "movie_showtimes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_stable_id", sa.String(length=128), nullable=False),
        sa.Column("theater_slug", sa.String(length=64), nullable=False),
        sa.Column("theater_name", sa.String(length=120), nullable=False),
        sa.Column("film_title", sa.String(length=255), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=True),
        sa.Column("genre", sa.String(length=120), nullable=True),
        sa.Column("runtime_minutes", sa.Integer(), nullable=True),
        sa.Column("director", sa.String(length=255), nullable=True),
        sa.Column("synopsis", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.String(length=2048), nullable=True),
        sa.Column("screen", sa.String(length=64), nullable=True),
        sa.Column("show_date", sa.Date(), nullable=False),
        sa.Column("show_time", sa.Time(), nullable=False),
        sa.Column("booking_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "is_sold_out", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("is_free", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("scraped_at", app.db.types.TZAwareDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "source_stable_id", name="uq_movie_showtimes_source_stable"
        ),
    )
    op.create_index(
        "ix_movie_showtimes_show_date", "movie_showtimes", ["show_date"], unique=False
    )
    op.create_index(
        "ix_movie_showtimes_theater_slug",
        "movie_showtimes",
        ["theater_slug"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_movie_showtimes_theater_slug", table_name="movie_showtimes")
    op.drop_index("ix_movie_showtimes_show_date", table_name="movie_showtimes")
    op.drop_table("movie_showtimes")
