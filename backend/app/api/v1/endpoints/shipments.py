"""Shipment endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.shipments.service import (
    ShipmentCreate,
    ShipmentResponse,
    ShipmentService,
    ShipmentTransitionRequest,
)

router = APIRouter()


@router.post("")
async def create_shipment(
    payload: ShipmentCreate,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    shipment = await service.create_shipment(
        tenant_id=user.tenant_id,
        actor_id=user.id,
        payload=payload,
    )
    await session.commit()
    return {
        "data": ShipmentResponse.model_validate(shipment),
        "meta": {},
        "errors": [],
    }


@router.get("")
async def list_shipments(
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    shipments = await service.repo.list(user.tenant_id)
    data = [ShipmentResponse.model_validate(s) for s in shipments]
    return {"data": data, "meta": {"total": len(data)}, "errors": []}


@router.get("/{shipment_id}")
async def get_shipment(
    shipment_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    shipment = await service.repo.get(shipment_id, user.tenant_id)
    if not shipment:
        raise NotFoundError("Shipment not found")
    return {"data": ShipmentResponse.model_validate(shipment), "meta": {}, "errors": []}


@router.post("/{shipment_id}/transition")
async def transition_shipment(
    shipment_id: uuid.UUID,
    payload: ShipmentTransitionRequest,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:transition"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    shipment = await service.transition(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        permission_codes=user.permissions,
        payload=payload,
    )
    await session.commit()
    return {"data": ShipmentResponse.model_validate(shipment), "meta": {}, "errors": []}
