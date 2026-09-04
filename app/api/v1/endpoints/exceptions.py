"""Exception Management API Endpoints (SRS Phase 4.7)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.modules.exceptions.service import ExceptionService

router = APIRouter()


class ExceptionCreateRequest(BaseModel):
    exception_type: str = Field(..., description="Exception type code, e.g. SHIPMENT_DELAY, VESSEL_ROLL, CARGO_DAMAGE")
    description: str = Field(..., min_length=5, description="Detailed description of the exception event")
    severity: str | None = Field(None, description="INFO, WARNING, CRITICAL (defaults to taxonomy default)")
    domain: str | None = Field(None, description="BOOKING, DOCUMENTATION, CUSTOMS, CARRIER, OPERATIONAL")
    financial_impact_estimated: float = Field(0.0, ge=0.0, description="Estimated financial exposure")
    owner_id: uuid.UUID | None = None


class ExceptionUpdateRequest(BaseModel):
    status: str | None = Field(None, description="OPEN, ACKNOWLEDGED, UNDER_INVESTIGATION, RESOLVED, CLOSED")
    owner_id: uuid.UUID | None = None
    resolution_notes: str | None = None
    financial_impact_estimated: float | None = Field(None, ge=0.0)


@router.post("/shipments/{shipment_id}/exceptions")
async def create_shipment_exception(
    shipment_id: uuid.UUID,
    payload: ExceptionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Raise a new shipment exception with taxonomy validation, escalation rules, and outbox notification."""
    service = ExceptionService(session)
    result = await service.create_exception(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        exception_type=payload.exception_type,
        description=payload.description,
        severity=payload.severity,
        domain=payload.domain,
        financial_impact_estimated=payload.financial_impact_estimated,
        owner_id=payload.owner_id,
        actor_id=user.id,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.patch("/shipments/{shipment_id}/exceptions/{exception_id}")
async def update_shipment_exception(
    shipment_id: uuid.UUID,
    exception_id: uuid.UUID,
    payload: ExceptionUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:transition"))],
) -> dict[str, Any]:
    """Update exception lifecycle status, ownership, resolution notes, or financial impact."""
    service = ExceptionService(session)
    result = await service.update_exception(
        exception_id=exception_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        status=payload.status,
        owner_id=payload.owner_id,
        resolution_notes=payload.resolution_notes,
        financial_impact_estimated=payload.financial_impact_estimated,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.get("/exceptions")
async def list_exceptions(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    status: str | None = Query(None, description="Filter by OPEN, ACKNOWLEDGED, UNDER_INVESTIGATION, RESOLVED, CLOSED"),
    severity: str | None = Query(None, description="Filter by INFO, WARNING, CRITICAL"),
    domain: str | None = Query(None, description="Filter by BOOKING, DOCUMENTATION, CUSTOMS, CARRIER, OPERATIONAL"),
    shipment_id: uuid.UUID | None = Query(None, description="Filter by specific shipment"),
) -> dict[str, Any]:
    """List exceptions register with multi-criteria filtering."""
    service = ExceptionService(session)
    items = await service.list_exceptions(
        tenant_id=user.tenant_id,
        shipment_id=shipment_id,
        status=status,
        severity=severity,
        domain=domain,
    )
    return {"success": True, "data": items, "errors": [], "meta": {"total": len(items)}}


@router.get("/exceptions/summary")
async def get_exceptions_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
) -> dict[str, Any]:
    """Aggregate exception metrics for control tower view (counts by status, severity, domain, financial exposure)."""
    service = ExceptionService(session)
    summary = await service.get_summary(tenant_id=user.tenant_id)
    return {"success": True, "data": summary, "errors": [], "meta": {}}

