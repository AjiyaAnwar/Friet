from pydantic import BaseModel
from typing import List, Optional, Dict
from decimal import Decimal

class OperationsAnalytics(BaseModel):
    total_shipments: int
    on_time_percentage: Decimal
    exception_rate: Decimal

class AgingBucket(BaseModel):
    bucket_name: str
    amount: Decimal

class FinancialAnalytics(BaseModel):
    total_revenue: Decimal
    total_cost: Decimal
    gross_margin_percentage: Decimal
    ar_aging: List[AgingBucket]
    ap_aging: List[AgingBucket]

class DemurrageAnalytics(BaseModel):
    total_demurrage_incurred: Decimal
    total_demurrage_billed: Decimal
    net_demurrage: Decimal

class CarrierPerformanceMetric(BaseModel):
    carrier_id: str
    carrier_name: str
    on_time_delivery_rate: Decimal
    rejection_rate: Decimal
    average_cost_per_mile: Decimal

class CarrierPerformanceAnalytics(BaseModel):
    metrics: List[CarrierPerformanceMetric]
