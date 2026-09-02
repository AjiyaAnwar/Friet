"""Global search endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, require_permission
from app.modules.search.service import SEARCH_INDICES, search_service

router = APIRouter()


@router.get("")
async def global_search(
    user: Annotated[CurrentUser, Depends(require_permission("search:read"))],
    q: str = Query(min_length=1),
) -> dict:
    allowed = []
    if "shipment:read" in user.permissions:
        allowed.extend(["shipments", "documents", "tracking"])
    if "quotation:read" in user.permissions or "rate:read" in user.permissions:
        allowed.extend(["customers", "vendors", "carriers", "rates", "invoices"])
    if not allowed:
        allowed = ["shipments"]
    indices = [i for i in allowed if i in SEARCH_INDICES]
    return await search_service.search(
        query=q,
        tenant_id=str(user.tenant_id),
        allowed_indices=indices,
    )
