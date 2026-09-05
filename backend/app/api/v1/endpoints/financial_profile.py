"""Shipment Financial Profile Endpoints (SRS Phase 5.1).

Exposes:
  - GET  /api/v1/shipments/{shipment_id}/revenue-ledger
  - POST /api/v1/shipments/{shipment_id}/revenue-ledger
  - GET  /api/v1/shipments/{shipment_id}/cost-ledger
  - POST /api/v1/shipments/{shipment_id}/cost-ledger
  - GET  /api/v1/shipments/{shipment_id}/profitability
  - POST /api/v1/financial/entries/{entry_id}/reverse
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.session import get_db
from app.modules.financial.schemas import (
    CostLineCreateRequest,
    FinancialEntryReverseRequest,
    RevenueLineCreateRequest,
)
from app.modules.financial.service import ShipmentFinancialService

router = APIRouter()


# ---------------------------------------------------------------------------
# Revenue Ledger Endpoints
# ---------------------------------------------------------------------------

@router.get("/shipments/{shipment_id}/revenue-ledger")
async def get_revenue_ledger(
    shipment_id: Annotated[uuid.UUID, Path(...)],
    user: Annotated[CurrentUser, Depends(require_permission("financial:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Retrieve all revenue ledger lines for a shipment."""
    service = ShipmentFinancialService(session)
    lines = await service.get_revenue_ledger(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
    )
    return {
        "success": True,
        "data": lines,
        "errors": [],
        "meta": {"count": len(lines)},
    }


@router.post("/shipments/{shipment_id}/revenue-ledger", status_code=201)
async def add_revenue_line(
    shipment_id: Annotated[uuid.UUID, Path(...)],
    payload: RevenueLineCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("financial:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Add a new revenue ledger line to a shipment."""
    service = ShipmentFinancialService(session)
    line = await service.add_revenue_line(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        charge_code=payload.charge_code,
        amount=payload.amount,
        currency_code=payload.currency_code,
        is_additional=payload.is_additional,
        description=payload.description,
        quantity=payload.quantity,
        unit_rate=payload.unit_rate,
        quotation_line_id=payload.quotation_line_id,
        status=payload.status,
    )
    await session.commit()
    return {
        "success": True,
        "data": line,
        "errors": [],
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Direct Cost Ledger Endpoints
# ---------------------------------------------------------------------------

@router.get("/shipments/{shipment_id}/cost-ledger")
async def get_cost_ledger(
    shipment_id: Annotated[uuid.UUID, Path(...)],
    user: Annotated[CurrentUser, Depends(require_permission("financial:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Retrieve all direct cost ledger lines for a shipment."""
    service = ShipmentFinancialService(session)
    lines = await service.get_cost_ledger(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
    )
    return {
        "success": True,
        "data": lines,
        "errors": [],
        "meta": {"count": len(lines)},
    }


@router.post("/shipments/{shipment_id}/cost-ledger", status_code=201)
async def add_cost_line(
    shipment_id: Annotated[uuid.UUID, Path(...)],
    payload: CostLineCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("financial:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Add a new direct cost ledger line to a shipment."""
    service = ShipmentFinancialService(session)
    line = await service.add_cost_line(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        charge_code=payload.charge_code,
        amount=payload.amount,
        currency_code=payload.currency_code,
        vendor_id=payload.vendor_id,
        carrier_id=payload.carrier_id,
        is_additional=payload.is_additional,
        description=payload.description,
        quantity=payload.quantity,
        unit_rate=payload.unit_rate,
        quotation_line_id=payload.quotation_line_id,
        status=payload.status,
    )
    await session.commit()
    return {
        "success": True,
        "data": line,
        "errors": [],
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Profitability & Financial Health Endpoints
# ---------------------------------------------------------------------------

@router.get("/shipments/{shipment_id}/profitability")
async def get_profitability(
    shipment_id: Annotated[uuid.UUID, Path(...)],
    user: Annotated[CurrentUser, Depends(require_permission("financial:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Retrieve live profitability, gross margin, and cost/revenue breakdown for a shipment."""
    service = ShipmentFinancialService(session)
    prof = await service.get_profitability(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
    )
    return {
        "success": True,
        "data": prof,
        "errors": [],
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Financial Entry Reversals & Immutability
# ---------------------------------------------------------------------------

@router.post("/financial/entries/{entry_id}/reverse")
async def reverse_financial_entry(
    entry_id: Annotated[uuid.UUID, Path(...)],
    payload: FinancialEntryReverseRequest,
    user: Annotated[CurrentUser, Depends(require_permission("financial:approve"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Reverse and correct an immutable financial ledger entry with full audit trail."""
    service = ShipmentFinancialService(session)
    result = await service.reverse_and_correct_entry(
        entry_id=entry_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        reason=payload.reason,
        new_debit_amount=payload.new_debit_amount,
        new_credit_amount=payload.new_credit_amount,
        new_description=payload.new_description,
        approved_by=payload.approved_by,
    )
    await session.commit()
    return {
        "success": True,
        "data": result,
        "errors": [],
        "meta": {},
    }
