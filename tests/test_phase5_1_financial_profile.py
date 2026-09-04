"""Unit and integration test suite for Phase 5.1: Shipment Financial Profile.

Verifies:
- Revenue Ledger (retrieval, addition, validation, status lifecycle)
- Direct Cost Ledger (retrieval, addition, vendor/carrier validation, status lifecycle)
- Profitability Calculations (positive margin, zero revenue, zero cost, quoted vs actual breakdown)
- Negative Margin Exception Management (CRITICAL exception, idempotency, resolution on recovery)
- Financial Entry Immutability & Reversals (3-entry chain, audit logging, validation)
- Strict Multi-Tenant Isolation
- FastAPI REST Endpoints & RBAC
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentUser, get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models.commercial import Customer, QuotationLine, Vendor
from app.db.models.reference import Carrier
from app.db.models.domain import CostLine, RevenueLine, Shipment, ShipmentException
from app.db.models.financial import FinancialEntry
from app.db.session import get_db
from app.main import app
from app.modules.financial.service import ShipmentFinancialService


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

def make_test_shipment(tenant_id: uuid.UUID, shipment_id: uuid.UUID | None = None) -> Shipment:
    s = Shipment(
        tenant_id=tenant_id,
        booking_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        mode="AIR",
        status="IN_PROGRESS",
    )
    s.id = shipment_id or uuid.uuid4()
    return s


# ---------------------------------------------------------------------------
# 1. Revenue Ledger Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_revenue_line_success():
    """Verify adding a valid revenue line persists with all fields."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Mocks:
    # 1. _get_tenant_shipment
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    # 2. get_profitability revenue lines
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    # 3. get_profitability cost lines
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = []
    # 4. _sync_negative_margin_exception lookup
    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_shp_res,
        mock_shp_res,
        mock_rev_res,
        mock_cost_res,
        mock_exc_res,
    ]

    service = ShipmentFinancialService(mock_session)
    result = await service.add_revenue_line(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        charge_code="FRT",
        amount=1500.0,
        currency_code="USD",
        is_additional=False,
        description="Air Freight Base Rate",
        quantity=2.0,
        unit_rate=750.0,
        status="ESTIMATED",
    )

    assert result["charge_code"] == "FRT"
    assert result["amount"] == 1500.0
    assert result["currency_code"] == "USD"
    assert result["quantity"] == 2.0
    assert result["unit_rate"] == 750.0
    assert result["is_additional"] is False
    assert result["status"] == "ESTIMATED"
    assert mock_session.add.called
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_revenue_line_validation_failures():
    """Verify validation errors for negative amount, empty charge code, and invalid status."""
    service = ShipmentFinancialService(None)
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    # Negative amount
    with pytest.raises(ValidationError, match="cannot be negative"):
        await service.add_revenue_line(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=None,
            charge_code="FRT",
            amount=-100.0,
        )

    # Empty charge code
    with pytest.raises(ValidationError, match="Charge code is required"):
        await service.add_revenue_line(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=None,
            charge_code="   ",
            amount=100.0,
        )

    # Invalid status
    with pytest.raises(ValidationError, match="Invalid status"):
        await service.add_revenue_line(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=None,
            charge_code="FRT",
            amount=100.0,
            status="UNKNOWN_STATUS",
        )


