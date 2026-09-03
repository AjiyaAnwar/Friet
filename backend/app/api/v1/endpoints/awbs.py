import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.session import get_db
from app.services.awb_service import AWBService
from app.schemas.awb import AWBCreateRequest, AWBResponse, AWBAmendmentRequest, AWBCancellationRequest

router = APIRouter()

@router.post("", response_model=dict)
async def create_awb(
    shipment_id: uuid.UUID,
    payload: AWBCreateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("awb:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AWBService(session)
    awb = await service.create_awb(user.tenant_id, user.id, payload)
    return {"data": awb.model_dump(), "meta": {}, "errors": []}

@router.post("/{awb_id}/amend", response_model=dict)
async def amend_awb(
    shipment_id: uuid.UUID,
    awb_id: uuid.UUID,
    payload: AWBAmendmentRequest,
    user: Annotated[CurrentUser, Depends(require_permission("awb:amend"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AWBService(session)
    awb = await service.amend_awb(awb_id, user.tenant_id, user.id, payload)
    return {"data": awb.model_dump(), "meta": {}, "errors": []}

@router.post("/{awb_id}/cancel", response_model=dict)
async def cancel_awb(
    shipment_id: uuid.UUID,
    awb_id: uuid.UUID,
    payload: AWBCancellationRequest,
    user: Annotated[CurrentUser, Depends(require_permission("awb:cancel"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AWBService(session)
    awb = await service.cancel_awb(awb_id, user.tenant_id, user.id, payload)
    return {"data": awb.model_dump(), "meta": {}, "errors": []}

@router.get("/{awb_id}/label")
async def generate_awb_label(
    shipment_id: uuid.UUID,
    awb_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_permission("awb_label:generate"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    service = AWBService(session)
    pdf_bytes = await service.generate_label(awb_id, user.tenant_id)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=awb_{awb_id}.pdf"})
