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
from app.schemas.shipment import (
    ShipmentWorkspaceResponse,
    CargoEntryFCL,
    CargoEntryAir,
    ShipmentTaskInfo
)
from app.schemas.cargo import CargoAcceptanceRequest
from app.services.cargo_acceptance import CargoAcceptanceService

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

@router.get("/{shipment_id}/workspace", response_model=dict)
async def get_shipment_workspace(
    shipment_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    workspace = await service.get_workspace(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        user_roles=user.permissions # using permissions as roles proxy
    )
    return {"data": workspace.model_dump(), "meta": {}, "errors": []}

@router.post("/{shipment_id}/cargo/fcl")
async def add_cargo_fcl(
    shipment_id: uuid.UUID,
    payload: CargoEntryFCL,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:update"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    cargo = await service.add_cargo_fcl(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        payload=payload
    )
    await session.commit()
    return {"data": {"cargo_id": str(cargo.id)}, "meta": {}, "errors": []}

@router.post("/{shipment_id}/cargo/air")
async def add_cargo_air(
    shipment_id: uuid.UUID,
    payload: CargoEntryAir,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:update"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ShipmentService(session)
    cargo = await service.add_cargo_air(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        payload=payload
    )
    await session.commit()
    return {"data": {"cargo_id": str(cargo.id)}, "meta": {}, "errors": []}

@router.get("/{shipment_id}/tasks")
async def get_shipment_tasks(
    shipment_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # Placeholder for tasks API
    return {"data": [], "meta": {}, "errors": []}

@router.post("/{shipment_id}/cargo-acceptance")
async def accept_cargo(
    shipment_id: uuid.UUID,
    payload: CargoAcceptanceRequest,
    user: Annotated[CurrentUser, Depends(require_permission("cargo_acceptance:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CargoAcceptanceService(session)
    result = await service.process_acceptance(shipment_id, user.tenant_id, user.id, payload)
    return {"data": result, "meta": {}, "errors": []}
