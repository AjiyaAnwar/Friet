"""phase5_financial_integrity

Revision ID: b1b3959d2ed6
Revises: a0a2948c1dc5
Create Date: 2026-09-03 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1b3959d2ed6'
down_revision: Union[str, None] = 'a0a2948c1dc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. vendor_bill_discrepancies
    op.create_table(
        'vendor_bill_discrepancies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('shipment_id', sa.UUID(), nullable=True),
        sa.Column('vendor_id', sa.UUID(), nullable=True),
        sa.Column('contracted_rate_id', sa.UUID(), nullable=True),
        sa.Column('contracted_rate_version_id', sa.UUID(), nullable=True),
        sa.Column('shipment_reference', sa.Text(), nullable=True),
        sa.Column('vendor_invoice_reference', sa.Text(), nullable=True),
        sa.Column('charge_code', sa.Text(), nullable=True),
        sa.Column('contracted_rate_amount', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('invoiced_rate_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('variance_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency_code', sa.CHAR(length=3), nullable=False),
        sa.Column('rate_effective_date', sa.Date(), nullable=True),
        sa.Column('rate_expiry_date', sa.Date(), nullable=True),
        sa.Column('rate_was_expired_at_invoice_date', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('invoice_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='OPEN'),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contracted_rate_id'], ['rates.id']),
        sa.ForeignKeyConstraint(['contracted_rate_version_id'], ['rate_versions.id']),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vbd_tenant_status', 'vendor_bill_discrepancies', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_vbd_vendor_id', 'vendor_bill_discrepancies', ['vendor_id'], unique=False)
    op.create_index('ix_vbd_shipment_id', 'vendor_bill_discrepancies', ['shipment_id'], unique=False)
    op.create_index('ix_vbd_detected_at', 'vendor_bill_discrepancies', ['detected_at'], unique=False)
    op.create_index(op.f('ix_vendor_bill_discrepancies_tenant_id'), 'vendor_bill_discrepancies', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_vendor_bill_discrepancies_status'), 'vendor_bill_discrepancies', ['status'], unique=False)

    # 2. agent_settlements
    op.create_table(
        'agent_settlements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('shipment_id', sa.UUID(), nullable=True),
        sa.Column('rate_agreement_id', sa.UUID(), nullable=True),
        sa.Column('rate_version_id', sa.UUID(), nullable=True),
        sa.Column('cost_entry_id', sa.UUID(), nullable=True),
        sa.Column('base_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('rate_applied', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('settlement_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency_code', sa.CHAR(length=3), nullable=False),
        sa.Column('settlement_date', sa.Date(), nullable=False),
        sa.Column('rate_effective_date', sa.Date(), nullable=True),
        sa.Column('rate_expiry_date', sa.Date(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('calculated_by', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='DRAFT'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['calculated_by'], ['users.id']),
        sa.ForeignKeyConstraint(['cost_entry_id'], ['financial_entries.id']),
        sa.ForeignKeyConstraint(['rate_agreement_id'], ['agent_rate_agreements.id']),
        sa.ForeignKeyConstraint(['rate_version_id'], ['rate_versions.id']),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_as_tenant_status', 'agent_settlements', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_as_agent_id', 'agent_settlements', ['agent_id'], unique=False)
    op.create_index('ix_as_shipment_id', 'agent_settlements', ['shipment_id'], unique=False)
    op.create_index('ix_as_settlement_date', 'agent_settlements', ['settlement_date'], unique=False)
    op.create_index(op.f('ix_agent_settlements_tenant_id'), 'agent_settlements', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_agent_settlements_status'), 'agent_settlements', ['status'], unique=False)

    # 3. market_rates
    op.create_table(
        'market_rates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('origin_location_id', sa.UUID(), nullable=False),
        sa.Column('destination_location_id', sa.UUID(), nullable=False),
        sa.Column('mode', sa.String(length=8), nullable=False),
        sa.Column('rate_type', sa.String(length=32), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency_code', sa.CHAR(length=3), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['destination_location_id'], ['locations.id']),
        sa.ForeignKeyConstraint(['origin_location_id'], ['locations.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'origin_location_id', 'destination_location_id', 'mode', 'rate_type', 'effective_date', 'source', name='uq_market_rate')
    )
    op.create_index('ix_mr_tenant_lane', 'market_rates', ['tenant_id', 'origin_location_id', 'destination_location_id'], unique=False)
    op.create_index('ix_mr_effective_expiry', 'market_rates', ['effective_date', 'expiry_date'], unique=False)
    op.create_index(op.f('ix_market_rates_tenant_id'), 'market_rates', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('market_rates')
    op.drop_table('agent_settlements')
    op.drop_table('vendor_bill_discrepancies')

