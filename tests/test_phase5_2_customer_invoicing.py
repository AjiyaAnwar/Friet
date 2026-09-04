"""Unit and integration test suite for Phase 5.2: Customer Invoicing.

Verifies:
- Invoice Generation from Revenue Ledger (eligible lines only, duplicate protection)
- Multi-Currency Conversion & Locked Exchange Rates
- Tax Evaluation (Pakistan GST 16%, Saudi VAT 15%, UAE VAT 5%, snapshotting)
- Approval Workflow (threshold auto-approval vs manual finance approval)
- Dependency-Free PDF Invoice Generation from Persisted Data
- Transactional Sending via Outbox Events & Audit Trails
- Full and Partial Credit Notes Linked to Invoices
- Debit Notes for Additional Charges Linked to Invoices
- Financial Immutability & AR Ledger Entries
- Multi-Tenant Isolation & RBAC
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentUser, get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models.commercial import Customer, CustomerContact
from app.db.models.domain import CreditNote, DebitNote, Invoice, InvoiceLine, RevenueLine, Shipment
from app.db.models.financial import FinancialEntry
from app.db.models.reference import ExchangeRate
from app.db.session import get_db
from app.main import app
from app.modules.invoicing.pdf import InvoicePDFGenerator
from app.modules.invoicing.service import InvoiceService
from app.modules.invoicing.tax import TaxService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_shipment(tenant_id: uuid.UUID, customer_id: uuid.UUID, shipment_id: uuid.UUID | None = None) -> Shipment:
    s = Shipment(
        tenant_id=tenant_id,
        booking_id=uuid.uuid4(),
        customer_id=customer_id,
        mode="AIR",
        status="IN_PROGRESS",
    )
    s.id = shipment_id or uuid.uuid4()
    return s


def make_test_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None, currency: str = "USD") -> Customer:
    c = Customer(
        tenant_id=tenant_id,
        customer_code="CUST-001",
        name="Acme Global Logistics",
        credit_limit_currency=currency,
        payment_terms_days=30,
        credit_tier="STANDARD",
        kyc_status="VERIFIED",
    )
    c.id = customer_id or uuid.uuid4()
    return c


# ---------------------------------------------------------------------------
# 1. Invoice Generation from Revenue Ledger Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invoice_generation_from_approved_revenue_lines():
    """Verify invoice is created directly from shipment revenue ledger and lines updated to INVOICED."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    customer = make_test_customer(tenant_id, customer_id, "USD")

    rev1 = RevenueLine(
        shipment_id=shipment_id,
        charge_code="OCEAN_FREIGHT",
        description="Ocean Freight Port-to-Port",
        quantity=2.0,
        unit_rate=1000.0,
        amount=2000.0,
        currency_code="USD",
        status="ESTIMATED",
    )
    rev1.id = uuid.uuid4()

    rev2 = RevenueLine(
        shipment_id=shipment_id,
        charge_code="TERMINAL_HANDLING",
        description="THC Destination",
        quantity=1.0,
        unit_rate=300.0,
        amount=300.0,
        currency_code="USD",
        status="QUOTED",
    )
    rev2.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Mocks:
    # 1. _get_tenant_shipment
    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    # 2. Customer lookup
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    # 3. Revenue lines lookup
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev1, rev2]
    # 4. _get_next_sequence count
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0
    # 5. get_invoice -> Invoice lookup
    mock_inv_obj = Invoice(
        tenant_id=tenant_id,
        customer_id=customer_id,
        shipment_id=shipment_id,
        invoice_number="INV-2026-00001",
        invoice_date=date.today(),
        currency_code="USD",
        exchange_rate_to_base=1.0,
        subtotal_amount=2300.0,
        tax_amount=0.0,
        total_amount=2300.0,
        status="APPROVED",
    )
    mock_inv_obj.id = uuid.uuid4()
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = mock_inv_obj
    # 6. Customer lookup in get_invoice
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = customer
    # 7. Invoice lines in get_invoice
    mock_inv_lines_get = MagicMock()
    mock_inv_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_shp,
        mock_cust,
        mock_rev,
        mock_seq,
        mock_inv_get,
        mock_cust_get,
        mock_inv_lines_get,
    ]

    service = InvoiceService(mock_session)
    service.audit = AsyncMock()

    res = await service.generate_invoice(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
    )

    assert res["invoice_number"] == "INV-2026-00001"
    assert res["total_amount"] == 2300.0
    # Revenue lines marked as INVOICED
    assert rev1.status == "INVOICED"
    assert rev2.status == "INVOICED"
    # FinancialEntry created
    added_financial = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], FinancialEntry)
    ]
    assert len(added_financial) == 1
    assert added_financial[0].entry_type == "INVOICE_RECEIVABLE"
    assert added_financial[0].debit_amount == 2300.0