@pytest.mark.asyncio
async def test_get_revenue_ledger_ordering():
    """Verify revenue ledger lines are returned in chronological order."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    line1 = RevenueLine(
        shipment_id=shipment_id,
        charge_code="FRT",
        amount=1000.0,
        currency_code="USD",
        status="ESTIMATED",
        created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )
    line1.id = uuid.uuid4()
    line2 = RevenueLine(
        shipment_id=shipment_id,
        charge_code="FSC",
        amount=200.0,
        currency_code="USD",
        status="QUOTED",
        created_at=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
    )
    line2.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    mock_lines_res = MagicMock()
    mock_lines_res.scalars.return_value.all.return_value = [line1, line2]

    mock_session.execute.side_effect = [mock_shp_res, mock_lines_res]

    service = ShipmentFinancialService(mock_session)
    ledger = await service.get_revenue_ledger(shipment_id=shipment_id, tenant_id=tenant_id)

    assert len(ledger) == 2
    assert ledger[0]["charge_code"] == "FRT"
    assert ledger[0]["amount"] == 1000.0
    assert ledger[1]["charge_code"] == "FSC"
    assert ledger[1]["amount"] == 200.0


# ---------------------------------------------------------------------------
# 2. Cost Ledger Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_cost_line_success():
    """Verify adding a direct cost line with vendor and carrier references."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    vendor_id = uuid.uuid4()
    carrier_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment

    mock_vendor_res = MagicMock()
    mock_vendor_res.scalar_one_or_none.return_value = Vendor(
        tenant_id=tenant_id, vendor_code="VEND1", name="Vendor 1", vendor_type="AIRLINE"
    )

    mock_carrier_res = MagicMock()
    mock_carrier_res.scalar_one_or_none.return_value = Carrier(
        carrier_type="AIRLINE", name="Emirates SkyCargo", iata_code="EK"
    )

    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = []
    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_shp_res,
        mock_vendor_res,
        mock_carrier_res,
        mock_shp_res,
        mock_rev_res,
        mock_cost_res,
        mock_exc_res,
    ]

    service = ShipmentFinancialService(mock_session)
    result = await service.add_cost_line(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        charge_code="AIR_FREIGHT",
        amount=800.0,
        currency_code="USD",
        vendor_id=vendor_id,
        carrier_id=carrier_id,
        is_additional=False,
        status="ACCRUED",
    )

    assert result["charge_code"] == "AIR_FREIGHT"
    assert result["amount"] == 800.0
    assert result["status"] == "ACCRUED"
    assert result["vendor_id"] == str(vendor_id)
    assert result["carrier_id"] == str(carrier_id)
    assert mock_session.add.called


@pytest.mark.asyncio
async def test_cost_line_validation_failures():
    """Verify validation errors for negative amount, empty charge code, and invalid vendor."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    # Vendor lookup returns None (not found)
    mock_vendor_res = MagicMock()
    mock_vendor_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_shp_res, mock_vendor_res]

    service = ShipmentFinancialService(mock_session)

    # Negative amount
    with pytest.raises(ValidationError, match="cannot be negative"):
        await service.add_cost_line(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=None,
            charge_code="AIR_COST",
            amount=-50.0,
        )

    # Vendor not found
    with pytest.raises(NotFoundError, match="Vendor .* not found"):
        await service.add_cost_line(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=None,
            charge_code="AIR_COST",
            amount=50.0,
            vendor_id=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# 3. Profitability Calculations & Breakdown Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profitability_positive_margin():
    """Verify profitability calculation with positive gross profit and margin %."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    r1 = RevenueLine(shipment_id=shipment_id, amount=2000.0, currency_code="USD", status="INVOICED", is_additional=False)
    r2 = RevenueLine(shipment_id=shipment_id, amount=500.0, currency_code="USD", status="ESTIMATED", is_additional=True)
    c1 = CostLine(shipment_id=shipment_id, amount=1500.0, currency_code="USD", status="BILLED", is_additional=False)

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = [r1, r2]
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = [c1]

    mock_session.execute.side_effect = [mock_shp_res, mock_rev_res, mock_cost_res]

    service = ShipmentFinancialService(mock_session)
    prof = await service.get_profitability(shipment_id=shipment_id, tenant_id=tenant_id)

    assert prof["gross_revenue"] == 2500.0
    assert prof["direct_cost"] == 1500.0
    assert prof["gross_profit"] == 1000.0
    assert prof["gross_margin_percent"] == 40.0
    assert prof["actual_revenue"] == 2000.0
    assert prof["actual_cost"] == 1500.0
    assert prof["quoted_revenue"] == 2000.0
    assert prof["quoted_cost"] == 1500.0


