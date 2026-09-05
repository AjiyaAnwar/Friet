from decimal import Decimal
from datetime import datetime
from app.schemas.reconciliation import ReconciliationReport, ReconciliationDiscrepancy
from app.repositories.reconciliation_repository import ReconciliationRepository

class ReconciliationService:
    def __init__(self, repository: ReconciliationRepository):
        self.repository = repository
        self.tolerance = Decimal("5.00")

    async def generate_report(self, start: datetime, end: datetime) -> ReconciliationReport:
        invoices = await self.repository.get_invoices_for_period(start, end)
        costs = await self.repository.get_costs_for_period(start, end)
        payments = await self.repository.get_payments_for_period(start, end)

        discrepancies = []
        total_revenue = Decimal("0.00")
        total_cost = Decimal("0.00")

        # Revenue
        for inv in invoices:
            expected = Decimal("0.00") # simplified logic
            actual = Decimal(str(inv.total_amount)) if hasattr(inv, "total_amount") else Decimal("0.00")
            total_revenue += actual
            
            diff = actual - expected
            if diff > self.tolerance:
                discrepancies.append(ReconciliationDiscrepancy(
                    type="revenue_overbilling",
                    description=f"Overbilled by {diff}",
                    amount=diff,
                    reference_id=str(inv.id),
                    auto_resolved=False
                ))

        # Cost
        for cost in costs:
            actual = Decimal(str(cost.amount)) if hasattr(cost, "amount") else Decimal("0.00")
            total_cost += actual

        return ReconciliationReport(
            report_id=f"REC-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}",
            period_start=start,
            period_end=end,
            total_revenue=total_revenue,
            total_cost=total_cost,
            discrepancies=discrepancies,
            status="completed" if not discrepancies else "needs_review"
        )
