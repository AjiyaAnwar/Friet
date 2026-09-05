from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
import uuid

class DGRItemCapture(BaseModel):
    un_number: str = Field(..., max_length=4)
    proper_shipping_name: str
    class_division: str
    subsidiary_risk: Optional[str] = None
    packing_group: Optional[str] = None
    quantity_per_package: Decimal = Field(..., gt=0)
    net_quantity: Decimal = Field(..., gt=0)
    num_packages: int = Field(..., gt=0)
    packaging_instruction: str
    erg_code: Optional[str] = None
    technical_name: Optional[str] = None
    unit_of_measure: str
    container_or_uld: Optional[str] = None

class DGRItemResponse(DGRItemCapture):
    id: uuid.UUID
    shipment_id: uuid.UUID
    created_at: datetime
    created_by: Optional[uuid.UUID] = None

class DGRRuleCreate(BaseModel):
    rule_type: str = Field(..., description="QUANTITY_LIMIT, COMPATIBILITY, PACKAGING, CARRIER_RESTRICTION, COUNTRY_VARIATION, DOCUMENT_REQUIREMENT")
    mode: str = Field(..., description="AIR or SEA")
    aircraft_type: Optional[str] = Field(None, description="PAX or CAO")
    carrier: str = "ALL"
    country_variation: Optional[str] = None
    effective_date: datetime
    expiry_date: Optional[datetime] = None
    conditions: Dict[str, Any]

class DGRRuleResponse(DGRRuleCreate):
    id: uuid.UUID
    version: int
    is_active: bool
    created_at: datetime
    created_by: Optional[uuid.UUID] = None

class DGRValidationCheck(BaseModel):
    rule_id: Optional[uuid.UUID] = None
    rule_version: Optional[int] = None
    category: str
    result: str # PASS, FAIL, NOT_APPLICABLE
    reason: str
    observed_value: Optional[str] = None
    expected_condition: Optional[str] = None
    timestamp: datetime

class DGRValidationResponse(BaseModel):
    item_id: uuid.UUID
    shipment_id: uuid.UUID
    status: str # PASS or FAIL
    checks: List[DGRValidationCheck]
    snapshot_id: uuid.UUID

class DGRApprovalRequest(BaseModel):
    reason: str = Field(..., min_length=10)
    supporting_documents: Optional[List[str]] = None
    expiry: Optional[datetime] = None

class DGRApprovalResponse(BaseModel):
    item_id: uuid.UUID
    approved_by: uuid.UUID
    reason: str
    timestamp: datetime
    status: str
