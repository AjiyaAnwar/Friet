"""Generic database-driven workflow engine."""

import uuid
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ValidationError
from app.db.models.workflow import (
    WorkflowInstance,
    WorkflowState,
    WorkflowTransition,
    WorkflowTransitionHistory,
)
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService


class GuardRegistry:
    _guards: ClassVar[dict[str, Any]] = {}

    @classmethod
    def register(cls, name: str, func: Any) -> None:
        cls._guards[name] = func

    @classmethod
    def evaluate(cls, name: str, context: dict[str, Any]) -> bool:
        if name not in cls._guards:
            raise ValidationError(f"Unknown guard: {name}")
        return bool(cls._guards[name](context))


GuardRegistry.register("always_true", lambda ctx: True)


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)
        self.outbox = OutboxService(session)

    async def transition(
        self,
        *,
        instance_id: uuid.UUID,
        to_state_code: str,
        actor_id: uuid.UUID,
        tenant_id: uuid.UUID,
        permission_codes: set[str],
        notes: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> WorkflowInstance:
        result = await self.session.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.id == instance_id,
                WorkflowInstance.tenant_id == tenant_id,
            )
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValidationError("Workflow instance not found")

        to_state = await self._get_state(instance.state_machine_id, to_state_code)
        transition = await self._find_transition(
            instance.state_machine_id, instance.current_state_id, to_state.id
        )
        if not transition or not transition.is_active:
            raise ValidationError(
                f"Invalid transition to {to_state_code}",
                errors=[{"field": "to_state", "message": "Transition not allowed"}],
            )

        if transition.required_permission and transition.required_permission not in permission_codes:
            raise ForbiddenError("Missing permission for transition")

        ctx = context or {}
        for guard in (transition.guard_definitions or {}).get("guards", []):
            if not GuardRegistry.evaluate(guard, ctx):
                raise ValidationError(f"Guard failed: {guard}")

        required = (transition.required_fields or {}).get("fields", [])
        missing = [f for f in required if f not in ctx]
        if missing:
            raise ValidationError(
                "Missing required fields",
                errors=[{"field": f, "message": "Required"} for f in missing],
            )

        from_state_id = instance.current_state_id
        instance.current_state_id = to_state.id
        instance.version += 1

        history = WorkflowTransitionHistory(
            workflow_instance_id=instance.id,
            from_state_id=from_state_id,
            to_state_id=to_state.id,
            actor_id=actor_id,
            notes=notes,
            occurred_at=instance.updated_at,
        )
        self.session.add(history)

        await self.audit.record(
            tenant_id=tenant_id,
            user_id=actor_id,
            branch_id=None,
            entity_type=instance.entity_type,
            entity_id=str(instance.entity_id),
            action="workflow.transition",
            previous_value={"state_id": str(from_state_id)},
            new_value={"state_id": str(to_state.id)},
        )

        await self.outbox.enqueue(
            event_type=f"{instance.entity_type}.state_changed",
            tenant_id=tenant_id,
            aggregate_type=instance.entity_type,
            aggregate_id=instance.entity_id,
            payload={"from_state_id": str(from_state_id), "to_state_id": str(to_state.id)},
        )
        return instance

    async def _get_state(self, machine_id: uuid.UUID, code: str) -> WorkflowState:
        result = await self.session.execute(
            select(WorkflowState).where(
                WorkflowState.state_machine_id == machine_id,
                WorkflowState.code == code,
            )
        )
        state = result.scalar_one_or_none()
        if not state:
            raise ValidationError(f"Unknown state: {code}")
        return state

    async def _find_transition(
        self, machine_id: uuid.UUID, from_state_id: uuid.UUID, to_state_id: uuid.UUID
    ) -> WorkflowTransition | None:
        result = await self.session.execute(
            select(WorkflowTransition).where(
                WorkflowTransition.state_machine_id == machine_id,
                WorkflowTransition.from_state_id == from_state_id,
                WorkflowTransition.to_state_id == to_state_id,
            )
        )
        return result.scalar_one_or_none()
