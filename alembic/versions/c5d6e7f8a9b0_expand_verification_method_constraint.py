"""expand providers.verification_method CHECK (operator enrichment vocab)

Lane P2.BL.45 — admits operator-facing values from the enrichment CSV
(``phone_call``, ``in_person``, ``web_form_submission``, ``email_confirmation``)
alongside legacy values so ingest no longer maps lossy into ``manual`` /
``owner_confirmed``.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
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
