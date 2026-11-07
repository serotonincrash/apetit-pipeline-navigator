"""metric range and action, assumption label

Revision ID: a7d3e1f09b52
Revises: c4029784fab3
Create Date: 2026-11-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d3e1f09b52"
down_revision: str | Sequence[str] | None = "c4029784fab3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("metric", sa.Column("low", sa.Float(), nullable=True))
    op.add_column("metric", sa.Column("high", sa.Float(), nullable=True))
    op.add_column("metric", sa.Column("action_id", sa.String(), nullable=True))
    op.add_column("assumption", sa.Column("label", sa.String(), nullable=True))
    op.execute("UPDATE assumption SET label = name")
    op.alter_column("assumption", "label", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assumption", "label")
    op.drop_column("metric", "action_id")
    op.drop_column("metric", "high")
    op.drop_column("metric", "low")
