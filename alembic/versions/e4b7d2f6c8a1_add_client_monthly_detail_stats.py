"""add_client_monthly_detail_stats

Revision ID: e4b7d2f6c8a1
Revises: c3f1d9a2b7e4
Create Date: 2026-03-31 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4b7d2f6c8a1"
down_revision: Union[str, Sequence[str], None] = "c3f1d9a2b7e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_monthly_detail_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("client_name", sa.String(), nullable=False),
        sa.Column("bill_type", sa.String(), nullable=True),
        sa.Column("service_type", sa.String(), nullable=True),
        sa.Column("flow_consumption", sa.Float(), nullable=True),
        sa.Column("managed_consumption", sa.Float(), nullable=True),
        sa.Column("net_consumption", sa.Float(), nullable=True),
        sa.Column("service_fee", sa.Float(), nullable=True),
        sa.Column("fixed_service_fee", sa.Float(), nullable=True),
        sa.Column("coupon", sa.Float(), nullable=True),
        sa.Column("dst", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("month", "client_name", name="_month_client_detail_uc"),
    )

    with op.batch_alter_table("client_monthly_detail_stats", schema=None) as batch_op:
        batch_op.create_index("ix_client_monthly_detail_stats_client_month", ["client_name", "month"], unique=False)
        batch_op.create_index("ix_client_monthly_detail_stats_month_total", ["month", "total"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("client_monthly_detail_stats", schema=None) as batch_op:
        batch_op.drop_index("ix_client_monthly_detail_stats_month_total")
        batch_op.drop_index("ix_client_monthly_detail_stats_client_month")

    op.drop_table("client_monthly_detail_stats")
