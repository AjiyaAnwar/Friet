from fastapi import APIRouter, Depends, Path
from typing import List
import uuid

from app.api.dependencies import CurrentUser, require_permission
from app.schemas.dgr import (
    DGRItemCapture,
    DGRItemResponse,
    DGRRuleCreate,
    DGRRuleResponse,
    DGRValidationResponse,
    DGRApprovalRequest,
    DGRApprovalResponse
)
from app.services.dgr_service import DGRRuleService, DGRComplianceEngine, DGRDocumentService

router = APIRouter()

@router.post("/shipments/{shipment_id}/dgr-items", response_model=DGRItemResponse, status_code=201)
async def capture_dgr_item(
    payload: DGRItemCapture,
    shipment_id: uuid.UUID = Path(...),
    current_user: CurrentUser = Depends(require_permission("dgr:manage_items"))
):
    eng = DGRComplianceEngine(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await eng.capture_item(shipment_id, payload)

@router.post("/admin/dgr-rules", response_model=DGRRuleResponse, status_code=201)
async def create_dgr_rule(
    payload: DGRRuleCreate,
    current_user: CurrentUser = Depends(require_permission("dgr:manage_rules"))
):
    svc = DGRRuleService(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await svc.create_rule(payload)

@router.post("/shipments/{shipment_id}/dgr-items/validate", response_model=List[DGRValidationResponse])
async def validate_dgr_items(
    shipment_id: uuid.UUID = Path(...),
    current_user: CurrentUser = Depends(require_permission("dgr:validate"))
):
    eng = DGRComplianceEngine(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await eng.validate_items(shipment_id)

@router.post("/shipments/{shipment_id}/dgr-items/{item_id}/approve", response_model=DGRApprovalResponse)
async def approve_dgr_exception(
    payload: DGRApprovalRequest,
    shipment_id: uuid.UUID = Path(...),
    item_id: uuid.UUID = Path(...),
    current_user: CurrentUser = Depends(require_permission("dgr:approve_exceptions"))
):
    eng = DGRComplianceEngine(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await eng.approve_exception(item_id, payload)

@router.post("/shipments/{shipment_id}/dgr-documents/{doc_type}")
async def generate_dgr_document(
    shipment_id: uuid.UUID = Path(...),
    doc_type: str = Path(...),
    current_user: CurrentUser = Depends(require_permission("dgr:generate_docs"))
):
    svc = DGRDocumentService(tenant_id=current_user.tenant_id, user_id=current_user.id)
    return await svc.generate_dgd(shipment_id, doc_type)
