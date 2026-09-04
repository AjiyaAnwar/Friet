"""Document Management System API Endpoints (Phase 4.4)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, require_permission
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.modules.documents.service import DocumentService

router = APIRouter()


class DocumentUploadJSONRequest(BaseModel):
    doc_type: str
    document_name: str
    file_content_base64: str | None = None
    file_url: str | None = None
    expiry_date: datetime | None = None
    is_mandatory: bool = False
    change_summary: str | None = None


class DocumentApproveRequest(BaseModel):
    notes: str | None = None


class DocumentRejectRequest(BaseModel):
    reason: str = Field(min_length=3)


class DocumentRevisionRequest(BaseModel):
    notes: str = Field(min_length=3)


class DocumentChecklistGenerateRequest(BaseModel):
    mode: str = "SEA"
    service_type: str = "FCL"
    commodity: str = "GENERAL"
    is_dgr: bool = False
    is_perishable: bool = False
    incoterm: str = "FOB"
    destination_country: str = "SA"
    has_letter_of_credit: bool = False
    lc_number: str | None = None


# ---------------------------------------------------------------------------
# Document Upload & Listing
# ---------------------------------------------------------------------------

@router.post("/shipments/{shipment_id}/documents")
async def upload_shipment_document(
    shipment_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
    doc_type: str = Form(...),
    document_name: str | None = Form(None),
    expiry_date: datetime | None = Form(None),
    is_mandatory: bool = Form(False),
    change_summary: str | None = Form(None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload document file for a shipment (multipart form upload with versioning)."""
    file_bytes = await file.read()
    if not file_bytes:
        raise ValidationError("Uploaded file cannot be empty.")

    client_ip = request.client.host if request.client else None
    service = DocumentService(session)

    result = await service.upload_document(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        doc_type=doc_type.upper(),
        document_name=document_name or file.filename or doc_type,
        file_bytes=file_bytes,
        filename=file.filename or f"{doc_type}.pdf",
        content_type=file.content_type,
        expiry_date=expiry_date,
        is_mandatory=is_mandatory,
        change_summary=change_summary,
        ip_address=client_ip,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.post("/shipments/{shipment_id}/documents/json", include_in_schema=False)
async def upload_shipment_document_json(
    shipment_id: uuid.UUID,
    payload: DocumentUploadJSONRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Upload document via JSON payload with base64 data or external URL reference."""
    import base64
    if payload.file_content_base64:
        try:
            file_bytes = base64.b64decode(payload.file_content_base64)
        except Exception:
            raise ValidationError("Invalid base64 payload in file_content_base64")
    else:
        file_bytes = f"REF:{payload.file_url or 'DOCUMENT'}".encode()

    client_ip = request.client.host if request.client else None
    service = DocumentService(session)

    result = await service.upload_document(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        doc_type=payload.doc_type.upper(),
        document_name=payload.document_name,
        file_bytes=file_bytes,
        filename=f"{payload.doc_type}.pdf",
        content_type="application/pdf",
        expiry_date=payload.expiry_date,
        is_mandatory=payload.is_mandatory,
        change_summary=payload.change_summary,
        ip_address=client_ip,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.get("/shipments/{shipment_id}/documents")
async def list_shipment_documents(
    shipment_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
) -> dict[str, Any]:
    """List documents for shipment with portal access control filtering."""
    client_ip = request.client.host if request.client else None
    service = DocumentService(session)

    docs = await service.list_shipment_documents(
        shipment_id=shipment_id,
        tenant_id=user.tenant_id,
        user_roles=user.roles,
        is_portal=user.is_portal,
        customer_id=user.customer_id,
        ip_address=client_ip,
        actor_id=user.id,
    )
    return {"success": True, "data": docs, "errors": [], "meta": {"total": len(docs)}}


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
) -> dict[str, Any]:
    """Get document details with complete version history."""
    client_ip = request.client.host if request.client else None
    service = DocumentService(session)
    doc = await service.get_document(document_id, actor_id=user.id, ip_address=client_ip)
    if session:
        await session.commit()
    return {"success": True, "data": doc, "errors": [], "meta": {}}


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
) -> Response:
    """Download document payload with access audit trail."""
    client_ip = request.client.host if request.client else None
    service = DocumentService(session)
    doc = await service.get_document(document_id, actor_id=user.id, ip_address=client_ip)
    file_bytes = await service.storage.retrieve(doc["file_url"])
    if session:
        await session.commit()
    return Response(
        content=file_bytes,
        media_type=doc.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={doc.get('document_name') or 'document'}"},
    )


# ---------------------------------------------------------------------------
# Document Approval Lifecycle
# ---------------------------------------------------------------------------

@router.post("/documents/{document_id}/approve")
async def approve_document(
    document_id: uuid.UUID,
    payload: DocumentApproveRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Approve document subject to role-specific compliance gates."""
    client_ip = request.client.host if request.client else None
    service = DocumentService(session)
    result = await service.approve_document(
        document_id=document_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        user_roles=user.roles,
        notes=payload.notes,
        ip_address=client_ip,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.post("/documents/{document_id}/reject")
async def reject_document(
    document_id: uuid.UUID,
    payload: DocumentRejectRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Reject document with recorded reason."""
    client_ip = request.client.host if request.client else None
    service = DocumentService(session)
    result = await service.reject_document(
        document_id=document_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        reason=payload.reason,
        ip_address=client_ip,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


@router.post("/documents/{document_id}/request-revision")
async def request_document_revision(
    document_id: uuid.UUID,
    payload: DocumentRevisionRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Request document revision."""
    client_ip = request.client.host if request.client else None
    service = DocumentService(session)
    result = await service.request_revision(
        document_id=document_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        notes=payload.notes,
        ip_address=client_ip,
    )
    if session:
        await session.commit()
    return {"success": True, "data": result, "errors": [], "meta": {}}


# ---------------------------------------------------------------------------
# Document Checklist Endpoints
# ---------------------------------------------------------------------------

@router.get("/shipments/{shipment_id}/document-checklist")
async def get_document_checklist(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
) -> dict[str, Any]:
    """Get document checklist status for shipment."""
    service = DocumentService(session)
    items = await service.get_checklist(shipment_id)
    return {"success": True, "data": items, "errors": [], "meta": {"total": len(items)}}


@router.post("/shipments/{shipment_id}/document-checklist/generate")
async def generate_document_checklist(
    shipment_id: uuid.UUID,
    payload: DocumentChecklistGenerateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:create"))],
) -> dict[str, Any]:
    """Auto-generate rule-driven document checklist based on shipment context."""
    service = DocumentService(session)
    items = await service.generate_checklist(
        shipment_id=shipment_id,
        context=payload.model_dump(),
    )
    if session:
        await session.commit()
    return {"success": True, "data": items, "errors": [], "meta": {"total": len(items)}}


# ---------------------------------------------------------------------------
# Document Expiry Monitoring Endpoint
# ---------------------------------------------------------------------------

@router.get("/documents/monitoring/expiring")
async def get_expiring_documents(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("shipment:read"))],
    days: int = Query(30, ge=1, le=90),
) -> dict[str, Any]:
    """List documents approaching expiration within configured threshold days."""
    service = DocumentService(session)
    alerts = await service.get_expiring_documents(
        tenant_id=user.tenant_id,
        thresholds=(days, 14, 7),
    )
    return {"success": True, "data": alerts, "errors": [], "meta": {"total": len(alerts)}}

