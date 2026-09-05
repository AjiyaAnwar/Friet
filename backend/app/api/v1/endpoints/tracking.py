"""Shipment Tracking & Event Timeline API Endpoints (Phase 4.5)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.modules.tracking.service import TrackingService

router = APIRouter()


class TrackingEventCreateRequest(BaseModel):
    event_type: str = Field(..., description="Standard ~60 taxonomy event code (e.g., DEPARTED, CUSTOMS_CLEARED)")
    location: str | None = Field(None, description="Location name, port/airport code, or terminal")
    event_time_original: str | None = Field(None, description="Event timestamp in original operational timezone")
    event_time_utc: datetime | None = Field(None, description="UTC normalized event timestamp")
    description: str | None = Field(None, description="Custom or carrier description")
    source: str = Field("MANUAL", description="Event source: MANUAL / CARRIER_API / AGENT / TERMINAL")


# ---------------------------------------------------------------------------
# Tracking Event Recording & Timeline
# ---------------------------------------------------------------------------

@router.post("/shipments/{shipment_id}/events")
async def record_shipment_tracking_event(
    shipment_id: uuid.UUID,
    payload: TrackingEventCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Record manual or external tracking event against shipment with full taxonomy validation."""
    service = TrackingService(session)
    result = await service.record_event(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        event_type=payload.event_type,
        location=payload.location,
        event_time_original=payload.event_time_original,
        event_time_utc=payload.event_time_utc,
        description=payload.description,
        source=payload.source,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.get("/shipments/{shipment_id}/timeline")
async def get_shipment_event_timeline(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    category: str | None = Query(None, description="Filter by category: BOOKING / CARGO / TRANSPORT / CUSTOMS / DELIVERY / EXCEPTION"),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Get chronological event timeline for shipment ordered most-recent first."""
    service = TrackingService(session)
    timeline = await service.get_timeline(
        shipment_id=shipment_id,
        category=category,
        limit=limit,
    )
    return {"success": True, "data": timeline, "errors": [], "meta": {"total": len(timeline)}}


@router.get("/tracking/taxonomy")
async def get_tracking_taxonomy_catalog(
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
) -> dict[str, Any]:
    """List all supported ~60 standard event taxonomy definitions grouped by category."""
    service = TrackingService()
    catalog = service.get_taxonomy_catalog()
    return {"success": True, "data": catalog, "errors": [], "meta": {"total": len(catalog)}}

