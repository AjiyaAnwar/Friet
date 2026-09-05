from pydantic import BaseModel
from typing import List
from decimal import Decimal
from datetime import datetime

class ReconciliationDiscrepancy(BaseModel):
    type: str
    description: str
    amount: Decimal
    reference_id: str
    auto_resolved: bool = False

class ReconciliationReport(BaseModel):
    report_id: str
    period_start: datetime
    period_end: datetime
    total_revenue: Decimal
    total_cost: Decimal
    discrepancies: List[ReconciliationDiscrepancy]
    status: str
