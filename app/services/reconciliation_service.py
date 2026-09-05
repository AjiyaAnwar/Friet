from decimal import Decimal
from datetime import datetime
from typing import List
from app.schemas.reconciliation import ReconciliationReport, ReconciliationDiscrepancy
from app.repositories.reconciliation_repository import ReconciliationRepositoryFake

class ReconciliationService:
    def __init__(self, repository: ReconciliationRepositoryFake):
        self.repository = repository
        self.tolerance = Decimal("5.00")

    def generate_report(self, start: datetime, end: datetime) -> ReconciliationReport:
        invoices = self.repository.get_invoices_for_period(start, end)
        costs = self.repository.get_costs_for_period(start, end)
        payments = self.repository.get_payments_for_period(start, end)

        discrepancies = []
        total_revenue = Decimal("0.00")
        total_cost = Decimal("0.00")

        # Revenue
        for inv in invoices:
            expected = Decimal(str(inv.get("expected_amount", "0.00")))
            actual = Decimal(str(inv.get("actual_amount", "0.00")))
            total_revenue += actual
            
            diff = actual - expected
            if diff > self.tolerance:
                discrepancies.append(ReconciliationDiscrepancy(
                    type="revenue_overbilling",
                    description=f"Overbilled by {diff}",
                    amount=diff,
                    reference_id=inv.get("id", "unknown"),
                    auto_resolved=False
                ))
            elif diff < -self.tolerance:
                discrepancies.append(ReconciliationDiscrepancy(
                    type="revenue_leakage",
                    description=f"Revenue leakage of {-diff}",
                    amount=-diff,
                    reference_id=inv.get("id", "unknown"),
                    auto_resolved=False
                ))
            elif diff != Decimal("0.00"):
                discrepancies.append(ReconciliationDiscrepancy(
                    type="revenue_variance_auto_resolved",
                    description=f"Variance of {diff} auto-resolved",
                    amount=diff,
                    reference_id=inv.get("id", "unknown"),
                    auto_resolved=True
                ))

        # Cost
        for cost in costs:
            expected = Decimal(str(cost.get("expected_amount", "0.00")))
            actual = Decimal(str(cost.get("actual_amount", "0.00")))
            total_cost += actual
            
            if not cost.get("registered", True):
                discrepancies.append(ReconciliationDiscrepancy(
                    type="unregistered_cost",
                    description=f"Unregistered cost of {actual}",
                    amount=actual,
                    reference_id=cost.get("id", "unknown"),
                    auto_resolved=False
                ))
            else:
                diff = actual - expected
                if abs(diff) > self.tolerance:
                    discrepancies.append(ReconciliationDiscrepancy(
                        type="cost_variance",
                        description=f"Cost variance of {diff}",
                        amount=diff,
                        reference_id=cost.get("id", "unknown"),
                        auto_resolved=False
                    ))
                elif diff != Decimal("0.00"):
                    discrepancies.append(ReconciliationDiscrepancy(
                        type="cost_variance_auto_resolved",
                        description=f"Variance of {diff} auto-resolved",
                        amount=diff,
                        reference_id=cost.get("id", "unknown"),
                        auto_resolved=True
                    ))

        # Payments
        for pay in payments:
            if not pay.get("matched", False):
                amount = Decimal(str(pay.get("amount", "0.00")))
                discrepancies.append(ReconciliationDiscrepancy(
                    type="suspense_payment",
                    description="Unmatched payment",
                    amount=amount,
                    reference_id=pay.get("id", "unknown"),
                    auto_resolved=False
                ))
        
        return ReconciliationReport(
            report_id=f"REC-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}",
            period_start=start,
            period_end=end,
            total_revenue=total_revenue,
            total_cost=total_cost,
            discrepancies=discrepancies,
            status="completed" if not discrepancies else "needs_review"
        )
