"""Pydantic schemas for Phase 5 Financial Integrity."""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class VendorBillMatchRequest(BaseModel):
    vendor_id: Optional[str] = None
    shipment_id: Optional[str] = None
    shipment_reference: Optional[str] = None
    vendor_invoice_reference: Optional[str] = None
    charge_code: Optional[str] = None
    invoiced_rate_amount: float = Field(..., ge=0)
    currency_code: str = Field(..., min_length=3, max_length=3)
    invoice_date: date
    origin_location_id: Optional[str] = None
    destination_location_id: Optional[str] = None
    mode: Optional[str] = None


class AgentSettlementRequest(BaseModel):
    agent_id: str
    shipment_id: Optional[str] = None
    base_amount: float = Field(..., ge=0)
    currency_code: str = Field(..., min_length=3, max_length=3)
    settlement_date: date
    notes: Optional[str] = None


class MarketRateCreateRequest(BaseModel):
    origin_location_id: str
    destination_location_id: str
    mode: str
    rate_type: str
    amount: float = Field(..., ge=0)
    currency_code: str = Field(..., min_length=3, max_length=3)
    effective_date: date
    expiry_date: Optional[date] = None
    source: str = "manual"
    notes: Optional[str] = None