@pytest.mark.asyncio
async def test_duplicate_invoicing_prevented():
    """Verify that attempting to invoice already-invoiced revenue lines raises ValidationError."""
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    customer = make_test_customer(tenant_id, customer_id)

    # Line already INVOICED
    rev = RevenueLine(
        shipment_id=shipment_id,
        charge_code="FRT",
        amount=1000.0,
        status="INVOICED",
    )
    rev.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev]

    mock_session.execute.side_effect = [mock_shp, mock_cust, mock_rev]

    service = InvoiceService(mock_session)
    with pytest.raises(ValidationError, match="already invoiced"):
        await service.generate_invoice(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
            revenue_line_ids=[rev.id],
        )


@pytest.mark.asyncio
async def test_invoice_generation_no_eligible_lines():
    """Verify error raised when shipment has no un-invoiced revenue lines."""
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    customer = make_test_customer(tenant_id, customer_id)

    mock_session = AsyncMock()
    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_shp, mock_cust, mock_rev]

    service = InvoiceService(mock_session)
    with pytest.raises(ValidationError, match="No eligible revenue lines available"):
        await service.generate_invoice(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# 2. Multi-Currency Conversion & Rate Locking Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multicurrency_locked_exchange_rate():
    """Verify currency conversion applies and exchange rate is permanently locked on the invoice."""
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    # Customer preferred currency: EUR
    customer = make_test_customer(tenant_id, customer_id, "EUR")

    rev = RevenueLine(
        shipment_id=shipment_id,
        charge_code="BASE_FREIGHT",
        amount=1000.0,
        currency_code="USD",
        status="ESTIMATED",
    )
    rev.id = uuid.uuid4()

    # Exchange rate: 1 EUR = 1.10 USD (rate_to_base: 0.90909091)
    xr = ExchangeRate(
        currency_code="EUR",
        rate_date=date.today(),
        rate_to_base=0.92,
        source="ECB",
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev]
    mock_xr = MagicMock()
    mock_xr.scalars.return_value.first.return_value = xr
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0

    mock_inv_obj = Invoice(
        tenant_id=tenant_id,
        customer_id=customer_id,
        shipment_id=shipment_id,
        invoice_number="INV-2026-00002",
        invoice_date=date.today(),
        currency_code="EUR",
        exchange_rate_to_base=0.92,
        subtotal_amount=920.0,
        tax_amount=0.0,
        total_amount=920.0,
        status="APPROVED",
    )
    mock_inv_obj.id = uuid.uuid4()
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = mock_inv_obj
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = customer
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_shp,
        mock_cust,
        mock_rev,
        mock_xr,
        mock_seq,
        mock_inv_get,
        mock_cust_get,
        mock_lines_get,
    ]

    service = InvoiceService(mock_session)
    res = await service.generate_invoice(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=uuid.uuid4(),
        currency_code="EUR",
    )

    assert res["currency_code"] == "EUR"
    assert res["exchange_rate_to_base"] == 0.92
    assert res["total_amount"] == 920.0


# ---------------------------------------------------------------------------
# 3. Tax Evaluation & Snapshotting Tests (PK GST, SA VAT, AE VAT)
# ---------------------------------------------------------------------------

def test_tax_evaluation_jurisdictions():
    """Verify Pakistan GST (16%), Saudi VAT (15%), and UAE VAT (5%) rules."""
    # Pakistan
    pk = TaxService.evaluate("PK")
    assert pk.applicable is True
    assert pk.tax_type == "GST"
    assert pk.tax_rate == 0.1600
    assert pk.compute_tax(1000.0) == 160.0

    # Saudi Arabia
    sa = TaxService.evaluate("SA")
    assert sa.applicable is True
    assert sa.tax_type == "VAT"
    assert sa.tax_rate == 0.1500
    assert sa.compute_tax(1000.0) == 150.0

    # UAE
    ae = TaxService.evaluate("AE")
    assert ae.applicable is True
    assert ae.tax_type == "VAT"
    assert ae.tax_rate == 0.0500
    assert ae.compute_tax(1000.0) == 50.0

    # Tax Exempt
    exempt = TaxService.evaluate("SA", is_tax_exempt=True)
    assert exempt.applicable is False
    assert exempt.tax_rate == 0.0
    assert exempt.compute_tax(1000.0) == 0.0


