"""merge alembic heads (relabel-departments + track-b1-dedupe)

Revision ID: 304cc3843188
Revises: 10c88d64d916
Create Date: 2026-06-14 12:52:41.716456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '304cc3843188'
down_revision: Union[str, Sequence[str], None] = '10c88d64d916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
