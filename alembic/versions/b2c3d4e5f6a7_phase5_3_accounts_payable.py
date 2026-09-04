"""phase5_3_accounts_payable

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-04 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. payables table
    op.create_table(
        'payables',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('shipment_id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=True),
        sa.Column('carrier_id', sa.UUID(), nullable=True),
        sa.Column('bill_number', sa.String(length=64), nullable=False),
        sa.Column('bill_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('currency_code', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('subtotal_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('paid_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='RECEIVED', nullable=False),
        sa.Column('verification_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('approval_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('verified_by', sa.UUID(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('variance_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('supporting_document_url', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('financial_entry_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['carrier_id'], ['carriers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['financial_entry_id'], ['financial_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'bill_number', name='uq_payable_bill_number')
    )
    op.create_index('ix_payables_tenant_id', 'payables', ['tenant_id'], unique=False)
    op.create_index('ix_payables_shipment_id', 'payables', ['shipment_id'], unique=False)
    op.create_index('ix_payables_vendor_id', 'payables', ['vendor_id'], unique=False)
    op.create_index('ix_payables_carrier_id', 'payables', ['carrier_id'], unique=False)
    op.create_index('ix_payables_bill_number', 'payables', ['bill_number'], unique=False)
    op.create_index('ix_payables_status', 'payables', ['status'], unique=False)
    op.create_index('ix_payables_verification_status', 'payables', ['verification_status'], unique=False)
    op.create_index('ix_payables_approval_status', 'payables', ['approval_status'], unique=False)

    # 2. payable_lines table
    op.create_table(
        'payable_lines',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('payable_id', sa.UUID(), nullable=False),
        sa.Column('cost_line_id', sa.UUID(), nullable=True),
        sa.Column('charge_code', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=12, scale=3), server_default='1.0', nullable=False),
        sa.Column('unit_rate', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('expected_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('billed_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('variance_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('currency_code', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['cost_line_id'], ['cost_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payable_id'], ['payables.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_payable_lines_tenant_id', 'payable_lines', ['tenant_id'], unique=False)
    op.create_index('ix_payable_lines_payable_id', 'payable_lines', ['payable_id'], unique=False)
    op.create_index('ix_payable_lines_cost_line_id', 'payable_lines', ['cost_line_id'], unique=False)

    # 3. payable_payments table
    op.create_table(
        'payable_payments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('payable_id', sa.UUID(), nullable=False),
        sa.Column('payment_reference', sa.String(length=64), nullable=False),
        sa.Column('payment_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency_code', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('payment_method', sa.String(length=32), server_default='WIRE_TRANSFER', nullable=False),
        sa.Column('financial_entry_id', sa.UUID(), nullable=True),
        sa.Column('recorded_by', sa.UUID(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['financial_entry_id'], ['financial_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payable_id'], ['payables.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_payable_payments_tenant_id', 'payable_payments', ['tenant_id'], unique=False)
    op.create_index('ix_payable_payments_payable_id', 'payable_payments', ['payable_id'], unique=False)
    op.create_index('ix_payable_payments_payment_reference', 'payable_payments', ['payment_reference'], unique=False)


def downgrade() -> None:
    op.drop_table('payable_payments')
    op.drop_table('payable_lines')
    op.drop_table('payables')
