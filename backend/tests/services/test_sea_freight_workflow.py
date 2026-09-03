import pytest
import uuid
from app.services.sea_freight import SeaFreightService
from app.db.models.workflow import StateMachine, WorkflowState, WorkflowTransition
from sqlalchemy import select

@pytest.mark.asyncio
async def test_ensure_workflow(db_session):
    tenant_id = uuid.uuid4()
    service = SeaFreightService(db_session)
    
    # First time, should create
    machine = await service.ensure_workflow(tenant_id)
    assert machine is not None
    assert machine.code == "sea_freight_fcl"
    assert machine.tenant_id == tenant_id

    # Verify states
    result = await db_session.execute(
        select(WorkflowState).where(WorkflowState.state_machine_id == machine.id)
    )
    states = result.scalars().all()
    assert len(states) == 8
    
    # Second time, should return existing
    machine_existing = await service.ensure_workflow(tenant_id)
    assert machine.id == machine_existing.id
