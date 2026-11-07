"""metric site

Revision ID: e8c14b7a5d20
Revises: d5b2a8c14e73
Create Date: 2026-11-07 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c14b7a5d20"
down_revision: str | Sequence[str] | None = "d5b2a8c14e73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("metric", sa.Column("site", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("metric", "site")
