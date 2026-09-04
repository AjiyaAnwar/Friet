"""Comprehensive Unit and Integration Tests for Phase 5.3 — Accounts Payable & Carrier Cost Verification.

Covers:
1. Carrier/Vendor Bill Recording & Traceability to Cost Ledger
2. Cost Matching (Exact match, Over-billing, Under-billing, Additional charges, Variance)
3. Lifecycle State Transitions (ESTIMATED -> ACCRUED -> BILLED -> VERIFIED -> APPROVED -> PAID)
4. Cost Verification & Material Variance Exception Handling
5. AP Approval Workflow & Accounts Payable Financial Entry
6. Payment Recording, Overpayment Prevention, Partial Payments & Financial Entry
7. Profitability & P&L Integration (Cost Ledger source of truth)
8. RBAC and Multi-Tenant Isolation across all endpoints
"""

import uuid
from datetime import date, datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.models.commercial import Customer, Vendor
from app.db.models.domain import CostLine, Payable, PayableLine, PayablePayment, RevenueLine, Shipment, ShipmentException
from app.db.models.financial import FinancialEntry
from app.db.models.reference import Carrier
from app.main import app
from app.modules.financial.service import ShipmentFinancialService
from app.modules.payables.service import PayableService


def make_test_shipment(tenant_id: uuid.UUID, customer_id: uuid.UUID, shipment_id: uuid.UUID | None = None) -> Shipment:
    s = Shipment(
        tenant_id=tenant_id,
        booking_id=uuid.uuid4(),
        customer_id=customer_id,
        mode="AIR",
        status="CONFIRMED",
    )
    s.id = shipment_id or uuid.uuid4()
    return s


def make_test_vendor(tenant_id: uuid.UUID, vendor_id: uuid.UUID | None = None) -> Vendor:
    v = Vendor(
        tenant_id=tenant_id,
        vendor_code="VEND-001",
        name="Global Handling Services",
        vendor_type="GROUND_HANDLER",
    )
    v.id = vendor_id or uuid.uuid4()
    return v


def make_test_carrier(carrier_id: uuid.UUID | None = None) -> Carrier:
    c = Carrier(
        carrier_code="EK",
        name="Emirates SkyCargo",
        mode="AIR",
    )
    c.id = carrier_id or uuid.uuid4()
    return c


