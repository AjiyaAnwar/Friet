from fastapi import APIRouter
from app.schemas.claims import ClaimCreate, ClaimResponse
from app.services.claims_service import ClaimsService
from app.repositories.claims_repository import ClaimsRepository

router = APIRouter()
repository = ClaimsRepository()
service = ClaimsService(repository)

@router.post("/", response_model=ClaimResponse, status_code=201)
def create_claim(claim: ClaimCreate):
    return service.create_claim(claim)
