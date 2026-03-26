"""add_user_permissions_column

Revision ID: 9a6c13d8d75a
Revises: 5d9c2a4a6f61
Create Date: 2026-03-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a6c13d8d75a"
down_revision: Union[str, Sequence[str], None] = "5d9c2a4a6f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("permissions", sa.String(), nullable=False, server_default="[]"))
    op.execute("UPDATE users SET permissions = '[]' WHERE permissions IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("permissions")