@pytest.mark.asyncio
async def test_profitability_zero_revenue_with_cost():
    """Verify margin calculation when revenue is 0 and costs exist (-100%)."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    c1 = CostLine(shipment_id=shipment_id, amount=500.0, currency_code="USD", status="ESTIMATED", is_additional=False)

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = [c1]

    mock_session.execute.side_effect = [mock_shp_res, mock_rev_res, mock_cost_res]

    service = ShipmentFinancialService(mock_session)
    prof = await service.get_profitability(shipment_id=shipment_id, tenant_id=tenant_id)

    assert prof["gross_revenue"] == 0.0
    assert prof["direct_cost"] == 500.0
    assert prof["gross_profit"] == -500.0
    assert prof["gross_margin_percent"] == -100.0


@pytest.mark.asyncio
async def test_profitability_zero_revenue_and_zero_cost():
    """Verify margin calculation when both revenue and costs are zero (0.0%)."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_shp_res, mock_rev_res, mock_cost_res]

    service = ShipmentFinancialService(mock_session)
    prof = await service.get_profitability(shipment_id=shipment_id, tenant_id=tenant_id)

    assert prof["gross_revenue"] == 0.0
    assert prof["direct_cost"] == 0.0
    assert prof["gross_profit"] == 0.0
    assert prof["gross_margin_percent"] == 0.0


# ---------------------------------------------------------------------------
# 4. Negative Margin Exception Synchronization Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_negative_margin_creates_critical_exception():
    """Verify that adding a cost line that creates a negative gross profit triggers a CRITICAL exception."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    # Revenue: $1,000; Existing Cost: $1,500 -> Loss: -$500
    r1 = RevenueLine(shipment_id=shipment_id, amount=1000.0, currency_code="USD", status="ESTIMATED")
    c1 = CostLine(shipment_id=shipment_id, amount=1500.0, currency_code="USD", status="ESTIMATED")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = [r1]
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = [c1]
    # No existing open exception
    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_shp_res,
        mock_shp_res,
        mock_rev_res,
        mock_cost_res,
        mock_exc_res,
    ]

    service = ShipmentFinancialService(mock_session)
    service.outbox = AsyncMock()

    await service.add_cost_line(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        charge_code="SURCHARGE",
        amount=500.0,
    )

    # Verify a new ShipmentException was added to session
    added_exceptions = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], ShipmentException)
    ]
    assert len(added_exceptions) == 1
    exc = added_exceptions[0]
    assert exc.severity == "CRITICAL"
    assert exc.status == "OPEN"
    assert exc.financial_impact_estimated == 500.0
    assert service.outbox.enqueue.called


@pytest.mark.asyncio
async def test_negative_margin_exception_idempotency():
    """Verify that multiple updates with negative margin do NOT create duplicate exceptions."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    existing_exc = ShipmentException(
        tenant_id=tenant_id,
        shipment_id=shipment_id,
        exception_type="CARGO_LOSS",
        severity="CRITICAL",
        status="OPEN",
        financial_impact_estimated=200.0,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = existing_exc
    mock_session.execute.return_value = mock_exc_res

    service = ShipmentFinancialService(mock_session)

    profitability = {
        "shipment_id": str(shipment_id),
        "gross_revenue": 1000.0,
        "direct_cost": 1600.0,
        "gross_profit": -600.0,
        "gross_margin_percent": -60.0,
    }

    await service._sync_negative_margin_exception(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        profitability=profitability,
    )

    # Must update existing exception, not add a new one
    assert existing_exc.financial_impact_estimated == 600.0
    assert not mock_session.add.called


