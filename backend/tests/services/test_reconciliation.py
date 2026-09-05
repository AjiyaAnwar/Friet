import pytest
from decimal import Decimal
from datetime import datetime
from app.services.reconciliation_service import ReconciliationService
from app.repositories.reconciliation_repository import ReconciliationRepositoryFake

def test_reconciliation_report_generation():
    repo = ReconciliationRepositoryFake()
    
    repo.invoices = [
        {"id": "INV-1", "expected_amount": "100.00", "actual_amount": "110.00"},
        {"id": "INV-2", "expected_amount": "100.00", "actual_amount": "90.00"},
        {"id": "INV-3", "expected_amount": "100.00", "actual_amount": "102.00"},
    ]
    
    repo.costs = [
        {"id": "CST-1", "expected_amount": "50.00", "actual_amount": "60.00", "registered": True},
        {"id": "CST-2", "expected_amount": "50.00", "actual_amount": "50.00", "registered": False},
    ]
    
    repo.payments = [
        {"id": "PAY-1", "amount": "100.00", "matched": True},
        {"id": "PAY-2", "amount": "50.00", "matched": False},
    ]
    
    service = ReconciliationService(repo)
    start = datetime(2023, 1, 1)
    end = datetime(2023, 1, 7)
    
    report = service.generate_report(start, end)
    
    assert report.total_revenue == Decimal("302.00")
    assert report.total_cost == Decimal("110.00")
    assert len(report.discrepancies) == 6
    
    discrepancy_types = [d.type for d in report.discrepancies]
    assert "revenue_overbilling" in discrepancy_types
    assert "revenue_leakage" in discrepancy_types
    assert "revenue_variance_auto_resolved" in discrepancy_types
    assert "cost_variance" in discrepancy_types
    assert "unregistered_cost" in discrepancy_types
    assert "suspense_payment" in discrepancy_types
