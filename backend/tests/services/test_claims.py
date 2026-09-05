import pytest
from decimal import Decimal
from app.schemas.claims import ClaimCreate, ClaimStatus
from app.repositories.claims_repository import ClaimsRepository
from app.services.claims_service import ClaimsService

def test_claims_state_machine_and_financials():
    repo = ClaimsRepository()
    service = ClaimsService(repo)
    
    claim_in = ClaimCreate(
        shipment_id="SHP123",
        carrier_id="CAR456",
        claim_amount=Decimal("1000.00"),
        description="Damaged goods"
    )
    
    claim = service.create_claim(claim_in)
    assert claim.status == ClaimStatus.REPORTED
    assert claim.id is not None
    
    # Transition to UNDER_REVIEW
    claim = service.process_claim_status(claim.id, ClaimStatus.UNDER_REVIEW)
    assert claim.status == ClaimStatus.UNDER_REVIEW
    
    # Transition to APPROVED
    claim = service.process_claim_status(
        claim.id, 
        ClaimStatus.APPROVED, 
        approved_amount=Decimal("800.00")
    )
    assert claim.status == ClaimStatus.APPROVED
    assert claim.approved_amount == Decimal("800.00")
    
    # Transition to CLOSED with settlement
    claim = service.process_claim_status(
        claim.id, 
        ClaimStatus.CLOSED, 
        settlement_amount=Decimal("500.00")
    )
    assert claim.status == ClaimStatus.CLOSED
    assert claim.net_loss == Decimal("300.00") # 800 - 500
    
    # Invalid transition
    with pytest.raises(ValueError):
        service.process_claim_status(claim.id, ClaimStatus.REPORTED)
        
    metrics = service.get_carrier_metrics("CAR456")
    assert metrics["total_claims"] == 1
    assert metrics["total_net_loss"] == Decimal("300.00")
