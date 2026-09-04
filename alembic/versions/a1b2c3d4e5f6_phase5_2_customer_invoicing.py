"""phase5_2_customer_invoicing

Revision ID: a1b2c3d4e5f6
Revises: f4a8b1c2d3e4
Create Date: 2026-09-04 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f4a8b1c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. invoices table extensions
    op.add_column('invoices', sa.Column('invoice_number', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('invoice_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=True))
    op.add_column('invoices', sa.Column('due_date', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('currency_code', sa.String(length=3), server_default='USD', nullable=False))
    op.add_column('invoices', sa.Column('exchange_rate_to_base', sa.Numeric(precision=18, scale=8), server_default='1.0', nullable=False))
    op.add_column('invoices', sa.Column('exchange_rate_source', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('subtotal_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False))
    op.add_column('invoices', sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False))
    op.add_column('invoices', sa.Column('total_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False))
    op.add_column('invoices', sa.Column('tax_jurisdiction', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('tax_rate', sa.Numeric(precision=5, scale=4), server_default='0.0', nullable=True))
    op.add_column('invoices', sa.Column('tax_type', sa.String(length=32), nullable=True))
    op.add_column('invoices', sa.Column('job_number', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('bl_awb_number', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('customer_po', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('quotation_id', sa.UUID(), nullable=True))
    op.add_column('invoices', sa.Column('approval_status', sa.String(length=32), server_default='PENDING_APPROVAL', nullable=False))
    op.add_column('invoices', sa.Column('approved_by', sa.UUID(), nullable=True))
    op.add_column('invoices', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('sent_by', sa.UUID(), nullable=True))
    op.add_column('invoices', sa.Column('customer_email', sa.String(length=255), nullable=True))
    op.add_column('invoices', sa.Column('payment_terms', sa.String(length=64), nullable=True))
    op.add_column('invoices', sa.Column('notes', sa.Text(), nullable=True))

    op.create_foreign_key('fk_invoices_quotation_id', 'invoices', 'quotations', ['quotation_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_invoices_approved_by', 'invoices', 'users', ['approved_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_invoices_sent_by', 'invoices', 'users', ['sent_by'], ['id'], ondelete='SET NULL')
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'], unique=False)
    op.create_index('ix_invoices_customer_id', 'invoices', ['customer_id'], unique=False)
    op.create_index('ix_invoices_shipment_id', 'invoices', ['shipment_id'], unique=False)
    op.create_index('ix_invoices_status', 'invoices', ['status'], unique=False)
    op.create_unique_constraint('uq_invoice_number', 'invoices', ['tenant_id', 'invoice_number'])

    # 2. invoice_lines table
    op.create_table(
        'invoice_lines',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('revenue_line_id', sa.UUID(), nullable=True),
        sa.Column('charge_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=12, scale=4), server_default='1.0', nullable=False),
        sa.Column('unit_rate', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('source_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('source_currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('exchange_rate', sa.Numeric(precision=18, scale=8), server_default='1.0', nullable=False),
        sa.Column('tax_rate', sa.Numeric(precision=5, scale=4), server_default='0.0', nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revenue_line_id'], ['revenue_lines.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_invoice_lines_tenant_id', 'invoice_lines', ['tenant_id'])
    op.create_index('ix_invoice_lines_invoice_id', 'invoice_lines', ['invoice_id'])
    op.create_index('ix_invoice_lines_revenue_line_id', 'invoice_lines', ['revenue_line_id'])

    # 3. credit_notes table
    op.create_table(
        'credit_notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('credit_note_number', sa.String(length=64), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency_code', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('credit_note_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='ISSUED', nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('financial_entry_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['financial_entry_id'], ['financial_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'credit_note_number', name='uq_credit_note_number')
    )
    op.create_index('ix_credit_notes_tenant_id', 'credit_notes', ['tenant_id'])
    op.create_index('ix_credit_notes_invoice_id', 'credit_notes', ['invoice_id'])
    op.create_index('ix_credit_notes_customer_id', 'credit_notes', ['customer_id'])
    op.create_index('ix_credit_notes_credit_note_number', 'credit_notes', ['credit_note_number'])

    # 4. debit_notes table
    op.create_table(
        'debit_notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('debit_note_number', sa.String(length=64), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), server_default='0.0', nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency_code', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('charge_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('debit_note_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='ISSUED', nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('financial_entry_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['financial_entry_id'], ['financial_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'debit_note_number', name='uq_debit_note_number')
    )
    op.create_index('ix_debit_notes_tenant_id', 'debit_notes', ['tenant_id'])
    op.create_index('ix_debit_notes_invoice_id', 'debit_notes', ['invoice_id'])
    op.create_index('ix_debit_notes_customer_id', 'debit_notes', ['customer_id'])
    op.create_index('ix_debit_notes_debit_note_number', 'debit_notes', ['debit_note_number'])


def downgrade() -> None:
    op.drop_table('debit_notes')
    op.drop_table('credit_notes')
    op.drop_table('invoice_lines')

    op.drop_constraint('uq_invoice_number', 'invoices', type_='unique')
    op.drop_index('ix_invoices_status', table_name='invoices')
    op.drop_index('ix_invoices_shipment_id', table_name='invoices')
    op.drop_index('ix_invoices_customer_id', table_name='invoices')
    op.drop_index('ix_invoices_invoice_number', table_name='invoices')
    op.drop_constraint('fk_invoices_sent_by', 'invoices', type_='foreignkey')
    op.drop_constraint('fk_invoices_approved_by', 'invoices', type_='foreignkey')
    op.drop_constraint('fk_invoices_quotation_id', 'invoices', type_='foreignkey')

    op.drop_column('invoices', 'notes')
    op.drop_column('invoices', 'payment_terms')
    op.drop_column('invoices', 'customer_email')
    op.drop_column('invoices', 'sent_by')
    op.drop_column('invoices', 'sent_at')
    op.drop_column('invoices', 'approved_at')
    op.drop_column('invoices', 'approved_by')
    op.drop_column('invoices', 'approval_status')
    op.drop_column('invoices', 'quotation_id')
    op.drop_column('invoices', 'customer_po')
    op.drop_column('invoices', 'bl_awb_number')
    op.drop_column('invoices', 'job_number')
    op.drop_column('invoices', 'tax_type')
    op.drop_column('invoices', 'tax_rate')
    op.drop_column('invoices', 'tax_jurisdiction')
    op.drop_column('invoices', 'total_amount')
    op.drop_column('invoices', 'tax_amount')
    op.drop_column('invoices', 'subtotal_amount')
    op.drop_column('invoices', 'exchange_rate_source')
    op.drop_column('invoices', 'exchange_rate_to_base')
    op.drop_column('invoices', 'currency_code')
    op.drop_column('invoices', 'due_date')
    op.drop_column('invoices', 'invoice_date')
    op.drop_column('invoices', 'invoice_number')
