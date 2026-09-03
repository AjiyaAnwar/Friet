"""
Master Data API contracts - field names match freightcore_unified_erd.html
exactly (source1 block: COUNTRY, LOCATION, INCOTERM, CONTAINER_TYPE).
"""

from pydantic import BaseModel, Field
from typing import Optional


class CountryCreate(BaseModel):
    iso_code: str = Field(..., min_length=2, max_length=2)
    name: str
    region: str
    trade_zone: str
    is_sanctioned: bool = False
    requires_permit: bool = False


class CountryResponse(CountryCreate):
    id: str


class LocationCreate(BaseModel):
    un_locode: str
    iata_code: Optional[str] = None
    name: str
    country_id: str
    city: str
    type: str
    timezone: str
    is_active: bool = True


class LocationResponse(LocationCreate):
    id: str


class IncotermCreate(BaseModel):
    code: str
    name: str


class ContainerTypeCreate(BaseModel):
    code: str
    cbm_capacity: float
    max_payload_kg: float
