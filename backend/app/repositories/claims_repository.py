from typing import List, Optional
from datetime import datetime
from app.schemas.claims import ClaimCreate, ClaimUpdate, ClaimResponse, ClaimStatus
import uuid

class ClaimsRepository:
    def __init__(self):
        self.claims = {}

    def create_claim(self, claim: ClaimCreate) -> ClaimResponse:
        claim_id = str(uuid.uuid4())
        new_claim = ClaimResponse(
            id=claim_id,
            status=ClaimStatus.REPORTED,
            reported_at=datetime.utcnow(),
            **claim.dict()
        )
        self.claims[claim_id] = new_claim
        return new_claim

    def get_claim(self, claim_id: str) -> Optional[ClaimResponse]:
        return self.claims.get(claim_id)

    def update_claim(self, claim_id: str, claim_update: ClaimUpdate) -> Optional[ClaimResponse]:
        claim = self.claims.get(claim_id)
        if not claim:
            return None
        
        update_data = claim_update.dict(exclude_unset=True)
        
        for key, value in update_data.items():
            setattr(claim, key, value)
            
        self.claims[claim_id] = claim
        return claim
