"""
RFQ Service (Commercial Domain).

Handles RFQ capture, dynamic field validation, assignment, and lifecycle management.
"""

from __future__ import annotations

from datetime import date
from domain.entities import Rfq, RfqStatus, PartyRole
from calculations.rfq_validation import validate_rfq, ValidationResult
from domain.interfaces import RfqRepositoryPort, MasterDataRepositoryPort


class RfqService:
    def __init__(
        self,
        rfq_repo: RfqRepositoryPort,
        master_data_repo: MasterDataRepositoryPort | None = None,
    ) -> None:
        self.rfq_repo = rfq_repo
        self.master_data_repo = master_data_repo

    def create_rfq(self, rfq: Rfq, today: date | None = None) -> tuple[Rfq, ValidationResult]:
        val_result = validate_rfq(rfq, today=today)
        if not val_result.is_valid:
            return rfq, val_result

        # Sanctions and embargo check if master repo available
        if self.master_data_repo:
            origin = self.master_data_repo.get_location_by_id(rfq.origin_location_id)
            dest = self.master_data_repo.get_location_by_id(rfq.destination_location_id)
            # Future expansion: cross-check with country is_sanctioned

        rfq.status = RfqStatus.SUBMITTED
        saved = self.rfq_repo.save(rfq)
        return saved, val_result

    def assign_to_analyst(self, rfq_id: str, user_id: str) -> Rfq:
        rfq = self.rfq_repo.get_by_id(rfq_id)
        if not rfq:
            raise ValueError(f"RFQ with ID {rfq_id} not found")
        rfq.assigned_to = user_id
        rfq.status = RfqStatus.PRICING_IN_PROGRESS
        return self.rfq_repo.save(rfq)
