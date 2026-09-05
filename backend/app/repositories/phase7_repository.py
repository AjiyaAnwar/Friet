from decimal import Decimal
from typing import Dict, List, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.domain import Shipment, Invoice, Payable, ShipmentException
from app.db.models.team3_entities import DemurrageAccrual
from app.db.models.reference import Carrier

class Phase7Repository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_operations_data(self) -> Dict[str, int]:
        total_stmt = select(func.count(Shipment.id))
        total_res = await self.db.execute(total_stmt)
        total_shipments = total_res.scalar() or 0

        exc_stmt = select(func.count(func.distinct(ShipmentException.shipment_id)))
        exc_res = await self.db.execute(exc_stmt)
        exception_shipments = exc_res.scalar() or 0

        on_time_shipments = total_shipments - exception_shipments

        return {
            "total_shipments": total_shipments,
            "on_time_shipments": on_time_shipments,
            "exception_shipments": exception_shipments
        }

    async def get_financial_data(self) -> Dict[str, Any]:
        rev_stmt = select(func.sum(Invoice.total_amount))
        rev_res = await self.db.execute(rev_stmt)
        total_revenue = rev_res.scalar() or Decimal("0.00")

        cost_stmt = select(func.sum(Payable.total_amount))
        cost_res = await self.db.execute(cost_stmt)
        total_cost = cost_res.scalar() or Decimal("0.00")

        return {
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "ar_aging": [
                {"bucket_name": "0-30", "amount": Decimal("0.00")},
                {"bucket_name": "31-60", "amount": Decimal("0.00")},
            ],
            "ap_aging": [
                {"bucket_name": "0-30", "amount": Decimal("0.00")},
                {"bucket_name": "31-60", "amount": Decimal("0.00")},
            ]
        }

    async def get_demurrage_data(self) -> Dict[str, Decimal]:
        dem_stmt = select(func.sum(DemurrageAccrual.amount))
        dem_res = await self.db.execute(dem_stmt)
        total_demurrage_incurred = dem_res.scalar() or Decimal("0.00")

        return {
            "total_demurrage_incurred": total_demurrage_incurred,
            "total_demurrage_billed": Decimal("0.00"),
        }

    async def get_carrier_performance_data(self) -> List[Dict[str, Any]]:
        c_stmt = select(Carrier.id, Carrier.name)
        c_res = await self.db.execute(c_stmt)
        carriers = c_res.all()

        results = []
        for c_id, c_name in carriers:
            results.append({
                "carrier_id": str(c_id),
                "carrier_name": c_name,
                "total_shipments": 0,
                "on_time_deliveries": 0,
                "rejections": 0,
                "total_miles": Decimal("0.00"),
                "total_cost": Decimal("0.00")
            })
        return results
