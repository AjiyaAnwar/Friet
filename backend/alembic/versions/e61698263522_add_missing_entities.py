"""add_missing_entities

Revision ID: e61698263522
Revises: a0a2948c1dc5
Create Date: 2026-09-03 05:56:57.784850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e61698263522'
down_revision: Union[str, None] = 'a0a2948c1dc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('idempotency_records',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('response_body', sa.JSON(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_idempotency_records_key'), 'idempotency_records', ['key'], unique=True)
    
    op.create_table('dead_letter_records',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('event_type', sa.String(length=128), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('awb_records',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('shipment_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('awb_type', sa.String(length=10), nullable=False),
        sa.Column('parent_mawb_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('airline_prefix', sa.String(length=3), nullable=False),
        sa.Column('serial_number', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['parent_mawb_id'], ['awb_records.id'], ),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('sea_shipment_details',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('shipment_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('mbl_number', sa.String(length=64), nullable=True),
        sa.Column('hbl_number', sa.String(length=64), nullable=True),
        sa.Column('vessel_name', sa.String(length=128), nullable=True),
        sa.Column('voyage_number', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('shipment_exceptions',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('shipment_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('exception_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('uld_assignments',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('uld_number', sa.String(length=32), nullable=False),
        sa.Column('flight_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('awb_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('pieces', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.ForeignKeyConstraint(['awb_id'], ['awb_records.id'], ),
        sa.ForeignKeyConstraint(['flight_id'], ['flight_schedules.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('notification_events',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=128), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('notification_events')
    op.drop_table('uld_assignments')
    op.drop_table('shipment_exceptions')
    op.drop_table('sea_shipment_details')
    op.drop_table('awb_records')
    op.drop_table('dead_letter_records')
    op.drop_index(op.f('ix_idempotency_records_key'), table_name='idempotency_records')
    op.drop_table('idempotency_records')
