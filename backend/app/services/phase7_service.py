from decimal import Decimal
from typing import Dict, Any
from app.repositories.phase7_repository import Phase7Repository
from app.schemas.phase7 import (
    OperationsAnalytics, FinancialAnalytics, DemurrageAnalytics,
    CarrierPerformanceAnalytics, CarrierPerformanceMetric, AgingBucket
)

class Phase7Service:
    def __init__(self, repository: Phase7Repository):
        self.repository = repository

    async def get_operations_analytics(self) -> OperationsAnalytics:
        data = await self.repository.get_operations_data()
        total = data.get("total_shipments", 0)
        on_time = data.get("on_time_shipments", 0)
        exceptions = data.get("exception_shipments", 0)
        
        on_time_percentage = Decimal(on_time) / Decimal(total) * Decimal("100") if total > 0 else Decimal("0")
        exception_rate = Decimal(exceptions) / Decimal(total) * Decimal("100") if total > 0 else Decimal("0")
        
        return OperationsAnalytics(
            total_shipments=total,
            on_time_percentage=on_time_percentage,
            exception_rate=exception_rate
        )

    async def get_financial_analytics(self) -> FinancialAnalytics:
        data = await self.repository.get_financial_data()
        rev = data.get("total_revenue", Decimal("0"))
        cost = data.get("total_cost", Decimal("0"))
        
        margin = rev - cost
        margin_pct = (margin / rev) * Decimal("100") if rev > Decimal("0") else Decimal("0")
        
        ar_aging = [AgingBucket(**b) for b in data.get("ar_aging", [])]
        ap_aging = [AgingBucket(**b) for b in data.get("ap_aging", [])]
        
        return FinancialAnalytics(
            total_revenue=rev,
            total_cost=cost,
            gross_margin_percentage=margin_pct,
            ar_aging=ar_aging,
            ap_aging=ap_aging
        )

    async def get_demurrage_analytics(self) -> DemurrageAnalytics:
        data = await self.repository.get_demurrage_data()
        incurred = data.get("total_demurrage_incurred", Decimal("0"))
        billed = data.get("total_demurrage_billed", Decimal("0"))
        net = billed - incurred
        
        return DemurrageAnalytics(
            total_demurrage_incurred=incurred,
            total_demurrage_billed=billed,
            net_demurrage=net
        )

    async def get_carrier_performance_analytics(self) -> CarrierPerformanceAnalytics:
        data = await self.repository.get_carrier_performance_data()
        metrics = []
        for c in data:
            total_shipments = c.get("total_shipments", 0)
            on_time = c.get("on_time_deliveries", 0)
            rejections = c.get("rejections", 0)
            total_miles = c.get("total_miles", Decimal("0"))
            total_cost = c.get("total_cost", Decimal("0"))
            
            on_time_rate = Decimal(on_time) / Decimal(total_shipments) * Decimal("100") if total_shipments > 0 else Decimal("0")
            rej_rate = Decimal(rejections) / Decimal(total_shipments) * Decimal("100") if total_shipments > 0 else Decimal("0")
            avg_cost = total_cost / total_miles if total_miles > Decimal("0") else Decimal("0")
            
            metrics.append(CarrierPerformanceMetric(
                carrier_id=c.get("carrier_id", ""),
                carrier_name=c.get("carrier_name", ""),
                on_time_delivery_rate=on_time_rate,
                rejection_rate=rej_rate,
                average_cost_per_mile=avg_cost
            ))
            
        return CarrierPerformanceAnalytics(metrics=metrics)
