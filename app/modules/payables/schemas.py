"""Pydantic schemas for Accounts Payable and Carrier Cost Verification (Phase 5.3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field


class PayableLineCreate(BaseModel):
    charge_code: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    quantity: float = Field(default=1.0, gt=0)
    unit_rate: float | None = None
    billed_amount: float = Field(..., gt=0)
    cost_line_id: uuid.UUID | None = None


class PayableCreateRequest(BaseModel):
    shipment_id: uuid.UUID
    vendor_id: uuid.UUID | None = None
    carrier_id: uuid.UUID | None = None
    bill_number: str = Field(..., min_length=1, max_length=64)
    bill_date: date | None = None
    due_date: date | None = None
    currency_code: str = Field(default="USD", min_length=3, max_length=3)
    tax_amount: float = Field(default=0.0, ge=0)
    lines: list[PayableLineCreate] = Field(..., min_length=1)
    supporting_document_url: str | None = None
    notes: str | None = None


class PayableVerifyRequest(BaseModel):
    notes: str | None = None
    allow_material_variance: bool = False


class PayableApproveRequest(BaseModel):
    notes: str | None = None


class PayablePaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)
    payment_reference: str = Field(..., min_length=1, max_length=64)
    payment_date: date | None = None
    currency_code: str | None = None
    payment_method: str = Field(default="WIRE_TRANSFER")
    notes: str | None = None


class PayableLineResponse(BaseModel):
    id: str
    charge_code: str
    description: str | None
    quantity: float
    unit_rate: float | None
    expected_amount: float
    billed_amount: float
    variance_amount: float
    currency_code: str
    status: str
    cost_line_id: str | None


class PayablePaymentResponse(BaseModel):
    id: str
    payment_reference: str
    payment_date: str
    amount: float
    currency_code: str
    payment_method: str
    recorded_by: str
    notes: str | None


class PayableResponse(BaseModel):
    id: str
    tenant_id: str
    shipment_id: str
    vendor_id: str | None
    carrier_id: str | None
    bill_number: str
    bill_date: str
    due_date: str | None
    currency_code: str
    subtotal_amount: float
    tax_amount: float
    total_amount: float
    paid_amount: float
    status: str
    verification_status: str
    approval_status: str
    verified_by: str | None
    verified_at: str | None
    approved_by: str | None
    approved_at: str | None
    rejection_reason: str | None
    variance_amount: float
    supporting_document_url: str | None
    notes: str | None
    lines: list[PayableLineResponse]
    payments: list[PayablePaymentResponse]
