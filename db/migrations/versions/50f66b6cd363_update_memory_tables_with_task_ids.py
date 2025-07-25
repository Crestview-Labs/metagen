"""Update memory tables with task_ids

Revision ID: 50f66b6cd363
Revises: 9ddc0291c1e4
Create Date: 2025-07-06 16:30:12.123456

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50f66b6cd363"
down_revision: Union[str, Sequence[str], None] = "9ddc0291c1e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create long_term_memories table
    op.create_table(
        "long_term_memories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_long_term_memories_created_at", "long_term_memories", ["created_at"], unique=False
    )
    op.create_index(
        "idx_long_term_memories_task_id", "long_term_memories", ["task_id"], unique=False
    )

    # Update compact_memories: replace session_ids with task_ids
    op.add_column("compact_memories", sa.Column("task_ids", sa.JSON(), nullable=True))
    op.drop_column("compact_memories", "session_ids")


def downgrade() -> None:
    """Downgrade schema."""
    # Restore compact_memories
    op.add_column("compact_memories", sa.Column("session_ids", sa.JSON(), nullable=True))
    op.drop_column("compact_memories", "task_ids")

    # Drop long_term_memories table
    op.drop_index("idx_long_term_memories_task_id", table_name="long_term_memories")
    op.drop_index("idx_long_term_memories_created_at", table_name="long_term_memories")
    op.drop_table("long_term_memories")
