"""Commercial Analytics endpoints (Phase 7).

Provides:
  7.1  RFQ Funnel Analytics
  7.2  Quotation Win / Loss Analytics
  7.3  Revenue Analytics
  7.4  Rate Competitiveness Analysis
  7.5  Rate Utilization Heatmap Data
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.session import get_db
from app.modules.commercial.analytics.service import CommercialAnalyticsService

router = APIRouter()


# ---------------------------------------------------------------------------
# 7.1 RFQ Funnel Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/rfq-funnel")
async def get_rfq_funnel(
    user: Annotated[CurrentUser, Depends(require_permission("quotation:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    customer_id: str | None = Query(None),
    mode: str | None = Query(None),
) -> dict[str, Any]:
    """Return RFQ count, count at each lifecycle stage, conversion rates, and average aging."""
    service = CommercialAnalyticsService(session)
    result = await service.rfq_funnel(
        tenant_id=user.tenant_id,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        mode=mode,
    )
    return {"success": True, "data": result, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# 7.2 Quotation Win/Loss Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/quotation-win-loss")
async def get_quotation_win_loss(
    user: Annotated[CurrentUser, Depends(require_permission("quotation:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    customer_id: str | None = Query(None),
    carrier_id: str | None = Query(None),
    origin_location_id: str | None = Query(None),
    destination_location_id: str | None = Query(None),
) -> dict[str, Any]:
    """Provide win/loss analytics grouped by customer, lane, and mode."""
    service = CommercialAnalyticsService(session)
    result = await service.quotation_win_loss(
        tenant_id=user.tenant_id,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        carrier_id=carrier_id,
        origin_location_id=origin_location_id,
        destination_location_id=destination_location_id,
    )
    return {"success": True, "data": result, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# 7.3 Revenue Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/revenue")
async def get_revenue_analytics(
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    customer_id: str | None = Query(None),
    mode: str | None = Query(None),
    origin_location_id: str | None = Query(None),
    destination_location_id: str | None = Query(None),
    branch_id: str | None = Query(None),
) -> dict[str, Any]:
    """Provide revenue analytics grouped/filterable by customer, trade lane, mode, and branch."""
    service = CommercialAnalyticsService(session)
    result = await service.revenue_analytics(
        tenant_id=user.tenant_id,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        mode=mode,
        origin_location_id=origin_location_id,
        destination_location_id=destination_location_id,
        branch_id=branch_id,
    )
    return {"success": True, "data": result, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# 7.4 Rate Competitiveness Analysis
# ---------------------------------------------------------------------------

@router.get("/analytics/rate-competitiveness")
async def get_rate_competitiveness(
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    as_of_date: date | None = Query(None),
    mode: str | None = Query(None),
    top_n: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Compare contracted rates against market averages for top lanes."""
    service = CommercialAnalyticsService(session)
    result = await service.rate_competitiveness(
        tenant_id=user.tenant_id,
        as_of_date=as_of_date,
        mode=mode,
        top_n=top_n,
    )
    return {"success": True, "data": result, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# 7.5 Rate Utilization Heatmap Data
# ---------------------------------------------------------------------------

@router.get("/analytics/rate-heatmap")
async def get_rate_heatmap(
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    as_of_date: date | None = Query(None),
    mode: str | None = Query(None),
) -> dict[str, Any]:
    """Identify lanes with active rate coverage vs uncovered lanes for frontend heatmap."""
    service = CommercialAnalyticsService(session)
    result = await service.rate_heatmap(
        tenant_id=user.tenant_id,
        as_of_date=as_of_date,
        mode=mode,
    )
    return {"success": True, "data": result, "errors": [], "meta": {}}

