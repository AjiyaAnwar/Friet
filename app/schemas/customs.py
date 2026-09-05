from datetime import datetime
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

class ClearanceStatus(str, Enum):
    PENDING = "PENDING"
    CLEARED = "CLEARED"
    REJECTED = "REJECTED"
    UNDER_REVIEW = "UNDER_REVIEW"

class CustomsDeclarationBase(BaseModel):
    declared_value: Decimal
    currency: str = Field(..., max_length=3)
    hs_code: str
    origin_country: str = Field(..., max_length=2)
    destination_country: str = Field(..., max_length=2)
    description: str

class CustomsDeclarationCreate(CustomsDeclarationBase):
    pass

class CustomsDeclaration(CustomsDeclarationBase):
    id: str
    shipment_id: str
    status: ClearanceStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
