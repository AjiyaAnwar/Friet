"""ETA/ETD Multi-Version Tracking API Endpoints (SRS Phase 4.6)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.modules.eta.service import EtaService

router = APIRouter()


class EtaVersionCreateRequest(BaseModel):
    leg_id: uuid.UUID
    type: str = Field(..., description="ETA or ETD")
    value: datetime = Field(..., description="Timestamp in UTC or ISO format")
    source: str = Field("MANUAL", description="QUOTATION/BOOKING/CARRIER_API/MANUAL/TERMINAL")
    reason: str | None = None
    has_firm_delivery_commitment: bool = False


@router.post("/shipments/{shipment_id}/eta-history")
async def record_eta_version(
    shipment_id: uuid.UUID,
    payload: EtaVersionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Record new ETA/ETD version with immutable auto-increment and multi-leg cascade."""
    service = EtaService(session)
    result = await service.record_version(
        shipment_id=shipment_id,
        leg_id=payload.leg_id,
        type=payload.type,
        value=payload.value,
        source=payload.source,
        reason=payload.reason,
        recorded_by=user.id,
        tenant_id=user.tenant_id,
        has_firm_delivery_commitment=payload.has_firm_delivery_commitment,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.get("/shipments/{shipment_id}/eta-history/{leg_id}")
async def get_leg_eta_history(
    shipment_id: uuid.UUID,
    leg_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    type: str | None = Query(None, description="Filter by ETA or ETD"),
) -> dict[str, Any]:
    """Get full ordered version history for a specific shipment leg."""
    service = EtaService(session)
    history = await service.get_leg_history(
        shipment_id=shipment_id,
        leg_id=leg_id,
        type=type,
    )
    return {"success": True, "data": history, "errors": [], "meta": {"total": len(history)}}

