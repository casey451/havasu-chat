"""Scraper auto-publish — contribution confidence + entity targeting/audit.

Revision ID: c3d4e5f6a7b8
Revises: d7e8f9a0b1c2
Create Date: 2026-06-04

Additive, all-nullable columns on ``contributions`` for the schedule-hunt
auto-publish loop:
  - ``confidence``         worker-supplied 0–1 score gating auto-publish
  - ``target_entity_id``   existing venue Entity a class schedule belongs to
  - ``created_entity_id``  audit pointer for the attach-to-existing-entity path
                           (writes Schedule/Offering but no Program row)
  - ``proposed_record``    structured ProgramApprovalFields-shaped JSON

Chains after ``d7e8f9a0b1c2`` (current head); single head preserved.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contributions", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("contributions", sa.Column("target_entity_id", sa.String(), nullable=True))
    op.add_column("contributions", sa.Column("created_entity_id", sa.String(), nullable=True))
    op.add_column("contributions", sa.Column("proposed_record", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("contributions", "proposed_record")
    op.drop_column("contributions", "created_entity_id")
    op.drop_column("contributions", "target_entity_id")
    op.drop_column("contributions", "confidence")