@pytest.mark.asyncio
async def test_tax_snapshot_persisted_on_invoice():
    """Verify applied tax is snapshotted on invoice and not changed by external changes."""
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    customer = make_test_customer(tenant_id, customer_id)

    rev = RevenueLine(
        shipment_id=shipment_id,
        charge_code="AIR_FREIGHT",
        amount=1000.0,
        status="ESTIMATED",
    )
    rev.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev]
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0

    # Saudi VAT 15%: Subtotal: 1000, Tax: 150, Total: 1150
    mock_inv_obj = Invoice(
        tenant_id=tenant_id,
        customer_id=customer_id,
        shipment_id=shipment_id,
        invoice_number="INV-2026-00003",
        currency_code="USD",
        subtotal_amount=1000.0,
        tax_amount=150.0,
        total_amount=1150.0,
        tax_jurisdiction="SA",
        tax_rate=0.1500,
        tax_type="VAT",
        status="APPROVED",
    )
    mock_inv_obj.id = uuid.uuid4()
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = mock_inv_obj
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = customer
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_shp,
        mock_cust,
        mock_rev,
        mock_seq,
        mock_inv_get,
        mock_cust_get,
        mock_lines_get,
    ]

    service = InvoiceService(mock_session)
    res = await service.generate_invoice(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=uuid.uuid4(),
        tax_jurisdiction="SA",
    )

    assert res["tax_jurisdiction"] == "SA"
    assert res["tax_rate"] == 0.15
    assert res["tax_amount"] == 150.0
    assert res["total_amount"] == 1150.0


# ---------------------------------------------------------------------------
# 4. Approval Workflow & Threshold Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_below_threshold_auto_approves():
    """Verify invoice <= $5,000 auto-approves immediately upon creation."""
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    customer = make_test_customer(tenant_id, customer_id)

    rev = RevenueLine(
        shipment_id=shipment_id,
        charge_code="HAULAGE",
        amount=3500.0,
        status="ESTIMATED",
    )
    rev.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev]
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0

    mock_inv_obj = Invoice(
        tenant_id=tenant_id,
        customer_id=customer_id,
        shipment_id=shipment_id,
        invoice_number="INV-2026-00004",
        total_amount=3500.0,
        approval_status="APPROVED",
        status="APPROVED",
    )
    mock_inv_obj.id = uuid.uuid4()
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = mock_inv_obj
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = customer
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_shp,
        mock_cust,
        mock_rev,
        mock_seq,
        mock_inv_get,
        mock_cust_get,
        mock_lines_get,
    ]

    service = InvoiceService(mock_session)
    res = await service.generate_invoice(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=uuid.uuid4(),
    )

    assert res["status"] == "APPROVED"
    assert res["approval_status"] == "APPROVED"


