"""fix_job_tasks_tenant_fk

Revision ID: e7f1b2c3d4e5
Revises: d3e8f0a51b02
Create Date: 2026-09-03 23:33:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f1b2c3d4e5'
down_revision: Union[str, None] = 'd3e8f0a51b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key('fk_job_tasks_tenant_id_tenants', 'job_tasks', 'tenants', ['tenant_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_job_tasks_tenant_id_tenants', 'job_tasks', type_='foreignkey')

