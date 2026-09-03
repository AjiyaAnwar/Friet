import uuid
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import CurrentUser, require_permission
from app.db.session import get_db
from app.services.uld_service import ULDService
from app.schemas.flight import FlightManifestResponse, ULDCreateRequest, ULDResponse, ULDAllocation

router = APIRouter()

@router.get("/{flight_id}/manifest", response_model=dict)
async def get_flight_manifest(
    flight_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_permission("flight_manifest:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ULDService(session)
    manifest = await service.generate_flight_manifest(user.tenant_id, flight_id)
    return {"data": manifest.model_dump(), "meta": {}, "errors": []}

@router.post("/ulds", response_model=dict)
async def create_uld(
    payload: ULDCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("uld:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ULDService(session)
    uld = await service.create_uld(user.tenant_id, payload)
    return {"data": uld.model_dump(), "meta": {}, "errors": []}

@router.post("/ulds/{uld_id}/assign", response_model=dict)
async def assign_uld(
    uld_id: uuid.UUID,
    payload: ULDAllocation,
    user: Annotated[CurrentUser, Depends(require_permission("uld:assign"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ULDService(session)
    uld = await service.assign_awb_to_uld(user.tenant_id, uld_id, payload)
    return {"data": uld.model_dump(), "meta": {}, "errors": []}
