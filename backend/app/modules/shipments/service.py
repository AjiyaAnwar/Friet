"""Shipment module schemas, repository, and service."""

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.domain import Shipment, Cargo, Container, TrackingEvent
from app.db.models.workflow import StateMachine, WorkflowInstance, WorkflowState
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService
from app.modules.workflow.service import WorkflowService
from app.schemas.shipment import ShipmentWorkspaceResponse, CargoEntryFCL, CargoEntryAir, ShipmentTaskInfo


class ShipmentCreate(BaseModel):
    customer_id: uuid.UUID
    booking_id: uuid.UUID
    mode: str = Field(pattern="^(SEA|AIR)$")


class ShipmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    booking_id: uuid.UUID
    mode: str
    status: str

    model_config = {"from_attributes": True}


class ShipmentTransitionRequest(BaseModel):
    to_state: str
    notes: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ShipmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def get(self, shipment_id: uuid.UUID, tenant_id: uuid.UUID) -> Shipment | None:
        result = await self.session.execute(
            select(Shipment).where(Shipment.id == shipment_id, Shipment.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list(self, tenant_id: uuid.UUID, limit: int = 50) -> list[Shipment]:
        result = await self.session.execute(
            select(Shipment).where(Shipment.tenant_id == tenant_id).limit(limit)
        )
        return list(result.scalars())


class ShipmentService:
    DEMO_MACHINE_CODE = "shipment_common"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ShipmentRepository(session)
        self.audit = AuditService(session)
        self.outbox = OutboxService(session)
        self.workflow = WorkflowService(session)

    async def create_shipment(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: ShipmentCreate,
    ) -> Shipment:
        shipment = Shipment(
            tenant_id=tenant_id,
            booking_id=payload.booking_id,
            customer_id=payload.customer_id,
            mode=payload.mode,
            status="DRAFT",
            created_by=actor_id,
        )
        await self.repo.create(shipment)

        machine = await self._ensure_demo_workflow(tenant_id)
        draft_state = await self._get_state(machine.id, "DRAFT")
        instance = WorkflowInstance(
            tenant_id=tenant_id,
            state_machine_id=machine.id,
            entity_type="shipment",
            entity_id=shipment.id,
            current_state_id=draft_state.id,
        )
        self.session.add(instance)

        await self.audit.record(
            tenant_id=tenant_id,
            user_id=actor_id,
            branch_id=None,
            entity_type="shipment",
            entity_id=str(shipment.id),
            action="create",
            new_value={"mode": payload.mode, "status": "DRAFT"},
        )
        await self.outbox.enqueue(
            event_type="shipment.created",
            tenant_id=tenant_id,
            aggregate_type="shipment",
            aggregate_id=shipment.id,
            payload={"mode": payload.mode},
        )
        return shipment

    async def transition(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        permission_codes: set[str],
        payload: ShipmentTransitionRequest,
    ) -> Shipment:
        shipment = await self.repo.get(shipment_id, tenant_id)
        if not shipment:
            raise NotFoundError("Shipment not found")

        result = await self.session.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.entity_type == "shipment",
                WorkflowInstance.entity_id == shipment_id,
                WorkflowInstance.tenant_id == tenant_id,
            )
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValidationError("Workflow instance not found")

        await self.workflow.transition(
            instance_id=instance.id,
            to_state_code=payload.to_state,
            actor_id=actor_id,
            tenant_id=tenant_id,
            permission_codes=permission_codes,
            notes=payload.notes,
            context=payload.context,
        )
        shipment.status = payload.to_state
        return shipment

    async def _ensure_demo_workflow(self, tenant_id: uuid.UUID) -> StateMachine:
        result = await self.session.execute(
            select(StateMachine).where(
                StateMachine.tenant_id == tenant_id,
                StateMachine.code == self.DEMO_MACHINE_CODE,
            )
        )
        machine = result.scalar_one_or_none()
        if machine:
            return machine

        machine = StateMachine(
            tenant_id=tenant_id,
            code=self.DEMO_MACHINE_CODE,
            name="Shipment Common Lifecycle",
            entity_type="shipment",
        )
        self.session.add(machine)
        await self.session.flush()

        states = [
            ("DRAFT", True, False),
            ("SUBMITTED", False, False),
            ("APPROVED", False, False),
            ("BOOKED", False, False),
            ("DEPARTED", False, False),
            ("ARRIVED", False, False),
            ("DELIVERED", False, False),
            ("CLOSED", False, True),
        ]
        state_map: dict[str, WorkflowState] = {}
        for code, is_initial, is_terminal in states:
            st = WorkflowState(
                state_machine_id=machine.id,
                code=code,
                name=code.title(),
                is_initial=is_initial,
                is_terminal=is_terminal,
            )
            self.session.add(st)
            await self.session.flush()
            state_map[code] = st

        from app.db.models.workflow import WorkflowTransition

        transitions = [
            ("DRAFT", "SUBMITTED"),
            ("SUBMITTED", "APPROVED"),
            ("APPROVED", "BOOKED"),
            ("BOOKED", "DEPARTED"),
            ("DEPARTED", "ARRIVED"),
            ("ARRIVED", "DELIVERED"),
            ("DELIVERED", "CLOSED"),
        ]
        for from_code, to_code in transitions:
            perm = "shipment:transition" if from_code != "DRAFT" else "shipment:create"
            self.session.add(
                WorkflowTransition(
                    state_machine_id=machine.id,
                    from_state_id=state_map[from_code].id,
                    to_state_id=state_map[to_code].id,
                    required_permission=perm,
                    guard_definitions={"guards": ["always_true"]},
                )
            )
        return machine

    async def _get_state(self, machine_id: uuid.UUID, code: str) -> WorkflowState:
        result = await self.session.execute(
            select(WorkflowState).where(
                WorkflowState.state_machine_id == machine_id,
                WorkflowState.code == code,
            )
        )
        return result.scalar_one()

    def _calculate_rag_status(self, shipment: Shipment) -> str:
        # Placeholder for RAG calculation logic
        # Could be RED (breached SLA), AMBER (approaching), GREEN (on track)
        if shipment.status in ("CLOSED", "DELIVERED"):
            return "GREEN"
        return "GREEN"

    async def get_workspace(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_roles: list[str]
    ) -> ShipmentWorkspaceResponse:
        shipment = await self.repo.get(shipment_id, tenant_id)
        if not shipment:
            raise NotFoundError("Shipment not found")

        # Fetch tracking events
        events_result = await self.session.execute(
            select(TrackingEvent).where(TrackingEvent.shipment_id == shipment_id).order_by(TrackingEvent.event_time.desc()).limit(5)
        )
        recent_events = [{"event_type": e.event_type, "event_time": e.event_time.isoformat()} for e in events_result.scalars()]

        # Fetch cargo
        cargo_result = await self.session.execute(
            select(Cargo).where(Cargo.shipment_id == shipment_id)
        )
        cargo_summary = [{"id": str(c.id), "weight": float(c.weight), "volume": float(c.volume)} for c in cargo_result.scalars()]

        rag_status = self._calculate_rag_status(shipment)
        
        financials = None
        if "finance" in user_roles or "admin" in user_roles:
            financials = {"total_cost": 0.0, "total_revenue": 0.0}  # Placeholder

        return ShipmentWorkspaceResponse(
            id=shipment.id,
            tenant_id=shipment.tenant_id,
            customer_id=shipment.customer_id,
            booking_id=shipment.booking_id,
            mode=shipment.mode,
            status=shipment.status,
            rag_status=rag_status,
            recent_events=recent_events,
            cargo_summary=cargo_summary,
            financials=financials,
            tasks=[]
        )

    async def add_cargo_fcl(self, shipment_id: uuid.UUID, tenant_id: uuid.UUID, payload: CargoEntryFCL) -> Cargo:
        shipment = await self.repo.get(shipment_id, tenant_id)
        if not shipment:
            raise NotFoundError("Shipment not found")

        cargo = Cargo(
            shipment_id=shipment_id,
            weight=payload.weight,
            volume=payload.volume
        )
        self.session.add(cargo)
        await self.session.flush()

        container = Container(
            shipment_id=shipment_id,
            container_no=payload.container_no,
            type=payload.type
        )
        self.session.add(container)
        
        return cargo

    async def add_cargo_air(self, shipment_id: uuid.UUID, tenant_id: uuid.UUID, payload: CargoEntryAir) -> Cargo:
        shipment = await self.repo.get(shipment_id, tenant_id)
        if not shipment:
            raise NotFoundError("Shipment not found")

        cargo = Cargo(
            shipment_id=shipment_id,
            weight=payload.weight,
            volume=payload.volume
        )
        self.session.add(cargo)
        return cargo
