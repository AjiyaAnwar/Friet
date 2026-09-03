"""add ERD-required city membership to inland zones

Revision ID: d3e8f0a51b02
Revises: c2a7e9d40f01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d3e8f0a51b02"
down_revision = "c2a7e9d40f01"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("zones", sa.Column("cities", postgresql.JSONB(), nullable=False, server_default="[]"))

def downgrade() -> None:
    op.drop_column("zones", "cities")
