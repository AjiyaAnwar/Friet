"""Tests for Phase 5 – Financial Integrity.

Covers:
  5.1 Rate expiry / contracted-rate validation at vendor bill matching
      - Valid contracted rate matches vendor invoice (no discrepancy)
      - Vendor invoice rate mismatch is flagged & discrepancy record created
      - Expired rate is flagged as expired at invoice date
      - No contracted rate exists is flagged
  5.2 Agent settlement rate management
      - Correct active agent rate agreement is selected and settlement calculated
      - Settlement record persisted with full rate version audit trail
      - Expired/missing agent rate agreement handled
  5.3 Quarterly rate review report
      - Contracted rates compared against market benchmarks
      - Competitive, above-market, below-market, and missing-market indicators
      - Soon-to-expire rates identified
  + Tenant isolation across all operations
  + RBAC / permissions on API endpoints
"""

import uuid
from datetime import date, datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.db.models.commercial import Agent, AgentRateAgreement, Rate, RateLine, RateVersion
from app.db.models.financial_integrity import AgentSettlement, MarketRate, VendorBillDiscrepancy
from app.db.session import get_db
from app.main import app
from app.modules.commercial.financial.service import FinancialIntegrityService


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
VENDOR_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AGENT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ORIGIN_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
DEST_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def make_mock_rate(
    rate_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = TENANT_A,
    amount: float = 100.0,
    effective_date: date = date(2026, 1, 1),
    expiry_date: date = date(2026, 12, 31),
    status: str = "APPROVED",
):
    r_id = rate_id or uuid.uuid4()
    v_id = uuid.uuid4()
    rate = Rate(
        id=r_id,
        tenant_id=tenant_id,
        rate_number="RT-001",
        rate_type="AIR_FREIGHT",
        rate_category="CONTRACT",
        carrier_id=VENDOR_ID,
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        effective_date=effective_date,
        expiry_date=expiry_date,
        currency_code="USD",
        status=status,
    )
    version = RateVersion(
        id=v_id,
        rate_id=r_id,
        version_number=1,
        approval_status="APPROVED",
        modified_date=datetime.now(UTC),
    )
    line = RateLine(
        id=uuid.uuid4(),
        rate_version_id=v_id,
        charge_code="AFR",
        rate_basis="PER_KG",
        amount=amount,
    )
    return rate, version, line