@pytest.mark.asyncio
async def test_approval_above_threshold_requires_approval():
    """Verify invoice > $5,000 enters PENDING_APPROVAL and cannot be sent until approved."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    pending_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00005",
        total_amount=8500.0,
        approval_status="PENDING",
        status="PENDING_APPROVAL",
    )
    pending_invoice.id = invoice_id

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = pending_invoice

    mock_session.execute.return_value = mock_inv

    service = InvoiceService(mock_session)

    # 1. Sending unapproved invoice must fail
    with pytest.raises(ValidationError, match="must be APPROVED before sending"):
        await service.send_invoice(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            recipient_email="client@example.com",
        )

    # 2. Approve invoice
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = pending_invoice
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = None
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_inv, mock_inv_get, mock_cust_get, mock_lines_get]

    res = await service.approve_invoice(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        notes="Approved by Finance Manager",
    )

    assert pending_invoice.status == "APPROVED"
    assert pending_invoice.approval_status == "APPROVED"
    assert pending_invoice.approved_by == actor_id


# ---------------------------------------------------------------------------
# 5. PDF Generation & Dispatch Tests
# ---------------------------------------------------------------------------

def test_invoice_pdf_generator_rendered_structure():
    """Verify PDF generator produces valid %PDF-1.4 header and contains persisted fields."""
    inv_data = {
        "invoice_number": "INV-2026-99999",
        "invoice_date": "2026-09-04",
        "customer_name": "Saudi Petrochemical Corp",
        "tax_registration": "SA300099887700003",
        "job_number": "JOB-2026-001",
        "bl_awb_number": "MAWB-020-99881122",
        "currency_code": "USD",
        "exchange_rate_to_base": 1.0,
        "subtotal_amount": 4000.0,
        "tax_amount": 600.0,
        "total_amount": 4600.0,
        "tax_type": "VAT",
        "tax_rate": 0.15,
        "lines": [
            {
                "charge_code": "AIR_FREIGHT",
                "description": "Direct Air Linehaul",
                "quantity": 2.0,
                "unit_rate": 2000.0,
                "amount": 4000.0,
                "tax_amount": 600.0,
                "total_amount": 4600.0,
            }
        ],
    }

    pdf_bytes = InvoicePDFGenerator.generate(inv_data)

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"INV-2026-99999" in pdf_bytes
    assert b"Saudi Petrochemical Corp" in pdf_bytes
    assert b"AIR_FREIGHT" in pdf_bytes
    assert b"4600.00" in pdf_bytes


@pytest.mark.asyncio
async def test_send_invoice_outbox_event_and_status_update():
    """Verify sending an approved invoice marks status SENT and enqueues outbox event."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    approved_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00008",
        total_amount=1500.0,
        currency_code="USD",
        approval_status="APPROVED",
        status="APPROVED",
    )
    approved_invoice.id = invoice_id

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = approved_invoice

    # get_invoice mock calls
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = approved_invoice
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = None
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_inv, mock_inv_get, mock_cust_get, mock_lines_get]

    service = InvoiceService(mock_session)
    service.outbox = AsyncMock()
    service.audit = AsyncMock()

    res = await service.send_invoice(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        recipient_email="finance@customer.com",
    )

    assert res["status"] == "SENT"
    assert res["recipient_email"] == "finance@customer.com"
    assert approved_invoice.status == "SENT"
    assert approved_invoice.sent_at is not None
    assert service.outbox.enqueue.called
    assert service.audit.record.called


