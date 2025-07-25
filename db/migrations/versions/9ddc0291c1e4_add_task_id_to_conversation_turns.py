"""Add task_id to conversation_turns

Revision ID: 9ddc0291c1e4
Revises: a33fa66e6935
Create Date: 2025-07-06 16:15:48.414054

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ddc0291c1e4"
down_revision: Union[str, Sequence[str], None] = "a33fa66e6935"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add task_id column to conversation_turns table
    op.add_column("conversation_turns", sa.Column("task_id", sa.String(), nullable=True))
    op.create_index("idx_turns_task_id", "conversation_turns", ["task_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_turns_task_id", table_name="conversation_turns")
    op.drop_column("conversation_turns", "task_id")