@pytest.mark.asyncio
async def test_negative_margin_recovery_resolves_exception():
    """Verify that when shipment returns to positive profitability, open exception is resolved."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    existing_exc = ShipmentException(
        tenant_id=tenant_id,
        shipment_id=shipment_id,
        exception_type="CARGO_LOSS",
        severity="CRITICAL",
        status="OPEN",
    )

    mock_session = AsyncMock()
    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = existing_exc
    mock_session.execute.return_value = mock_exc_res

    service = ShipmentFinancialService(mock_session)

    positive_profitability = {
        "shipment_id": str(shipment_id),
        "gross_revenue": 2000.0,
        "direct_cost": 1200.0,
        "gross_profit": 800.0,
        "gross_margin_percent": 40.0,
    }

    await service._sync_negative_margin_exception(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        profitability=positive_profitability,
    )

    assert existing_exc.status == "RESOLVED"
    assert existing_exc.resolved_at is not None
    assert "positive" in existing_exc.resolution_notes


# ---------------------------------------------------------------------------
# 5. Financial Immutability & Reversals Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_financial_entry_reversal_creates_three_entry_chain():
    """Verify standard 3-entry chain: Original (REVERSED) -> Reversal (REVERSAL) -> Corrected (POSTED)."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    entry_id = uuid.uuid4()

    orig_entry = FinancialEntry(
        tenant_id=tenant_id,
        shipment_id=shipment_id,
        entry_date=date(2026, 9, 1),
        entry_type="INVOICE_REVENUE",
        debit_amount=0.0,
        credit_amount=1500.0,
        currency_code="USD",
        status="POSTED",
        description="Original Invoice Revenue",
    )
    orig_entry.id = entry_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = orig_entry
    mock_session.execute.return_value = mock_exec_res

    service = ShipmentFinancialService(mock_session)
    service.audit = AsyncMock()

    res = await service.reverse_and_correct_entry(
        entry_id=entry_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        reason="Incorrect exchange rate applied on line 2",
        new_debit_amount=0.0,
        new_credit_amount=1450.0,
        new_description="Corrected Invoice Revenue",
    )

    assert res["status"] == "SUCCESS"
    assert res["original_entry_id"] == str(entry_id)
    assert orig_entry.status == "REVERSED"
    assert orig_entry.reversal_reason == "Incorrect exchange rate applied on line 2"

    # Verify reversal entry and corrected entry were added
    added = [call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], FinancialEntry)]
    assert len(added) == 2

    reversal_entry = added[0]
    assert reversal_entry.status == "REVERSAL"
    assert reversal_entry.debit_amount == 1500.0  # Flipped credit -> debit
    assert reversal_entry.credit_amount == 0.0
    assert reversal_entry.reversal_of_id == orig_entry.id

    corrected_entry = added[1]
    assert corrected_entry.status == "POSTED"
    assert corrected_entry.credit_amount == 1450.0
    assert corrected_entry.description == "Corrected Invoice Revenue"
    assert service.audit.record.called


