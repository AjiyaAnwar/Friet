"""Document Management Service (Phase 4.4)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models.domain import (
    Document,
    DocumentAccessLog,
    DocumentChecklistItem,
    DocumentVersion,
    Shipment,
)
from app.modules.audit.service import AuditService
from app.modules.documents.checklist import checklist_engine
from app.modules.documents.expiry import check_document_expiries
from app.modules.documents.storage import get_storage_backend
from app.modules.events.service import OutboxService

# Transport document types visible to Carrier Portal users
TRANSPORT_DOC_TYPES = {
    "BILL_OF_LADING",
    "AIR_WAYBILL",
    "MANIFEST",
    "CARGO_MANIFEST",
    "SHIPPING_INSTRUCTIONS",
    "VGM_CERTIFICATE",
    "SECURITY_SCREENING_CERT",
    "PROOF_OF_DELIVERY",
}

# Role-specific approval requirements
DOCUMENT_APPROVAL_GATES: dict[str, set[str]] = {
    "DGR_DECLARATION": {"COMPLIANCE", "COMPLIANCE_OFFICER", "SUPER_ADMIN"},
    "DGR_EMERGENCY_RESPONSE": {"COMPLIANCE", "COMPLIANCE_OFFICER", "SUPER_ADMIN"},
    "COMMERCIAL_INVOICE": {"CUSTOMS", "FINANCE", "FINANCE_CONTROLLER", "OPERATIONS", "SUPER_ADMIN"},
    "US_ISF_10_2": {"CUSTOMS", "OPERATIONS", "SUPER_ADMIN"},
    "SABER_SASO_CERTIFICATE": {"CUSTOMS", "COMPLIANCE", "SUPER_ADMIN"},
    "PHYTOSANITARY_CERT": {"CUSTOMS", "COMPLIANCE", "SUPER_ADMIN"},
    "BILL_OF_LADING": {"OPERATIONS", "PRICING", "SUPER_ADMIN"},
    "AIR_WAYBILL": {"OPERATIONS", "PRICING", "SUPER_ADMIN"},
}


class DocumentService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.storage = get_storage_backend()
        self.audit = AuditService(session) if session else None
        self.outbox = OutboxService(session) if session else None

    # -----------------------------------------------------------------------
    # Document Upload & Versioning
    # -----------------------------------------------------------------------

    async def upload_document(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        doc_type: str,
        document_name: str,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        expiry_date: datetime | None = None,
        is_mandatory: bool = False,
        change_summary: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Upload a new document or create an immutable next version if existing."""
        file_size = len(file_bytes)
        file_url = await self.storage.upload(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            shipment_id=shipment_id,
        )

        now = datetime.now(timezone.utc)

        if self.session is None:
            # In-memory test double
            doc_id = uuid.uuid4()
            return {
                "id": str(doc_id),
                "shipment_id": str(shipment_id),
                "doc_type": doc_type,
                "document_name": document_name,
                "file_url": file_url,
                "version_number": 1,
                "file_size": file_size,
                "mime_type": content_type,
                "status": "PENDING_REVIEW",
                "uploaded_at": now.isoformat(),
                "expiry_date": expiry_date.isoformat() if expiry_date else None,
            }

        # Check if active document record of this type exists on this shipment
        existing_doc = (
            await self.session.execute(
                select(Document).where(
                    Document.shipment_id == shipment_id,
                    Document.doc_type == doc_type,
                )
            )
        ).scalar_one_or_none()

        if existing_doc:
            # Increment version number on parent record (previous versions remain immutable)
            next_version = existing_doc.version_number + 1
            existing_doc.version_number = next_version
            existing_doc.file_url = file_url
            existing_doc.file_size = file_size
            existing_doc.uploaded_by = actor_id
            existing_doc.uploaded_at = now
            existing_doc.status = "PENDING_REVIEW"
            if expiry_date:
                existing_doc.expiry_date = expiry_date
            if document_name:
                existing_doc.document_name = document_name
            target_doc = existing_doc
        else:
            next_version = 1
            target_doc = Document(
                shipment_id=shipment_id,
                doc_type=doc_type,
                document_name=document_name or filename,
                file_url=file_url,
                version_number=1,
                uploaded_by=actor_id,
                uploaded_at=now,
                file_size=file_size,
                mime_type=content_type,
                status="PENDING_REVIEW",
                expiry_date=expiry_date,
                is_mandatory=is_mandatory,
            )
            self.session.add(target_doc)
            await self.session.flush()

        # Create immutable version record
        version_record = DocumentVersion(
            document_id=target_doc.id,
            version_number=next_version,
            file_url=file_url,
            file_size=file_size,
            uploaded_by=actor_id,
            uploaded_at=now,
            change_summary=change_summary or f"Version {next_version} upload",
            status="PENDING_REVIEW",
        )
        self.session.add(version_record)

        # Update checklist item status if present
        checklist_item = (
            await self.session.execute(
                select(DocumentChecklistItem).where(
                    DocumentChecklistItem.shipment_id == shipment_id,
                    DocumentChecklistItem.doc_type_code == doc_type,
                )
            )
        ).scalar_one_or_none()
        if checklist_item:
            checklist_item.status = "UPLOADED"
            checklist_item.document_id = target_doc.id

        # Access / Action log
        access_log = DocumentAccessLog(
            document_id=target_doc.id,
            user_id=actor_id,
            action="UPLOAD",
            ip_address=ip_address,
            timestamp=now,
        )
        self.session.add(access_log)

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="document",
                entity_id=str(target_doc.id),
                action="document.upload",
                new_value={
                    "doc_type": doc_type,
                    "version": next_version,
                    "file_url": file_url,
                },
            )

        if self.outbox:
            await self.outbox.enqueue(
                event_type="document.uploaded",
                tenant_id=tenant_id,
                aggregate_type="document",
                aggregate_id=target_doc.id,
                payload={
                    "shipment_id": str(shipment_id),
                    "doc_type": doc_type,
                    "version": next_version,
                },
            )

        return {
            "id": str(target_doc.id),
            "shipment_id": str(target_doc.shipment_id),
            "doc_type": target_doc.doc_type,
            "document_name": target_doc.document_name,
            "file_url": target_doc.file_url,
            "version_number": target_doc.version_number,
            "file_size": target_doc.file_size,
            "mime_type": target_doc.mime_type,
            "status": target_doc.status,
            "uploaded_at": str(target_doc.uploaded_at),
            "expiry_date": str(target_doc.expiry_date) if target_doc.expiry_date else None,
        }

    # -----------------------------------------------------------------------
    # Document Retrieval & List with Access Control
    # -----------------------------------------------------------------------

    async def list_shipment_documents(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_roles: set[str],
        is_portal: bool = False,
        customer_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """List documents for shipment applying strict portal access control."""
        if self.session is None:
            return []

        # Enforce Customer Portal isolation: verify shipment belongs to customer
        if is_portal and customer_id:
            shipment = (
                await self.session.execute(
                    select(Shipment).where(
                        Shipment.id == shipment_id,
                        Shipment.tenant_id == tenant_id,
                        Shipment.customer_id == customer_id,
                    )
                )
            ).scalar_one_or_none()
            if not shipment:
                raise ForbiddenError("You do not have access to documents for this shipment.")

        docs = (
            await self.session.execute(
                select(Document)
                .where(Document.shipment_id == shipment_id)
                .order_by(Document.created_at.desc())
            )
        ).scalars().all()

        results: list[dict[str, Any]] = []
        is_carrier_portal = "CARRIER_PORTAL" in user_roles or "CARRIER" in user_roles

        for doc in docs:
            # Carrier Portal filter: see transport documents only
            if is_carrier_portal and doc.doc_type not in TRANSPORT_DOC_TYPES:
                continue

            results.append({
                "id": str(doc.id),
                "shipment_id": str(doc.shipment_id),
                "doc_type": doc.doc_type,
                "document_name": doc.document_name,
                "file_url": doc.file_url,
                "version_number": doc.version_number,
                "file_size": doc.file_size,
                "status": doc.status,
                "is_mandatory": doc.is_mandatory,
                "uploaded_at": str(doc.uploaded_at) if doc.uploaded_at else None,
                "expiry_date": str(doc.expiry_date) if doc.expiry_date else None,
            })

        return results

    async def get_document(
        self,
        document_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Fetch document details along with complete version history."""
        if self.session is None:
            raise NotFoundError("Document not found")

        doc = (
            await self.session.execute(
                select(Document).where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document not found")

        versions = (
            await self.session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(desc(DocumentVersion.version_number))
            )
        ).scalars().all()

        # Log view access
        if actor_id:
            log = DocumentAccessLog(
                document_id=doc.id,
                user_id=actor_id,
                action="VIEW",
                ip_address=ip_address,
                timestamp=datetime.now(timezone.utc),
            )
            self.session.add(log)

        return {
            "id": str(doc.id),
            "shipment_id": str(doc.shipment_id),
            "doc_type": doc.doc_type,
            "document_name": doc.document_name,
            "file_url": doc.file_url,
            "version_number": doc.version_number,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "status": doc.status,
            "is_mandatory": doc.is_mandatory,
            "expiry_date": str(doc.expiry_date) if doc.expiry_date else None,
            "uploaded_at": str(doc.uploaded_at) if doc.uploaded_at else None,
            "versions": [
                {
                    "id": str(v.id),
                    "version_number": v.version_number,
                    "file_url": v.file_url,
                    "file_size": v.file_size,
                    "uploaded_at": str(v.uploaded_at),
                    "change_summary": v.change_summary,
                    "status": v.status,
                }
                for v in versions
            ],
        }

    # -----------------------------------------------------------------------
    # Document Approval Lifecycle & Role Gates
    # -----------------------------------------------------------------------

    async def approve_document(
        self,
        *,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        user_roles: set[str],
        notes: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Approve document subject to role-specific compliance gates."""
        if self.session is None:
            return {"id": str(document_id), "status": "APPROVED"}

        doc = (
            await self.session.execute(
                select(Document).where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document not found")

        # Validate role gate
        required_roles = DOCUMENT_APPROVAL_GATES.get(doc.doc_type)
        if required_roles and not (user_roles & required_roles) and "SUPER_ADMIN" not in user_roles:
            raise ForbiddenError(
                f"Approval of {doc.doc_type} requires one of roles: {', '.join(required_roles)}"
            )

        doc.status = "APPROVED"
        doc.rejection_reason = None

        # Update checklist item if linked
        checklist_item = (
            await self.session.execute(
                select(DocumentChecklistItem).where(
                    DocumentChecklistItem.shipment_id == doc.shipment_id,
                    DocumentChecklistItem.doc_type_code == doc.doc_type,
                )
            )
        ).scalar_one_or_none()
        if checklist_item:
            checklist_item.status = "APPROVED"

        # Log action
        self.session.add(
            DocumentAccessLog(
                document_id=doc.id,
                user_id=actor_id,
                action="APPROVE",
                ip_address=ip_address,
                timestamp=datetime.now(timezone.utc),
            )
        )

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="document",
                entity_id=str(doc.id),
                action="document.approve",
                new_value={"status": "APPROVED", "notes": notes},
            )

        return {"id": str(doc.id), "status": "APPROVED", "doc_type": doc.doc_type}

    async def reject_document(
        self,
        *,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Reject document with a recorded reason."""
        if self.session is None:
            return {"id": str(document_id), "status": "REJECTED", "reason": reason}

        doc = (
            await self.session.execute(
                select(Document).where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document not found")

        doc.status = "REJECTED"
        doc.rejection_reason = reason

        checklist_item = (
            await self.session.execute(
                select(DocumentChecklistItem).where(
                    DocumentChecklistItem.shipment_id == doc.shipment_id,
                    DocumentChecklistItem.doc_type_code == doc.doc_type,
                )
            )
        ).scalar_one_or_none()
        if checklist_item:
            checklist_item.status = "MISSING"

        self.session.add(
            DocumentAccessLog(
                document_id=doc.id,
                user_id=actor_id,
                action="REJECT",
                ip_address=ip_address,
                timestamp=datetime.now(timezone.utc),
            )
        )

        return {"id": str(doc.id), "status": "REJECTED", "rejection_reason": reason}

    async def request_revision(
        self,
        *,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        notes: str,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Request revision on document."""
        if self.session is None:
            return {"id": str(document_id), "status": "REVISION_REQUESTED", "notes": notes}

        doc = (
            await self.session.execute(
                select(Document).where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document not found")

        doc.status = "REVISION_REQUESTED"
        doc.rejection_reason = notes

        self.session.add(
            DocumentAccessLog(
                document_id=doc.id,
                user_id=actor_id,
                action="REQUEST_REVISION",
                ip_address=ip_address,
                timestamp=datetime.now(timezone.utc),
            )
        )

        return {"id": str(doc.id), "status": "REVISION_REQUESTED", "notes": notes}

    # -----------------------------------------------------------------------
    # Document Checklist Management & Transition Gates
    # -----------------------------------------------------------------------

    async def generate_checklist(
        self,
        *,
        shipment_id: uuid.UUID,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate and persist rule-driven document checklist for a shipment."""
        items = checklist_engine.generate_checklist(context)

        if self.session is not None:
            # Delete or update existing items
            existing_items = (
                await self.session.execute(
                    select(DocumentChecklistItem).where(
                        DocumentChecklistItem.shipment_id == shipment_id
                    )
                )
            ).scalars().all()
            existing_codes = {item.doc_type_code for item in existing_items}

            for rule_item in items:
                if rule_item["doc_type_code"] not in existing_codes:
                    db_item = DocumentChecklistItem(
                        shipment_id=shipment_id,
                        doc_type_code=rule_item["doc_type_code"],
                        doc_name=rule_item["doc_name"],
                        is_mandatory=rule_item["is_mandatory"],
                        status="REQUIRED",
                        approval_role=rule_item["approval_role"],
                    )
                    self.session.add(db_item)
            await self.session.flush()

        return items

    async def get_checklist(
        self,
        shipment_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Get current checklist status for a shipment."""
        if self.session is None:
            return []

        items = (
            await self.session.execute(
                select(DocumentChecklistItem)
                .where(DocumentChecklistItem.shipment_id == shipment_id)
                .order_by(DocumentChecklistItem.created_at.asc())
            )
        ).scalars().all()

        return [
            {
                "id": str(item.id),
                "shipment_id": str(item.shipment_id),
                "doc_type_code": item.doc_type_code,
                "doc_name": item.doc_name,
                "is_mandatory": item.is_mandatory,
                "status": item.status,
                "document_id": str(item.document_id) if item.document_id else None,
                "approval_role": item.approval_role,
            }
            for item in items
        ]

    async def validate_transition_documents(
        self,
        shipment_id: uuid.UUID,
        target_stage: str | None = None,
    ) -> dict[str, Any]:
        """Verify that all mandatory checklist documents are APPROVED before state transition."""
        if self.session is None:
            return {"can_proceed": True, "missing_documents": [], "unapproved_documents": []}

        items = (
            await self.session.execute(
                select(DocumentChecklistItem).where(
                    DocumentChecklistItem.shipment_id == shipment_id,
                    DocumentChecklistItem.is_mandatory.is_(True),
                )
            )
        ).scalars().all()

        missing = []
        unapproved = []

        for item in items:
            if item.status == "REQUIRED" or not item.document_id:
                missing.append({
                    "doc_type_code": item.doc_type_code,
                    "doc_name": item.doc_name,
                    "approval_role": item.approval_role,
                })
            elif item.status != "APPROVED":
                unapproved.append({
                    "doc_type_code": item.doc_type_code,
                    "doc_name": item.doc_name,
                    "status": item.status,
                    "approval_role": item.approval_role,
                })

        can_proceed = len(missing) == 0 and len(unapproved) == 0
        return {
            "can_proceed": can_proceed,
            "missing_documents": missing,
            "unapproved_documents": unapproved,
        }

    # -----------------------------------------------------------------------
    # Document Expiry Monitoring
    # -----------------------------------------------------------------------

    async def get_expiring_documents(
        self,
        tenant_id: uuid.UUID | None = None,
        today: datetime | None = None,
        thresholds: tuple[int, int, int] = (30, 14, 7),
    ) -> list[dict[str, Any]]:
        """Retrieve documents approaching expiration across 30/14/7 day thresholds."""
        if self.session is None:
            return []

        stmt = select(Document).where(Document.expiry_date.is_not(None))
        docs = (await self.session.execute(stmt)).scalars().all()

        doc_dicts = [
            {
                "id": str(d.id),
                "shipment_id": str(d.shipment_id),
                "doc_type": d.doc_type,
                "document_name": d.document_name,
                "expiry_date": d.expiry_date,
            }
            for d in docs
        ]

        return check_document_expiries(doc_dicts, today=today, thresholds=thresholds)

