"""add_audit_log_and_dashboard_indexes

Revision ID: c3f1d9a2b7e4
Revises: 9a6c13d8d75a
Create Date: 2026-03-23 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f1d9a2b7e4"
down_revision: Union[str, Sequence[str], None] = "9a6c13d8d75a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operation_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_file", sa.String(), nullable=True),
        sa.Column("output_file", sa.String(), nullable=True),
        sa.Column("result_ref", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("operation_audit_logs", schema=None) as batch_op:
        batch_op.create_index("ix_operation_audit_logs_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_operation_audit_logs_actor_created_at", ["actor", "created_at"], unique=False)
        batch_op.create_index("ix_operation_audit_logs_action_created_at", ["action", "created_at"], unique=False)

    with op.batch_alter_table("billing_history", schema=None) as batch_op:
        batch_op.create_index("ix_billing_history_created_at", ["created_at"], unique=False)

    with op.batch_alter_table("client_monthly_stats", schema=None) as batch_op:
        batch_op.create_index("ix_client_monthly_stats_client_month", ["client_name", "month"], unique=False)
        batch_op.create_index("ix_client_monthly_stats_month_consumption", ["month", "consumption"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("client_monthly_stats", schema=None) as batch_op:
        batch_op.drop_index("ix_client_monthly_stats_month_consumption")
        batch_op.drop_index("ix_client_monthly_stats_client_month")

    with op.batch_alter_table("billing_history", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_history_created_at")

    with op.batch_alter_table("operation_audit_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_operation_audit_logs_action_created_at")
        batch_op.drop_index("ix_operation_audit_logs_actor_created_at")
        batch_op.drop_index("ix_operation_audit_logs_created_at")

    op.drop_table("operation_audit_logs")
