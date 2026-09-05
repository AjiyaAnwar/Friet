from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class HAWB(BaseModel):
    id: str
    destination: str
    actual_weight: Decimal
    volume: Decimal
    ready_date: datetime

class PlanningSuggestion(BaseModel):
    suggested_hawbs: List[str]
    total_actual_weight: Decimal
    total_volume: Decimal
    total_volumetric_weight: Decimal
    total_chargeable_weight: Decimal
    utilization_weight_pct: Decimal
    utilization_volume_pct: Decimal

class DeconsolidationItem(BaseModel):
    hawb_id: str
    received_weight: Decimal
    condition: str = "good"
    discrepancy_notes: Optional[str] = None

class DeconsolidationRequest(BaseModel):
    mawb_id: str
    items: List[DeconsolidationItem]
    location: str

class DeconsolidationResult(BaseModel):
    mawb_id: str
    status: str
    exceptions_raised: int
    processed_items: int
