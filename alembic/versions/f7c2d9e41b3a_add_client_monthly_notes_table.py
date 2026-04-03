"""add_client_monthly_notes_table

Revision ID: f7c2d9e41b3a
Revises: e4b7d2f6c8a1
Create Date: 2026-03-31 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7c2d9e41b3a"
down_revision: Union[str, Sequence[str], None] = "e4b7d2f6c8a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_monthly_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("client_name", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("month", "client_name", name="_month_client_note_uc"),
    )

    with op.batch_alter_table("client_monthly_notes", schema=None) as batch_op:
        batch_op.create_index("ix_client_monthly_notes_client_month", ["client_name", "month"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("client_monthly_notes", schema=None) as batch_op:
        batch_op.drop_index("ix_client_monthly_notes_client_month")

    op.drop_table("client_monthly_notes")
