from fastapi import APIRouter, Depends, Query, Path
from typing import List, Optional
import uuid
from datetime import datetime, UTC

from app.api.dependencies import CurrentUser, require_permission
from app.schemas.ar import (
    ARAgingReport,
    PaymentCreate,
    PaymentResponse,
    PaymentAllocationRequest,
    PaymentAllocationResponse
)
from app.services.ar_service import ARService, DunningService

router = APIRouter()

@router.get("/aging", response_model=ARAgingReport)
async def get_ar_aging(
    as_of_date: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    currency: str = Query(..., min_length=3, max_length=3),
    customer_id: Optional[uuid.UUID] = Query(None),
    current_user: CurrentUser = Depends(require_permission("ar:view_aging"))
):
    service = ARService(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await service.get_aging_report(as_of_date, currency, customer_id)

@router.post("/payments", response_model=PaymentResponse, status_code=201)
async def record_payment(
    payload: PaymentCreate,
    current_user: CurrentUser = Depends(require_permission("payments:record"))
):
    service = ARService(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await service.record_payment(payload)

@router.post("/payments/{payment_id}/allocate", response_model=PaymentAllocationResponse)
async def allocate_payment(
    payload: PaymentAllocationRequest,
    payment_id: uuid.UUID = Path(...),
    current_user: CurrentUser = Depends(require_permission("payments:allocate"))
):
    service = ARService(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await service.allocate_payment(payment_id, payload)

@router.post("/dunning/run", status_code=202)
async def run_dunning_workflow_manually(
    as_of_date: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    current_user: CurrentUser = Depends(require_permission("ar:run_dunning"))
):
    service = DunningService(tenant_id=current_user.tenant_id)
    await service.run_dunning(as_of_date)
    return {"status": "accepted", "message": "Dunning workflow executed for tenant"}
