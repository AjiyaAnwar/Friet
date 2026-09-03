"""Commercial RFQ API endpoints (Phase 3)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user_optional
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.commercial.service import CommercialService

router = APIRouter()


class RFQCreateRequest(BaseModel):
    customer_id: str
    mode: str = "AIR"
    service_type: str | None = None
    origin_location_id: str | None = None
    destination_location_id: str | None = None
    cargo_ready_date: str | None = None
    packages: int | None = None
    gross_weight_kg: float | None = None


class RFQAssignRequest(BaseModel):
    assigned_to: str


@router.post("/rfqs")
async def create_rfq(
    payload: RFQCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict[str, Any]:
    service = CommercialService(session)
    tenant_id = user.tenant_id if user else None
    rfq = await service.create_rfq(payload.model_dump(), tenant_id=tenant_id)
    if session:
        await session.commit()
    return {"success": True, "data": rfq, "errors": [], "meta": {}}


@router.get("/rfqs/{rfq_id}")
async def get_rfq(
    rfq_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict[str, Any]:
    service = CommercialService(session)
    rfq = await service.get_rfq(rfq_id)
    if not rfq:
        raise NotFoundError(f"RFQ {rfq_id} not found")
    return {"success": True, "data": rfq, "errors": [], "meta": {}}


@router.patch("/rfqs/{rfq_id}/assign")
async def assign_rfq(
    rfq_id: str,
    payload: RFQAssignRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict[str, Any]:
    service = CommercialService(session)
    rfq = await service.assign_rfq(rfq_id, payload.assigned_to)
    if not rfq:
        raise NotFoundError(f"RFQ {rfq_id} not found")
    if session:
        await session.commit()
    return {"success": True, "data": rfq, "errors": [], "meta": {}}
