"""Commercial Rate Engine API endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user_optional
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.commercial.schemas.rate import (
    RateCreate,
    RateVersionCreateRequest,
)
from app.modules.commercial.service import CommercialService

router = APIRouter()


@router.post("/rates")
async def create_rate(
    payload: RateCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    tenant_id = user.tenant_id if user else None
    rate = await service.create_rate(payload.model_dump(), tenant_id=tenant_id)
    if session:
        await session.commit()
    return {"success": True, "data": rate, "errors": [], "meta": {}}


@router.get("/rates/monitoring/expiry")
async def get_rate_expiry_report(
    session: Annotated[AsyncSession, Depends(get_db)],
    today: date | None = None,
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    report = await service.get_expiry_report(today=today)
    return {"success": True, "data": report, "errors": [], "meta": {}}


@router.get("/rates/{rate_id}")
async def get_rate(
    rate_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
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
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    version = await service.create_rate_version(rate_id, payload.model_dump())
    if not version:
        raise NotFoundError(f"Rate {rate_id} not found")
    if session:
        await session.commit()
    return {"success": True, "data": version, "errors": [], "meta": {}}
