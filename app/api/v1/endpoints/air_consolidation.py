from fastapi import APIRouter, Depends, Query, HTTPException
from decimal import Decimal
from app.schemas.air_consolidation import PlanningSuggestion, DeconsolidationRequest, DeconsolidationResult
from app.services.air_consolidation_service import AirConsolidationService
from app.repositories.air_consolidation_repository import AirConsolidationRepositoryFake

router = APIRouter()

# Global fake repo for demo/tests
fake_repo = AirConsolidationRepositoryFake()

def get_service() -> AirConsolidationService:
    return AirConsolidationService(fake_repo)

@router.get("/api/v1/consolidations/air/planning", response_model=PlanningSuggestion)
def get_planning_suggestions(
    target_destination: str = Query(...),
    max_weight: Decimal = Query(...),
    max_volume: Decimal = Query(...),
    service: AirConsolidationService = Depends(get_service)
):
    return service.get_planning_suggestions(target_destination, max_weight, max_volume)

@router.post("/api/v1/consolidations/{id}/deconsolidate", response_model=DeconsolidationResult)
def deconsolidate_mawb(
    id: str,
    req: DeconsolidationRequest,
    service: AirConsolidationService = Depends(get_service)
):
    if id != req.mawb_id:
        raise HTTPException(status_code=400, detail="MAWB ID mismatch")
    return service.deconsolidate(req)