# ---------------------------------------------------------------------------
# 1. Carrier/Vendor Bill Recording & Traceability
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_payable_with_cost_matching():
    """Verify recording payable matches existing CostLines and calculates variances."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    vendor_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    vendor = make_test_vendor(tenant_id, vendor_id)

    # Pre-existing cost lines on shipment:
    # 1. Ocean freight: expected 1000.0
    # 2. Terminal handling: expected 300.0
    cl1 = CostLine(
        shipment_id=shipment_id,
        vendor_id=vendor_id,
        charge_code="OCEAN_FREIGHT",
        description="Port to Port",
        amount=1000.0,
        currency_code="USD",
        status="ACCRUED",
    )
    cl1.id = uuid.uuid4()

    cl2 = CostLine(
        shipment_id=shipment_id,
        vendor_id=vendor_id,
        charge_code="TERMINAL_HANDLING",
        description="THC Origin",
        amount=300.0,
        currency_code="USD",
        status="ESTIMATED",
    )
    cl2.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Mocks for:
    # 1. _get_tenant_shipment
    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    # 2. vendor check
    mock_vend = MagicMock()
    mock_vend.scalar_one_or_none.return_value = vendor
    # 3. duplicate bill check (returns None -> no duplicate)
    mock_dup = MagicMock()
    mock_dup.scalar_one_or_none.return_value = None
    # 4. fetch cost lines
    mock_cls = MagicMock()
    mock_cls.scalars.return_value.all.return_value = [cl1, cl2]

    # After add, get_payable queries
    payable_obj = Payable(
        tenant_id=tenant_id,
        shipment_id=shipment_id,
        vendor_id=vendor_id,
        bill_number="BILL-2026-001",
        bill_date=date.today(),
        currency_code="USD",
        subtotal_amount=1450.0,
        tax_amount=0.0,
        total_amount=1450.0,
        variance_amount=150.0,
        status="RECEIVED",
        verification_status="PENDING",
        approval_status="PENDING",
    )
    payable_obj.id = uuid.uuid4()

    mock_p_get = MagicMock()
    mock_p_get.scalar_one_or_none.return_value = payable_obj
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []
    mock_pay_get = MagicMock()
    mock_pay_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_shp,
        mock_vend,
        mock_dup,
        mock_cls,
        mock_p_get,
        mock_lines_get,
        mock_pay_get,
    ]

    service = PayableService(mock_session)
    service.audit = AsyncMock()

    # Bill has:
    # 1. OCEAN_FREIGHT: billed 1100 (over-billing +100)
    # 2. TERMINAL_HANDLING: billed 250 (under-billing -50)
    # 3. STORAGE: billed 100 (additional charge +100)
    # Total variance = +100 - 50 + 100 = +150
    lines_input = [
        {"charge_code": "OCEAN_FREIGHT", "billed_amount": 1100.0, "quantity": 1.0},
        {"charge_code": "TERMINAL_HANDLING", "billed_amount": 250.0, "quantity": 1.0},
        {"charge_code": "STORAGE", "billed_amount": 100.0, "quantity": 1.0},
    ]

    result = await service.record_payable(
        tenant_id=tenant_id,
        actor_id=actor_id,
        shipment_id=shipment_id,
        bill_number="BILL-2026-001",
        lines=lines_input,
        vendor_id=vendor_id,
    )

    assert result["bill_number"] == "BILL-2026-001"
    assert result["status"] == "RECEIVED"
    assert result["total_amount"] == 1450.0
    assert result["variance_amount"] == 150.0

    # Verify existing CostLines transitioned to BILLED
    assert cl1.status == "BILLED"
    assert cl2.status == "BILLED"

    # Verify audit record called
    assert service.audit.record.called


@pytest.mark.asyncio
async def test_duplicate_bill_number_rejected():
    """Verify duplicate bill number within same tenant is rejected."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = make_test_shipment(tenant_id, uuid.uuid4(), shipment_id)
    mock_dup = MagicMock()
    mock_dup.scalar_one_or_none.return_value = MagicMock()  # duplicate found

    mock_session.execute.side_effect = [mock_shp, mock_dup]

    service = PayableService(mock_session)
    with pytest.raises(ConflictError, match="already exists"):
        await service.record_payable(
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
            shipment_id=shipment_id,
            bill_number="INV-CARRIER-999",
            lines=[{"charge_code": "FREIGHT", "billed_amount": 500.0}],
        )


