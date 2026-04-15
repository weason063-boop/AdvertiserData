"""add client contract change reviews table

Revision ID: 7b2c4d6e8f90
Revises: ef411ec1cdbb
Create Date: 2026-04-15 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b2c4d6e8f90'
down_revision: Union[str, Sequence[str], None] = 'ef411ec1cdbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'client_contract_change_reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('client_name', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('source_token', sa.String(), nullable=False),
        sa.Column('sync_batch_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('change_fields_json', sa.String(), nullable=False, server_default='[]'),
        sa.Column('current_business_type', sa.String(), nullable=True),
        sa.Column('new_business_type', sa.String(), nullable=True),
        sa.Column('current_department', sa.String(), nullable=True),
        sa.Column('new_department', sa.String(), nullable=True),
        sa.Column('current_entity', sa.String(), nullable=True),
        sa.Column('new_entity', sa.String(), nullable=True),
        sa.Column('current_fee_clause', sa.String(), nullable=True),
        sa.Column('new_fee_clause', sa.String(), nullable=True),
        sa.Column('current_payment_term', sa.String(), nullable=True),
        sa.Column('new_payment_term', sa.String(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('client_contract_change_reviews', schema=None) as batch_op:
        batch_op.create_index('ix_contract_change_reviews_source', ['source_type', 'source_token'], unique=False)
        batch_op.create_index('ix_contract_change_reviews_status_client', ['status', 'client_name'], unique=False)

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_contract_change_reviews_pending_client_source
        ON client_contract_change_reviews (client_name, source_type, source_token)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ux_contract_change_reviews_pending_client_source")
    with op.batch_alter_table('client_contract_change_reviews', schema=None) as batch_op:
        batch_op.drop_index('ix_contract_change_reviews_status_client')
        batch_op.drop_index('ix_contract_change_reviews_source')

    op.drop_table('client_contract_change_reviews')
