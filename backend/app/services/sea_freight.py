import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.workflow import StateMachine, WorkflowState, WorkflowTransition
from app.core.exceptions import NotFoundError

class SeaFreightService:
    MACHINE_CODE = "sea_freight_fcl"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_workflow(self, tenant_id: uuid.UUID) -> StateMachine:
        # Check if exists
        from sqlalchemy import select
        result = await self.session.execute(
            select(StateMachine).where(
                StateMachine.tenant_id == tenant_id,
                StateMachine.code == self.MACHINE_CODE
            )
        )
        machine = result.scalar_one_or_none()
        if machine:
            return machine

        # Create state machine for Sea Freight FCL
        machine = StateMachine(
            tenant_id=tenant_id,
            code=self.MACHINE_CODE,
            name="Sea Freight FCL Lifecycle",
            entity_type="shipment"
        )
        self.session.add(machine)
        await self.session.flush()

        # Define States
        states = [
            ("BOOKING", True, False),
            ("EMPTY_RELEASED", False, False),
            ("GATE_IN", False, False),
            ("VGM_SUBMITTED", False, False),
            ("LOADED", False, False),
            ("DEPARTED", False, False),
            ("ARRIVED", False, False),
            ("DELIVERED", False, True)
        ]
        
        state_map: dict[str, WorkflowState] = {}
        for code, is_initial, is_terminal in states:
            st = WorkflowState(
                state_machine_id=machine.id,
                code=code,
                name=code.replace("_", " ").title(),
                is_initial=is_initial,
                is_terminal=is_terminal
            )
            self.session.add(st)
            await self.session.flush()
            state_map[code] = st

        # Define Transitions
        transitions = [
            ("BOOKING", "EMPTY_RELEASED", "shipment:update"),
            ("EMPTY_RELEASED", "GATE_IN", "shipment:update"),
            ("GATE_IN", "VGM_SUBMITTED", "shipment:vgm"),
            ("VGM_SUBMITTED", "LOADED", "shipment:update"),
            ("LOADED", "DEPARTED", "shipment:update"),
            ("DEPARTED", "ARRIVED", "shipment:update"),
            ("ARRIVED", "DELIVERED", "shipment:update"),
        ]

        for from_code, to_code, perm in transitions:
            self.session.add(
                WorkflowTransition(
                    state_machine_id=machine.id,
                    from_state_id=state_map[from_code].id,
                    to_state_id=state_map[to_code].id,
                    required_permission=perm,
                    guard_definitions={"guards": ["always_true"]}
                )
            )

        await self.session.commit()
        return machine

    async def submit_vgm(self, shipment_id: uuid.UUID, weight: float, method: str):
        # Implementation for VGM Submission
        pass

    async def generate_bl_pdf(self, shipment_id: uuid.UUID):
        # Placeholder for BL generation
        return "https://mock-s3-bucket/bl/document.pdf"
