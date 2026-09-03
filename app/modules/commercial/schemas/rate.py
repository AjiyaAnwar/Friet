"""
Rate Engine API contracts - field names match freightcore_unified_erd.html
exactly (source3 block: RATE, RATE_VERSION, RATE_LINE).
"""

from pydantic import BaseModel
from datetime import date
from typing import Optional


class RateCreate(BaseModel):
    rate_number: str
    rate_type: str
    rate_category: str
    carrier_vendor_id: str
    provider_type: str = "CARRIER"
    service_name: str
    origin_location_id: str
    destination_location_id: str
    via_routing: Optional[str] = None
    commodity_id: Optional[str] = None
    customer_id: Optional[str] = None
    effective_date: date
    expiry_date: date
    currency_code: str


class RateResponse(RateCreate):
    id: str
    status: str


class RateLineInput(BaseModel):
    charge_code: str
    rate_basis: str
    weight_break_from: Optional[float] = None
    weight_break_to: Optional[float] = None
    container_type_code: Optional[str] = None
    amount: float


class RateVersionCreateRequest(BaseModel):
    modified_by: str
    reason: str
    lines: list[RateLineInput]


class RateVersionResponse(BaseModel):
    id: str
    rate_id: str
    version_number: int
    modified_by: str
    reason: str
    approval_status: str


class RateExpiryReport(BaseModel):
    warning: list[str]
    escalation: list[str]
    newly_expired: list[str]
