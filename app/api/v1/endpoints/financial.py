"""Financial Integrity endpoints (Phase 5).

Provides:
  5.1  Vendor bill matching & discrepancy management
  5.2  Agent settlement rate management & audit trail
  5.3  Quarterly rate review report
  +    Market rate ingestion (support for 5.3 and 7.4)
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.commercial.financial.service import FinancialIntegrityService
from app.modules.commercial.schemas.financial import (
    AgentSettlementRequest,
    MarketRateCreateRequest,
    VendorBillMatchRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# 5.1 Vendor Bill Matching
# ---------------------------------------------------------------------------

@router.post("/financial/vendor-bills/match")
async def match_vendor_bill(
    payload: VendorBillMatchRequest,
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Match vendor invoice rate against applicable contracted rate."""
    service = FinancialIntegrityService(session)
    result = await service.match_vendor_bill(
        tenant_id=user.tenant_id,
        vendor_id=payload.vendor_id,
        shipment_id=payload.shipment_id,
        shipment_reference=payload.shipment_reference,
        vendor_invoice_reference=payload.vendor_invoice_reference,
        charge_code=payload.charge_code,
        invoiced_rate_amount=payload.invoiced_rate_amount,
        currency_code=payload.currency_code,
        invoice_date=payload.invoice_date,
        origin_location_id=payload.origin_location_id,
        destination_location_id=payload.destination_location_id,
        mode=payload.mode,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.get("/financial/vendor-bills/discrepancies")
async def list_vendor_bill_discrepancies(
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None),
    vendor_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """List open or filtered vendor bill discrepancies."""
    service = FinancialIntegrityService(session)
    discrepancies = await service.list_discrepancies(
        tenant_id=user.tenant_id,
        status=status,
        vendor_id=vendor_id,
        limit=limit,
    )
    return {
        "success": True,
        "data": discrepancies,
        "errors": [],
        "meta": {"total": len(discrepancies)},
    }


@router.get("/financial/vendor-bills/discrepancies/{discrepancy_id}")
async def get_vendor_bill_discrepancy(
    discrepancy_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Get single vendor bill discrepancy by ID."""
    service = FinancialIntegrityService(session)
    discrepancy = await service.get_discrepancy(discrepancy_id, user.tenant_id)
    return {"success": True, "data": discrepancy, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# 5.2 Agent Settlement Rate Management
# ---------------------------------------------------------------------------

@router.post("/financial/agent-settlements")
async def calculate_agent_settlement(
    payload: AgentSettlementRequest,
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Calculate agent settlement amount using active contracted rate."""
    service = FinancialIntegrityService(session)
    settlement = await service.calculate_agent_settlement(
        tenant_id=user.tenant_id,
        agent_id=payload.agent_id,
        shipment_id=payload.shipment_id,
        base_amount=payload.base_amount,
        currency_code=payload.currency_code,
        settlement_date=payload.settlement_date,
        calculated_by=user.id,
        notes=payload.notes,
    )
    if session:
        await session.commit()
    return {"success": True, "data": settlement, "errors": [], "meta": {}}


@router.get("/financial/agent-settlements/{settlement_id}")
async def get_agent_settlement(
    settlement_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Get single agent settlement record by ID."""
    service = FinancialIntegrityService(session)
    settlement = await service.get_settlement(settlement_id, user.tenant_id)
    return {"success": True, "data": settlement, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# 5.3 Quarterly Rate Review Report
# ---------------------------------------------------------------------------

@router.get("/financial/rate-review")
async def quarterly_rate_review(
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    as_of_date: date | None = Query(None),
    mode: str | None = Query(None),
    origin_location_id: str | None = Query(None),
    destination_location_id: str | None = Query(None),
    warning_days: int = Query(90, ge=1, le=365),
) -> dict[str, Any]:
    """Generate quarterly rate review report comparing contracted vs market rates."""
    service = FinancialIntegrityService(session)
    report = await service.quarterly_rate_review(
        tenant_id=user.tenant_id,
        as_of_date=as_of_date,
        mode=mode,
        origin_location_id=origin_location_id,
        destination_location_id=destination_location_id,
        warning_days=warning_days,
    )
    return {"success": True, "data": report, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# Market Rate Ingestion (Supports 5.3 and 7.4)
# ---------------------------------------------------------------------------

@router.post("/financial/market-rates")
async def create_market_rate(
    payload: MarketRateCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Ingest external market rate benchmark for a lane."""
    service = FinancialIntegrityService(session)
    result = await service.create_market_rate(
        payload.model_dump(), tenant_id=user.tenant_id
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}

