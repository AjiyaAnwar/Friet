"""Commercial Quotation API endpoints (Phase 3)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user_optional, require_permission
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.commercial.service import CommercialService

router = APIRouter()


class QuotationCreateRequest(BaseModel):
    rfq_id: str
    total_amount: Decimal | None = None
    expiry_date: date | None = None
    markup_pct: Decimal = Decimal("10")
    currency_code: str = "USD"
    rate_id: str | None = None


class QuotationAcceptRequest(BaseModel):
    customer_id: str | None = None


def _pdf_document(title: str, lines: list[str]) -> bytes:
    """Small dependency-free PDF renderer for a persisted quotation summary."""
    body = "\\n".join([f"({value.replace('(', '[').replace(')', ']')}) Tj T*"] for value in [title, *lines])
    stream = f"BT /F1 12 Tf 50 760 Td 16 TL {body} ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>", b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream), b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{index} 0 obj\n".encode()); output.extend(obj); output.extend(b"\nendobj\n")
    xref = len(output); output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)


@router.post("/quotations")
async def create_quotation(
    payload: QuotationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:approve"))],
) -> dict[str, Any]:
    service = CommercialService(session)
    quotation = await service.create_quotation(payload.model_dump(), tenant_id=user.tenant_id)
    if session:
        await session.commit()
    return {"success": True, "data": quotation, "errors": [], "meta": {}}


@router.get("/quotations/{quotation_id}")
async def get_quotation(
    quotation_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict[str, Any]:
    service = CommercialService(session)
    quotation = await service.get_quotation(quotation_id)
    if not quotation:
        raise NotFoundError(f"Quotation {quotation_id} not found")
    return {"success": True, "data": quotation, "errors": [], "meta": {}}


@router.post("/quotations/{quotation_id}/accept")
async def accept_quotation(
    quotation_id: str,
    payload: QuotationAcceptRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:approve"))],
) -> dict[str, Any]:
    service = CommercialService(session)
    job = await service.accept_quotation(
        quotation_id,
        customer_id=payload.customer_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
    )
    if not job:
        raise NotFoundError(f"Quotation {quotation_id} not found")
    if session:
        await session.commit()
    return {"success": True, "data": job, "errors": [], "meta": {}}


@router.post("/quotations/{quotation_id}/send")
async def send_quotation(
    quotation_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:approve"))],
) -> dict[str, Any]:
    quote = await CommercialService(session).send_quotation(quotation_id, tenant_id=user.tenant_id, actor_id=user.id)
    await session.commit()
    return {"success": True, "data": quote, "errors": [], "meta": {}}


@router.get("/quotations/{quotation_id}/pdf")
async def quotation_pdf(
    quotation_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:read"))],
) -> Response:
    quote = await CommercialService(session).get_quotation(quotation_id)
    document = _pdf_document("FreightCore Quotation", [
        f"Reference: {quote['quotation_number']}", f"Status: {quote['status']}",
        f"Total: {quote['total_amount']}",
    ])
    return Response(document, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={quote['quotation_number']}.pdf"})


class QuotationReviseRequest(BaseModel):
    markup_pct: Decimal | None = None
    total_amount: Decimal | None = None
    expiry_date: date | None = None
    notes: str | None = None


@router.get("/quotations")
async def list_quotations(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:read"))],
    rfq_id: str | None = None,
    customer_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    from sqlalchemy import select
    from app.db.models.commercial import Quotation
    import uuid

    if session is not None:
        stmt = select(Quotation).where(Quotation.tenant_id == user.tenant_id).order_by(Quotation.created_at.desc())
        if rfq_id:
            try:
                r_id = uuid.UUID(rfq_id)
                stmt = stmt.where(Quotation.rfq_id == r_id)
            except ValueError:
                pass
        if customer_id:
            try:
                c_id = uuid.UUID(customer_id)
                stmt = stmt.where(Quotation.customer_id == c_id)
            except ValueError:
                pass
        if status:
            stmt = stmt.where(Quotation.status == status.upper())
        quotes = (await session.execute(stmt)).scalars().all()
        data = [
            {
                "id": str(q.id),
                "quotation_number": q.quotation_number,
                "rfq_id": str(q.rfq_id),
                "customer_id": str(q.customer_id) if q.customer_id else None,
                "status": q.status,
                "total_amount": str(q.total_amount) if q.total_amount is not None else None,
                "currency_code": q.currency_code,
                "expiry_date": str(q.expiry_date) if q.expiry_date else None,
                "parent_quotation_id": str(q.parent_quotation_id) if q.parent_quotation_id else None,
                "created_at": str(q.created_at) if q.created_at else None,
            }
            for q in quotes
        ]
    else:
        from app.modules.commercial.repository import _IN_MEMORY_QUOTATIONS
        data = list(_IN_MEMORY_QUOTATIONS.values())
        if rfq_id:
            data = [q for q in data if q.get("rfq_id") == rfq_id]
        if status:
            data = [q for q in data if q.get("status") == status]
    return {"success": True, "data": data, "errors": [], "meta": {"total": len(data)}}


@router.post("/quotations/{quotation_id}/revise")
async def revise_quotation(
    quotation_id: str,
    payload: QuotationReviseRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:approve"))],
) -> dict[str, Any]:
    from sqlalchemy import select
    from app.db.models.commercial import Quotation
    import uuid

    if session is not None:
        try:
            q_uuid = uuid.UUID(quotation_id)
        except ValueError:
            raise NotFoundError(f"Quotation {quotation_id} not found")
        parent = (await session.execute(
            select(Quotation).where(Quotation.id == q_uuid, Quotation.tenant_id == user.tenant_id)
        )).scalar_one_or_none()
        if not parent:
            raise NotFoundError(f"Quotation {quotation_id} not found")
        parent.status = "REVISED"
        service = CommercialService(session)
        create_payload = {
            "rfq_id": str(parent.rfq_id),
            "total_amount": payload.total_amount if payload.total_amount is not None else parent.total_amount,
            "expiry_date": payload.expiry_date if payload.expiry_date is not None else parent.expiry_date,
            "markup_pct": payload.markup_pct if payload.markup_pct is not None else Decimal("10"),
            "currency_code": parent.currency_code,
            "parent_quotation_id": str(parent.id),
        }
        revised = await service.create_quotation(create_payload, tenant_id=user.tenant_id)
        await session.commit()
        return {"success": True, "data": revised, "errors": [], "meta": {}}
    else:
        from app.modules.commercial.repository import _IN_MEMORY_QUOTATIONS
        parent = _IN_MEMORY_QUOTATIONS.get(quotation_id)
        if not parent:
            raise NotFoundError(f"Quotation {quotation_id} not found")
        parent["status"] = "REVISED"
        service = CommercialService()
        create_payload = {
            "rfq_id": parent["rfq_id"],
            "total_amount": float(payload.total_amount) if payload.total_amount is not None else parent.get("total_amount", 1000.0),
            "expiry_date": payload.expiry_date or parent.get("expiry_date"),
            "parent_quotation_id": quotation_id,
        }
        revised = await service.create_quotation(create_payload, tenant_id=user.tenant_id)
        return {"success": True, "data": revised, "errors": [], "meta": {}}
