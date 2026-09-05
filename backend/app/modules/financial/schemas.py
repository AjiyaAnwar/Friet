"""Pydantic schemas for Shipment Financial Profile (Phase 5.1)."""

from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RevenueLineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    charge_code: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., ge=0)
    currency_code: str = Field(default="USD", min_length=3, max_length=3)
    is_additional: bool = Field(default=True)
    description: str | None = Field(default=None, max_length=255)
    quantity: float = Field(default=1.0, gt=0)
    unit_rate: float | None = Field(default=None, ge=0)
    quotation_line_id: uuid.UUID | None = Field(default=None)
    status: str = Field(default="ESTIMATED")


class CostLineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    charge_code: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., ge=0)
    currency_code: str = Field(default="USD", min_length=3, max_length=3)
    vendor_id: uuid.UUID | None = Field(default=None)
    carrier_id: uuid.UUID | None = Field(default=None)
    is_additional: bool = Field(default=True)
    description: str | None = Field(default=None, max_length=255)
    quantity: float = Field(default=1.0, gt=0)
    unit_rate: float | None = Field(default=None, ge=0)
    quotation_line_id: uuid.UUID | None = Field(default=None)
    status: str = Field(default="ESTIMATED")


class FinancialEntryReverseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=3, max_length=500)
    new_debit_amount: float = Field(default=0.0, ge=0)
    new_credit_amount: float = Field(default=0.0, ge=0)
    new_description: str | None = Field(default=None, max_length=500)
    approved_by: uuid.UUID | None = Field(default=None)
