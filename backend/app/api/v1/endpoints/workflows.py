"""Workflow management endpoints."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.models.workflow import StateMachine
from app.db.session import get_db
from app.modules.workflow.service import WorkflowService

router = APIRouter()


class TransitionRequest(BaseModel):
    to_state: str
    notes: str | None = None
    context: dict[str, Any] = {}


@router.get("")
async def list_workflows(
    user: Annotated[CurrentUser, Depends(require_permission("workflow:manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await session.execute(
        select(StateMachine).where(StateMachine.tenant_id == user.tenant_id)
    )
    data = [
        {"id": str(m.id), "code": m.code, "name": m.name, "entity_type": m.entity_type}
        for m in result.scalars()
    ]
    return {"data": data, "meta": {"total": len(data)}, "errors": []}


@router.post("/workflow-instances/{instance_id}/transitions")
async def transition_instance(
    instance_id: uuid.UUID,
    payload: TransitionRequest,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:transition"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = WorkflowService(session)
    instance = await service.transition(
        instance_id=instance_id,
        to_state_code=payload.to_state,
        actor_id=user.id,
        tenant_id=user.tenant_id,
        permission_codes=user.permissions,
        notes=payload.notes,
        context=payload.context,
    )
    await session.commit()
    return {
        "data": {"instance_id": str(instance.id), "state_id": str(instance.current_state_id)},
        "meta": {},
        "errors": [],
    }
