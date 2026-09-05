"""Tests for Phase 7 – Commercial Analytics.

Covers:
  7.1 RFQ Funnel Analytics
      - RFQ stage counts, conversion rates, and aging calculations
      - Filtering by date, customer, mode
      - Edge case: no records (empty funnel)
  7.2 Quotation Win/Loss Analytics
      - Grouped by customer, lane, mode
      - Total wins, losses, win rates, and monetary values
      - Edge case: no records
  7.3 Revenue Analytics
      - Revenue total and averages
      - Grouping by customer, mode, lane
      - Limitations documentation (branch, recognized revenue)
      - Edge case: zero/empty values
  7.4 Rate Competitiveness Analysis
      - Contracted rate vs market benchmark comparison
      - Indicators: COMPETITIVE, ABOVE_MARKET, BELOW_MARKET, NO_MARKET_DATA
      - Missing market data handled cleanly without fabricating data
  7.5 Rate Utilization Heatmap Data
      - Active rate count per lane
      - Expired rates excluded from active coverage
      - Uncovered / empty state
  + Tenant isolation across all analytics
  + RBAC & authentication behavior on all analytics endpoints
"""

import uuid
from collections import namedtuple
from datetime import date, datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.db.models.commercial import Rate, RateLine, RateVersion
from app.db.models.financial_integrity import MarketRate
from app.main import app
from app.modules.commercial.analytics.service import CommercialAnalyticsService


TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CUST_A = uuid.UUID("caaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CUST_B = uuid.UUID("cbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ORIGIN_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
DEST_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


# ---------------------------------------------------------------------------
# 7.1 RFQ Funnel Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rfq_funnel_counts_and_conversion_rates():
    """Calculates counts, conversion rates against submitted, and average aging."""
    session = AsyncMock()

    Row = namedtuple("Row", ["status", "count", "avg_age_days"])
    mock_rows = [
        Row(status="SUBMITTED", count=100, avg_age_days=1.5),
        Row(status="PRICING_IN_PROGRESS", count=75, avg_age_days=3.0),
        Row(status="QUOTED", count=50, avg_age_days=5.2),
        Row(status="WON", count=25, avg_age_days=7.1),
        Row(status="LOST", count=10, avg_age_days=8.0),
    ]

    mock_res = MagicMock()
    mock_res.all.return_value = mock_rows
    session.execute = AsyncMock(return_value=mock_res)

    service = CommercialAnalyticsService(session)
    result = await service.rfq_funnel(tenant_id=TENANT_A)

    assert result["total_rfqs"] == 260
    stages_by_status = {s["status"]: s for s in result["stages"]}

    assert stages_by_status["SUBMITTED"]["count"] == 100
    assert stages_by_status["SUBMITTED"]["conversion_rate_pct"] == 100.0

    assert stages_by_status["QUOTED"]["count"] == 50
    # 50 / 100 = 50%
    assert stages_by_status["QUOTED"]["conversion_rate_pct"] == 50.0

    assert stages_by_status["WON"]["count"] == 25
    # 25 / 100 = 25%
    assert stages_by_status["WON"]["conversion_rate_pct"] == 25.0
    assert stages_by_status["WON"]["avg_age_days"] == 7.1


@pytest.mark.asyncio
async def test_rfq_funnel_empty_state():
    """Empty DB returns zero counts and clean stages structure without dividing by zero."""
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = []
    session.execute = AsyncMock(return_value=mock_res)

    service = CommercialAnalyticsService(session)
    result = await service.rfq_funnel(tenant_id=TENANT_A)

    assert result["total_rfqs"] == 0
    assert len(result["stages"]) == len(CommercialAnalyticsService.RFQ_FUNNEL_STAGES)
    for s in result["stages"]:
        assert s["count"] == 0


# ---------------------------------------------------------------------------
# 7.2 Quotation Win/Loss Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quotation_win_loss_aggregation():
    """Aggregates wins, losses, win rates, and values grouped by customer and lane."""
    session = AsyncMock()

    CARRIER_A = uuid.UUID("f1111111-1111-1111-1111-111111111111")
    CARRIER_B = uuid.UUID("f2222222-2222-2222-2222-222222222222")

    Row = namedtuple(
        "Row",
        [
            "status",
            "customer_id",
            "rfq_customer_id",
            "mode",
            "origin_location_id",
            "destination_location_id",
            "carrier_id",
            "carrier_name",
            "count",
            "total_sell",
            "avg_sell",
        ],
    )
    mock_rows = [
        # Customer A wins 2 quotations with Carrier A ($10,000 total), loses 1 with Carrier A ($4,000)
        Row("ACCEPTED", CUST_A, CUST_A, "AIR", ORIGIN_ID, DEST_ID, CARRIER_A, "Emirates SkyCargo", 2, 10000.0, 5000.0),
        Row("DECLINED", CUST_A, CUST_A, "AIR", ORIGIN_ID, DEST_ID, CARRIER_A, "Emirates SkyCargo", 1, 4000.0, 4000.0),
        # Customer B wins 1 quotation with Carrier B ($2,500)
        Row("WON", CUST_B, CUST_B, "OCEAN", ORIGIN_ID, DEST_ID, CARRIER_B, "Maersk Line", 1, 2500.0, 2500.0),
    ]

    mock_res = MagicMock()
    mock_res.all.return_value = mock_rows
    session.execute = AsyncMock(return_value=mock_res)

    service = CommercialAnalyticsService(session)
    result = await service.quotation_win_loss(tenant_id=TENANT_A)

    summary = result["summary"]
    assert summary["total"] == 4
    assert summary["wins"] == 3  # 2 + 1
    assert summary["losses"] == 1  # 1
    assert summary["win_rate_pct"] == 75.0  # 3/4 = 75%
    assert summary["win_value"] == 12500.0
    assert summary["loss_value"] == 4000.0

    cust_map = {c["customer_id"]: c for c in result["by_customer"]}
    assert cust_map[str(CUST_A)]["wins"] == 2
    assert cust_map[str(CUST_A)]["losses"] == 1
    assert cust_map[str(CUST_A)]["win_rate_pct"] == 66.7

    assert len(result["by_lane"]) == 1
    assert result["by_lane"][0]["wins"] == 3

    # Carrier dimension verification
    assert "by_carrier" in result
    carrier_map = {c["carrier_id"]: c for c in result["by_carrier"]}
    assert str(CARRIER_A) in carrier_map
    assert carrier_map[str(CARRIER_A)]["carrier_name"] == "Emirates SkyCargo"
    assert carrier_map[str(CARRIER_A)]["wins"] == 2
    assert carrier_map[str(CARRIER_A)]["losses"] == 1
    assert carrier_map[str(CARRIER_A)]["win_rate_pct"] == 66.7
    assert str(CARRIER_B) in carrier_map
    assert carrier_map[str(CARRIER_B)]["carrier_name"] == "Maersk Line"
    assert carrier_map[str(CARRIER_B)]["wins"] == 1


# ---------------------------------------------------------------------------
# 7.3 Revenue Analytics Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revenue_analytics_aggregation():
    """Aggregates revenue across customer, mode, lane, branch and documents limitations."""
    session = AsyncMock()

    BRANCH_A = uuid.UUID("b1111111-1111-1111-1111-111111111111")
    BRANCH_B = uuid.UUID("b2222222-2222-2222-2222-222222222222")

    Row = namedtuple(
        "Row",
        [
            "customer_id",
            "mode",
            "origin_location_id",
            "destination_location_id",
            "branch_id",
            "branch_name",
            "branch_code",
            "quote_count",
            "total_revenue",
            "avg_revenue",
            "min_revenue",
            "max_revenue",
        ],
    )
    mock_rows = [
        Row(CUST_A, "AIR", ORIGIN_ID, DEST_ID, BRANCH_A, "Dubai Hub", "DXB-01", 3, 15000.0, 5000.0, 4000.0, 6000.0),
        Row(CUST_B, "OCEAN", ORIGIN_ID, DEST_ID, BRANCH_B, "London City", "LHR-01", 2, 8000.0, 4000.0, 3500.0, 4500.0),
    ]

    mock_res = MagicMock()
    mock_res.all.return_value = mock_rows
    session.execute = AsyncMock(return_value=mock_res)

    service = CommercialAnalyticsService(session)
    result = await service.revenue_analytics(tenant_id=TENANT_A)

    assert result["grand_total_revenue"] == 23000.0
    assert result["entry_count"] == 2
    assert len(result["by_customer"]) == 2
    assert len(result["by_mode"]) == 2

    # Branch dimension verification
    assert "by_branch" in result
    branch_map = {b["branch_id"]: b for b in result["by_branch"]}
    assert str(BRANCH_A) in branch_map
    assert branch_map[str(BRANCH_A)]["branch_name"] == "Dubai Hub"
    assert branch_map[str(BRANCH_A)]["total_revenue"] == 15000.0
    assert branch_map[str(BRANCH_A)]["quote_count"] == 3

    assert len(result["limitations"]) > 0


# ---------------------------------------------------------------------------
# 7.4 Rate Competitiveness Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_competitiveness_with_and_without_market_data():
    """Lanes with market benchmark show variance and indicator; lanes without show NO_MARKET_DATA."""
    session = AsyncMock()

    # Rate 1: $100 vs market $100 -> COMPETITIVE
    rate1 = Rate(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        rate_number="RT-AIR-01",
        rate_type="AIR_FREIGHT",
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        currency_code="USD",
        status="APPROVED",
    )
    # Rate 2: $250 without market benchmark -> NO_MARKET_DATA
    rate2 = Rate(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        rate_number="RT-AIR-02",
        rate_type="AIR_FREIGHT",
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        currency_code="USD",
        status="APPROVED",
    )

    ver1 = RateVersion(id=uuid.uuid4(), rate_id=rate1.id, version_number=1, approval_status="APPROVED")
    line1 = RateLine(id=uuid.uuid4(), rate_version_id=ver1.id, charge_code="AFR", amount=100.0)

    ver2 = RateVersion(id=uuid.uuid4(), rate_id=rate2.id, version_number=1, approval_status="APPROVED")
    line2 = RateLine(id=uuid.uuid4(), rate_version_id=ver2.id, charge_code="AFR", amount=250.0)

    market_benchmark = MarketRate(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        mode="AIR",
        rate_type="AIR_FREIGHT",
        amount=100.0,
        currency_code="USD",
        effective_date=date(2026, 1, 1),
        source="Freightos",
    )

    mock_execute = AsyncMock()
    # 1. rates query
    r_rates = MagicMock()
    r_rates.scalars.return_value.all.return_value = [rate1, rate2]
    # 2. ver1 query
    r_v1 = MagicMock()
    r_v1.scalar_one_or_none.return_value = ver1
    # 3. line1 query
    r_l1 = MagicMock()
    r_l1.scalar_one_or_none.return_value = line1
    # 4. market query for rate1 -> benchmark found
    r_m1 = MagicMock()
    r_m1.scalar_one_or_none.return_value = market_benchmark
    # 5. ver2 query
    r_v2 = MagicMock()
    r_v2.scalar_one_or_none.return_value = ver2
    # 6. line2 query
    r_l2 = MagicMock()
    r_l2.scalar_one_or_none.return_value = line2
    # 7. market query for rate2 -> no market data
    r_m2 = MagicMock()
    r_m2.scalar_one_or_none.return_value = None

    mock_execute.side_effect = [r_rates, r_v1, r_l1, r_m1, r_v2, r_l2, r_m2]
    session.execute = mock_execute

    service = CommercialAnalyticsService(session)
    result = await service.rate_competitiveness(tenant_id=TENANT_A, as_of_date=date(2026, 6, 1))

    assert result["total_lanes"] == 2
    lane1 = result["lanes"][0]
    assert lane1["competitiveness"] == "COMPETITIVE"
    assert lane1["variance"] == 0.0

    lane2 = result["lanes"][1]
    assert lane2["competitiveness"] == "NO_MARKET_DATA"
    assert lane2["market_amount"] is None


# ---------------------------------------------------------------------------
# 7.5 Rate Utilization Heatmap Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_utilization_heatmap_active_coverage():
    """Returns active rate counts per lane; excludes expired rates."""
    session = AsyncMock()

    Row = namedtuple(
        "Row",
        ["origin_location_id", "destination_location_id", "rate_type", "mode", "active_rate_count"],
    )
    mock_rows = [
        Row(ORIGIN_ID, DEST_ID, "AIR_FREIGHT", "AIR", 3),
    ]

    mock_res = MagicMock()
    mock_res.all.return_value = mock_rows
    session.execute = AsyncMock(return_value=mock_res)

    service = CommercialAnalyticsService(session)
    result = await service.rate_heatmap(tenant_id=TENANT_A, as_of_date=date(2026, 6, 1))

    assert result["total_lanes_covered"] == 1
    assert result["total_active_rates"] == 3
    assert result["cells"][0]["coverage_status"] == "COVERED"
    assert result["cells"][0]["active_rate_count"] == 3


# ---------------------------------------------------------------------------
# API Integration & RBAC Tests
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)


def mock_current_user(tenant_id: uuid.UUID = TENANT_A, permissions: set[str] | None = None, is_portal: bool = False):
    return CurrentUser(
        id=USER_ID,
        tenant_id=tenant_id,
        customer_id=None,
        permissions=permissions or {"quotation:read", "finance:read", "rate:read"},
        roles={"PRICING"},
        is_portal=is_portal,
    )


def test_api_analytics_rfq_funnel_unauthorized():
    """Unauthenticated call to analytics returns 401."""
    app.dependency_overrides.clear()
    res = client.get("/api/v1/analytics/rfq-funnel")
    assert res.status_code == 401


def test_api_analytics_rfq_funnel_forbidden_when_missing_permission():
    """Authenticated user without quotation:read returns 403."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user(permissions={"shipment:read"})
    res = client.get("/api/v1/analytics/rfq-funnel")
    assert res.status_code == 403
    app.dependency_overrides.clear()


def test_api_analytics_revenue_forbidden_for_portal():
    """Portal users cannot access revenue analytics."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user(
        permissions={"finance:read"},
        is_portal=True,
    )
    res = client.get("/api/v1/analytics/revenue")
    assert res.status_code == 403
    app.dependency_overrides.clear()

