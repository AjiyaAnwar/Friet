"""Commercial Quotation API endpoints (Phase 3)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user_optional
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.commercial.service import CommercialService

router = APIRouter()


class QuotationCreateRequest(BaseModel):
    rfq_id: str
    total_amount: float = 0.0
    expiry_date: str | None = None


class QuotationAcceptRequest(BaseModel):
    customer_id: str | None = None


@router.post("/quotations")
async def create_quotation(
    payload: QuotationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict[str, Any]:
    service = CommercialService(session)
    tenant_id = user.tenant_id if user else None
    quotation = await service.create_quotation(payload.model_dump(), tenant_id=tenant_id)
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
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)] = None,
) -> dict[str, Any]:
    service = CommercialService(session)
    job = await service.accept_quotation(quotation_id, customer_id=payload.customer_id)
    if not job:
        raise NotFoundError(f"Quotation {quotation_id} not found")
    if session:
        await session.commit()
    return {"success": True, "data": job, "errors": [], "meta": {}}
