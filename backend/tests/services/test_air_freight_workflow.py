import pytest
import uuid
from app.services.air_freight_state import AirFreightStateService
from app.db.models.workflow import StateMachine, WorkflowState, WorkflowTransition
from sqlalchemy import select

@pytest.mark.asyncio
async def test_ensure_air_workflow(db_session):
    tenant_id = uuid.uuid4()
    service = AirFreightStateService(db_session)
    
    machine = await service.ensure_workflow(tenant_id)
    assert machine is not None
    assert machine.code == "air_freight_direct"

    # Verify states
    result = await db_session.execute(
        select(WorkflowState).where(WorkflowState.state_machine_id == machine.id)
    )
    states = result.scalars().all()
    assert len(states) == 21
    
    # Check some guards
    result = await db_session.execute(
        select(WorkflowTransition).where(WorkflowTransition.state_machine_id == machine.id)
    )
    transitions = result.scalars().all()
    
    has_mawb_guard = any(
        "mawb_approved_guard" in t.guard_definitions.get("guards", []) 
        for t in transitions
    )
    assert has_mawb_guard
