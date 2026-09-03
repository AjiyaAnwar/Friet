"""Commercial route planning CRUD using ERD Route and RouteLeg entities."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.commercial import RFQ, Route, RouteLeg
from app.db.session import get_db

router = APIRouter()


class RouteLegCreate(BaseModel):
    sequence: int = Field(ge=1)
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    carrier_id: uuid.UUID | None = None
    vessel_id: uuid.UUID | None = None
    flight_schedule_id: uuid.UUID | None = None
    etd: datetime | None = None
    eta: datetime | None = None
    transit_time_hours: float | None = Field(None, ge=0)
    is_transshipment: bool = False


class RouteCreate(BaseModel):
    origin_location_id: uuid.UUID
    destination_location_id: uuid.UUID
    mode: str
    legs: list[RouteLegCreate] = Field(min_length=1)


@router.post("/routes")
async def create_route(payload: RouteCreate, session: Annotated[AsyncSession, Depends(get_db)], user: Annotated[CurrentUser, Depends(require_permission("rate:create"))]) -> dict:
    if payload.mode not in {"SEA", "AIR"}: raise ValidationError("Route mode must be SEA or AIR")
    if len({leg.sequence for leg in payload.legs}) != len(payload.legs): raise ValidationError("Route-leg sequence must be unique")
    ordered = sorted(payload.legs, key=lambda leg: leg.sequence)
    if ordered[0].from_location_id != payload.origin_location_id or ordered[-1].to_location_id != payload.destination_location_id:
        raise ValidationError("Route legs must connect declared origin and destination")
    route = Route(tenant_id=user.tenant_id, origin_location_id=payload.origin_location_id, destination_location_id=payload.destination_location_id, mode=payload.mode)
    session.add(route); await session.flush()
    for leg in ordered: session.add(RouteLeg(route_id=route.id, **leg.model_dump()))
    await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(route.id), "leg_count": len(ordered)}, "errors": [], "meta": {}}


@router.get("/rfqs/{rfq_id}/route-options")
async def rfq_route_options(rfq_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)], user: Annotated[CurrentUser, Depends(require_permission("rate:read"))]) -> dict:
    rfq = (await session.execute(select(RFQ).where(RFQ.id == rfq_id, RFQ.tenant_id == user.tenant_id))).scalar_one_or_none()
    if not rfq: raise NotFoundError("RFQ not found")
    routes = (await session.execute(select(Route).where(Route.tenant_id == user.tenant_id, Route.origin_location_id == rfq.origin_location_id, Route.destination_location_id == rfq.destination_location_id, Route.mode == rfq.mode))).scalars().all()
    data = []
    for route in routes:
        legs = (await session.execute(select(RouteLeg).where(RouteLeg.route_id == route.id).order_by(RouteLeg.sequence))).scalars().all()
        data.append({"route_id": str(route.id), "transit_time_hours": sum(float(leg.transit_time_hours or 0) for leg in legs), "transshipment_count": sum(1 for leg in legs if leg.is_transshipment), "legs": [{"from_location_id": str(leg.from_location_id), "to_location_id": str(leg.to_location_id), "carrier_id": str(leg.carrier_id) if leg.carrier_id else None, "etd": leg.etd, "eta": leg.eta} for leg in legs]})
    return {"success": True, "data": sorted(data, key=lambda value: (value["transshipment_count"], value["transit_time_hours"])), "errors": [], "meta": {"total": len(data)}}


@router.get("/rfqs/{rfq_id}/rate-options")
async def rfq_rate_options(
    rfq_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    """Multi-carrier rate comparison cascade (SRS §5.7).

    Returns applicable rates across carriers on the RFQ trade lane with
    landed cost breakdown and recommendation scores.
    """
    from app.db.models.commercial import RFQ, Rate, RateLine, RateVersion
    from app.db.models.reference import Carrier
    from datetime import date

    rfq = (await session.execute(select(RFQ).where(RFQ.id == rfq_id, RFQ.tenant_id == user.tenant_id))).scalar_one_or_none()
    if not rfq:
        raise NotFoundError("RFQ not found")

    today = date.today()
    stmt = (
        select(Rate, Carrier, RateVersion, RateLine)
        .outerjoin(Carrier, Rate.carrier_id == Carrier.id)
        .join(RateVersion, RateVersion.rate_id == Rate.id)
        .outerjoin(RateLine, RateLine.rate_version_id == RateVersion.id)
        .where(
            Rate.tenant_id == user.tenant_id,
            Rate.origin_location_id == rfq.origin_location_id,
            Rate.destination_location_id == rfq.destination_location_id,
            Rate.mode == rfq.mode,
            Rate.status == "APPROVED",
            Rate.effective_date <= today,
            Rate.expiry_date >= today,
        )
    )
    rows = (await session.execute(stmt)).all()

    rates_map: dict[str, dict] = {}
    for r, car, rv, rl in rows:
        rid = str(r.id)
        if rid not in rates_map:
            rates_map[rid] = {
                "rate_id": rid,
                "rate_number": r.rate_number,
                "carrier_id": str(car.id) if car else None,
                "carrier_name": car.name if car else "Direct / Unassigned",
                "service_name": r.service_name or "Standard Service",
                "transit_time_days": 3 if r.mode == "AIR" else 18,
                "base_freight": 0.0,
                "surcharges": 0.0,
                "currency_code": r.currency_code,
                "rate_category": r.rate_category,
            }
        if rl:
            amount = float(rl.amount or 0.0)
            if "FREIGHT" in (rl.charge_code or "").upper() or rl.charge_code in {"AFR", "OFR"}:
                rates_map[rid]["base_freight"] += amount
            else:
                rates_map[rid]["surcharges"] += amount

    results = []
    for val in rates_map.values():
        landed_cost = val["base_freight"] + val["surcharges"]
        proposed_sell = round(landed_cost * 1.15, 2)
        margin = round(proposed_sell - landed_cost, 2)
        margin_pct = round((margin / proposed_sell * 100) if proposed_sell else 0.0, 1)
        score = 100.0 - (landed_cost / 100.0)
        results.append({
            **val,
            "total_landed_cost": round(landed_cost, 2),
            "proposed_sell": proposed_sell,
            "gross_margin": margin,
            "margin_pct": margin_pct,
            "recommendation_score": round(max(score, 10.0), 1),
        })

    results.sort(key=lambda item: item["total_landed_cost"])
    return {"success": True, "data": results, "errors": [], "meta": {"total": len(results)}}