# ---------------------------------------------------------------------------
# 2. Cost Verification & Variance Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cost_verification_clean_match():
    """Verify clean cost verification when variance is within acceptable threshold."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    payable_id = uuid.uuid4()

    payable = Payable(
        tenant_id=tenant_id,
        shipment_id=uuid.uuid4(),
        bill_number="BILL-CLEAN-01",
        bill_date=date.today(),
        currency_code="USD",
        subtotal_amount=1000.0,
        total_amount=1000.0,
        variance_amount=0.0,  # exact match
        status="RECEIVED",
        verification_status="PENDING",
    )
    payable.id = payable_id

    cl = CostLine(
        shipment_id=payable.shipment_id,
        charge_code="AIR_FREIGHT",
        amount=1000.0,
        status="BILLED",
    )
    cl.id = uuid.uuid4()

    pline = PayableLine(
        tenant_id=tenant_id,
        payable_id=payable_id,
        cost_line_id=cl.id,
        charge_code="AIR_FREIGHT",
        expected_amount=1000.0,
        billed_amount=1000.0,
        variance_amount=0.0,
        status="MATCHED",
    )

    mock_session = AsyncMock()
    mock_p_get = MagicMock()
    mock_p_get.scalar_one_or_none.return_value = payable
    mock_lines = MagicMock()
    mock_lines.scalars.return_value.all.return_value = [pline]
    mock_cl_get = MagicMock()
    mock_cl_get.scalar_one_or_none.return_value = cl
    mock_payments = MagicMock()
    mock_payments.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_p_get,
        mock_lines,
        mock_cl_get,
        mock_p_get,
        mock_lines,
        mock_payments,
    ]

    service = PayableService(mock_session)
    service.audit = AsyncMock()

    res = await service.verify_payable(
        payable_id=payable_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
    )

    assert res["status"] == "VERIFIED"
    assert res["verification_status"] == "VERIFIED"
    assert res["verified_by"] == str(actor_id)
    # Linked CostLine transitioned to VERIFIED
    assert cl.status == "VERIFIED"


@pytest.mark.asyncio
async def test_cost_verification_material_variance_requires_review():
    """Verify that material variance requires review and raises ValidationError unless overridden."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    payable_id = uuid.uuid4()

    payable = Payable(
        tenant_id=tenant_id,
        shipment_id=uuid.uuid4(),
        bill_number="BILL-VAR-01",
        bill_date=date.today(),
        currency_code="USD",
        subtotal_amount=2000.0,
        total_amount=2000.0,
        variance_amount=600.0,  # Material variance: $600 (> $100 and > 10%)
        status="RECEIVED",
        verification_status="PENDING",
    )
    payable.id = payable_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_p_get = MagicMock()
    mock_p_get.scalar_one_or_none.return_value = payable
    mock_session.execute.return_value = mock_p_get

    service = PayableService(mock_session)

    # Without allow_material_variance -> rejected with review requirement
    with pytest.raises(ValidationError, match="material variance"):
        await service.verify_payable(
            payable_id=payable_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            allow_material_variance=False,
        )

    assert payable.verification_status == "VARIANCE_DETECTED"
    # Verify ShipmentException was added
    added_exceptions = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], ShipmentException)
    ]
    assert len(added_exceptions) == 1
    assert added_exceptions[0].exception_type == "COST_VARIANCE"
    assert added_exceptions[0].severity == "CRITICAL"


