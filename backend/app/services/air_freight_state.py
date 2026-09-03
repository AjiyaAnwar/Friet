import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.workflow import StateMachine, WorkflowState, WorkflowTransition

class AirFreightStateService:
    MACHINE_CODE = "air_freight_direct"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_workflow(self, tenant_id: uuid.UUID) -> StateMachine:
        result = await self.session.execute(
            select(StateMachine).where(
                StateMachine.tenant_id == tenant_id,
                StateMachine.code == self.MACHINE_CODE
            )
        )
        machine = result.scalar_one_or_none()
        if machine:
            return machine

        machine = StateMachine(
            tenant_id=tenant_id,
            code=self.MACHINE_CODE,
            name="Air Freight Direct Lifecycle",
            entity_type="shipment"
        )
        self.session.add(machine)
        await self.session.flush()

        states = [
            ("ENQUIRY", True, False),
            ("QUOTED", False, False),
            ("CONFIRMED", False, False),
            ("CARGO_READY", False, False),
            ("PICKED_UP", False, False),
            ("RECEIVED_AT_WAREHOUSE", False, False),
            ("SCREENED", False, False),
            ("DOCUMENTATION_COMPLETE", False, False),
            ("MAWB_ISSUED", False, False),
            ("BOOKED_ON_FLIGHT", False, False),
            ("ACCEPTED_BY_AIRLINE", False, False),
            ("DEPARTED", False, False),
            ("IN_TRANSIT", False, False),
            ("ARRIVED", False, False),
            ("CARGO_BREAKDOWN", False, False),
            ("CUSTOMS_CLEARED", False, False),
            ("OUT_FOR_DELIVERY", False, False),
            ("DELIVERED", False, False),
            ("POD_CONFIRMED", False, False),
            ("FINANCIALLY_SETTLED", False, False),
            ("CLOSED", False, True)
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

        transitions = [
            ("ENQUIRY", "QUOTED", "air_shipment:transition", []),
            ("QUOTED", "CONFIRMED", "air_shipment:transition", []),
            ("CONFIRMED", "CARGO_READY", "air_shipment:transition", []),
            ("CARGO_READY", "PICKED_UP", "air_shipment:transition", ["pickup_assigned_guard"]),
            ("PICKED_UP", "RECEIVED_AT_WAREHOUSE", "air_shipment:transition", ["warehouse_receipt_guard"]),
            ("RECEIVED_AT_WAREHOUSE", "SCREENED", "air_shipment:transition", ["received_pieces_recorded_guard"]),
            ("SCREENED", "DOCUMENTATION_COMPLETE", "air_shipment:transition", ["screening_complete_guard"]),
            ("DOCUMENTATION_COMPLETE", "MAWB_ISSUED", "air_shipment:transition", ["mawb_approved_guard"]),
            ("MAWB_ISSUED", "BOOKED_ON_FLIGHT", "air_shipment:transition", ["flight_booking_guard"]),
            ("BOOKED_ON_FLIGHT", "ACCEPTED_BY_AIRLINE", "air_shipment:transition", ["airline_acceptance_guard"]),
            ("ACCEPTED_BY_AIRLINE", "DEPARTED", "air_shipment:transition", ["no_blocking_exceptions_guard"]),
            ("DEPARTED", "IN_TRANSIT", "air_shipment:transition", []),
            ("IN_TRANSIT", "ARRIVED", "air_shipment:transition", []),
            ("ARRIVED", "CARGO_BREAKDOWN", "air_shipment:transition", ["arrival_confirmed_guard"]),
            ("CARGO_BREAKDOWN", "CUSTOMS_CLEARED", "air_shipment:transition", ["customs_records_guard"]),
            ("CUSTOMS_CLEARED", "OUT_FOR_DELIVERY", "air_shipment:transition", []),
            ("OUT_FOR_DELIVERY", "DELIVERED", "air_shipment:transition", []),
            ("DELIVERED", "POD_CONFIRMED", "air_shipment:transition", ["pod_valid_guard"]),
            ("POD_CONFIRMED", "FINANCIALLY_SETTLED", "air_shipment:transition", ["financial_settlement_guard"]),
            ("FINANCIALLY_SETTLED", "CLOSED", "air_shipment:transition", ["no_open_tasks_guard"])
        ]

        for from_code, to_code, perm, guards in transitions:
            self.session.add(
                WorkflowTransition(
                    state_machine_id=machine.id,
                    from_state_id=state_map[from_code].id,
                    to_state_id=state_map[to_code].id,
                    required_permission=perm,
                    guard_definitions={"guards": guards} if guards else {"guards": ["always_true"]}
                )
            )

        await self.session.commit()
        return machine
