"""Phase 2B.1 — owner-uploaded ``photos`` table (R2 keys + URLs + lifecycle).

Revision ID: f9e8d7c6b5a4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-12

Chains Phase 2B.2 FTS migration. Boolean defaults use ``sa.true()`` /
``sa.false()``; timestamps use ``sa.func.now()`` where a server default is
required (Phase 2A.1 precedent).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f9e8d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=32), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("cdn_url", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1024), nullable=True),
        sa.Column("medium_url", sa.String(length=1024), nullable=True),
        sa.Column("hero_url", sa.String(length=1024), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "is_hero",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="uploading",
        ),
        sa.Column("processing_error", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('uploading', 'processing', 'live', 'flagged', 'deleted')",
            name="ck_photos_status",
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_photos_mime_type",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_photos_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_photos_uploaded_by_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photos_entity_id", "photos", ["entity_id"], unique=False)
    op.create_index(
        "ix_photos_uploaded_by_user_id",
        "photos",
        ["uploaded_by_user_id"],
        unique=False,
    )
    op.create_index("ix_photos_status", "photos", ["status"], unique=False)
    op.create_index("ix_photos_image_hash", "photos", ["image_hash"], unique=False)
    op.create_index(
        "ix_photos_entity_hash_status",
        "photos",
        ["entity_id", "image_hash", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_photos_entity_hash_status", table_name="photos")
    op.drop_index("ix_photos_image_hash", table_name="photos")
    op.drop_index("ix_photos_status", table_name="photos")
    op.drop_index("ix_photos_uploaded_by_user_id", table_name="photos")
    op.drop_index("ix_photos_entity_id", table_name="photos")
    op.drop_table("photos")