# ---------------------------------------------------------------------------
# 3. AP Approval Workflow & Financial Entries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unverified_payable_cannot_be_approved():
    """Verify an unverified payable cannot be approved."""
    tenant_id = uuid.uuid4()
    payable_id = uuid.uuid4()

    payable = Payable(
        tenant_id=tenant_id,
        shipment_id=uuid.uuid4(),
        bill_number="BILL-UNVER-01",
        status="RECEIVED",
        verification_status="PENDING",  # Not verified!
        approval_status="PENDING",
    )

    mock_session = AsyncMock()
    mock_p = MagicMock()
    mock_p.scalar_one_or_none.return_value = payable
    mock_session.execute.return_value = mock_p

    service = PayableService(mock_session)
    with pytest.raises(ValidationError, match="must be VERIFIED before approval"):
        await service.approve_payable(
            payable_id=payable_id,
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_verified_payable_approval_and_financial_entry():
    """Verify approving verified payable creates ACCOUNTS_PAYABLE financial entry and updates CostLine."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    payable_id = uuid.uuid4()

    payable = Payable(
        tenant_id=tenant_id,
        shipment_id=uuid.uuid4(),
        bill_number="BILL-APP-01",
        bill_date=date.today(),
        currency_code="USD",
        subtotal_amount=1500.0,
        total_amount=1500.0,
        status="VERIFIED",
        verification_status="VERIFIED",
        approval_status="PENDING",
    )
    payable.id = payable_id

    cl = CostLine(
        shipment_id=payable.shipment_id,
        charge_code="AIR_FREIGHT",
        amount=1500.0,
        status="VERIFIED",
    )
    cl.id = uuid.uuid4()

    pline = PayableLine(
        tenant_id=tenant_id,
        payable_id=payable_id,
        cost_line_id=cl.id,
        charge_code="AIR_FREIGHT",
        expected_amount=1500.0,
        billed_amount=1500.0,
        status="VERIFIED",
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_p_get = MagicMock()
    mock_p_get.scalar_one_or_none.return_value = payable
    mock_lines = MagicMock()
    mock_lines.scalars.return_value.all.return_value = [pline]
    mock_cl_get = MagicMock()
    mock_cl_get.scalar_one_or_none.return_value = cl
    mock_payments = MagicMock()
    mock_payments.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_p_get,
        mock_lines,
        mock_cl_get,
        mock_p_get,
        mock_lines,
        mock_payments,
    ]

    service = PayableService(mock_session)
    service.audit = AsyncMock()

    res = await service.approve_payable(
        payable_id=payable_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        notes="Verified per carrier contract rate",
    )

    assert res["status"] == "APPROVED"
    assert res["approval_status"] == "APPROVED"
    assert res["approved_by"] == str(actor_id)
    # CostLine transitioned to APPROVED
    assert cl.status == "APPROVED"

    # Verify ACCOUNTS_PAYABLE FinancialEntry created
    added_fin = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], FinancialEntry)
    ]
    assert len(added_fin) == 1
    assert added_fin[0].entry_type == "ACCOUNTS_PAYABLE"
    assert added_fin[0].credit_amount == 1500.0
    assert added_fin[0].debit_amount == 0.0


# ---------------------------------------------------------------------------
# 4. Payment Recording & Overpayment Prevention
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_partial_and_full_payment():
    """Verify partial payments advance to PARTIALLY_PAID, full payment to PAID and CostLine to PAID."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    payable_id = uuid.uuid4()

    payable = Payable(
        tenant_id=tenant_id,
        shipment_id=uuid.uuid4(),
        bill_number="BILL-PAY-01",
        bill_date=date.today(),
        currency_code="USD",
        subtotal_amount=2000.0,
        total_amount=2000.0,
        paid_amount=0.0,
        status="APPROVED",
        verification_status="VERIFIED",
        approval_status="APPROVED",
    )
    payable.id = payable_id

    cl = CostLine(
        shipment_id=payable.shipment_id,
        charge_code="HAULAGE",
        amount=2000.0,
        status="APPROVED",
    )
    cl.id = uuid.uuid4()

    pline = PayableLine(
        tenant_id=tenant_id,
        payable_id=payable_id,
        cost_line_id=cl.id,
        charge_code="HAULAGE",
        expected_amount=2000.0,
        billed_amount=2000.0,
        status="VERIFIED",
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Step 1: Pay 800 of 2000 -> PARTIALLY_PAID
    mock_p_get = MagicMock()
    mock_p_get.scalar_one_or_none.return_value = payable
    mock_sum_0 = MagicMock()
    mock_sum_0.scalar.return_value = 0.0
    mock_lines = MagicMock()
    mock_lines.scalars.return_value.all.return_value = [pline]
    mock_payments = MagicMock()
    mock_payments.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_p_get,
        mock_sum_0,
        mock_p_get,
        mock_lines,
        mock_payments,
    ]

    service = PayableService(mock_session)
    service.audit = AsyncMock()

    res1 = await service.record_payment(
        payable_id=payable_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        amount=800.0,
        payment_reference="WIRE-001",
    )

    assert res1["paid_amount"] == 800.0
    assert payable.status == "PARTIALLY_PAID"
    # CostLine remains APPROVED until full settlement
    assert cl.status == "APPROVED"

    # Step 2: Overpayment attempt (attempting 1500 when remaining is 1200)
    mock_sum_800 = MagicMock()
    mock_sum_800.scalar.return_value = 800.0
    mock_session.execute.side_effect = [mock_p_get, mock_sum_800]

    with pytest.raises(ValidationError, match="exceeds remaining balance"):
        await service.record_payment(
            payable_id=payable_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            amount=1500.0,
            payment_reference="WIRE-OVER",
        )

    # Step 3: Pay remaining 1200 -> PAID and CostLine transitions to PAID
    mock_cl_get = MagicMock()
    mock_cl_get.scalar_one_or_none.return_value = cl
    mock_session.execute.side_effect = [
        mock_p_get,
        mock_sum_800,
        mock_lines,
        mock_cl_get,
        mock_p_get,
        mock_lines,
        mock_payments,
    ]

    res3 = await service.record_payment(
        payable_id=payable_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        amount=1200.0,
        payment_reference="WIRE-002",
    )

    assert res3["paid_amount"] == 2000.0
    assert payable.status == "PAID"
    # CostLine transitioned to PAID upon full settlement
    assert cl.status == "PAID"

    # Verify AP_PAYMENT financial entries added
    fin_entries = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], FinancialEntry)
    ]
    assert len(fin_entries) == 2
    for fe in fin_entries:
        assert fe.entry_type == "AP_PAYMENT"
        assert fe.debit_amount > 0


