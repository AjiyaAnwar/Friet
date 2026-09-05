"""Commercial Master Data API endpoints."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user_optional, require_permission
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.db.models.reference import (
    Carrier,
    ChargeCode,
    Commodity,
    ContainerType,
    Currency,
    DocumentTypeRef,
    ExchangeRate,
    FlightSchedule,
    Incoterm,
    Location,
    PackageType,
    UldType,
    Vessel,
    VesselSchedule,
    Zone,
)
from app.modules.commercial.schemas.master_data import (
    CountryCreate,
    LocationCreate,
)
from app.modules.commercial.service import CommercialService

router = APIRouter()


class CarrierCreate(BaseModel):
    carrier_type: str
    name: str
    scac_code: str | None = None
    iata_code: str | None = None
    iata_prefix: str | None = None
    is_nvocc: bool = False
    hub_locations: list[str] | None = None


class VesselCreate(BaseModel):
    imo_number: str
    name: str
    owner_carrier_id: uuid.UUID
    flag: str | None = None
    teu_capacity: int | None = Field(None, ge=0)
    vessel_type: str | None = None


class VesselScheduleCreate(BaseModel):
    carrier_id: uuid.UUID
    vessel_id: uuid.UUID
    service_name: str
    voyage_number: str
    port_rotation: dict
    cy_cutoff: date | None = None
    si_cutoff: date | None = None
    vgm_cutoff: date | None = None


class FlightScheduleCreate(BaseModel):
    carrier_id: uuid.UUID
    origin_location_id: uuid.UUID
    destination_location_id: uuid.UUID
    flight_number: str
    frequency: list[str] | None = None
    scheduled_departure: str | None = None
    scheduled_arrival: str | None = None
    cargo_cutoff: str | None = None
    documentation_cutoff: str | None = None


class ZoneCreate(BaseModel):
    zone_code: str
    name: str
    country_id: uuid.UUID
    cities: list[str] = Field(default_factory=list)


class ExchangeRateUpsert(BaseModel):
    rate_to_base: Decimal = Field(gt=0)
    rate_date: date | None = None
    source: str = "MANUAL"


class IncotermCreate(BaseModel):
    code: str
    name: str


class ContainerTypeCreate(BaseModel):
    code: str
    cbm_capacity: Decimal = Field(gt=0)
    max_payload_kg: Decimal = Field(gt=0)


class CommodityCreate(BaseModel):
    hs_code: str = Field(min_length=6, max_length=6)
    name: str
    is_dgr: bool = False
    export_restricted: bool = False
    import_restricted: bool = False


class CurrencyCreate(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    name: str
    symbol: str | None = None


class PackageTypeCreate(BaseModel):
    code: str
    name: str


class UldTypeCreate(BaseModel):
    code: str
    name: str
    volume_cbm: Decimal = Field(gt=0)


class ChargeCodeCreate(BaseModel):
    code: str
    name: str
    charge_type: str
    rate_basis: str
    applicable_mode: str


class DocumentTypeCreate(BaseModel):
    code: str
    name: str
    applicable_mode: str


@router.post("/admin/zones")
async def create_zone(
    payload: ZoneCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    zone = Zone(**payload.model_dump()); session.add(zone); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(zone.id), **payload.model_dump(mode="json")}, "errors": [], "meta": {}}


@router.get("/admin/zones")
async def list_zones(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    q: str = "",
) -> dict:
    rows = (await session.execute(select(Zone).order_by(Zone.zone_code))).scalars().all()
    rows = [row for row in rows if not q or q.lower() in row.name.lower() or q.lower() in row.zone_code.lower()]
    return {"success": True, "data": [{"id": str(row.id), "zone_code": row.zone_code, "name": row.name, "country_id": str(row.country_id), "cities": row.cities} for row in rows], "errors": [], "meta": {"total": len(rows)}}


@router.patch("/admin/currencies/{code}/exchange-rate")
async def update_exchange_rate(
    code: str,
    payload: ExchangeRateUpsert,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
) -> dict:
    code = code.upper()
    if not (await session.execute(select(Currency.code).where(Currency.code == code))).scalar_one_or_none():
        raise NotFoundError("Currency not found")
    on_date = payload.rate_date or date.today()
    rate = (await session.execute(select(ExchangeRate).where(
        ExchangeRate.currency_code == code, ExchangeRate.rate_date == on_date, ExchangeRate.source == payload.source
    ))).scalar_one_or_none()
    if rate: rate.rate_to_base = payload.rate_to_base
    else:
        rate = ExchangeRate(currency_code=code, rate_date=on_date, rate_to_base=payload.rate_to_base, source=payload.source)
        session.add(rate)
    await session.flush(); await session.commit()
    return {"success": True, "data": {"currency_code": code, "rate_date": str(on_date), "rate_to_base": str(rate.rate_to_base), "source": rate.source}, "errors": [], "meta": {}}


@router.post("/admin/carriers")
async def create_carrier(
    payload: CarrierCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    carrier = Carrier(**payload.model_dump())
    session.add(carrier); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(carrier.id), **payload.model_dump()}, "errors": [], "meta": {}}


@router.get("/admin/carriers")
async def list_carriers(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    rows = (await session.execute(select(Carrier).order_by(Carrier.name))).scalars().all()
    return {"success": True, "data": [{"id": str(row.id), "name": row.name, "carrier_type": row.carrier_type, "scac_code": row.scac_code, "iata_code": row.iata_code, "iata_prefix": row.iata_prefix, "is_nvocc": row.is_nvocc, "hub_locations": row.hub_locations} for row in rows], "errors": [], "meta": {"total": len(rows)}}


@router.post("/admin/vessels")
async def create_vessel(
    payload: VesselCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    carrier = (await session.execute(select(Carrier.id).where(Carrier.id == payload.owner_carrier_id))).scalar_one_or_none()
    if not carrier: raise NotFoundError("Carrier not found")
    vessel = Vessel(**payload.model_dump()); session.add(vessel); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(vessel.id), "imo_number": vessel.imo_number, "name": vessel.name}, "errors": [], "meta": {}}


@router.post("/admin/vessel-schedules")
async def create_vessel_schedule(
    payload: VesselScheduleCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    if not isinstance(payload.port_rotation.get("calls", payload.port_rotation), list):
        raise ValueError("port_rotation must contain a calls list")
    schedule = VesselSchedule(**payload.model_dump()); session.add(schedule); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(schedule.id), "voyage_number": schedule.voyage_number}, "errors": [], "meta": {}}


@router.get("/customers/{customer_id}/credit-position")
async def customer_credit_position(
    customer_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
) -> dict:
    position = await CommercialService(session).credit_position(customer_id, user.tenant_id)
    return {"success": True, "data": position, "errors": [], "meta": {}}


@router.get("/admin/countries")
@router.get("/countries")
async def list_countries(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    countries = await CommercialService(session).list_countries()
    return {"success": True, "data": countries, "errors": [], "meta": {"total": len(countries)}}


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


# ---------------------------------------------------------------------------
# Flight Schedule Master
# ---------------------------------------------------------------------------

@router.post("/admin/flight-schedules")
async def create_flight_schedule(
    payload: FlightScheduleCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    schedule = FlightSchedule(**payload.model_dump())
    session.add(schedule)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"id": str(schedule.id), "flight_number": schedule.flight_number}, "errors": [], "meta": {}}


@router.get("/admin/flight-schedules")
async def list_flight_schedules(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(FlightSchedule).order_by(FlightSchedule.flight_number))).scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "carrier_id": str(r.carrier_id),
                "origin_location_id": str(r.origin_location_id),
                "destination_location_id": str(r.destination_location_id),
                "flight_number": r.flight_number,
                "frequency": r.frequency,
                "scheduled_departure": r.scheduled_departure,
                "scheduled_arrival": r.scheduled_arrival,
                "cargo_cutoff": r.cargo_cutoff,
                "documentation_cutoff": r.documentation_cutoff,
            }
            for r in rows
        ],
        "errors": [],
        "meta": {"total": len(rows)},
    }


# ---------------------------------------------------------------------------
# Reference Lookups (Incoterms, Containers, Commodities, etc.)
# ---------------------------------------------------------------------------

@router.post("/admin/incoterms")
async def create_incoterm(
    payload: IncotermCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(Incoterm).where(Incoterm.code == code))).scalar_one_or_none()
    if existing:
        existing.name = payload.name
    else:
        existing = Incoterm(code=code, name=payload.name)
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "name": payload.name}, "errors": [], "meta": {}}


@router.get("/admin/incoterms")
@router.get("/incoterms")
async def list_incoterms(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(Incoterm).order_by(Incoterm.code))).scalars().all()
    return {"success": True, "data": [{"code": r.code, "name": r.name} for r in rows], "errors": [], "meta": {"total": len(rows)}}


@router.post("/admin/container-types")
async def create_container_type(
    payload: ContainerTypeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(ContainerType).where(ContainerType.code == code))).scalar_one_or_none()
    if existing:
        existing.cbm_capacity = payload.cbm_capacity
        existing.max_payload_kg = payload.max_payload_kg
    else:
        existing = ContainerType(code=code, cbm_capacity=payload.cbm_capacity, max_payload_kg=payload.max_payload_kg)
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "cbm_capacity": float(payload.cbm_capacity), "max_payload_kg": float(payload.max_payload_kg)}, "errors": [], "meta": {}}


@router.get("/admin/container-types")
@router.get("/container-types")
async def list_container_types(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(ContainerType).order_by(ContainerType.code))).scalars().all()
    return {
        "success": True,
        "data": [{"code": r.code, "cbm_capacity": float(r.cbm_capacity), "max_payload_kg": float(r.max_payload_kg)} for r in rows],
        "errors": [],
        "meta": {"total": len(rows)},
    }


@router.post("/admin/commodities")
async def create_commodity(
    payload: CommodityCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    commodity = Commodity(**payload.model_dump())
    session.add(commodity)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"id": str(commodity.id), "hs_code": commodity.hs_code, "name": commodity.name}, "errors": [], "meta": {}}


@router.get("/admin/commodities")
@router.get("/commodities")
async def list_commodities(
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str = "",
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(Commodity).order_by(Commodity.name))).scalars().all()
    if q:
        rows = [r for r in rows if q.lower() in r.name.lower() or q in r.hs_code]
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "hs_code": r.hs_code,
                "name": r.name,
                "is_dgr": r.is_dgr,
                "export_restricted": r.export_restricted,
                "import_restricted": r.import_restricted,
            }
            for r in rows
        ],
        "errors": [],
        "meta": {"total": len(rows)},
    }


@router.post("/admin/currencies")
async def create_currency(
    payload: CurrencyCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(Currency).where(Currency.code == code))).scalar_one_or_none()
    if existing:
        existing.name = payload.name
        existing.symbol = payload.symbol
    else:
        existing = Currency(code=code, name=payload.name, symbol=payload.symbol)
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "name": payload.name, "symbol": payload.symbol}, "errors": [], "meta": {}}


@router.get("/admin/currencies")
@router.get("/currencies")
async def list_currencies(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(Currency).order_by(Currency.code))).scalars().all()
    return {"success": True, "data": [{"code": r.code, "name": r.name, "symbol": r.symbol} for r in rows], "errors": [], "meta": {"total": len(rows)}}


@router.post("/admin/package-types")
async def create_package_type(
    payload: PackageTypeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(PackageType).where(PackageType.code == code))).scalar_one_or_none()
    if existing:
        existing.name = payload.name
    else:
        existing = PackageType(code=code, name=payload.name)
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "name": payload.name}, "errors": [], "meta": {}}


@router.get("/admin/package-types")
@router.get("/package-types")
async def list_package_types(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(PackageType).order_by(PackageType.code))).scalars().all()
    return {"success": True, "data": [{"code": r.code, "name": r.name} for r in rows], "errors": [], "meta": {"total": len(rows)}}


@router.post("/admin/uld-types")
async def create_uld_type(
    payload: UldTypeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(UldType).where(UldType.code == code))).scalar_one_or_none()
    if existing:
        existing.name = payload.name
        existing.volume_cbm = payload.volume_cbm
    else:
        existing = UldType(code=code, name=payload.name, volume_cbm=payload.volume_cbm)
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "name": payload.name, "volume_cbm": float(payload.volume_cbm)}, "errors": [], "meta": {}}


@router.get("/admin/uld-types")
@router.get("/uld-types")
async def list_uld_types(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(UldType).order_by(UldType.code))).scalars().all()
    return {"success": True, "data": [{"code": r.code, "name": r.name, "volume_cbm": float(r.volume_cbm)} for r in rows], "errors": [], "meta": {"total": len(rows)}}


@router.post("/admin/charge-codes")
async def create_charge_code(
    payload: ChargeCodeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(ChargeCode).where(ChargeCode.code == code))).scalar_one_or_none()
    if existing:
        existing.name = payload.name
        existing.charge_type = payload.charge_type
        existing.rate_basis = payload.rate_basis
        existing.applicable_mode = payload.applicable_mode
    else:
        existing = ChargeCode(
            code=code,
            name=payload.name,
            charge_type=payload.charge_type,
            rate_basis=payload.rate_basis,
            applicable_mode=payload.applicable_mode,
        )
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "name": payload.name}, "errors": [], "meta": {}}


@router.get("/admin/charge-codes")
@router.get("/charge-codes")
async def list_charge_codes(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(ChargeCode).order_by(ChargeCode.code))).scalars().all()
    return {
        "success": True,
        "data": [
            {
                "code": r.code,
                "name": r.name,
                "charge_type": r.charge_type,
                "rate_basis": r.rate_basis,
                "applicable_mode": r.applicable_mode,
            }
            for r in rows
        ],
        "errors": [],
        "meta": {"total": len(rows)},
    }


@router.post("/admin/document-types")
async def create_document_type(
    payload: DocumentTypeCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    code = payload.code.upper()
    existing = (await session.execute(select(DocumentTypeRef).where(DocumentTypeRef.code == code))).scalar_one_or_none()
    if existing:
        existing.name = payload.name
        existing.applicable_mode = payload.applicable_mode
    else:
        existing = DocumentTypeRef(code=code, name=payload.name, applicable_mode=payload.applicable_mode)
        session.add(existing)
    await session.flush()
    await session.commit()
    return {"success": True, "data": {"code": code, "name": payload.name}, "errors": [], "meta": {}}


@router.get("/admin/document-types")
@router.get("/document-types")
async def list_document_types(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    rows = (await session.execute(select(DocumentTypeRef).order_by(DocumentTypeRef.code))).scalars().all()
    return {"success": True, "data": [{"code": r.code, "name": r.name, "applicable_mode": r.applicable_mode} for r in rows], "errors": [], "meta": {"total": len(rows)}}
