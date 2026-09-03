import uuid
from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field

class SLI(BaseModel):
    id: uuid.UUID
    hawb_id: uuid.UUID
    shipper: str
    consignee: str
    routing_instructions: str
    handling_instructions: str
    commodity_description: str
    pieces: int
    weight: float
    dimensions: str | None = None
    customs_info: str | None = None
    dgr_reference: str | None = None
    document_reference: str | None = None
    approval_status: str = "DRAFT"

class AWBBase(BaseModel):
    shipment_id: uuid.UUID
    awb_type: str = Field(pattern="^(HAWB|MAWB)$")
    parent_mawb_id: uuid.UUID | None = None
    airline_name: str
    airline_prefix: str = Field(min_length=3, max_length=3)
    serial_number: str | None = None
    full_awb_number: str | None = None
    shipper: str
    consignee: str
    origin_airport: str = Field(min_length=3, max_length=3)
    destination_airport: str = Field(min_length=3, max_length=3)
    routing: str
    pieces: int
    gross_weight: float
    chargeable_weight: float
    commodity: str
    special_handling_codes: list[str] = Field(default_factory=list)
    
class AWBCreateRequest(AWBBase):
    pass

class AWBResponse(AWBBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    issue_date: datetime | None = None
    issuing_user: uuid.UUID | None = None
    status: str = "DRAFT"
    version: int = 1
    sli: SLI | None = None

    model_config = {"from_attributes": True}

class AWBAmendmentRequest(BaseModel):
    reason: str
    fields_changed: dict[str, Any]
    carrier_confirmation_ref: str | None = None

class AWBCancellationRequest(BaseModel):
    reason: str
    replacement_awb_id: uuid.UUID | None = None