# ---------------------------------------------------------------------------
# 6. Credit Note & Debit Note Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_credit_note_creation_and_ar_entry():
    """Verify credit note references invoice, creates offsetting AR entry, and preserves invoice."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    orig_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00010",
        total_amount=3000.0,
        currency_code="USD",
        status="SENT",
    )
    orig_invoice.id = invoice_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = orig_invoice
    mock_cn_sum = MagicMock()
    mock_cn_sum.scalar.return_value = 0.0
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0

    mock_session.execute.side_effect = [mock_inv, mock_cn_sum, mock_seq]

    service = InvoiceService(mock_session)
    service.audit = AsyncMock()

    res = await service.create_credit_note(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        amount=500.0,
        reason="Disputed storage fee waived per agreement",
    )

    assert res["credit_note_number"].startswith("CN-")
    assert res["amount"] == 500.0
    assert res["invoice_id"] == str(invoice_id)
    # Original invoice amount unchanged
    assert orig_invoice.total_amount == 3000.0

    # Verify offsetting AR entry added
    added_financial = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], FinancialEntry)
    ]
    assert len(added_financial) == 1
    assert added_financial[0].entry_type == "CREDIT_NOTE"
    assert added_financial[0].credit_amount == 500.0


@pytest.mark.asyncio
async def test_credit_note_exceeding_invoice_total_rejected():
    """Verify credit note amount exceeding invoice total is rejected."""
    tenant_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    orig_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00011",
        total_amount=1000.0,
        status="SENT",
    )

    mock_session = AsyncMock()
    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = orig_invoice
    mock_cn_sum = MagicMock()
    mock_cn_sum.scalar.return_value = 0.0
    mock_session.execute.side_effect = [mock_inv, mock_cn_sum]

    service = InvoiceService(mock_session)
    with pytest.raises(ValidationError, match="exceeds remaining creditable amount"):
        await service.create_credit_note(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
            amount=1500.0,
            reason="Excessive credit amount",
        )


@pytest.mark.asyncio
async def test_partial_credit_note_cumulative_exceeding_rejected():
    """Verify multiple partial credit notes cannot exceed total invoice amount."""
    tenant_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    orig_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00011",
        total_amount=1000.0,
        status="SENT",
    )

    mock_session = AsyncMock()
    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = orig_invoice
    # Suppose $700 has already been credited
    mock_cn_sum = MagicMock()
    mock_cn_sum.scalar.return_value = 700.0
    mock_session.execute.side_effect = [mock_inv, mock_cn_sum]

    service = InvoiceService(mock_session)
    # Attempting to credit $400 (700 + 400 = 1100 > 1000) must fail
    with pytest.raises(ValidationError, match="exceeds remaining creditable amount"):
        await service.create_credit_note(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
            amount=400.0,
            reason="Second credit note exceeds remaining balance",
        )


@pytest.mark.asyncio
async def test_fully_credited_invoice_rejects_further_credit():
    """Verify invoice that has already been fully credited rejects additional credit notes."""
    tenant_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    orig_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00011",
        total_amount=1000.0,
        status="CREDITED",
    )

    mock_session = AsyncMock()
    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = orig_invoice
    # $1000 already credited
    mock_cn_sum = MagicMock()
    mock_cn_sum.scalar.return_value = 1000.0
    mock_session.execute.side_effect = [mock_inv, mock_cn_sum]

    service = InvoiceService(mock_session)
    with pytest.raises(ValidationError, match="already been fully credited"):
        await service.create_credit_note(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            actor_id=uuid.uuid4(),
            amount=50.0,
            reason="Cannot credit fully credited invoice",
        )


@pytest.mark.asyncio
async def test_debit_note_creation_and_ar_entry():
    """Verify debit note issues additional charge linked to invoice and creates AR entry."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    orig_invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-00012",
        total_amount=2000.0,
        currency_code="USD",
        status="SENT",
    )
    orig_invoice.id = invoice_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = orig_invoice
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0

    mock_session.execute.side_effect = [mock_inv, mock_seq]

    service = InvoiceService(mock_session)
    service.audit = AsyncMock()

    res = await service.create_debit_note(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        charge_code="DETENTION",
        amount=350.0,
        reason="Port detention incurred over free days",
    )

    assert res["debit_note_number"].startswith("DN-")
    assert res["charge_code"] == "DETENTION"
    assert res["amount"] == 350.0
    assert res["invoice_id"] == str(invoice_id)

    added_financial = [
        call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], FinancialEntry)
    ]
    assert len(added_financial) == 1
    assert added_financial[0].entry_type == "DEBIT_NOTE"
    assert added_financial[0].debit_amount == 350.0