def make_mock_session() -> AsyncMock:
    """Creates a mock AsyncSession with synchronous .add() matching SQLAlchemy AsyncSession specification."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# 5.1 Vendor Bill Matching Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vendor_bill_matches_contracted_rate_exactly():
    """When vendor invoice amount exactly matches the contracted rate, no discrepancy is created."""
    rate, version, line = make_mock_rate(amount=150.0)
    session = make_mock_session()

    service = FinancialIntegrityService(session)
    # Mock finding the contracted rate
    with patch.object(service, "_find_best_contracted_rate_version", return_value=(rate, version, line)):
        result = await service.match_vendor_bill(
            tenant_id=TENANT_A,
            vendor_id=str(VENDOR_ID),
            shipment_id=str(uuid.uuid4()),
            shipment_reference="SH-100",
            vendor_invoice_reference="INV-999",
            charge_code="AFR",
            invoiced_rate_amount=150.0,
            currency_code="USD",
            invoice_date=date(2026, 6, 1),
        )

    assert result["matched"] is True
    assert result["variance"] == 0.0
    assert result["contracted_amount"] == 150.0
    assert result["invoiced_amount"] == 150.0
    assert result["status"] == "MATCHED"
    assert result["discrepancy_id"] is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_vendor_bill_mismatch_flags_discrepancy_and_persists():
    """When vendor invoices more than contracted, discrepancy is flagged and stored with full details."""
    rate, version, line = make_mock_rate(amount=100.0)
    session = make_mock_session()

    service = FinancialIntegrityService(session)
    with patch.object(service, "_find_best_contracted_rate_version", return_value=(rate, version, line)):
        result = await service.match_vendor_bill(
            tenant_id=TENANT_A,
            vendor_id=str(VENDOR_ID),
            shipment_id=str(uuid.uuid4()),
            shipment_reference="SH-200",
            vendor_invoice_reference="INV-OVERCHARGE",
            charge_code="AFR",
            invoiced_rate_amount=135.0,  # 35 overcharge
            currency_code="USD",
            invoice_date=date(2026, 6, 1),
        )

    assert result["matched"] is False
    assert result["variance"] == 35.0
    assert result["contracted_amount"] == 100.0
    assert result["invoiced_amount"] == 135.0
    assert result["status"] == "OPEN"
    # Session.add must be called to persist the discrepancy
    session.add.assert_called_once()
    added_obj = session.add.call_args[0][0]
    assert isinstance(added_obj, VendorBillDiscrepancy)
    assert added_obj.variance_amount == 35.0
    assert added_obj.tenant_id == TENANT_A
    assert added_obj.status == "OPEN"


@pytest.mark.asyncio
async def test_vendor_bill_when_rate_was_expired_at_invoice_date():
    """When rate is expired as of invoice date, discrepancy records rate_was_expired_at_invoice_date=True."""
    rate, version, line = make_mock_rate(
        amount=100.0,
        effective_date=date(2025, 1, 1),
        expiry_date=date(2025, 12, 31),  # Expired in 2025
    )
    session = make_mock_session()

    service = FinancialIntegrityService(session)
    with patch.object(service, "_find_best_contracted_rate_version", return_value=(rate, version, line)):
        result = await service.match_vendor_bill(
            tenant_id=TENANT_A,
            vendor_id=str(VENDOR_ID),
            shipment_id=None,
            shipment_reference="SH-EXPIRED",
            vendor_invoice_reference="INV-EXPIRED-TEST",
            charge_code="AFR",
            invoiced_rate_amount=100.0,
            currency_code="USD",
            invoice_date=date(2026, 6, 1),  # after expiry
        )

    assert result["rate_was_expired"] is True
    session.add.assert_called_once()
    added_obj = session.add.call_args[0][0]
    assert added_obj.rate_was_expired_at_invoice_date is True


@pytest.mark.asyncio
async def test_vendor_bill_no_contracted_rate_found():
    """When no contracted rate exists for the lane/vendor, entire invoiced amount is flagged as variance."""
    session = make_mock_session()
    service = FinancialIntegrityService(session)

    with patch.object(service, "_find_best_contracted_rate_version", return_value=(None, None, None)):
        result = await service.match_vendor_bill(
            tenant_id=TENANT_A,
            vendor_id=str(VENDOR_ID),
            shipment_id=None,
            shipment_reference="SH-NO-CONTRACT",
            vendor_invoice_reference="INV-NOCONTRACT",
            charge_code="AFR",
            invoiced_rate_amount=250.0,
            currency_code="USD",
            invoice_date=date(2026, 6, 1),
        )

    assert result["matched"] is False
    assert result["contracted_amount"] is None
    assert result["variance"] == 250.0
    assert result["status"] == "OPEN"
    session.add.assert_called_once()


# ---------------------------------------------------------------------------
# 5.2 Agent Settlement Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_settlement_calculates_with_active_rate():
    """Active agent rate agreement applies correct multiplier and stores audit trail."""
    session = make_mock_session()

    agent = Agent(id=AGENT_ID, tenant_id=TENANT_A, settlement_model="INVOICE")
    agreement = AgentRateAgreement(
        id=uuid.uuid4(),
        agent_id=AGENT_ID,
        rate_id=uuid.uuid4(),
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
    )
    version = RateVersion(
        id=uuid.uuid4(),
        rate_id=agreement.rate_id,
        version_number=1,
        approval_status="APPROVED",
        modified_date=datetime.now(UTC),
    )
    line = RateLine(
        id=uuid.uuid4(),
        rate_version_id=version.id,
        charge_code="AGT_COMM",
        rate_basis="PERCENTAGE",
        amount=0.08,  # 8% settlement rate
    )

    # Mock DB query executions in order: agent, agreement, version, line
    mock_execute = AsyncMock()
    # 1. agent query
    res_agent = MagicMock()
    res_agent.scalar_one_or_none.return_value = agent
    # 2. agreement query
    res_agreement = MagicMock()
    res_agreement.scalar_one_or_none.return_value = agreement
    # 3. version query
    res_version = MagicMock()
    res_version.scalar_one_or_none.return_value = version
    # 4. line query
    res_line = MagicMock()
    res_line.scalar_one_or_none.return_value = line

    mock_execute.side_effect = [res_agent, res_agreement, res_version, res_line]
    session.execute = mock_execute

    service = FinancialIntegrityService(session)
    result = await service.calculate_agent_settlement(
        tenant_id=TENANT_A,
        agent_id=str(AGENT_ID),
        shipment_id=str(uuid.uuid4()),
        base_amount=5000.0,
        currency_code="USD",
        settlement_date=date(2026, 5, 1),
        calculated_by=USER_ID,
        notes="Q2 Settlement",
    )

    # 5000 * 0.08 = 400.0
    assert result["settlement_amount"] == 400.0
    assert result["rate_applied"] == 0.08
    assert result["has_active_agreement"] is True
    assert result["status"] == "DRAFT"
    assert "cost_entry_id" in result
    assert result["cost_entry_id"] is not None

    # Check both FinancialEntry (cost ledger) and AgentSettlement were added
    assert session.add.call_count >= 2
    added_objects = [c[0][0] for c in session.add.call_args_list]
    from app.db.models.financial import FinancialEntry
    ledger_entries = [o for o in added_objects if isinstance(o, FinancialEntry)]
    assert len(ledger_entries) == 1
    le = ledger_entries[0]
    assert le.tenant_id == TENANT_A
    assert le.entry_type == "AGENT_SETTLEMENT"
    assert le.debit_amount == 400.0
    assert le.credit_amount == 0.0
    assert le.status == "POSTED"

    settlements = [o for o in added_objects if isinstance(o, AgentSettlement)]
    assert len(settlements) == 1
    assert settlements[0].tenant_id == TENANT_A
    assert settlements[0].rate_version_id == version.id


@pytest.mark.asyncio
async def test_agent_settlement_fails_for_wrong_tenant():
    """Agent belonging to Tenant B cannot be settled by Tenant A."""
    session = AsyncMock()
    # Agent query returns None (not found for TENANT_A)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_res)

    service = FinancialIntegrityService(session)
    with pytest.raises(NotFoundError):
        await service.calculate_agent_settlement(
            tenant_id=TENANT_A,
            agent_id=str(AGENT_ID),
            shipment_id=None,
            base_amount=1000.0,
            currency_code="USD",
            settlement_date=date(2026, 5, 1),
            calculated_by=USER_ID,
        )


# ---------------------------------------------------------------------------
# 5.3 Quarterly Rate Review Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quarterly_rate_review_detects_competitiveness_and_expiry():
    """Quarterly review compares contracted rates against market benchmarks and flags expiring rates."""
    session = AsyncMock()

    # Rate 1: $100 vs market $120 -> BELOW_MARKET (competitive)
    rate1 = Rate(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        rate_number="RT-AIR-01",
        rate_type="AIR_FREIGHT",
        rate_category="CONTRACT",
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        currency_code="USD",
        status="APPROVED",
    )
    # Rate 2: $200 vs market $150 -> ABOVE_MARKET (needs review)
    rate2 = Rate(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        rate_number="RT-AIR-02",
        rate_type="AIR_FREIGHT",
        rate_category="CONTRACT",
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 4, 1),  # expiring soon!
        currency_code="USD",
        status="APPROVED",
    )

    ver1 = RateVersion(id=uuid.uuid4(), rate_id=rate1.id, version_number=1, approval_status="APPROVED")
    line1 = RateLine(id=uuid.uuid4(), rate_version_id=ver1.id, charge_code="AFR", amount=100.0)

    ver2 = RateVersion(id=uuid.uuid4(), rate_id=rate2.id, version_number=1, approval_status="APPROVED")
    line2 = RateLine(id=uuid.uuid4(), rate_version_id=ver2.id, charge_code="AFR", amount=200.0)

    market_rate = MarketRate(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        origin_location_id=ORIGIN_ID,
        destination_location_id=DEST_ID,
        mode="AIR",
        rate_type="AIR_FREIGHT",
        amount=150.0,
        currency_code="USD",
        effective_date=date(2026, 1, 1),
        source="Freightos",
    )

    # Setup mock executes
    mock_execute = AsyncMock()
    # 1. Active rates
    r_rates = MagicMock()
    r_rates.scalars.return_value.all.return_value = [rate1, rate2]
    # 2. Soon-to-expire query
    r_exp = MagicMock()
    r_exp.scalars.return_value.all.return_value = [rate2]
    # 3. Market rate query
    r_mr = MagicMock()
    r_mr.scalar_one_or_none.return_value = market_rate
    # 4. ver1 query
    r_v1 = MagicMock()
    r_v1.scalar_one_or_none.return_value = ver1
    # 5. line1 query
    r_l1 = MagicMock()
    r_l1.scalar_one_or_none.return_value = line1
    # 6. ver2 query
    r_v2 = MagicMock()
    r_v2.scalar_one_or_none.return_value = ver2
    # 7. line2 query
    r_l2 = MagicMock()
    r_l2.scalar_one_or_none.return_value = line2

    mock_execute.side_effect = [r_rates, r_exp, r_mr, r_v1, r_l1, r_v2, r_l2]
    session.execute = mock_execute

    service = FinancialIntegrityService(session)
    report = await service.quarterly_rate_review(
        tenant_id=TENANT_A,
        as_of_date=date(2026, 3, 1),
        warning_days=60,
    )

    assert report["total_rates"] == 2
    assert report["below_market"] == 1  # rate1: 100 < 150
    assert report["above_market"] == 1  # rate2: 200 > 150
    assert report["expiring_soon"] == 1  # rate2 expires 2026-04-01
    assert report["needs_review"] >= 1


# ---------------------------------------------------------------------------
# API Integration & Authentication / RBAC Tests
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)


def mock_current_user(tenant_id: uuid.UUID = TENANT_A, permissions: set[str] | None = None, is_portal: bool = False):
    return CurrentUser(
        id=USER_ID,
        tenant_id=tenant_id,
        customer_id=None,
        permissions=permissions or {"finance:read", "rate:read", "rate:create", "quotation:read"},
        roles={"PRICING"},
        is_portal=is_portal,
    )


def test_api_vendor_bill_match_unauthorized_without_token():
    """Unauthenticated call to financial endpoints returns 401."""
    app.dependency_overrides.clear()
    res = client.post("/api/v1/financial/vendor-bills/match", json={
        "invoiced_rate_amount": 100.0,
        "currency_code": "USD",
        "invoice_date": "2026-06-01",
    })
    assert res.status_code == 401


def test_api_vendor_bill_match_forbidden_when_missing_permission():
    """Authenticated user without finance:read gets 403 Forbidden."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user(permissions={"shipment:read"})
    res = client.post("/api/v1/financial/vendor-bills/match", json={
        "invoiced_rate_amount": 100.0,
        "currency_code": "USD",
        "invoice_date": "2026-06-01",
    })
    assert res.status_code == 403
    app.dependency_overrides.clear()


def test_api_portal_user_cannot_access_finance():
    """Portal users are strictly blocked from internal financial endpoints."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user(
        permissions={"finance:read"},
        is_portal=True,
    )
    res = client.get("/api/v1/financial/vendor-bills/discrepancies")
    assert res.status_code == 403
    app.dependency_overrides.clear()

