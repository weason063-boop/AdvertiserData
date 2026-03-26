"""add_client_contract_lines_table

Revision ID: 5d9c2a4a6f61
Revises: 0405ed990f4e
Create Date: 2026-03-13 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d9c2a4a6f61'
down_revision: Union[str, Sequence[str], None] = '0405ed990f4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'client_contract_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('source_token', sa.String(), nullable=False),
        sa.Column('source_row_index', sa.Integer(), nullable=False),
        sa.Column('client_name', sa.String(), nullable=False),
        sa.Column('business_type', sa.String(), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('entity', sa.String(), nullable=True),
        sa.Column('fee_clause', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_type', 'source_token', 'source_row_index',
            name='_contract_line_source_row_uc'
        ),
    )
    with op.batch_alter_table('client_contract_lines', schema=None) as batch_op:
        batch_op.create_index('ix_contract_lines_source', ['source_type', 'source_token'], unique=False)
        batch_op.create_index('ix_contract_lines_client_name', ['client_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('client_contract_lines', schema=None) as batch_op:
        batch_op.drop_index('ix_contract_lines_client_name')
        batch_op.drop_index('ix_contract_lines_source')

    op.drop_table('client_contract_lines')

