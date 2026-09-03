"""Commercial RFQ API endpoints (Phase 3)."""

from datetime import date, datetime
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
    incoterm_code: str | None = None
    movement_type: str | None = None
    cargo_ready_date: date | None = None
    preferred_departure: datetime | None = None
    required_delivery: datetime | None = None
    preferred_carrier_id: str | None = None
    priority: str | None = None
    parties: list[dict[str, Any]] = []
    cargo_lines: list[dict[str, Any]] = []
    container_requirements: list[dict[str, Any]] = []
    special_requirement: dict[str, Any] | None = None


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


@router.get("/rfqs")
async def list_rfqs(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
    customer_id: str | None = None,
    status: str | None = None,
    mode: str | None = None,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    from sqlalchemy import select
    from app.db.models.commercial import RFQ
    import uuid

    tenant_id = user.tenant_id if user else None
    if session is not None and tenant_id is not None:
        stmt = select(RFQ).where(RFQ.tenant_id == tenant_id).order_by(RFQ.created_at.desc())
        if customer_id:
            try:
                c_id = uuid.UUID(customer_id)
                stmt = stmt.where(RFQ.customer_id == c_id)
            except ValueError:
                pass
        if status:
            stmt = stmt.where(RFQ.status == status.upper())
        if mode:
            stmt = stmt.where(RFQ.mode == mode.upper())
        if assigned_to:
            try:
                u_id = uuid.UUID(assigned_to)
                stmt = stmt.where(RFQ.assigned_to == u_id)
            except ValueError:
                pass
        rfqs = (await session.execute(stmt)).scalars().all()
        data = [
            {
                "id": str(r.id),
                "rfq_number": r.rfq_number,
                "customer_id": str(r.customer_id) if r.customer_id else None,
                "mode": r.mode,
                "service_type": r.service_type,
                "origin_location_id": str(r.origin_location_id) if r.origin_location_id else None,
                "destination_location_id": str(r.destination_location_id) if r.destination_location_id else None,
                "status": r.status,
                "assigned_to": str(r.assigned_to) if r.assigned_to else None,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rfqs
        ]
    else:
        from app.modules.commercial.repository import _IN_MEMORY_RFQS
        data = list(_IN_MEMORY_RFQS.values())
        if customer_id:
            data = [r for r in data if r.get("customer_id") == customer_id]
        if status:
            data = [r for r in data if r.get("status") == status]
        if mode:
            data = [r for r in data if r.get("mode") == mode]
    return {"success": True, "data": data, "errors": [], "meta": {"total": len(data)}}
