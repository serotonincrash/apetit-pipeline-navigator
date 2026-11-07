"""action option scenario

Revision ID: d5b2a8c14e73
Revises: a7d3e1f09b52
Create Date: 2026-11-07 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b2a8c14e73"
down_revision: str | Sequence[str] | None = "a7d3e1f09b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("action_option", sa.Column("scenario", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("action_option", "scenario")