@pytest.mark.asyncio
async def test_reversal_validation_failures():
    """Verify rejection of invalid reversal requests (short reason, wrong status, negative amount)."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    entry_id = uuid.uuid4()

    service = ShipmentFinancialService(None)

    # Empty or too short reason
    with pytest.raises(ValidationError, match="Reversal reason is required"):
        await service.reverse_and_correct_entry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            reason="ok",
            new_debit_amount=10.0,
            new_credit_amount=0.0,
        )

    # Negative amount
    with pytest.raises(ValidationError, match="cannot be negative"):
        await service.reverse_and_correct_entry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            reason="Valid explanation of error",
            new_debit_amount=-10.0,
            new_credit_amount=0.0,
        )

    # Non-POSTED original entry
    orig_entry = FinancialEntry(
        tenant_id=tenant_id,
        entry_date=date(2026, 9, 1),
        entry_type="COST_ACCRUAL",
        debit_amount=100.0,
        credit_amount=0.0,
        status="DRAFT",
    )
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = orig_entry
    mock_session.execute.return_value = mock_res

    service_db = ShipmentFinancialService(mock_session)
    with pytest.raises(ValidationError, match="Cannot reverse financial entry in status 'DRAFT'"):
        await service_db.reverse_and_correct_entry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            reason="Fixing draft entry",
            new_debit_amount=50.0,
            new_credit_amount=0.0,
        )


# ---------------------------------------------------------------------------
# 6. Multi-Tenant Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_access_rejected():
    """Verify that querying or modifying a shipment owned by Tenant B is rejected for Tenant A."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    shipment_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # Not found for tenant A
    mock_session.execute.return_value = mock_res

    service = ShipmentFinancialService(mock_session)

    with pytest.raises(NotFoundError, match="not found or does not belong to tenant"):
        await service.get_revenue_ledger(shipment_id=shipment_id, tenant_id=tenant_a)

    with pytest.raises(NotFoundError, match="not found or does not belong to tenant"):
        await service.get_cost_ledger(shipment_id=shipment_id, tenant_id=tenant_a)

    with pytest.raises(NotFoundError, match="not found or does not belong to tenant"):
        await service.get_profitability(shipment_id=shipment_id, tenant_id=tenant_a)


# ---------------------------------------------------------------------------
# 7. FastAPI REST API Integration & RBAC Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_revenue_ledger_get_and_post():
    """Verify HTTP GET and POST /api/v1/shipments/{id}/revenue-ledger."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_CONTROLLER"},
        permissions={"financial:read", "financial:create"},
        is_portal=False,
    )

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = make_test_shipment(tenant_id, shipment_id)
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = []
    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_shp_res,
        mock_rev_res,  # for GET
        mock_shp_res,
        mock_shp_res,
        mock_rev_res,
        mock_cost_res,
        mock_exc_res,  # for POST
    ]

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET
            get_resp = await client.get(f"/api/v1/shipments/{shipment_id}/revenue-ledger")
            assert get_resp.status_code == 200
            assert get_resp.json()["success"] is True

            # 2. POST
            post_resp = await client.post(
                f"/api/v1/shipments/{shipment_id}/revenue-ledger",
                json={
                    "charge_code": "OCEAN_FREIGHT",
                    "amount": 2400.0,
                    "currency_code": "USD",
                    "quantity": 1.0,
                    "unit_rate": 2400.0,
                    "is_additional": False,
                },
            )
            assert post_resp.status_code == 201
            assert post_resp.json()["success"] is True
            assert post_resp.json()["data"]["charge_code"] == "OCEAN_FREIGHT"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_profitability_endpoint():
    """Verify HTTP GET /api/v1/shipments/{id}/profitability."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_CONTROLLER"},
        permissions={"financial:read"},
        is_portal=False,
    )

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = make_test_shipment(tenant_id, shipment_id)
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_shp_res, mock_rev_res, mock_cost_res]

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/shipments/{shipment_id}/profitability")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert "gross_revenue" in data
            assert "direct_cost" in data
            assert "gross_profit" in data
            assert "gross_margin_percent" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_reversal_endpoint():
    """Verify HTTP POST /api/v1/financial/entries/{id}/reverse with financial:approve permission."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    entry_id = uuid.uuid4()

    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_CONTROLLER"},
        permissions={"financial:approve"},
        is_portal=False,
    )

    orig_entry = FinancialEntry(
        tenant_id=tenant_id,
        entry_date=date(2026, 9, 1),
        entry_type="INVOICE_REVENUE",
        debit_amount=0.0,
        credit_amount=1000.0,
        currency_code="USD",
        status="POSTED",
    )
    orig_entry.id = entry_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = orig_entry
    mock_session.execute.return_value = mock_res

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/financial/entries/{entry_id}/reverse",
                json={
                    "reason": "Billing correction needed per customer contract amend",
                    "new_debit_amount": 0.0,
                    "new_credit_amount": 950.0,
                },
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "SUCCESS"
            assert data["original_entry_id"] == str(entry_id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_rbac_insufficient_permission():
    """Verify 403 Forbidden when user lacks financial permissions."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    # User only has user:read
    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"CUSTOMER_SERVICE"},
        permissions={"user:read"},
        is_portal=False,
    )

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/shipments/{shipment_id}/revenue-ledger")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_cost_ledger_get_and_post():
    """Verify HTTP GET and POST /api/v1/shipments/{id}/cost-ledger."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_CONTROLLER"},
        permissions={"financial:read", "financial:create"},
        is_portal=False,
    )

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = make_test_shipment(tenant_id, shipment_id)
    mock_rev_res = MagicMock()
    mock_rev_res.scalars.return_value.all.return_value = []
    mock_cost_res = MagicMock()
    mock_cost_res.scalars.return_value.all.return_value = []
    mock_exc_res = MagicMock()
    mock_exc_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_shp_res,
        mock_cost_res,  # for GET
        mock_shp_res,
        mock_shp_res,
        mock_rev_res,
        mock_cost_res,
        mock_exc_res,  # for POST
    ]

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET
            get_resp = await client.get(f"/api/v1/shipments/{shipment_id}/cost-ledger")
            assert get_resp.status_code == 200
            assert get_resp.json()["success"] is True

            # 2. POST
            post_resp = await client.post(
                f"/api/v1/shipments/{shipment_id}/cost-ledger",
                json={
                    "charge_code": "AIR_LINE_HAUL",
                    "amount": 1200.0,
                    "currency_code": "USD",
                    "quantity": 1.0,
                    "unit_rate": 1200.0,
                    "is_additional": False,
                },
            )
            assert post_resp.status_code == 201
            assert post_resp.json()["success"] is True
            assert post_resp.json()["data"]["charge_code"] == "AIR_LINE_HAUL"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reversal_cross_tenant_rejected():
    """Verify that attempting to reverse an entry of another tenant raises NotFoundError."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    entry_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # Not found under tenant_a
    mock_session.execute.return_value = mock_res

    service = ShipmentFinancialService(mock_session)
    with pytest.raises(NotFoundError, match="Financial entry .* not found"):
        await service.reverse_and_correct_entry(
            entry_id=entry_id,
            tenant_id=tenant_a,
            actor_id=actor_id,
            reason="Unauthorized attempt to reverse cross-tenant entry",
            new_debit_amount=100.0,
            new_credit_amount=0.0,
        )


