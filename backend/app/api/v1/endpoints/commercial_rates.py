"""Commercial Rate Engine API endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.db.models.reference import Carrier, Location
from app.modules.commercial.rate_engine.import_service import validate_rate_rows
from app.modules.commercial.schemas.rate import (
    RateCreate,
    RateVersionCreateRequest,
)
from app.modules.commercial.service import CommercialService

router = APIRouter()


class RateTransitionRequest(BaseModel):
    to_status: str


class RateImportRequest(BaseModel):
    rows: list[dict]
    dry_run: bool = True


@router.post("/rates")
async def create_rate(
    payload: RateCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    service = CommercialService(session)
    tenant_id = user.tenant_id
    rate = await service.create_rate(payload.model_dump(), tenant_id=tenant_id)
    if session:
        await session.commit()
    return {"success": True, "data": rate, "errors": [], "meta": {}}


@router.get("/rates/monitoring/expiry")
async def get_rate_expiry_report(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    today: date | None = None,
) -> dict:
    service = CommercialService(session)
    report = await service.get_expiry_report(today=today)
    return {"success": True, "data": report, "errors": [], "meta": {}}


@router.get("/rates/{rate_id}")
async def get_rate(
    rate_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    service = CommercialService(session)
    rate = await service.get_rate(rate_id)
    if not rate:
        raise NotFoundError(f"Rate {rate_id} not found")
    return {"success": True, "data": rate, "errors": [], "meta": {}}


@router.post("/rates/{rate_id}/versions")
async def create_rate_version(
    rate_id: str,
    payload: RateVersionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    service = CommercialService(session)
    version = await service.create_rate_version(rate_id, payload.model_dump())
    if not version:
        raise NotFoundError(f"Rate {rate_id} not found")
    if session:
        await session.commit()
    return {"success": True, "data": version, "errors": [], "meta": {}}


@router.post("/rates/{rate_id}/transition")
async def transition_rate(
    rate_id: str,
    payload: RateTransitionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    rate = await CommercialService(session).transition_rate(rate_id, payload.to_status)
    await session.commit()
    return {"success": True, "data": rate, "errors": [], "meta": {}}


@router.post("/rates/import")
async def import_rates(
    payload: RateImportRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    """Validate a structured import before persistence; file adapters feed rows here."""
    locations = {str(value) for value in (await session.execute(select(Location.id))).scalars().all()}
    carriers = {str(value) for value in (await session.execute(select(Carrier.id))).scalars().all()}
    report = validate_rate_rows(payload.rows, locations, carriers, dry_run=payload.dry_run)
    if not payload.dry_run:
        if report.error_count:
            return {"success": False, "data": None, "errors": [error.__dict__ for error in report.row_errors], "meta": {"success_count": 0, "error_count": report.error_count}}
        service = CommercialService(session)
        for row in report.valid_rows:
            await service.create_rate(row, tenant_id=user.tenant_id)
        await session.commit()
    return {"success": report.error_count == 0, "data": {"total_rows": report.total_rows, "success_count": report.success_count, "error_count": report.error_count, "dry_run": payload.dry_run, "row_errors": [error.__dict__ for error in report.row_errors]}, "errors": [], "meta": {}}


@router.get("/rates")
async def list_rates(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    rate_type: str | None = None,
    rate_category: str | None = None,
    origin_location_id: str | None = None,
    destination_location_id: str | None = None,
    status: str | None = None,
) -> dict:
    from app.db.models.commercial import Rate
    import uuid

    if session is not None:
        stmt = select(Rate).where(Rate.tenant_id == user.tenant_id).order_by(Rate.created_at.desc())
        if rate_type:
            stmt = stmt.where(Rate.rate_type == rate_type.upper())
        if rate_category:
            stmt = stmt.where(Rate.rate_category == rate_category.upper())
        if origin_location_id:
            try:
                stmt = stmt.where(Rate.origin_location_id == uuid.UUID(origin_location_id))
            except ValueError:
                pass
        if destination_location_id:
            try:
                stmt = stmt.where(Rate.destination_location_id == uuid.UUID(destination_location_id))
            except ValueError:
                pass
        if status:
            stmt = stmt.where(Rate.status == status.upper())
        rates = (await session.execute(stmt)).scalars().all()
        data = [
            {
                "id": str(r.id),
                "rate_number": r.rate_number,
                "rate_type": r.rate_type,
                "rate_category": r.rate_category,
                "carrier_vendor_id": str(r.carrier_vendor_id) if r.carrier_vendor_id else None,
                "service_name": r.service_name,
                "origin_location_id": str(r.origin_location_id) if r.origin_location_id else None,
                "destination_location_id": str(r.destination_location_id) if r.destination_location_id else None,
                "effective_date": str(r.effective_date),
                "expiry_date": str(r.expiry_date),
                "currency_code": r.currency_code,
                "status": r.status,
            }
            for r in rates
        ]
    else:
        from app.modules.commercial.repository import _IN_MEMORY_RATES
        data = list(_IN_MEMORY_RATES.values())
        if rate_type:
            data = [r for r in data if r.get("rate_type") == rate_type]
        if status:
            data = [r for r in data if r.get("status") == status]
    return {"success": True, "data": data, "errors": [], "meta": {"total": len(data)}}


@router.get("/rates/{rate_id}/versions/compare")
async def compare_rate_versions(
    rate_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    v1: int = 1,
    v2: int = 2,
) -> dict:
    service = CommercialService(session)
    rate = await service.get_rate(rate_id)
    if not rate:
        raise NotFoundError(f"Rate {rate_id} not found")

    if session is not None:
        from app.db.models.commercial import RateLine, RateVersion
        import uuid
        try:
            r_uuid = uuid.UUID(rate_id)
        except ValueError:
            raise NotFoundError(f"Rate {rate_id} not found")
        v_a = (await session.execute(
            select(RateVersion).where(RateVersion.rate_id == r_uuid, RateVersion.version_number == v1)
        )).scalar_one_or_none()
        v_b = (await session.execute(
            select(RateVersion).where(RateVersion.rate_id == r_uuid, RateVersion.version_number == v2)
        )).scalar_one_or_none()
        if not v_a or not v_b:
            raise NotFoundError(f"One or both versions ({v1}, {v2}) not found for rate {rate_id}")
        lines_a = (await session.execute(
            select(RateLine).where(RateLine.rate_version_id == v_a.id)
        )).scalars().all()
        lines_b = (await session.execute(
            select(RateLine).where(RateLine.rate_version_id == v_b.id)
        )).scalars().all()
        return {
            "success": True,
            "data": {
                "rate_id": rate_id,
                "version_a": {"version_number": v_a.version_number, "reason": v_a.reason, "lines": [{"charge_code": l.charge_code, "amount": float(l.amount)} for l in lines_a]},
                "version_b": {"version_number": v_b.version_number, "reason": v_b.reason, "lines": [{"charge_code": l.charge_code, "amount": float(l.amount)} for l in lines_b]},
            },
            "errors": [],
            "meta": {},
        }
    else:
        from app.modules.commercial.repository import _IN_MEMORY_RATE_VERSIONS
        versions = _IN_MEMORY_RATE_VERSIONS.get(rate_id, [])
        va = next((v for v in versions if v.get("version_number") == v1), None)
        vb = next((v for v in versions if v.get("version_number") == v2), None)
        va = va or {"version_number": v1, "reason": "Initial", "lines": []}
        vb = vb or {"version_number": v2, "reason": "Update", "lines": []}
        return {
            "success": True,
            "data": {
                "rate_id": rate_id,
                "version_a": va,
                "version_b": vb,
            },
            "errors": [],
            "meta": {},
        }
