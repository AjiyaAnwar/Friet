"""commercial booking handoff and estimated ledger fields

Revision ID: c2a7e9d40f01
Revises: b1b3959d2ed6
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c2a7e9d40f01"
down_revision = "b1b3959d2ed6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shipments", sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_shipments_job_id", "shipments", "jobs", ["job_id"], ["id"])
    op.create_unique_constraint("uq_shipments_job_id", "shipments", ["job_id"])
    op.add_column("revenue_lines", sa.Column("currency_code", sa.String(length=3), nullable=True))
    op.add_column("revenue_lines", sa.Column("status", sa.String(length=32), nullable=False, server_default="ESTIMATED"))
    op.add_column("cost_lines", sa.Column("charge_code", sa.Text(), nullable=True))
    op.add_column("cost_lines", sa.Column("currency_code", sa.String(length=3), nullable=True))
    op.add_column("cost_lines", sa.Column("status", sa.String(length=32), nullable=False, server_default="ESTIMATED"))
    op.create_table(
        "job_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("department", sa.String(length=32), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_job_tasks_job_id", "job_tasks", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_tasks_job_id", table_name="job_tasks")
    op.drop_table("job_tasks")
    op.drop_column("cost_lines", "status")
    op.drop_column("cost_lines", "currency_code")
    op.drop_column("cost_lines", "charge_code")
    op.drop_column("revenue_lines", "status")
    op.drop_column("revenue_lines", "currency_code")
    op.drop_constraint("uq_shipments_job_id", "shipments", type_="unique")
    op.drop_constraint("fk_shipments_job_id", "shipments", type_="foreignkey")
    op.drop_column("shipments", "job_id")
