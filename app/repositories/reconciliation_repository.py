from typing import List, Dict, Any
from datetime import datetime

class ReconciliationRepositoryFake:
    def __init__(self):
        self.invoices = []
        self.costs = []
        self.payments = []

    def get_invoices_for_period(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        return self.invoices

    def get_costs_for_period(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        return self.costs

    def get_payments_for_period(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        return self.payments
