"""Pydantic schemas for Customer Invoicing (Phase 5.2)."""

from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class InvoiceGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: uuid.UUID
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    tax_jurisdiction: str | None = Field(default=None, max_length=64)
    payment_terms: str | None = Field(default=None, max_length=64)
    customer_po: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=500)
    revenue_line_ids: list[uuid.UUID] | None = Field(default=None)


class InvoiceApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=500)


class InvoiceSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_email: str | None = Field(default=None, max_length=255)


class CreditNoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=500)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class DebitNoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    charge_code: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=500)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=255)