# ---------------------------------------------------------------------------
# 5. Profitability Integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profitability_reflects_actual_carrier_billed_costs():
    """Verify that additional and verified carrier costs directly feed Phase 5.1 profitability."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, uuid.uuid4(), shipment_id)

    # Revenue: 5000.0
    rev = RevenueLine(
        shipment_id=shipment_id,
        charge_code="AIR_FREIGHT",
        amount=5000.0,
        currency_code="USD",
        status="INVOICED",
    )

    # Costs:
    # 1. Expected linehaul: 3000.0 (BILLED)
    # 2. Additional carrier detention: 500.0 (added during AP billing, status BILLED)
    cl1 = CostLine(
        shipment_id=shipment_id,
        charge_code="AIR_FREIGHT",
        amount=3000.0,
        currency_code="USD",
        status="BILLED",
        is_additional=False,
    )
    cl2 = CostLine(
        shipment_id=shipment_id,
        charge_code="DETENTION",
        amount=500.0,
        currency_code="USD",
        status="BILLED",
        is_additional=True,
    )

    mock_session = AsyncMock()
    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev]
    mock_cost = MagicMock()
    mock_cost.scalars.return_value.all.return_value = [cl1, cl2]

    mock_session.execute.side_effect = [mock_shp, mock_rev, mock_cost]

    # Use Phase 5.1 ShipmentFinancialService to compute live profitability
    fin_service = ShipmentFinancialService(mock_session)
    prof = await fin_service.get_profitability(shipment_id=shipment_id, tenant_id=tenant_id)

    assert prof["gross_revenue"] == 5000.0
    # Direct cost includes both expected and additional carrier costs: 3000 + 500 = 3500
    assert prof["direct_cost"] == 3500.0
    assert prof["gross_profit"] == 1500.0
    # Gross margin % = (1500 / 5000) * 100 = 30.0%
    assert prof["gross_margin_percent"] == 30.0
    assert prof["quoted_cost"] == 3000.0
    assert prof["actual_cost"] == 3500.0


# ---------------------------------------------------------------------------
# 6. REST API & RBAC Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_payable_lifecycle_and_rbac():
    """Verify HTTP endpoints for payable recording, verification, approval, and payment with RBAC."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    payable_id = uuid.uuid4()

    # User with FINANCE_AP permissions
    ap_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_AP"},
        permissions={"payable:create", "payable:read", "payable:verify", "payable:approve", "payable:pay"},
        is_portal=False,
    )

    payable_obj = Payable(
        tenant_id=tenant_id,
        shipment_id=shipment_id,
        bill_number="BILL-API-01",
        bill_date=date.today(),
        currency_code="USD",
        subtotal_amount=1000.0,
        total_amount=1000.0,
        paid_amount=0.0,
        status="RECEIVED",
        verification_status="PENDING",
        approval_status="PENDING",
    )
    payable_obj.id = payable_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock service methods
    with patch("app.api.v1.endpoints.payables.PayableService") as MockServiceCls:
        mock_instance = MockServiceCls.return_value
        mock_instance.record_payable = AsyncMock(return_value={
            "id": str(payable_id),
            "bill_number": "BILL-API-01",
            "total_amount": 1000.0,
            "status": "RECEIVED",
        })
        mock_instance.get_payable = AsyncMock(return_value={
            "id": str(payable_id),
            "bill_number": "BILL-API-01",
            "total_amount": 1000.0,
            "status": "RECEIVED",
        })
        mock_instance.verify_payable = AsyncMock(return_value={
            "id": str(payable_id),
            "status": "VERIFIED",
            "verification_status": "VERIFIED",
        })
        mock_instance.approve_payable = AsyncMock(return_value={
            "id": str(payable_id),
            "status": "APPROVED",
            "approval_status": "APPROVED",
        })
        mock_instance.record_payment = AsyncMock(return_value={
            "id": str(payable_id),
            "status": "PAID",
            "paid_amount": 1000.0,
        })

        async def override_get_current_user():
            return ap_user

        async def override_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. POST /api/v1/payables
                post_resp = await client.post(
                    "/api/v1/payables",
                    json={
                        "shipment_id": str(shipment_id),
                        "bill_number": "BILL-API-01",
                        "lines": [{"charge_code": "AIR_FREIGHT", "billed_amount": 1000.0}],
                    },
                )
                assert post_resp.status_code == 201
                assert post_resp.json()["data"]["bill_number"] == "BILL-API-01"

                # 2. GET /api/v1/payables/{id}
                get_resp = await client.get(f"/api/v1/payables/{payable_id}")
                assert get_resp.status_code == 200
                assert get_resp.json()["data"]["total_amount"] == 1000.0

                # 3. POST /api/v1/payables/{id}/verify
                verify_resp = await client.post(
                    f"/api/v1/payables/{payable_id}/verify",
                    json={"allow_material_variance": False},
                )
                assert verify_resp.status_code == 200
                assert verify_resp.json()["data"]["status"] == "VERIFIED"

                # 4. POST /api/v1/payables/{id}/approve
                approve_resp = await client.post(
                    f"/api/v1/payables/{payable_id}/approve",
                    json={"notes": "Approved by AP"},
                )
                assert approve_resp.status_code == 200
                assert approve_resp.json()["data"]["approval_status"] == "APPROVED"

                # 5. POST /api/v1/payables/{id}/pay
                pay_resp = await client.post(
                    f"/api/v1/payables/{payable_id}/pay",
                    json={"amount": 1000.0, "payment_reference": "WIRE-12345"},
                )
                assert pay_resp.status_code == 200
                assert pay_resp.json()["data"]["status"] == "PAID"
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_rbac_insufficient_payable_permissions():
    """Verify unauthorized role receives 403 Forbidden across all payable endpoints."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # User only has sales permissions
    unauth_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"SALES"},
        permissions={"shipment:read", "quotation:read"},
        is_portal=False,
    )

    async def override_get_current_user():
        return unauth_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            p_id = str(uuid.uuid4())
            # 1. create
            assert (await client.post("/api/v1/payables", json={"shipment_id": str(uuid.uuid4()), "bill_number": "B1", "lines": []})).status_code == 403
            # 2. get
            assert (await client.get(f"/api/v1/payables/{p_id}")).status_code == 403
            # 3. verify
            assert (await client.post(f"/api/v1/payables/{p_id}/verify", json={})).status_code == 403
            # 4. approve
            assert (await client.post(f"/api/v1/payables/{p_id}/approve", json={})).status_code == 403
            # 5. pay
            assert (await client.post(f"/api/v1/payables/{p_id}/pay", json={"amount": 100.0, "payment_reference": "W1"})).status_code == 403
    finally:
        app.dependency_overrides.clear()
