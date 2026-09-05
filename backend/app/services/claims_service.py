from decimal import Decimal
from typing import Optional, Dict, Any
from app.schemas.claims import ClaimCreate, ClaimUpdate, ClaimResponse, ClaimStatus
from app.repositories.claims_repository import ClaimsRepository
from datetime import datetime

class ClaimsService:
    def __init__(self, repository: ClaimsRepository):
        self.repository = repository

    def create_claim(self, claim_in: ClaimCreate) -> ClaimResponse:
        return self.repository.create_claim(claim_in)

    def get_claim(self, claim_id: str) -> Optional[ClaimResponse]:
        return self.repository.get_claim(claim_id)

    def process_claim_status(self, claim_id: str, status: ClaimStatus, approved_amount: Optional[Decimal] = None, settlement_amount: Optional[Decimal] = None, notes: Optional[str] = None) -> Optional[ClaimResponse]:
        claim = self.repository.get_claim(claim_id)
        if not claim:
            raise ValueError("Claim not found")

        # State machine validation
        valid_transitions = {
            ClaimStatus.REPORTED: [ClaimStatus.UNDER_REVIEW, ClaimStatus.DENIED, ClaimStatus.CLOSED],
            ClaimStatus.UNDER_REVIEW: [ClaimStatus.APPROVED, ClaimStatus.DENIED],
            ClaimStatus.APPROVED: [ClaimStatus.CLOSED],
            ClaimStatus.DENIED: [ClaimStatus.CLOSED],
            ClaimStatus.CLOSED: []
        }
        
        if status not in valid_transitions[claim.status] and status != claim.status:
            raise ValueError(f"Invalid state transition from {claim.status} to {status}")

        update_data = ClaimUpdate(status=status, notes=notes)
        if approved_amount is not None:
            update_data.approved_amount = approved_amount
        if settlement_amount is not None:
            update_data.settlement_amount = settlement_amount
            
        if status == ClaimStatus.CLOSED and claim.status != ClaimStatus.CLOSED:
            update_data.closed_at = datetime.utcnow()
            
            appr = update_data.approved_amount if update_data.approved_amount is not None else (claim.approved_amount or Decimal("0.0"))
            sett = update_data.settlement_amount if update_data.settlement_amount is not None else (claim.settlement_amount or Decimal("0.0"))
            update_data.net_loss = appr - sett

        updated_claim = self.repository.update_claim(claim_id, update_data)
        return updated_claim
        
    def get_carrier_metrics(self, carrier_id: str) -> Dict[str, Any]:
        """Carrier-performance integration metric inputs"""
        carrier_claims = [c for c in self.repository.claims.values() if c.carrier_id == carrier_id]
        total_claims = len(carrier_claims)
        total_claim_amount = sum((c.claim_amount for c in carrier_claims), Decimal("0.0"))
        total_net_loss = sum((c.net_loss for c in carrier_claims if c.net_loss is not None), Decimal("0.0"))
        
        return {
            "carrier_id": carrier_id,
            "total_claims": total_claims,
            "total_claim_amount": total_claim_amount,
            "total_net_loss": total_net_loss
        }
