from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
from typing import Optional
from app.schemas.reconciliation import ReconciliationReport
from app.services.reconciliation_service import ReconciliationService
from app.repositories.reconciliation_repository import ReconciliationRepositoryFake

router = APIRouter()

def get_reconciliation_service():
    repo = ReconciliationRepositoryFake()
    return ReconciliationService(repo)

@router.get("/report", response_model=ReconciliationReport)
def get_reconciliation_report(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    service: ReconciliationService = Depends(get_reconciliation_service)
):
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=7)
    return service.generate_report(start_date, end_date)
