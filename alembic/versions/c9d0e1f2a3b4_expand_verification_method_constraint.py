"""Expand providers.verification_method CHECK to operator enrichment vocab.

Adds ``phone_call``, ``in_person``, ``web_form_submission``, and
``email_confirmation`` alongside legacy values so enrichment ingest can
persist operator-facing strings without lossy mapping.

Revision ID: c9d0e1f2a3b4
Revises: b4c5d6e7f8a9
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_providers_verification_method", type_="check")
        batch_op.create_check_constraint(
            "ck_providers_verification_method",
            sa.text(
                "verification_method IS NULL OR verification_method IN ("
                "'manual', 'scraper', 'owner_confirmed', 'npi_registry', 'none', "
                "'phone_call', 'in_person', 'web_form_submission', 'email_confirmation'"
                ")"
            ),
        )


def downgrade() -> None:
    # Reverse — note: any rows with the new vocab values must be remapped before
    # the downgrade can succeed, or the constraint creation will fail.
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_providers_verification_method", type_="check")
        batch_op.create_check_constraint(
            "ck_providers_verification_method",
            sa.text(
                "verification_method IS NULL OR verification_method IN ("
                "'manual', 'scraper', 'owner_confirmed', 'npi_registry', 'none'"
                ")"
            ),
        )
