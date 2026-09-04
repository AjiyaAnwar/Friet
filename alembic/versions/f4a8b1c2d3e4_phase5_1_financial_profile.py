"""phase5_1_financial_profile

Revision ID: f4a8b1c2d3e4
Revises: 53cc4b778f6e
Create Date: 2026-09-04 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a8b1c2d3e4'
down_revision: Union[str, None] = '53cc4b778f6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. revenue_lines extensions
    op.add_column('revenue_lines', sa.Column('is_additional', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('revenue_lines', sa.Column('description', sa.String(length=255), nullable=True))
    op.add_column('revenue_lines', sa.Column('quantity', sa.Numeric(precision=12, scale=4), server_default='1.0', nullable=False))
    op.add_column('revenue_lines', sa.Column('unit_rate', sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column('revenue_lines', sa.Column('quotation_line_id', sa.UUID(), nullable=True))
    op.add_column('revenue_lines', sa.Column('created_by', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_revenue_lines_quotation_line_id',
        'revenue_lines', 'quotation_lines',
        ['quotation_line_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_revenue_lines_created_by',
        'revenue_lines', 'users',
        ['created_by'], ['id'],
        ondelete='SET NULL'
    )

    # 2. cost_lines extensions
    op.add_column('cost_lines', sa.Column('carrier_id', sa.UUID(), nullable=True))
    op.add_column('cost_lines', sa.Column('is_additional', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('cost_lines', sa.Column('description', sa.String(length=255), nullable=True))
    op.add_column('cost_lines', sa.Column('quantity', sa.Numeric(precision=12, scale=4), server_default='1.0', nullable=False))
    op.add_column('cost_lines', sa.Column('unit_rate', sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column('cost_lines', sa.Column('quotation_line_id', sa.UUID(), nullable=True))
    op.add_column('cost_lines', sa.Column('created_by', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_cost_lines_carrier_id',
        'cost_lines', 'carriers',
        ['carrier_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_cost_lines_quotation_line_id',
        'cost_lines', 'quotation_lines',
        ['quotation_line_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_cost_lines_created_by',
        'cost_lines', 'users',
        ['created_by'], ['id'],
        ondelete='SET NULL'
    )

    # 3. financial_entries extensions
    op.add_column('financial_entries', sa.Column('reversal_reason', sa.Text(), nullable=True))
    op.add_column('financial_entries', sa.Column('approved_by', sa.UUID(), nullable=True))
    op.add_column('financial_entries', sa.Column('revenue_line_id', sa.UUID(), nullable=True))
    op.add_column('financial_entries', sa.Column('cost_line_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_financial_entries_approved_by',
        'financial_entries', 'users',
        ['approved_by'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_financial_entries_revenue_line_id',
        'financial_entries', 'revenue_lines',
        ['revenue_line_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_financial_entries_cost_line_id',
        'financial_entries', 'cost_lines',
        ['cost_line_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # financial_entries
    op.drop_constraint('fk_financial_entries_cost_line_id', 'financial_entries', type_='foreignkey')
    op.drop_constraint('fk_financial_entries_revenue_line_id', 'financial_entries', type_='foreignkey')
    op.drop_constraint('fk_financial_entries_approved_by', 'financial_entries', type_='foreignkey')
    op.drop_column('financial_entries', 'cost_line_id')
    op.drop_column('financial_entries', 'revenue_line_id')
    op.drop_column('financial_entries', 'approved_by')
    op.drop_column('financial_entries', 'reversal_reason')

    # cost_lines
    op.drop_constraint('fk_cost_lines_created_by', 'cost_lines', type_='foreignkey')
    op.drop_constraint('fk_cost_lines_quotation_line_id', 'cost_lines', type_='foreignkey')
    op.drop_constraint('fk_cost_lines_carrier_id', 'cost_lines', type_='foreignkey')
    op.drop_column('cost_lines', 'created_by')
    op.drop_column('cost_lines', 'quotation_line_id')
    op.drop_column('cost_lines', 'unit_rate')
    op.drop_column('cost_lines', 'quantity')
    op.drop_column('cost_lines', 'description')
    op.drop_column('cost_lines', 'is_additional')
    op.drop_column('cost_lines', 'carrier_id')

    # revenue_lines
    op.drop_constraint('fk_revenue_lines_created_by', 'revenue_lines', type_='foreignkey')
    op.drop_constraint('fk_revenue_lines_quotation_line_id', 'revenue_lines', type_='foreignkey')
    op.drop_column('revenue_lines', 'created_by')
    op.drop_column('revenue_lines', 'quotation_line_id')
    op.drop_column('revenue_lines', 'unit_rate')
    op.drop_column('revenue_lines', 'quantity')
    op.drop_column('revenue_lines', 'description')
    op.drop_column('revenue_lines', 'is_additional')
