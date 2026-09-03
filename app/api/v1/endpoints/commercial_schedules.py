"""Carrier schedule search backed by the ERD vessel schedule/port rotations."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.models.reference import VesselSchedule
from app.db.session import get_db

router = APIRouter()


@router.get("/schedules/sea")
async def search_sea_schedules(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    origin: str = Query(..., min_length=3),
    destination: str = Query(..., min_length=3),
    from_date: date | None = Query(None, alias="from"),
) -> dict[str, Any]:
    """Find rotations containing origin before destination with ETD/ETA data."""
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    schedules = (await session.execute(select(VesselSchedule))).scalars().all()
    results = []
    for schedule in schedules:
        rotation = schedule.port_rotation or {}
        calls = rotation.get("calls", rotation if isinstance(rotation, list) else [])
        if not isinstance(calls, list):
            continue
        origin_call = next((call for call in calls if call.get("location_code") == origin), None)
        destination_call = next((call for call in calls if call.get("location_code") == destination), None)
        if not origin_call or not destination_call:
            continue
        etd = origin_call.get("etd")
        eta = destination_call.get("eta")
        if from_date and etd and str(etd)[:10] < str(from_date):
            continue
        results.append({
            "schedule_id": str(schedule.id), "carrier_id": str(schedule.carrier_id),
            "vessel_id": str(schedule.vessel_id), "service_name": schedule.service_name,
            "voyage_number": schedule.voyage_number, "origin": origin, "destination": destination,
            "etd": etd, "eta": eta, "cy_cutoff": str(schedule.cy_cutoff) if schedule.cy_cutoff else None,
            "si_cutoff": str(schedule.si_cutoff) if schedule.si_cutoff else None,
            "vgm_cutoff": str(schedule.vgm_cutoff) if schedule.vgm_cutoff else None,
        })
    return {"success": True, "data": results, "errors": [], "meta": {"total": len(results)}}


@router.get("/schedules/air")
async def search_air_schedules(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    origin: str | None = Query(None),
    destination: str | None = Query(None),
) -> dict[str, Any]:
    """Find air schedules with cut-off and frequency data."""
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    from app.db.models.reference import FlightSchedule
    schedules = (await session.execute(select(FlightSchedule))).scalars().all()
    results = [
        {
            "schedule_id": str(s.id),
            "carrier_id": str(s.carrier_id),
            "origin_location_id": str(s.origin_location_id),
            "destination_location_id": str(s.destination_location_id),
            "flight_number": s.flight_number,
            "frequency": s.frequency,
            "scheduled_departure": s.scheduled_departure,
            "scheduled_arrival": s.scheduled_arrival,
            "cargo_cutoff": s.cargo_cutoff,
            "documentation_cutoff": s.documentation_cutoff,
        }
        for s in schedules
    ]
    return {"success": True, "data": results, "errors": [], "meta": {"total": len(results)}}
