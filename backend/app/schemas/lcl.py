from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import uuid

class HBLSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    weight: Decimal
    cbm: Decimal
    origin: str
    destination: str

class ConsolidationSuggestion(BaseModel):
    suggestion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mbl_id: str
    hbl_ids: List[str]
    total_weight: Decimal
    total_cbm: Decimal
    weight_utilization: Decimal
    cbm_utilization: Decimal

class ConsolidationCreate(BaseModel):
    mbl_id: str
    hbl_ids: List[str]

class ConsolidationResponse(BaseModel):
    id: str
    mbl_id: str
    hbl_ids: List[str]
    created_at: datetime

class HBLCostAllocation(BaseModel):
    hbl_id: str
    allocated_cost: Decimal

class CostAllocationResponse(BaseModel):
    consolidation_id: str
    total_cost: Decimal
    allocations: List[HBLCostAllocation]