@pytest.mark.asyncio
async def test_get_cost_ledger_ordering():
    """Verify cost ledger lines are returned in chronological order with proper serialization."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    shipment = make_test_shipment(tenant_id, shipment_id)

    line1 = CostLine(
        shipment_id=shipment_id,
        charge_code="BUNKER",
        amount=300.0,
        currency_code="USD",
        status="ESTIMATED",
        created_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
    )
    line1.id = uuid.uuid4()
    line2 = CostLine(
        shipment_id=shipment_id,
        charge_code="TERMINAL",
        amount=150.0,
        currency_code="USD",
        status="BILLED",
        created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )
    line2.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_shp_res = MagicMock()
    mock_shp_res.scalar_one_or_none.return_value = shipment
    mock_lines_res = MagicMock()
    mock_lines_res.scalars.return_value.all.return_value = [line1, line2]

    mock_session.execute.side_effect = [mock_shp_res, mock_lines_res]

    service = ShipmentFinancialService(mock_session)
    ledger = await service.get_cost_ledger(shipment_id=shipment_id, tenant_id=tenant_id)

    assert len(ledger) == 2
    assert ledger[0]["charge_code"] == "BUNKER"
    assert ledger[0]["amount"] == 300.0
    assert ledger[1]["charge_code"] == "TERMINAL"
    assert ledger[1]["amount"] == 150.0

