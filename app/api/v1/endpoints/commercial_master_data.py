"""Commercial Master Data API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user_optional
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.commercial.schemas.master_data import (
    CountryCreate,
    LocationCreate,
)
from app.modules.commercial.service import CommercialService

router = APIRouter()


@router.post("/admin/countries")
@router.post("/countries")
async def create_country(
    payload: CountryCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    country = await service.create_country(payload.model_dump())
    if session:
        await session.commit()
    return {"success": True, "data": country, "errors": [], "meta": {}}


@router.get("/admin/countries/{country_id}")
@router.get("/countries/{country_id}")
async def get_country(
    country_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    country = await service.get_country(country_id)
    if not country:
        raise NotFoundError(f"Country {country_id} not found")
    return {"success": True, "data": country, "errors": [], "meta": {}}


@router.post("/admin/locations")
async def create_location(
    payload: LocationCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    location = await service.create_location(payload.model_dump())
    if session:
        await session.commit()
    return {"success": True, "data": location, "errors": [], "meta": {}}


@router.get("/locations")
async def search_locations(
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str = "",
    type: str | None = None,
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    service = CommercialService(session)
    locations = await service.search_locations(query=q, location_type=type)
    return {"success": True, "data": locations, "errors": [], "meta": {"total": len(locations)}}
