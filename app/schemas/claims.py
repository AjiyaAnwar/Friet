from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from datetime import datetime
from enum import Enum

class ClaimStatus(str, Enum):
    REPORTED = "REPORTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CLOSED = "CLOSED"

class ClaimBase(BaseModel):
    shipment_id: str
    carrier_id: str
    claim_amount: Decimal
    description: str

class ClaimCreate(ClaimBase):
    pass

class ClaimUpdate(BaseModel):
    status: Optional[ClaimStatus] = None
    approved_amount: Optional[Decimal] = None
    settlement_amount: Optional[Decimal] = None
    net_loss: Optional[Decimal] = None
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None

class ClaimResponse(ClaimBase):
    id: str
    status: ClaimStatus
    approved_amount: Optional[Decimal] = None
    settlement_amount: Optional[Decimal] = None
    net_loss: Optional[Decimal] = None
    reported_at: datetime
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None
    
    class Config:
        orm_mode = True
