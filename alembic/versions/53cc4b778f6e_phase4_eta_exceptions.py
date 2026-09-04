"""phase4_eta_exceptions

Revision ID: 53cc4b778f6e
Revises: 94a04ba72517
Create Date: 2026-09-03 23:36:26.083771

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53cc4b778f6e'
down_revision: Union[str, None] = '94a04ba72517'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. eta_history table (Phase 4.6)
    op.create_table(
        'eta_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('shipment_id', sa.UUID(), nullable=False),
        sa.Column('leg_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=8), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('value', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=32), server_default='MANUAL', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('recorded_by', sa.UUID(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['leg_id'], ['shipment_legs.id']),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_eta_history_leg_id'), 'eta_history', ['leg_id'], unique=False)
    op.create_index(op.f('ix_eta_history_shipment_id'), 'eta_history', ['shipment_id'], unique=False)

    # 2. shipment_exceptions table (Phase 4.7)
    op.create_table(
        'shipment_exceptions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('shipment_id', sa.UUID(), nullable=False),
        sa.Column('exception_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=16), server_default='WARNING', nullable=False),
        sa.Column('domain', sa.String(length=32), server_default='OPERATIONAL', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='OPEN', nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('financial_impact_estimated', sa.Numeric(precision=12, scale=2), server_default='0.0', nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_shipment_exceptions_domain'), 'shipment_exceptions', ['domain'], unique=False)
    op.create_index(op.f('ix_shipment_exceptions_exception_type'), 'shipment_exceptions', ['exception_type'], unique=False)
    op.create_index(op.f('ix_shipment_exceptions_severity'), 'shipment_exceptions', ['severity'], unique=False)
    op.create_index(op.f('ix_shipment_exceptions_shipment_id'), 'shipment_exceptions', ['shipment_id'], unique=False)
    op.create_index(op.f('ix_shipment_exceptions_status'), 'shipment_exceptions', ['status'], unique=False)
    op.create_index(op.f('ix_shipment_exceptions_tenant_id'), 'shipment_exceptions', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_shipment_exceptions_tenant_id'), table_name='shipment_exceptions')
    op.drop_index(op.f('ix_shipment_exceptions_status'), table_name='shipment_exceptions')
    op.drop_index(op.f('ix_shipment_exceptions_shipment_id'), table_name='shipment_exceptions')
    op.drop_index(op.f('ix_shipment_exceptions_severity'), table_name='shipment_exceptions')
    op.drop_index(op.f('ix_shipment_exceptions_exception_type'), table_name='shipment_exceptions')
    op.drop_index(op.f('ix_shipment_exceptions_domain'), table_name='shipment_exceptions')
    op.drop_table('shipment_exceptions')

    op.drop_index(op.f('ix_eta_history_shipment_id'), table_name='eta_history')
    op.drop_index(op.f('ix_eta_history_leg_id'), table_name='eta_history')
    op.drop_table('eta_history')
