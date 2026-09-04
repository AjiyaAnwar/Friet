"""Accounts Payable & Carrier Cost Verification API Endpoints (Phase 5.3)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.modules.payables.schemas import (
    PayableApproveRequest,
    PayableCreateRequest,
    PayablePaymentRequest,
    PayableVerifyRequest,
)
from app.modules.payables.service import PayableService

router = APIRouter(tags=["payables"])


@router.post("/payables", status_code=status.HTTP_201_CREATED)
async def create_payable(
    payload: PayableCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("payable:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Record a carrier/vendor bill against a shipment and its Cost Ledger."""
    service = PayableService(session)
    result = await service.record_payable(
        tenant_id=user.tenant_id,
        actor_id=user.id,
        shipment_id=payload.shipment_id,
        bill_number=payload.bill_number,
        lines=[l.model_dump() for l in payload.lines],
        vendor_id=payload.vendor_id,
        carrier_id=payload.carrier_id,
        bill_date=payload.bill_date,
        due_date=payload.due_date,
        currency_code=payload.currency_code,
        tax_amount=payload.tax_amount,
        supporting_document_url=payload.supporting_document_url,
        notes=payload.notes,
    )
    await session.commit()
    return {
        "success": True,
        "data": result,
        "errors": [],
        "meta": {},
    }


@router.get("/payables")
async def list_payables(
    user: Annotated[CurrentUser, Depends(require_permission("payable:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    shipment_id: Annotated[uuid.UUID | None, Query()] = None,
    vendor_id: Annotated[uuid.UUID | None, Query()] = None,
    carrier_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    """List tenant payables with optional filtering."""
    service = PayableService(session)
    items = await service.list_payables(
        tenant_id=user.tenant_id,
        shipment_id=shipment_id,
        vendor_id=vendor_id,
        carrier_id=carrier_id,
        status=status,
        limit=limit,
    )
    return {
        "success": True,
        "data": items,
        "errors": [],
        "meta": {"count": len(items)},
    }


@router.get("/payables/{payable_id}")
async def get_payable(
    payable_id: Annotated[uuid.UUID, Path(...)],
    user: Annotated[CurrentUser, Depends(require_permission("payable:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Retrieve full details of a payable bill including line verification and payments."""
    service = PayableService(session)
    payable = await service.get_payable(payable_id, user.tenant_id)
    return {
        "success": True,
        "data": payable,
        "errors": [],
        "meta": {},
    }


@router.post("/payables/{payable_id}/verify")
async def verify_payable(
    payable_id: Annotated[uuid.UUID, Path(...)],
    payload: PayableVerifyRequest,
    user: Annotated[CurrentUser, Depends(require_permission("payable:verify"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Perform cost verification against the Cost Ledger and flag variances."""
    service = PayableService(session)
    result = await service.verify_payable(
        payable_id=payable_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        allow_material_variance=payload.allow_material_variance,
        notes=payload.notes,
    )
    await session.commit()
    return {
        "success": True,
        "data": result,
        "errors": [],
        "meta": {},
    }


@router.post("/payables/{payable_id}/approve")
async def approve_payable(
    payable_id: Annotated[uuid.UUID, Path(...)],
    payload: PayableApproveRequest,
    user: Annotated[CurrentUser, Depends(require_permission("payable:approve"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Explicit AP approval for a verified carrier/vendor bill."""
    service = PayableService(session)
    result = await service.approve_payable(
        payable_id=payable_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        notes=payload.notes,
    )
    await session.commit()
    return {
        "success": True,
        "data": result,
        "errors": [],
        "meta": {},
    }


@router.post("/payables/{payable_id}/pay")
async def record_payment(
    payable_id: Annotated[uuid.UUID, Path(...)],
    payload: PayablePaymentRequest,
    user: Annotated[CurrentUser, Depends(require_permission("payable:pay"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Record partial or full payment against an approved payable bill."""
    service = PayableService(session)
    result = await service.record_payment(
        payable_id=payable_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        amount=payload.amount,
        payment_reference=payload.payment_reference,
        payment_date=payload.payment_date,
        currency_code=payload.currency_code,
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    await session.commit()
    return {
        "success": True,
        "data": result,
        "errors": [],
        "meta": {},
    }
