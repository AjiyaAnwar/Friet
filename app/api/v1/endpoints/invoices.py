"""Customer Invoicing Endpoints (Phase 5.2).

Exposes:
  - POST /api/v1/invoices
  - GET  /api/v1/invoices/{invoice_id}
  - GET  /api/v1/invoices
  - POST /api/v1/invoices/{invoice_id}/approve
  - GET  /api/v1/invoices/{invoice_id}/pdf
  - POST /api/v1/invoices/{invoice_id}/send
  - POST /api/v1/invoices/{invoice_id}/credit-note
  - POST /api/v1/invoices/{invoice_id}/debit-note
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.session import get_db
from app.modules.invoicing.schemas import (
    CreditNoteCreateRequest,
    DebitNoteCreateRequest,
    InvoiceApproveRequest,
    InvoiceGenerateRequest,
    InvoiceSendRequest,
)
from app.modules.invoicing.service import InvoiceService

router = APIRouter()


# ---------------------------------------------------------------------------
# 1. Invoice Generation & Retrieval
# ---------------------------------------------------------------------------

@router.post("/invoices", status_code=201)
async def generate_invoice(
    payload: InvoiceGenerateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("invoice:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Generate a customer invoice directly from shipment revenue ledger lines."""
    service = InvoiceService(session)
    invoice = await service.generate_invoice(
        shipment_id=payload.shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        currency_code=payload.currency_code,
        tax_jurisdiction=payload.tax_jurisdiction,
        payment_terms=payload.payment_terms,
        customer_po=payload.customer_po,
        notes=payload.notes,
        revenue_line_ids=payload.revenue_line_ids,
    )
    await session.commit()
    return {
        "success": True,
        "data": invoice,
        "errors": [],
        "meta": {},
    }


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: Annotated[uuid.UUID, Path(...)],
    user: Annotated[CurrentUser, Depends(require_permission("invoice:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Retrieve full details of an invoice with itemized lines and locked tax/exchange data."""
    service = InvoiceService(session)
    invoice = await service.get_invoice(invoice_id, user.tenant_id)
    return {
        "success": True,
        "data": invoice,
        "errors": [],
        "meta": {},
    }


@router.get("/invoices")
async def list_invoices(
    user: Annotated[CurrentUser, Depends(require_permission("invoice:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    customer_id: uuid.UUID | None = Query(None),
    shipment_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List invoices for the current tenant with optional filters."""
    service = InvoiceService(session)
    invoices = await service.list_invoices(
        tenant_id=user.tenant_id,
        customer_id=customer_id,
        shipment_id=shipment_id,
        status=status,
        limit=limit,
    )
    return {
        "success": True,
        "data": invoices,
        "errors": [],
        "meta": {"count": len(invoices)},
    }


# ---------------------------------------------------------------------------
# 2. Approval Workflow
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/approve")
async def approve_invoice(
    invoice_id: Annotated[uuid.UUID, Path(...)],
    payload: InvoiceApproveRequest,
    user: Annotated[CurrentUser, Depends(require_permission("invoice:approve"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Approve an invoice requiring managerial or finance approval."""
    service = InvoiceService(session)
    invoice = await service.approve_invoice(
        invoice_id=invoice_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        notes=payload.notes,
    )
    await session.commit()
    return {
        "success": True,
        "data": invoice,
        "errors": [],
        "meta": {},
    }


# ---------------------------------------------------------------------------
# 3. PDF Generation & Dispatch
# ---------------------------------------------------------------------------

@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: Annotated[uuid.UUID, Path(...)],
    user: Annotated[CurrentUser, Depends(require_permission("invoice:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Generate and download a branded PDF invoice rendered from persisted values."""
    service = InvoiceService(session)
    pdf_bytes = await service.generate_invoice_pdf(invoice_id, user.tenant_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=invoice_{invoice_id}.pdf"},
    )


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(
    invoice_id: Annotated[uuid.UUID, Path(...)],
    payload: InvoiceSendRequest,
    user: Annotated[CurrentUser, Depends(require_permission("invoice:send"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Send an approved invoice to the customer with an attached PDF via outbox events."""
    service = InvoiceService(session)
    result = await service.send_invoice(
        invoice_id=invoice_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        recipient_email=payload.recipient_email,
    )
    await session.commit()
    return {
        "success": True,
        "data": result,
        "errors": [],
        "meta": {},
    }


# ---------------------------------------------------------------------------
# 4. Credit & Debit Notes
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/credit-note", status_code=201)
async def create_credit_note(
    invoice_id: Annotated[uuid.UUID, Path(...)],
    payload: CreditNoteCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("invoice:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Issue a full or partial credit note linked to an existing invoice."""
    service = InvoiceService(session)
    cn = await service.create_credit_note(
        invoice_id=invoice_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        amount=payload.amount,
        reason=payload.reason,
        currency_code=payload.currency_code,
    )
    await session.commit()
    return {
        "success": True,
        "data": cn,
        "errors": [],
        "meta": {},
    }


@router.post("/invoices/{invoice_id}/debit-note", status_code=201)
async def create_debit_note(
    invoice_id: Annotated[uuid.UUID, Path(...)],
    payload: DebitNoteCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("invoice:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Issue a debit note for additional charges linked to an existing invoice."""
    service = InvoiceService(session)
    dn = await service.create_debit_note(
        invoice_id=invoice_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        charge_code=payload.charge_code,
        amount=payload.amount,
        reason=payload.reason,
        currency_code=payload.currency_code,
        description=payload.description,
    )
    await session.commit()
    return {
        "success": True,
        "data": dn,
        "errors": [],
        "meta": {},
    }