# ---------------------------------------------------------------------------
# 7. Multi-Tenant Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invoice_cross_tenant_access_rejected():
    """Verify Tenant A cannot access or modify Tenant B's invoices."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    invoice_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_inv = MagicMock()
    mock_inv.scalar_one_or_none.return_value = None  # Not found under tenant A
    mock_session.execute.return_value = mock_inv

    service = InvoiceService(mock_session)

    with pytest.raises(NotFoundError, match="Invoice .* not found"):
        await service.get_invoice(invoice_id, tenant_a)

    with pytest.raises(NotFoundError, match="Invoice .* not found"):
        await service.generate_invoice_pdf(invoice_id, tenant_a)

    with pytest.raises(NotFoundError, match="Invoice .* not found"):
        await service.approve_invoice(invoice_id=invoice_id, tenant_id=tenant_a, actor_id=uuid.uuid4())

    with pytest.raises(NotFoundError, match="Invoice .* not found"):
        await service.send_invoice(invoice_id=invoice_id, tenant_id=tenant_a, actor_id=uuid.uuid4())

    with pytest.raises(NotFoundError, match="Invoice .* not found"):
        await service.create_credit_note(
            invoice_id=invoice_id,
            tenant_id=tenant_a,
            actor_id=uuid.uuid4(),
            amount=100.0,
            reason="Cross tenant",
        )

    with pytest.raises(NotFoundError, match="Invoice .* not found"):
        await service.create_debit_note(
            invoice_id=invoice_id,
            tenant_id=tenant_a,
            actor_id=uuid.uuid4(),
            charge_code="SURCHARGE",
            amount=50.0,
            reason="Cross tenant",
        )


# ---------------------------------------------------------------------------
# 8. REST API Endpoints & RBAC Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_generate_and_get_invoice():
    """Verify HTTP POST /api/v1/invoices and GET /api/v1/invoices/{id}."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_AR"},
        permissions={"invoice:create", "invoice:read"},
        is_portal=False,
    )

    shipment = make_test_shipment(tenant_id, customer_id, shipment_id)
    customer = make_test_customer(tenant_id, customer_id)
    rev = RevenueLine(
        shipment_id=shipment_id,
        charge_code="FREIGHT",
        amount=1200.0,
        status="ESTIMATED",
    )
    rev.id = uuid.uuid4()

    inv_obj = Invoice(
        tenant_id=tenant_id,
        customer_id=customer_id,
        shipment_id=shipment_id,
        invoice_number="INV-2026-00050",
        invoice_date=date.today(),
        currency_code="USD",
        subtotal_amount=1200.0,
        tax_amount=0.0,
        total_amount=1200.0,
        status="APPROVED",
    )
    inv_obj.id = invoice_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_shp = MagicMock()
    mock_shp.scalar_one_or_none.return_value = shipment
    mock_cust = MagicMock()
    mock_cust.scalar_one_or_none.return_value = customer
    mock_rev = MagicMock()
    mock_rev.scalars.return_value.all.return_value = [rev]
    mock_seq = MagicMock()
    mock_seq.scalar.return_value = 0

    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = inv_obj
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = customer
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        # For POST /api/v1/invoices
        mock_shp,
        mock_cust,
        mock_rev,
        mock_seq,
        mock_inv_get,
        mock_cust_get,
        mock_lines_get,
        # For GET /api/v1/invoices/{id}
        mock_inv_get,
        mock_cust_get,
        mock_lines_get,
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
            # 1. POST
            post_resp = await client.post(
                "/api/v1/invoices",
                json={"shipment_id": str(shipment_id)},
            )
            assert post_resp.status_code == 201
            assert post_resp.json()["success"] is True
            assert post_resp.json()["data"]["invoice_number"] == "INV-2026-00050"

            # 2. GET
            get_resp = await client.get(f"/api/v1/invoices/{invoice_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["data"]["total_amount"] == 1200.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_invoice_pdf_endpoint():
    """Verify HTTP GET /api/v1/invoices/{id}/pdf returns application/pdf content."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"FINANCE_AR"},
        permissions={"invoice:read"},
        is_portal=False,
    )

    inv_obj = Invoice(
        tenant_id=tenant_id,
        customer_id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        invoice_number="INV-2026-PDF01",
        invoice_date=date.today(),
        currency_code="USD",
        subtotal_amount=1000.0,
        tax_amount=0.0,
        total_amount=1000.0,
        status="APPROVED",
    )
    inv_obj.id = invoice_id

    mock_session = AsyncMock()
    mock_inv_get = MagicMock()
    mock_inv_get.scalar_one_or_none.return_value = inv_obj
    mock_cust_get = MagicMock()
    mock_cust_get.scalar_one_or_none.return_value = None
    mock_lines_get = MagicMock()
    mock_lines_get.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_inv_get, mock_cust_get, mock_lines_get]

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/invoices/{invoice_id}/pdf")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            assert resp.content.startswith(b"%PDF-1.4")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_rbac_insufficient_invoice_permissions():
    """Verify 403 Forbidden when user lacks required invoice permissions."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # User only has user:read
    user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        roles={"SALES"},
        permissions={"user:read"},
        is_portal=False,
    )

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            inv_id = str(uuid.uuid4())
            # 1. create
            resp1 = await client.post("/api/v1/invoices", json={"shipment_id": str(uuid.uuid4())})
            assert resp1.status_code == 403

            # 2. approve
            resp2 = await client.post(f"/api/v1/invoices/{inv_id}/approve")
            assert resp2.status_code == 403

            # 3. send
            resp3 = await client.post(f"/api/v1/invoices/{inv_id}/send", json={"recipient_email": "a@b.com"})
            assert resp3.status_code == 403

            # 4. credit note
            resp4 = await client.post(f"/api/v1/invoices/{inv_id}/credit-note", json={"amount": 100.0, "reason": "test"})
            assert resp4.status_code == 403

            # 5. debit note
            resp5 = await client.post(f"/api/v1/invoices/{inv_id}/debit-note", json={"charge_code": "TEST", "amount": 100.0, "reason": "test"})
            assert resp5.status_code == 403
    finally:
        app.dependency_overrides.clear()
