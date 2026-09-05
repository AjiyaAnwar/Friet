import uuid
from datetime import datetime, UTC
from typing import List, Optional
from fastapi import HTTPException
import hashlib

from app.schemas.dgr import (
    DGRItemCapture,
    DGRItemResponse,
    DGRRuleCreate,
    DGRRuleResponse,
    DGRValidationResponse,
    DGRValidationCheck,
    DGRApprovalRequest,
    DGRApprovalResponse
)
from app.repositories.dgr_repository import (
    dgr_repo,
    DGRItemModel,
    DGRRuleModel,
    DGRExceptionModel,
    DGRValidationSnapshotModel,
    DGRApprovalModel,
    DGRDocumentModel
)

class DGRRuleService:
    def __init__(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = dgr_repo

    async def create_rule(self, payload: DGRRuleCreate) -> DGRRuleResponse:
        # In a real app we check if an older version exists and increment version.
        rule = DGRRuleModel(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            rule_type=payload.rule_type,
            mode=payload.mode,
            aircraft_type=payload.aircraft_type,
            carrier=payload.carrier,
            country_variation=payload.country_variation,
            effective_date=payload.effective_date,
            expiry_date=payload.expiry_date,
            conditions=payload.conditions,
            version=1,
            is_active=True,
            created_at=datetime.now(UTC),
            created_by=self.user_id
        )
        saved = await self.repo.save_rule(rule)
        return DGRRuleResponse(**saved.__dict__)


class DGRComplianceEngine:
    def __init__(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = dgr_repo

    async def capture_item(self, shipment_id: uuid.UUID, payload: DGRItemCapture) -> DGRItemResponse:
        item = DGRItemModel(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            shipment_id=shipment_id,
            created_at=datetime.now(UTC),
            created_by=self.user_id,
            **payload.dict()
        )
        saved = await self.repo.save_item(item)
        return DGRItemResponse(**saved.__dict__)

    async def validate_items(self, shipment_id: uuid.UUID) -> List[DGRValidationResponse]:
        items = await self.repo.get_items_by_shipment(shipment_id)
        if not items:
            raise HTTPException(status_code=400, detail="No DGR items found for shipment")

        as_of = datetime.now(UTC)
        rules = await self.repo.get_active_rules(self.tenant_id, as_of)

        responses = []
        for item in items:
            checks = []
            item_status = "PASS"
            
            # 1. UN Number validity (Mocked deterministic check)
            un_valid = len(item.un_number) == 4 and item.un_number.isdigit()
            checks.append(DGRValidationCheck(
                category="UN_LOOKUP",
                result="PASS" if un_valid else "FAIL",
                reason="UN number is valid" if un_valid else "Invalid UN format",
                observed_value=item.un_number,
                timestamp=as_of
            ))
            if not un_valid:
                item_status = "FAIL"

            # 2. Evaluate Dynamic Rules
            for rule in rules:
                # Mode match check
                # Skipping complex mode logic for brevity, assuming rule applies if we process it
                rule_pass = True
                reason = "Condition met"
                
                if rule.rule_type == "QUANTITY_LIMIT":
                    max_qty = rule.conditions.get("max_net_quantity_kg")
                    if max_qty and item.net_quantity > max_qty:
                        rule_pass = False
                        reason = f"Exceeds max qty {max_qty}"
                        
                elif rule.rule_type == "CARRIER_RESTRICTION":
                    forbidden = rule.conditions.get("forbidden_classes", [])
                    if item.class_division in forbidden:
                        rule_pass = False
                        reason = f"Class {item.class_division} forbidden by carrier"
                
                res_str = "PASS" if rule_pass else "FAIL"
                checks.append(DGRValidationCheck(
                    rule_id=rule.id,
                    rule_version=rule.version,
                    category=rule.rule_type,
                    result=res_str,
                    reason=reason,
                    timestamp=as_of
                ))
                
                if not rule_pass:
                    item_status = "FAIL"
                    
                    exc = DGRExceptionModel(
                        id=uuid.uuid4(),
                        tenant_id=self.tenant_id,
                        item_id=item.id,
                        shipment_id=item.shipment_id,
                        rule_id=rule.id,
                        status="OPEN",
                        details={"reason": reason},
                        created_at=as_of
                    )
                    await self.repo.save_exception(exc)

            snap = DGRValidationSnapshotModel(
                id=uuid.uuid4(),
                tenant_id=self.tenant_id,
                item_id=item.id,
                shipment_id=shipment_id,
                status=item_status,
                checks=[c.dict() for c in checks],
                created_at=as_of
            )
            saved_snap = await self.repo.save_snapshot(snap)
            
            responses.append(DGRValidationResponse(
                item_id=item.id,
                shipment_id=shipment_id,
                status=item_status,
                checks=checks,
                snapshot_id=saved_snap.id
            ))
            
        return responses

    async def approve_exception(self, item_id: uuid.UUID, payload: DGRApprovalRequest) -> DGRApprovalResponse:
        item = await self.repo.get_item(item_id)
        if not item or item.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="DGR item not found")

        open_exceptions = await self.repo.get_open_exceptions(item_id)
        if not open_exceptions:
            raise HTTPException(status_code=400, detail="No open exceptions to approve")
            
        # Check non-overridable
        for exc in open_exceptions:
            rule = self.repo.rules.get(exc.rule_id)
            if rule and rule.conditions.get("non_overridable", False):
                raise HTTPException(status_code=403, detail=f"Rule {rule.id} is non-overridable")

        as_of = datetime.now(UTC)
        apprv = DGRApprovalModel(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            item_id=item_id,
            approved_by=self.user_id,
            reason=payload.reason,
            status="APPROVED",
            timestamp=as_of,
            snapshot_id=uuid.uuid4() # Mock snapshot id
        )
        saved = await self.repo.save_approval(apprv)
        
        for exc in open_exceptions:
            exc.status = "APPROVED"
            await self.repo.update_exception(exc)
            
        return DGRApprovalResponse(
            item_id=item_id,
            approved_by=saved.approved_by,
            reason=saved.reason,
            timestamp=saved.timestamp,
            status=saved.status
        )


class DGRDocumentService:
    def __init__(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = dgr_repo
        
    async def generate_dgd(self, shipment_id: uuid.UUID, doc_type: str) -> dict:
        items = await self.repo.get_items_by_shipment(shipment_id)
        if not items:
            raise HTTPException(status_code=400, detail="No DGR items for documentation")
            
        # Validate that there are no OPEN exceptions
        for item in items:
            open_exc = await self.repo.get_open_exceptions(item.id)
            if open_exc:
                raise HTTPException(status_code=403, detail="Cannot generate document with open DGR exceptions")
                
        version = await self.repo.get_latest_document_version(shipment_id, doc_type) + 1
        
        # Mock generation
        content = f"{doc_type} Data for {shipment_id}"
        checksum = hashlib.sha256(content.encode()).hexdigest()
        
        doc = DGRDocumentModel(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            shipment_id=shipment_id,
            doc_type=doc_type,
            version=version,
            file_url=f"s3://freightcore/docs/{shipment_id}_{doc_type}_v{version}.pdf",
            checksum=checksum,
            created_at=datetime.now(UTC),
            created_by=self.user_id
        )
        saved = await self.repo.save_document(doc)
        
        return {
            "id": str(saved.id),
            "doc_type": saved.doc_type,
            "version": saved.version,
            "file_url": saved.file_url,
            "checksum": saved.checksum
        }
